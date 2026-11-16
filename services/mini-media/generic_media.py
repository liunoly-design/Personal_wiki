"""File-only extension for the existing Mini gateway and its single durable worker.

No URLs are fetched by this module. Source metadata is a client acquisition claim,
cryptographically bound to the uploaded original, not independent platform proof.
"""
import asyncio,fcntl,hashlib,json,math,mimetypes,os,re,secrets,shutil,time
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import Depends,Request
from fastapi.responses import FileResponse,JSONResponse

LIMIT=1_000_000_000
FORMATS='mov,matroska,webm,mp3,wav,flac,ogg,aac,aiff,caf'
EXTENSIONS={'.mp4','.mov','.mkv','.webm','.m4v','.mp3','.m4a','.wav','.aac','.flac','.ogg','.opus','.aiff','.aif','.caf'}
SHA=re.compile(r'^[a-f0-9]{64}$')

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def immutable(path,body):
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 temporary=path.parent/('.immutable-'+secrets.token_hex(12))
 try:
  with temporary.open('xb') as f:
   os.chmod(temporary,0o600);f.write(body);f.flush();os.fsync(f.fileno())
  try:os.link(temporary,path)
  except FileExistsError:
   if path.is_symlink() or path.read_bytes()!=body:raise ValueError('Immutable artifact differs')
  fd=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 finally:temporary.unlink(missing_ok=True)
def json_bytes(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def validate(body):
 if not isinstance(body,dict) or set(body)!={'source','file'}:raise ValueError()
 s,f=body['source'],body['file']
 if not isinstance(s,dict) or not isinstance(f,dict) or set(f)!={'sha256','bytes','extension'}:raise ValueError()
 if not SHA.fullmatch(f.get('sha256','')) or type(f.get('bytes')) is not int or f['bytes']<=0 or f.get('extension') not in EXTENSIONS:raise ValueError()
 if set(s)-{'platform','id','url','asset_id','title','author','duration_seconds','acquisition_sha256','provenance'}:raise ValueError()
 if any(not isinstance(s.get(k),str) or not 0<len(s[k])<=2048 for k in ('platform','id','url','asset_id','title')):raise ValueError()
 u=urlsplit(s['url'])
 if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.query or u.fragment:raise ValueError()
 if s['platform']=='file':
  if s['id']!=f['sha256'] or u.hostname!='file.personal-wiki.invalid' or u.path!='/'+s['id']:raise ValueError()
 elif s['platform']=='x':
  if u.hostname!='x.com' or not re.fullmatch(r'/[A-Za-z0-9_]+/status/'+re.escape(s['id']),u.path) or not s['id'].isdigit():raise ValueError()
 elif s['platform']=='xiaohongshu':
  if u.hostname!='www.xiaohongshu.com' or not re.fullmatch(r'[a-f0-9]{24}',s['id']) or u.path!='/explore/'+s['id']:raise ValueError()
 else:raise ValueError()
 if 'duration_seconds' in s and (type(s['duration_seconds']) not in (int,float) or not math.isfinite(s['duration_seconds']) or s['duration_seconds']<=0):raise ValueError()
 if 'acquisition_sha256' in s and not SHA.fullmatch(s['acquisition_sha256']):raise ValueError()
 return body

async def command(args,timeout=1800):
 proc=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
 try:out,err=await asyncio.wait_for(proc.communicate(),timeout)
 except BaseException:
  if proc.returncode is None:proc.kill()
  await proc.wait();raise
 if proc.returncode:raise ValueError('Media command rejected input')
 return out

def coverage(raw,duration):
 segments=raw.get('segments');previous=0
 if not raw.get('text','').strip() or not isinstance(segments,list) or not segments:raise ValueError('Empty transcript')
 if all(re.fullmatch(r'[\s\[\]()（）♪♫*.,!，。！-]*(?:music|upbeat music|欢快的音乐|音乐|音樂|掌声|掌聲|applause|silence|无声|無聲)[\s\[\]()（）♪♫*.,!，。！-]*',s.get('text',''),re.I) for s in segments):raise ValueError('No usable speech; original retained')
 for s in segments:
  start,end=s.get('start'),s.get('end')
  if any(type(x) not in (int,float) or not math.isfinite(x) for x in (start,end)) or start<0 or end<=start or start<previous-.25 or end>duration+1 or not s.get('text','').strip():raise ValueError('Transcript segment invalid')
  previous=end
 if segments[0]['start']>10 or duration-segments[-1]['end']>10:raise ValueError('Transcript head/tail incomplete')
 return {'first_start':segments[0]['start'],'last_end':segments[-1]['end'],'segments':len(segments),'head_tail_verified':True}

def register(api,articles=None):
 data=api.DATA
 def directory(jid):
  if not re.fullmatch(r'[a-f0-9]{32}',jid):api.fail(404,'NOT_FOUND','Job not found')
  p=data/'file-jobs'/jid;p.mkdir(parents=True,exist_ok=True,mode=0o700);return p
 def request_for(jid):
  j=api.get(jid);r=json.loads(j['request_json'])
  if r.get('kind')!='file':api.fail(404,'NOT_FOUND','File job not found')
  return j,r['input']
 def saved(jid):
  j,_=request_for(jid)
  if j['status']!='succeeded':api.fail(409,'RESULT_NOT_READY','Result not ready')
  p=directory(jid)/'result.json'
  m=json.loads(p.read_text());verify(m)
  return m
 def verify(m):
  if m.get('kind')!='file':raise ValueError('Invalid file result')
  for f in m['files'].values():
   p=data/f['path']
   if p.is_symlink() or not p.is_file() or p.stat().st_size!=f['bytes'] or digest(p)!=f['sha256']:raise ValueError('File artifact integrity mismatch')
  if m['files']['original']['sha256']!=m['input']['file']['sha256'] or m['files']['original']['bytes']!=m['input']['file']['bytes']:raise ValueError('Original binding mismatch')
  if m['verification']['original']['full_decode'] is not True or m['verification']['audio']['full_decode'] is not True:raise ValueError('Decode proof missing')
  if json.loads((data/m['files']['raw_transcript']['path']).read_text())!=m['raw']:raise ValueError('Raw transcript binding mismatch')
  coverage(m['raw'],m['duration_seconds'])
 @api.app.post('/v1/file-jobs',dependencies=[Depends(api.auth)])
 async def submit_file(request:Request):
  try:body=validate(await request.json())
  except (ValueError,TypeError,KeyError):api.fail(400,'INVALID_INPUT','Invalid file source or metadata')
  if body['file']['bytes']>LIMIT:api.fail(413,'CONFIRMATION_REQUIRED','File exceeds 1GB')
  if body['source'].get('duration_seconds',0)>1800:api.fail(409,'CONFIRMATION_REQUIRED','File exceeds 30 minutes')
  if shutil.disk_usage(data).free<body['file']['bytes']+1024**3:api.fail(507,'STORAGE_FULL','Insufficient storage')
  key=request.headers.get('idempotency-key','')
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',key):api.fail(400,'INVALID_IDEMPOTENCY_KEY','Valid key required')
  canonical=json.dumps({'kind':'file','input':body},sort_keys=True,separators=(',',':'),ensure_ascii=False);rh=hashlib.sha256(canonical.encode()).hexdigest();cfg=api.CONFIG.get('output_fingerprint',api.CONFIG['asr_fingerprint'])
  with api.connect() as c:
   c.execute('BEGIN IMMEDIATE');known=c.execute('SELECT * FROM idempotency WHERE key=?',(key,)).fetchone()
   if known:
    if known['request_hash']!=rh:api.fail(409,'IDEMPOTENCY_CONFLICT','Key used for different input')
    j=dict(c.execute('SELECT * FROM jobs WHERE id=?',(known['job_id'],)).fetchone());reused=True
   else:
    prior=c.execute('SELECT * FROM jobs WHERE request_hash=? AND config_hash=? ORDER BY created DESC LIMIT 1',(rh,cfg)).fetchone()
    if prior:j=dict(prior);reused=True
    else:
     if c.execute("SELECT COUNT(*) FROM jobs WHERE status NOT IN ('succeeded','failed','partial_failed','waiting_login','waiting_confirmation')").fetchone()[0]>=100:api.fail(429,'QUEUE_FULL','Queue full',True)
     j={'id':secrets.token_hex(16),'status':'waiting_upload'};now=time.time();reused=False
     c.execute('INSERT INTO jobs(id,url,request_json,request_hash,config_hash,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',(j['id'],body['source']['url'],canonical,rh,cfg,j['status'],now,now))
    c.execute('INSERT INTO idempotency VALUES(?,?,?)',(key,rh,j['id']))
  return JSONResponse({'api_version':'1','job_id':j['id'],'status':j['status'],'reused':reused},status_code=200 if reused else 202)
 @api.app.put('/v1/file-jobs/{jid}/content',dependencies=[Depends(api.auth)])
 async def upload(jid:str,request:Request):
  j,body=request_for(jid);p=directory(jid);f=body['file'];target=p/('source'+f['extension'])
  with (p/'upload.lock').open('a') as lock:
   try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:api.fail(409,'UPLOAD_BUSY','Upload active',True)
   if target.exists():
    if target.is_symlink() or target.stat().st_size!=f['bytes'] or digest(target)!=f['sha256']:api.fail(409,'INTEGRITY_FAILURE','Original mismatch')
    # A crash between the immutable rename and queue transaction is recoverable.
   else:
    if j['status']!='waiting_upload':api.fail(409,'INVALID_STATE','Upload not expected')
    part=p/'upload.part';sha=hashlib.sha256();size=0
    with part.open('wb') as out:
     os.chmod(part,0o600)
     async for chunk in request.stream():
      size+=len(chunk)
      if size>f['bytes'] or size>LIMIT:api.fail(422,'INTEGRITY_FAILURE','Uploaded size mismatch')
      sha.update(chunk);out.write(chunk)
     out.flush();os.fsync(out.fileno())
    if size!=f['bytes'] or sha.hexdigest()!=f['sha256']:api.fail(422,'INTEGRITY_FAILURE','Uploaded hash or size mismatch')
    os.link(part,target);part.unlink()
    fd=os.open(p,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
   with api.connect() as c:c.execute("UPDATE jobs SET status='queued',updated=? WHERE id=? AND status='waiting_upload'",(time.time(),jid))
  return {'api_version':'1','job_id':jid,'status':api.get(jid)['status'],'reused':j['status']!='waiting_upload'}
 @api.app.post('/v1/file-jobs/{jid}/resume',dependencies=[Depends(api.auth)])
 def resume_file(jid:str):
  j,body=request_for(jid)
  if j['status'] not in ('failed','partial_failed','waiting_confirmation'):api.fail(409,'INVALID_STATE','Stopped job required')
  p=directory(jid)/('source'+body['file']['extension'])
  if not p.is_file() or digest(p)!=body['file']['sha256']:api.fail(409,'INTEGRITY_FAILURE','Original unavailable')
  with api.connect() as c:c.execute("UPDATE jobs SET status='queued',error=NULL,updated=? WHERE id=? AND status=?",(time.time(),jid,j['status']))
  return {'api_version':'1','job_id':jid,'status':'queued','reused':True}
 @api.app.get('/v1/file-jobs/{jid}/manifest',dependencies=[Depends(api.auth)])
 def manifest(jid:str):
  m=saved(jid)
  return {'api_version':'1','kind':'file','job_id':jid,'input':m['input'],'duration_seconds':m['duration_seconds'],'transcription':m['asr'],'translation':m.get('translation'),'verification':m['verification'],'coverage':m['coverage'],'segments':m['delivered_segments'],'markdown':{k:m['files']['markdown'][k] for k in ('sha256','bytes')},'media':{k:{'path':f'/v1/file-media/{jid}/{k}','sha256':v['sha256'],'bytes':v['bytes'],'mime':m['mime'][k]} for k,v in m['files'].items() if k in ('original','audio')}}
 @api.app.get('/v1/file-jobs/{jid}/markdown',dependencies=[Depends(api.auth)])
 def markdown(jid:str):return FileResponse(data/saved(jid)['files']['markdown']['path'],media_type='text/markdown; charset=utf-8')
 @api.app.api_route('/v1/file-media/{jid}/{kind}',methods=['GET','HEAD'],dependencies=[Depends(api.auth)])
 def media(jid:str,kind:str):
  if kind not in ('original','audio'):api.fail(404,'NOT_FOUND','Unknown media')
  m=saved(jid);return FileResponse(data/m['files'][kind]['path'],media_type=m['mime'][kind],headers={'ETag':'"'+m['files'][kind]['sha256']+'"','Accept-Ranges':'bytes'})
 old_process,old_evidence,old_snapshot=api.process,api.evidence,api.snapshot
 async def dispatch(job,stage,**kw):
  r=json.loads(job['request_json'])
  if r.get('kind')!='file':return await old_process(job,stage,**kw)
  return await process_file(job,r['input'],directory(job['id']),api,stage)
 def dispatch_evidence(m):return verify(m) if m.get('kind')=='file' else old_evidence(m)
 def dispatch_snapshot(m):
  if m.get('kind')!='file':return old_snapshot(m)
  verify(m);aid='file_'+m['media_id'];immutable(data/'metadata'/'v1'/(aid+'.json'),json_bytes(m));return aid,m
 api.process=dispatch;api.evidence=dispatch_evidence;api.snapshot=dispatch_snapshot
 # Generic transcripts are compiled by LLM Wiki, never the service's optional AI enrichment.
 if articles:
  original_enqueue=articles.enqueue
  def enqueue(aid,*args,**kwargs):return 'skipped' if aid.startswith('file_') else original_enqueue(aid,*args,**kwargs)
  articles.enqueue=enqueue

async def process_file(job,body,p,api,stage):
 from douyin2text.providers.registry import asr_provider
 original=p/('source'+body['file']['extension']);cfg=api.CONFIG
 if original.is_symlink() or digest(original)!=body['file']['sha256'] or original.stat().st_size!=body['file']['bytes']:raise ValueError('Input integrity mismatch')
 if (p/'result.json').exists():
  m=json.loads((p/'result.json').read_text())
  if m['asr']['fingerprint']==cfg['asr_fingerprint'] and m['output_fingerprint']==cfg['output_fingerprint']:return m
 stage('extracting',media_id=job['id'])
 ffmpeg=cfg.get('generic_ffmpeg','/opt/homebrew/bin/ffmpeg');ffprobe=cfg.get('generic_ffprobe','/opt/homebrew/bin/ffprobe')
 probe=json.loads(await command([ffprobe,'-v','error','-protocol_whitelist','file,pipe','-format_whitelist',FORMATS,'-show_streams','-show_format','-of','json',str(original)],60))
 streams=probe.get('streams',[])
 if not any(s.get('codec_type')=='audio' for s in streams):raise ValueError('No audio stream')
 duration=float(probe['format']['duration'])
 if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid duration')
 if duration>1800:raise api.ConfirmationRequired('Media exceeds 30 minutes')
 expected=body['source'].get('duration_seconds',duration)
 if abs(expected-duration)>max(1,duration*.005):raise ValueError('Platform duration mismatch')
 stage('verifying',media_id=job['id'])
 await command([ffmpeg,'-nostdin','-v','error','-xerror','-err_detect','explode','-protocol_whitelist','file,pipe','-format_whitelist',FORMATS,'-i',str(original),'-map','0:a:0','-map','0:v:0?','-f','null','-'])
 audio=p/'audio.wav';audio_binding=p/'audio.binding.json'
 if not audio.exists():
  part=p/'audio.part.wav';await command([ffmpeg,'-nostdin','-y','-v','error','-protocol_whitelist','file,pipe','-format_whitelist',FORMATS,'-i',str(original),'-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(part)])
  immutable(audio_binding,json_bytes({'input_sha256':digest(original),'audio_sha256':digest(part)}));os.link(part,audio);part.unlink()
 if not audio_binding.exists() or json.loads(audio_binding.read_text())!={'input_sha256':digest(original),'audio_sha256':digest(audio)}:raise ValueError('Audio input binding mismatch')
 await command([ffmpeg,'-nostdin','-v','error','-xerror','-i',str(audio),'-f','null','-'])
 ap=json.loads(await command([ffprobe,'-v','error','-show_format','-of','json',str(audio)],60));aduration=float(ap['format']['duration'])
 if abs(duration-aduration)>max(1,duration*.005):raise ValueError('Audio duration mismatch')
 binding={'input_sha256':digest(original),'audio_sha256':digest(audio),'fingerprint':cfg['asr_fingerprint']}
 raw_path=p/('asr-'+cfg['asr_fingerprint'][:12]+'.json');checkpoint=raw_path.with_suffix('.binding.json')
 stage('transcribing',media_id=job['id']);t=time.monotonic()
 if checkpoint.exists():
  bind=json.loads(checkpoint.read_text())
  if any(bind.get(k)!=v for k,v in binding.items()):raise ValueError('ASR checkpoint input mismatch')
  if not raw_path.exists() and 'raw' in bind:immutable(raw_path,json_bytes(bind['raw']))
  if not raw_path.exists() or bind.get('raw_sha256')!=digest(raw_path):raise ValueError('ASR checkpoint mismatch')
  raw=json.loads(raw_path.read_text())
 elif raw_path.exists():raise ValueError('ASR checkpoint binding missing; original retained')
 else:
  provider=asr_provider(cfg);transcript=await asyncio.wait_for(provider.transcribe(audio),timeout=7200);raw=transcript.as_dict()
  raw_bytes=json_bytes(raw)
  immutable(checkpoint,json_bytes({**binding,'raw_sha256':hashlib.sha256(raw_bytes).hexdigest(),'raw':raw}))
  immutable(raw_path,raw_bytes)
 cov=coverage(raw,duration);delivered=raw['segments'];translation=None
 if raw.get('language') not in ('zh','chinese'):
  trcfg=cfg.get('translation',{})
  if not trcfg.get('enabled'):raise ValueError('Local Chinese translation not configured')
  stage('translating',media_id=job['id']);tr=p/('translation-'+cfg['output_fingerprint'][:12]+'.json')
  if not tr.exists():await command([str(trcfg['python']),str(trcfg['script']),str(raw_path),str(tr)],1800)
  result=json.loads(tr.read_text());delivered=result.get('segments',[])
  if result.get('source_transcript_sha256')!=digest(raw_path) or result.get('model_sha256')!=trcfg['sha256'] or len(delivered)!=len(raw['segments']) or any(t.get('start')!=s['start'] or t.get('end')!=s['end'] or not t.get('text','').strip() for s,t in zip(raw['segments'],delivered)):raise ValueError('Translation coverage mismatch')
  translation={k:v for k,v in result.items() if k not in ('segments','text','raw_model_outputs')}
 if not re.search(r'[\u3400-\u9fff]',''.join(s['text'] for s in delivered)):raise ValueError('Chinese delivery missing')
 def stamp(x):
  ms=round(x*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'
 def lines(ss):return '\n\n'.join(f"[{stamp(s['start'])} → {stamp(s['end'])}] {s['text'].strip()}" for s in ss)
 text='# '+body['source']['title'].replace('\n',' ')+'\n\n> 完整机器转写'+('及本地机器中文翻译' if translation else '')+'；未经人工校订。\n\n来源：'+body['source']['url']+'\n\n## 完整中文正文\n\n'+lines(delivered)+'\n\n## 完整原始转写\n\n'+lines(raw['segments'])+'\n'
 md=p/('transcript-'+cfg['output_fingerprint'][:12]+'.md');immutable(md,text.encode())
 def record(path):return {'path':str(path.relative_to(api.DATA)),'sha256':digest(path),'bytes':path.stat().st_size}
 model=cfg['model'];asr={'engine':'whisper.cpp','model':model['name'],'model_sha256':model['sha256'],'fingerprint':cfg['asr_fingerprint'],'language':raw['language'],'elapsed_seconds':round(time.monotonic()-t,3)}
 m={'kind':'file','media_id':job['id'],'versioned_media_id':'file_'+job['id'],'input':body,'duration_seconds':duration,'asr':asr,'output_fingerprint':cfg['output_fingerprint'],'raw':raw,'delivered_segments':delivered,'translation':translation,'coverage':cov,'verification':{'input_sha256':digest(original),'original':{'full_decode':True,'duration_seconds':duration},'audio':{'full_decode':True,'duration_seconds':aduration},'source_binding':'client_acquisition_claim'},'files':{'original':record(original),'audio':record(audio),'raw_transcript':record(raw_path),'markdown':record(md)},'mime':{'original':mimetypes.guess_type(original)[0] or 'application/octet-stream','audio':'audio/wav'}}
 if translation:m['files']['raw_translation']=record(tr)
 immutable(p/'result.json',json_bytes(m));return m
