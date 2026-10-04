#!/usr/bin/env python3
"""Bounded public Douyin capture and recoverable media/ASR. Never reads cookies."""
import hashlib
import ipaddress
import socket
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urljoin, unquote
try:
    from .attachment_resume import atomic_json, download, safe_destination
    from .blog_capture import public_addresses, PinnedHTTPS
except ImportError:
    from attachment_resume import atomic_json, download, safe_destination
    from blog_capture import public_addresses, PinnedHTTPS

VERSION='douyin-v1-aac128-x264-crf28'
ASR_VERSION='codex-asr-0.1.2'
LIMIT=1_000_000_000
PAGE_HOSTS={'v.douyin.com','www.douyin.com','douyin.com','www.iesdouyin.com','iesdouyin.com'}
MEDIA_SUFFIXES=('douyinvod.com','douyin.com','bytecdn.cn','ibytedtos.com','byteimg.com','pstatp.com')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def check_url(url,media=False):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443):raise ValueError('Unsupported source URL')
    allowed=any(u.hostname==s or (u.hostname or '').endswith('.'+s) for s in MEDIA_SUFFIXES) if media else u.hostname in PAGE_HOSTS
    if not allowed:raise ValueError('Unsupported source URL host')
    return u


def source_url(url):
    u=check_url(url)
    if u.hostname=='v.douyin.com' and re.fullmatch(r'/[A-Za-z0-9_-]+/?',u.path):return url
    match=re.fullmatch(r'/(?:share/)?video/([0-9]{10,24})/?',u.path)
    if not match:raise ValueError('Unsupported source URL: single Douyin video required')
    return 'https://www.douyin.com/video/'+match[1]


def douyin_addresses(url):
    # Only the known local Fake-IP range gets a public DoH resolution fallback.
    # Private/LAN targets remain rejected. HTTPS DNS results are validated and
    # the actual TLS connection is pinned to a public answer.
    try:return public_addresses(url)
    except ValueError:
        u=check_url(url,media=urlsplit(url).hostname not in PAGE_HOSTS)
        addresses={x[4][0] for x in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)}
        if not addresses or not all(ipaddress.ip_address(x) in ipaddress.ip_network('198.18.0.0/15') for x in addresses):raise
        import httpx
        response=httpx.get('https://dns.google/resolve',params={'name':u.hostname,'type':'A'},timeout=20,follow_redirects=False)
        response.raise_for_status();value=response.json()
        if value.get('Status')!=0:raise ValueError('Public DNS resolution failed')
        answers=sorted({x['data'] for x in value.get('Answer',[]) if x.get('type')==1})
        if not answers or any(not ipaddress.ip_address(x).is_global or ipaddress.ip_address(x).is_multicast for x in answers):raise ValueError('Non-public DoH address rejected')
        return u,answers


def fetch_page(url):
    current=url
    for _ in range(6):
        check_url(current);u,addresses=douyin_addresses(current)
        conn=PinnedHTTPS(u.hostname,addresses[0])
        try:
            conn.request('GET',u.path+('?' + u.query if u.query else ''),headers={'User-Agent':'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148','Accept-Encoding':'identity'})
            r=conn.getresponse()
            if r.status in (301,302,303,307,308):current=urljoin(current,r.getheader('Location') or '');continue
            if r.status in (401,403):raise ValueError('Douyin login/captcha required (public HTTP '+str(r.status)+')')
            if r.status!=200:raise OSError('Douyin HTTP '+str(r.status))
            data=r.read(8*1024*1024+1)
            if len(data)>8*1024*1024:raise ValueError('Douyin metadata exceeds limit')
            return current,data.decode('utf8',errors='replace')
        finally:conn.close()
    raise ValueError('Douyin redirect limit exceeded')


def metadata(url):
    url=source_url(url);final,html=fetch_page(url)
    match=re.search(r'/(?:share/)?video/([0-9]{10,24})',urlsplit(final).path)
    if not match:raise ValueError('Unsupported source URL: redirect is not a single video')
    vid=match[1]
    # Public mobile HTML embeds the same platform aweme data; no signature/cookie bypass.
    _,html=fetch_page('https://www.iesdouyin.com/share/video/'+vid+'/')
    candidates=[]
    for pattern in [r'window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>',r'<script[^>]*id="RENDER_DATA"[^>]*>(.*?)</script>']:
        m=re.search(pattern,html,re.S)
        if m:
            try:candidates.append(json.loads(unquote(m[1])))
            except json.JSONDecodeError:pass
    def walk(v):
        if isinstance(v,dict):
            if str(v.get('aweme_id'))==vid and isinstance(v.get('video'),dict):return v
            for child in v.values():
                found=walk(child)
                if found:return found
        elif isinstance(v,list):
            for child in v:
                found=walk(child)
                if found:return found
    detail=next((x for v in candidates if (x:=walk(v))),None)
    if not detail:raise ValueError('Douyin login/captcha or extractor unavailable; public video metadata missing')
    if detail.get('images') or detail.get('aweme_type') not in (None,0,4,55):raise ValueError('Unsupported source URL: slideshow/non-video')
    video=detail['video'];formats=[]
    for entry in video.get('bit_rate',[])+[video]:
        address=entry.get('play_addr',{});w=address.get('width') or video.get('width');h=address.get('height') or video.get('height')
        if not w or not h or min(w,h)>1080:continue
        for remote in address.get('url_list',[]):
            try:check_url(remote,True)
            except ValueError:continue
            formats.append(dict(url=remote,width=w,height=h,bitrate=entry.get('bit_rate',0),expected_size=address.get('data_size')))
    if not formats:raise ValueError('unsupported media: no direct stream at or below 1080p')
    chosen=max(formats,key=lambda f:(min(f['width'],f['height']),f['bitrate']))
    duration=video.get('duration',detail.get('duration'))
    if not isinstance(duration,(int,float)) or duration<=0:raise ValueError('unsupported media: duration unavailable')
    return dict(id=vid,url='https://www.douyin.com/video/'+vid,title=detail.get('desc') or 'Douyin '+vid,author=detail.get('author',{}).get('nickname',''),duration=duration/1000,**chosen)


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_media(args,timeout=3600):
    p=subprocess.run([ffmpeg(),'-nostdin','-hide_banner',*args],capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise ValueError('Media encode/decode failed; materials retained')
    return p.stderr


def media_probe(path,video=True):
    result=subprocess.run([ffmpeg(),'-nostdin','-hide_banner','-i',str(path)],capture_output=True,text=True,timeout=30)
    output=result.stderr
    t=re.search(r'Duration: (\d+):(\d+):([\d.]+)',output)
    if not t:raise ValueError('Damaged media: duration unavailable')
    duration=int(t[1])*3600+int(t[2])*60+float(t[3])
    info=dict(duration=duration,bytes=Path(path).stat().st_size,sha256=sha(path))
    if video:
        dims=re.search(r'Video:.*?\b(\d{2,5})x(\d{2,5})\b',output)
        if not dims or 'Audio:' not in output:raise ValueError('Damaged video or no audio track')
        info.update(width=int(dims[1]),height=int(dims[2]))
        fps=re.search(r'([\d.]+) fps',output);info['fps']=float(fps[1]) if fps else None
        rot=re.search(r'rotation of ([\d.-]+)',output);info['rotation']=float(rot[1]) if rot else 0
    run_media(['-v','error','-i',str(path),'-map','0:v?' if video else '0:a','-map','0:a','-f','null','-'])
    return info


def load(path):return json.loads(path.read_text()) if path.exists() else None


def freeze_file(root,path):
    relative=str(path.relative_to(root));safe_destination(root,relative)
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode):raise ValueError('Work material is not a regular file')
    return dict(path=relative,sha256=sha(path),device=st.st_dev,inode=st.st_ino,bytes=st.st_size)


def prepare_media(root,source,mode):
    root=Path(root);source=Path(source);package=root/'package';package.mkdir(exist_ok=True)
    prior=load(root/'media.json')
    if prior:
        if prior['mode']!=mode or prior['version']!=VERSION:raise ValueError('Media config changed; create a new version')
        for key in ['video','audio']:
            path=safe_destination(package,prior[key]['path'])
            if sha(path)!=prior[key]['sha256']:raise ValueError('Formal media integrity mismatch')
        return prior
    if mode not in ('compressed','original'):raise ValueError('Invalid video mode')
    info=media_probe(source)
    if min(info['width'],info['height'])>1080:raise ValueError('Video exceeds 1080p')
    if shutil.disk_usage(root).free<max(64*1024*1024,info['bytes']*2+info['duration']*32000):raise ValueError('Insufficient disk space; materials retained')
    audio=package/'audio.m4a';video=package/'video.mp4'
    # Extract complete audio from the verified source before any video conversion.
    if not audio.exists():
        tmp=root/'audio.tmp.m4a';run_media(['-v','error','-i',str(source),'-vn','-c:a','aac','-b:a','128k',str(tmp),'-y']);tmp.replace(audio)
    a=media_probe(audio,False)
    if abs(a['duration']-info['duration'])>.25:raise ValueError('Incomplete audio duration')
    if not video.exists():
        if mode=='original':shutil.copyfile(source,video)
        else:
            tmp=root/'video.tmp.mp4'
            scale="scale=w='trunc(iw*min(1,720/min(iw,ih))/2)*2':h='trunc(ih*min(1,720/min(iw,ih))/2)*2'"
            run_media(['-v','error','-i',str(source),'-vf',scale,'-c:v','libx264','-crf','28','-preset','medium','-c:a','aac','-b:a','128k','-movflags','+faststart',str(tmp),'-y']);tmp.replace(video)
    v=media_probe(video)
    if abs(v['duration']-info['duration'])>.25:raise ValueError('Incomplete archive video')
    if mode=='compressed' and (min(v['width'],v['height'])>720 or v['bytes']>=info['bytes']):raise ValueError('Compression did not save bytes or exceeds 720p; retained')
    result=dict(mode=mode,version=VERSION,encoder=subprocess.run([ffmpeg(),'-version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],source=info,video=dict(path='video.mp4',**v),audio=dict(path='audio.m4a',**a))
    atomic_json(root/'media.json',result)
    if mode=='compressed':atomic_json(root/'cleanup.json',dict(version=1,files=[freeze_file(root,source)],deleted=[]))
    return result


def acquire_media(url,root,mode,meta=None,approved=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    meta=meta or load(root/'metadata.json') or metadata(url)
    atomic_json(root/'metadata.json',meta)
    if (meta['duration']>1800 or (meta.get('expected_size') or 0)>=LIMIT) and not approved:raise ValueError('Video confirmation required: exceeds 30 minutes or 1 GB')
    estimate=meta.get('expected_size') or LIMIT
    if shutil.disk_usage(root).free<estimate*3+meta['duration']*32000:raise ValueError('Insufficient disk space; materials retained')
    source=root/'download.mp4'
    if not source.exists():download(meta['url'],source,approved=approved,validate_url=lambda u:check_url(u,True),resolve_addresses=douyin_addresses)
    result=prepare_media(root,source,mode)
    if result['source']['duration']>1800 and not approved:raise ValueError('Video confirmation required: actual duration exceeds 30 minutes')
    if abs(result['source']['duration']-meta['duration'])>1:raise ValueError('Downloaded source duration mismatch')
    return dict(metadata=meta,**result)


def clean_verified(root,verified=False):
    try:
        from .protected_store import Root
    except ImportError:
        from protected_store import Root
    root=Path(root);media=load(root/'media.json')
    if not verified:raise ValueError('Publication verification required before cleanup')
    if media['mode']=='original':return dict(status='retained_original',bytes=0)
    manifest=load(root/'cleanup.json');deleted=manifest['deleted'];store=Root(root)
    try:
        for entry in manifest['files']:
            rel=entry['path']
            if rel!='download.mp4' and not re.fullmatch(r'chunks/[0-9]{4}\.wav',rel):raise ValueError('Unsafe cleanup target')
            fd,name=store.parent(rel)
            quarantine='.cleanup-'+hashlib.sha256(rel.encode()).hexdigest()[:16]
            try:
                def exists(n):
                    try:os.stat(n,dir_fd=fd,follow_symlinks=False);return True
                    except FileNotFoundError:return False
                if rel in deleted:
                    if exists(name) or exists(quarantine):raise ValueError('Deleted work path reused; refuse cleanup')
                    continue
                if not exists(quarantine) and exists(name):
                    if not stat.S_ISREG(os.stat(name,dir_fd=fd,follow_symlinks=False).st_mode):raise ValueError('Cleanup symlink/non-file rejected')
                    os.rename(name,quarantine,src_dir_fd=fd,dst_dir_fd=fd)
                if exists(quarantine):
                    stream=os.open(quarantine,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                    try:
                        st=os.fstat(stream);h=hashlib.sha256()
                        if not stat.S_ISREG(st.st_mode):raise ValueError('Cleanup identity changed')
                        while True:
                            data=os.read(stream,1024*1024)
                            if not data:break
                            h.update(data)
                        if (st.st_dev,st.st_ino,st.st_size,h.hexdigest())!=(entry['device'],entry['inode'],entry['bytes'],entry['sha256']):
                            if not exists(name):os.rename(quarantine,name,src_dir_fd=fd,dst_dir_fd=fd)
                            raise ValueError('Cleanup file identity changed')
                    finally:os.close(stream)
                    os.unlink(quarantine,dir_fd=fd);os.fsync(fd)
                deleted.append(rel);atomic_json(root/'cleanup.json',manifest)
            finally:os.close(fd)
    finally:os.close(store.fd)
    return dict(status='complete',bytes=sum(f['bytes'] for f in manifest['files']),deleted=deleted)


class ASRFailure(Exception):
    def __init__(self,reason,unknown=False):super().__init__(reason);self.unknown=unknown


def codex_asr(binary,path):
    if not binary or not Path(binary).is_file():raise ASRFailure('ASR backend unavailable; configure codex-asr 0.1.2')
    version=subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=10)
    if version.stdout.strip()!='codex-asr 0.1.2':raise ASRFailure('ASR backend version changed')
    try:
        r=subprocess.run([binary,str(path),'--language','zh','--json'],capture_output=True,text=True,timeout=330)
    except subprocess.TimeoutExpired:raise ASRFailure('ASR unknown cloud result: timeout',True)
    if r.returncode:
        # Never propagate remote bodies, auth data or arbitrary CLI stderr into logs.
        status=re.search(r'(?:HTTP|status)[^0-9]{0,15}([45][0-9]{2})',r.stderr,re.I)
        code=status[1] if status else None
        if code in ('401','403'):raise ASRFailure('ASR login required: HTTP '+code)
        if code in ('402','429'):raise ASRFailure('ASR quota waiting: HTTP '+code)
        if code:raise ASRFailure('ASR backend HTTP '+code)
        raise ASRFailure('ASR unknown cloud result: network or interface error',True)
    try:value=json.loads(r.stdout)
    except json.JSONDecodeError:raise ASRFailure('ASR unknown cloud result: invalid response',True)
    if not isinstance(value.get('text'),str):raise ASRFailure('ASR unknown cloud result: missing text',True)
    return value


def silence_ranges(audio):
    output=run_media(['-i',str(audio),'-af','silencedetect=noise=-45dB:d=0.4','-f','null','-'])
    starts=[float(x) for x in re.findall(r'silence_start: ([0-9.]+)',output)]
    ends=[float(x) for x in re.findall(r'silence_end: ([0-9.]+)',output)]
    return list(zip(starts,ends))


def transcribe_audio(root,binary=None,backend=None,recovery=False):
    root=Path(root);package=safe_destination(root,'package/audio.m4a').parent;audio=safe_destination(root,'package/audio.m4a')
    info=media_probe(audio,False);config=dict(version=ASR_VERSION,segment_seconds=60,overlap_seconds=1,language='zh',audio_hash=info['sha256'],pause_cut_version=2)
    done=load(root/'transcript-result.json')
    if done:
        if done['config']!=config or sha(Path(done['transcript']))!=done['sha256']:raise ValueError('Transcript integrity/config mismatch')
        return done
    plan=load(root/'segments.json')
    if plan:
        if plan['config']!=config:raise ValueError('ASR config changed; preserve old version')
    else:
        ranges=silence_ranges(audio);segments=[];start=0
        while start<info['duration']-.01:
            end=min(info['duration'],start+60)
            pauses=[min(b,end)-.05 for a,b in ranges if min(b,end)-max(a,end-10)>.4 and min(b,end)-.05>start+1]
            paused=False
            if end<info['duration'] and pauses:end=max(pauses);paused=True
            segments.append(dict(index=len(segments),start=round(start,3),end=round(end,3),overlap=0 if paused or end==info['duration'] else 1))
            start=end-(0 if paused or end==info['duration'] else 1)
        plan=dict(config=config,duration=info['duration'],segments=segments);atomic_json(root/'segments.json',plan)
    safe_destination(root,'package/responses/0000.json');safe_destination(root,'chunks/0000.wav')
    state=load(root/'asr-state.json') or {};texts=[]
    for segment in plan['segments']:
        idx=f"{segment['index']:04}";response=safe_destination(root,f'package/responses/{idx}.json')
        job=state.setdefault(idx,dict(attempts=0,status='pending'))
        if response.exists():
            raw=load(response)
            if job.get('response_hash') and sha(response)!=job['response_hash']:raise ValueError('ASR response integrity mismatch')
            if raw['segment']!=segment or raw['config']!=config:raise ValueError('ASR segment identity mismatch')
            job.update(status='complete',response_hash=sha(response));atomic_json(root/'asr-state.json',state)
        else:
            recovery_id=(recovery.get('messageId') if isinstance(recovery,dict) else 'direct' if recovery else None)
            fresh_recovery=bool(recovery_id and recovery_id!=job.get('recovery_id'))
            if job['status'] in ('in_flight','unknown') and not fresh_recovery:raise ASRFailure('ASR unknown cloud result: explicit continue required',True)
            if job['status'] in ('waiting_login','waiting_capacity','backend_unavailable') and not fresh_recovery:raise ASRFailure(job['reason'])
            if job['attempts']>=5:raise ASRFailure('ASR retry budget exhausted; materials retained')
            path=root/'chunks'/f'{idx}.wav'
            if not path.exists():run_media(['-v','error','-ss',str(segment['start']),'-i',str(audio),'-t',str(segment['end']-segment['start']),'-ac','1','-ar','16000','-c:a','pcm_s16le',str(path),'-y'])
            input_hash=sha(path)
            if job.get('input_hash') and job['input_hash']!=input_hash:raise ValueError('ASR chunk integrity mismatch')
            manifest=load(root/'cleanup.json')
            if manifest and not any(v['path']==f'chunks/{idx}.wav' for v in manifest['files']):manifest['files'].append(freeze_file(root,path));atomic_json(root/'cleanup.json',manifest)
            quiet=silence_ranges(path)
            seconds=segment['end']-segment['start']
            silent=any(a<=.05 and b>=seconds-.1 for a,b in quiet)
            voiced_seconds=max(0,seconds-sum(b-a for a,b in quiet))
            job.update(status='in_flight',input_hash=input_hash,attempts=job['attempts']+1,recovery_id=recovery_id or job.get('recovery_id'));atomic_json(root/'asr-state.json',state)
            try:
                value={'text':'','silence':True} if silent else (backend(path) if backend else codex_asr(binary,path))
                if not isinstance(value.get('text'),str) or (not silent and not value['text'].strip()):raise ASRFailure('ASR empty voiced segment; review required')
                if not silent and voiced_seconds>10 and len(re.sub(r'\s','',value['text']))<voiced_seconds*.3:raise ASRFailure('ASR suspected truncation; too little text for voiced duration')
                if not silent and (value.get('truncated') or value['text'].rstrip().endswith(('…','...'))):raise ASRFailure('ASR suspected truncation; review required')
                raw=dict(segment=segment,config=config,input_hash=input_hash,response=value)
                atomic_json(response,raw)
                job.update(status='complete',response_hash=sha(response));atomic_json(root/'asr-state.json',state)
            except ASRFailure as e:
                status='unknown' if e.unknown else 'waiting_capacity' if 'quota' in str(e) else 'waiting_login' if 'login' in str(e) else 'backend_unavailable' if 'unavailable' in str(e) or 'version changed' in str(e) else 'failed'
                job.update(status=status,reason=str(e));atomic_json(root/'asr-state.json',state);raise
        text=raw['response']['text'];anchor=f"{int(segment['start'])//60:02}:{int(segment['start'])%60:02}"
        texts.append(f"## [{anchor}] 粗粒度时间锚\n\n"+(text if text.strip() else '［静音段，无正文］')+("\n\n> 本段末尾与下一段重叠1秒，保留原机器响应，未凭文字猜删重复。" if segment['overlap'] else ''))
    # Continuous global coverage is derived from the audio plan, never backend prose.
    cursor=0
    for seg in plan['segments']:
        if seg['start']>cursor+.01 or seg['end']<=seg['start']:raise ValueError('Transcript time coverage gap')
        cursor=seg['end']
    if abs(cursor-info['duration'])>.05:raise ValueError('Transcript tail missing')
    transcript=package/'transcript.md';body='# 原始机器转录全文\n\n> 未经人工校订；时间锚为分段起点，不是词级对齐。\n\n'+'\n\n'.join(texts)+'\n'
    if transcript.exists() and transcript.read_text()!=body:raise ValueError('Existing machine transcript protected')
    transcript.write_text(body)
    shutil.copyfile(root/'segments.json',package/'segments.json')
    result=dict(transcript=str(transcript),sha256=sha(transcript),config=config,segments=len(plan['segments']),overlap_boundaries=sum(bool(v['overlap']) for v in plan['segments']))
    atomic_json(root/'transcript-result.json',result);return result


def main(request):
    root=Path(request['root'])
    # Workspace ownership/lease is handled by the shared queue and video lock.
    if request['operation']=='metadata':return metadata(request['url'])
    if root.is_symlink():raise ValueError('Symlink workspace rejected')
    if request['operation']=='media':return acquire_media(request['url'],root,request['mode'],request.get('metadata'),request.get('approved',False))
    if request['operation']=='transcribe':return transcribe_audio(root,request.get('binary'),recovery=request.get('recovery',False))
    if request['operation']=='cleanup':return clean_verified(root,request.get('verified',False))
    raise ValueError('Unsupported operation')

if __name__=='__main__':
    try:print(json.dumps(main(json.load(sys.stdin)),ensure_ascii=False))
    except Exception as e:
        print(json.dumps(dict(error=str(e)),ensure_ascii=False));sys.exit(1)
