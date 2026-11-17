import asyncio,hashlib,json,time,subprocess,os
import httpx
from .verification import binding, durations, evidence, VerificationError
from pathlib import Path
from .safe_network import client as platform_client
from .artifacts import valid_files, safe_path
from datetime import datetime,timezone
from .markdown import finish
from .providers.contracts import LoginRequired, ConfirmationRequired
from .providers.registry import source_provider, asr_provider
from .runtime import DATA, load_config
ROOT=Path(__file__).resolve().parent
CONFIG=load_config()

def artifact_dir(kind):
    namespace=CONFIG.get('artifact_namespace','')
    if namespace:
        import re
        if not re.fullmatch(r'[a-z0-9_-]{1,64}',namespace):raise ValueError('Invalid artifact namespace')
    path=DATA/kind/namespace if namespace else DATA/kind
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    return path

def dump(path,value):
    from .artifacts import atomic_json
    atomic_json(Path(path),value)

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def probe(path):
    return json.loads(subprocess.check_output([CONFIG['generic_ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(path)]))
def run(args):
    r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if r.returncode:
        error=VerificationError('media command failed','MEDIA_INVALID')
        error.diagnostics={'returncode':r.returncode,'stderr':r.stderr.decode(errors='replace'),'stdout':r.stdout.decode(errors='replace')}
        raise error
    return {'returncode':r.returncode,'stderr':r.stderr.decode(errors='replace'),'stdout':r.stdout.decode(errors='replace')}
async def fetch(url,path,headers):
    part=path.with_suffix(path.suffix+'.part')
    async with platform_client(media=True,follow_redirects=True,timeout=60,headers=headers) as c:
        async with c.stream('GET',url) as r:
            r.raise_for_status()
            with part.open('wb') as f:
                async for b in r.aiter_bytes():
                    if f.tell()+len(b)>1024**3:raise ConfirmationRequired('Media exceeds 1GB')
                    f.write(b)
    if not part.stat().st_size:raise RuntimeError('empty download')
    part.replace(path)
async def fetch_candidates(urls,path,headers):
    last=None
    for url in urls:
        try:await fetch(url,path,headers);return url
        except ConfirmationRequired:raise
        except Exception as exc:last=exc
    if isinstance(last,httpx.HTTPStatusError):
        code='AUTH_REQUIRED' if last.response.status_code in (401,403) else 'SOURCE_UNAVAILABLE' if last.response.status_code in (404,410) else 'DOWNLOAD_FAILED'
        raise VerificationError('Media request failed; retain original job',code,last.response.status_code>=500) from last
    raise VerificationError('Media request failed; retain original job','DOWNLOAD_FAILED',isinstance(last,httpx.TransportError)) from last
def record(path,kind):
    return {'path':str(path.relative_to(DATA)),'bytes':path.stat().st_size,'sha256':digest(path),'url':CONFIG['base_url']+'/v1/media/'+path.stem+'/'+kind}
async def process(job,stage,*,source=None,transcriber=None):
    source = source or source_provider(CONFIG)
    transcriber = transcriber or asr_provider(CONFIG)
    start=time.monotonic();timings={}
    stage('resolving')
    try:
        vid=await source.resolve_id(job['url'])
    finally:
        dump(DATA/'metadata'/f'{job["id"]}.resolution-attempt.json',{'input_url':job['url'],'steps':getattr(source,'resolution_evidence',[])})
    binding(job['url'],vid)
    if job.get('media_id') and job['media_id']!=vid:raise VerificationError('Share URL resolution changed','SOURCE_MISMATCH')
    dump(DATA/'metadata'/f'{job["id"]}.resolution.json',{'input_url':job['url'],'resolved_id':vid,'steps':getattr(source,'resolution_evidence',[])})
    stage('downloading',media_id=vid)
    manifest_path=DATA/'metadata'/f'{vid}.{CONFIG["asr_fingerprint"][:12]}.manifest.json'
    fingerprint=CONFIG['asr_fingerprint']
    if manifest_path.exists():
        previous=json.loads(manifest_path.read_text())
        if previous.get('asr',{}).get('fingerprint')==fingerprint and valid_files(previous):
            evidence(previous)
            previous['verification']['input_url']=job['url']
            if previous.get('output_fingerprint')==CONFIG.get('output_fingerprint'):
                stage('transcribing',media_id=vid,reused=True);return previous
            raw=json.loads(safe_path(previous['files']['raw_transcript']['path']).read_text())
            return await finish(previous,raw,CONFIG,stage)
    raw_path=DATA/'metadata'/f'{vid}.{job["id"]}.raw.json'
    stage('metadata',media_id=vid)
    try:
        info = await source.describe(vid, max_short_edge=1080)
    finally:
        if hasattr(source,'detail_evidence'):
            dump(DATA/'metadata'/f'{vid}.{job["id"]}.detail.json',source.detail_evidence)
    if info.media_id != vid:raise VerificationError('Source provider returned mismatched media ID','SOURCE_MISMATCH')
    dump(DATA/'metadata'/f'{vid}.{job["id"]}.detail.json',dict(info.raw_metadata))
    # Provider media_id must be taken from the actual detail response.
    detail_id=str(info.raw_metadata.get('aweme_detail',{}).get('aweme_id',''))
    if detail_id!=vid:raise VerificationError('Detail response ID missing or mismatched','SOURCE_MISMATCH')
    if info.duration_seconds > 1800:raise ConfirmationRequired('Video exceeds 30 minutes')
    dump(raw_path,dict(info.raw_metadata))
    video=artifact_dir('video')/f'{vid}.mp4'; cover=artifact_dir('metadata')/f'{vid}.cover'
    selection_path=artifact_dir('metadata')/f'{vid}.selection.json'
    selection=dict(info.selection)
    stage('downloading',media_id=vid)
    if video.exists():safe_path(str(video.relative_to(DATA)))
    if not video.exists():
        if info.expected_bytes>1024**3:raise ConfirmationRequired('Video exceeds 1GB')
        downloaded_url=await fetch_candidates(info.video_urls,video,source.headers())
        selected=next((variant for variant in selection.get('variants',[]) if downloaded_url in variant['address']['url_list']),None)
        if selected:selection.update({key:selected[key] for key in ('gear','bit_rate','address')})
        selection.update(sha256=digest(video),downloaded_id=info.media_id,detail_id=detail_id);dump(selection_path,selection)
    elif selection_path.exists():
        selection=json.loads(selection_path.read_text())
        if selection.get('sha256') != digest(video):raise VerificationError('Stored video integrity mismatch','MEDIA_INVALID')
        if selection.get('downloaded_id')!=vid or selection.get('detail_id')!=vid:raise VerificationError('Stored download binding missing or mismatched','SOURCE_MISMATCH')
    else:raise RuntimeError('Existing video lacks provenance; manual inspection required')
    if cover.exists():safe_path(str(cover.relative_to(DATA)))
    if not cover.exists():await fetch_candidates(info.cover_urls,cover,source.headers())
    vp=await asyncio.to_thread(probe,video)
    vs=next((s for s in vp['streams'] if s['codec_type']=='video'),None)
    audio_stream=next((s for s in vp['streams'] if s['codec_type']=='audio'),None)
    if not vs or not audio_stream:raise VerificationError('Video or audio stream missing','MEDIA_INVALID')
    if min(vs['width'],vs['height'])>1080:raise RuntimeError('Downloaded video exceeds 1080p policy')
    timings['download_seconds']=round(time.monotonic()-start,3)
    stage('extracting',media_id=vid)
    t=time.monotonic();audio=artifact_dir('audio')/f'{vid}.m4a'
    ac=audio_stream['codec_name']
    method='copy original audio stream'
    if ac not in ('aac','alac'):
        audio=artifact_dir('audio')/f'{vid}.mka'
    audio_binding=artifact_dir('metadata')/f'{vid}.audio-binding.json'
    video_hash=digest(video)
    if audio.exists():
        safe_path(str(audio.relative_to(DATA)))
        saved=json.loads(audio_binding.read_text()) if audio_binding.exists() else {}
        if saved.get('video_sha256')!=video_hash or saved.get('audio_sha256')!=digest(audio):raise VerificationError('Audio extraction binding mismatch','MEDIA_INVALID')
    if not audio.exists():
        tmp=audio.with_name(vid+'.partial'+audio.suffix)
        await asyncio.to_thread(run,[CONFIG['generic_ffmpeg'],'-nostdin','-y','-v','error','-i',str(video),'-map','0:a:0','-vn','-c:a','copy',str(tmp)])
        tmp.replace(audio)
        dump(audio_binding,{'video_sha256':video_hash,'audio_sha256':digest(audio)})
    wav=artifact_dir('tmp')/f'{vid}.asr.wav'
    ap=await asyncio.to_thread(probe,audio)
    stage('verifying',media_id=vid)
    checks={}
    for kind,path,metadata in [('video',video,vp),('audio',audio,ap)]:
        sha=digest(path);size=path.stat().st_size
        checkpoint=artifact_dir('metadata')/f'{vid}.{kind}.decode.json'
        saved=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        if saved.get('sha256')!=sha or saved.get('bytes')!=size or saved.get('full_decode') is not True:
            args=[CONFIG['generic_ffmpeg'],'-nostdin','-v','error','-xerror','-err_detect','explode','-i',str(path),'-map','0:v:0','-map','0:a:0','-f','null','-'] if kind=='video' else [CONFIG['generic_ffmpeg'],'-nostdin','-v','error','-xerror','-err_detect','explode','-i',str(path),'-map','0:a:0','-f','null','-']
            try:
                decoded=await asyncio.to_thread(run,args)
            except Exception as exc:
                dump(checkpoint,{'sha256':sha,'bytes':size,'full_decode':False,'ffmpeg':getattr(exc,'diagnostics',None)})
                raise
            saved={'sha256':sha,'bytes':size,'full_decode':True,'duration_seconds':float(metadata['format']['duration']),'ffmpeg':decoded}
            dump(checkpoint,saved)
        checks[kind]={k:saved[k] for k in ('sha256','bytes','full_decode','duration_seconds')}
    duration=checks['video']['duration_seconds'];aduration=checks['audio']['duration_seconds']
    durations(duration,aduration,info.duration_seconds)
    if duration>1800 or video.stat().st_size>1024**3:raise ConfirmationRequired('Media exceeds configured limits')
    timings['extract_and_validate_seconds']=round(time.monotonic()-t,3)
    stage('transcribing',media_id=vid)
    asr_raw=DATA/'transcripts'/f'{vid}.{fingerprint[:12]}.raw.json';t=time.monotonic()
    peak=0
    asr_checkpoint=asr_raw.with_suffix('.checkpoint.json')
    video_hash=await asyncio.to_thread(digest,video)
    reusable=None
    if asr_raw.exists() and asr_checkpoint.exists():
        checkpoint=json.loads(asr_checkpoint.read_text())
        if checkpoint.get('video_sha256')==video_hash and checkpoint.get('fingerprint')==fingerprint and checkpoint.get('raw_sha256')==digest(asr_raw):
            reusable=json.loads(asr_raw.read_text())
    if reusable is not None:
        result=reusable
    else:
        await asyncio.to_thread(run,[CONFIG['generic_ffmpeg'],'-nostdin','-y','-v','error','-i',str(audio),'-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)])
        transcript=await transcriber.transcribe(wav)
        result=transcript.as_dict();peak=transcript.peak_rss_bytes
        dump(asr_raw,result)
        dump(asr_checkpoint,{'video_sha256':video_hash,'fingerprint':fingerprint,'raw_sha256':digest(asr_raw)})
    timings['transcribe_seconds']=round(time.monotonic()-t,3)
    segments=result.get('segments',[])
    if not segments or not result.get('text'):raise RuntimeError('ASR returned no transcription')
    if max(s['end'] for s in segments)<duration-10:raise RuntimeError('ASR ends too early; raw output retained for inspection')
    from collections import Counter
    repeated=Counter(s['text'].strip() for s in segments if s['text'].strip())
    if repeated and max(repeated.values())>max(20,len(segments)*.3):raise RuntimeError('ASR content QA failed: excessive repeated segments; original result retained')
    full=DATA/'transcripts'/f'{vid}.{fingerprint[:12]}.txt';full.write_text(result['text'])
    model=CONFIG['model']
    manifest={'media_id':vid,'platform':'douyin','original_share_url':job['url'],'canonical_url':info.canonical_url,
      'title':info.title, 'description':info.description,'author':info.author,
      'published_at':info.published_at,'duration_seconds':duration,'platform_duration_seconds':info.duration_seconds,
      'selected_video':{'width':vs['width'],'height':vs['height'],'codec':vs['codec_name'],'gear':selection.get('gear'),'bit_rate':selection.get('bit_rate')},
      'audio':{'method':method,'codec':ac,'duration_seconds':aduration,'asr_format':'PCM signed 16-bit WAV, 16000Hz mono'},
      'cover_kind':'platform original cover','versions':CONFIG['versions'],
      'source_provider':source.name,
      'asr':{'engine':transcriber.name,'model':model['name'],'model_source':model['source'],'model_sha256':model['sha256'],'fingerprint':fingerprint,'language':result.get('language'),'parameters':dict(transcriber.parameters),'elapsed_seconds':timings['transcribe_seconds'],'peak_server_rss_bytes':peak,'note':'Provider-specific RSS measurement; accelerator allocations may not be included'},
      'timings':timings,'processed_at':datetime.now().astimezone().isoformat(),'validation':{'full_video_decode':True,'full_audio_decode':True,'duration_difference_seconds':round(abs(duration-aduration),6),'last_segment_end':max(s['end'] for s in segments)},
      'verification':{'input_url':job['url'],'resolved_id':vid,'detail_id':detail_id,'downloaded_id':selection['downloaded_id'],**checks},
      'files':{}}
    for key,path in [('video',video),('audio',audio),('cover',cover),('raw_metadata',raw_path),('raw_transcript',asr_raw),('text',full)]:
        manifest['files'][key]={'path':str(path.relative_to(DATA)),'bytes':path.stat().st_size,'sha256':digest(path)}
        if key in ('video','audio','cover'):manifest['files'][key]['url']=CONFIG['base_url']+f'/v1/media/{vid}/{key}'
    timings['total_seconds']=round(time.monotonic()-start,3)
    evidence(manifest)
    final=await finish(manifest,result,CONFIG,stage)
    wav.unlink(missing_ok=True)
    return final
