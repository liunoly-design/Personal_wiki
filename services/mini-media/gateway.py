"""Independent Mini gateway: initialize private state before importing the API."""
import argparse,hashlib,json,os,secrets,shutil,sys,tempfile
from urllib.parse import urlsplit
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def safe(path):
 path=Path(path).absolute()
 for parent in [path,*path.parents]:
  if parent.is_symlink():raise ValueError('Regular installation paths required')
 return path

def initialize(args):
 if not args.data.is_absolute() or not args.model_file or not args.model_file.is_absolute():raise ValueError('Absolute data and model paths required')
 data=safe(args.data);model=safe(args.model_file)
 if not 1<=args.port<=65535:raise ValueError('Invalid service port')
 origin=urlsplit(args.base_url or f'http://{args.bind}:{args.port}')
 asr=urlsplit(args.asr_url)
 if origin.scheme not in ('http','https') or not origin.hostname or origin.username or origin.password or origin.path or origin.query or origin.fragment:raise ValueError('Service origin required')
 if asr.scheme not in ('http','https') or asr.hostname not in ('127.0.0.1','localhost','::1') or asr.username or asr.password or asr.path or asr.query or asr.fragment:raise ValueError('Loopback ASR origin required')
 if not model.is_file() or digest(model)!=args.model_sha256:raise ValueError('Verified model file and SHA256 required')
 ffmpeg=shutil.which(args.ffmpeg);ffprobe=shutil.which(args.ffprobe)
 if not ffmpeg or not ffprobe:raise ValueError('FFmpeg and FFprobe executables required')
 data.mkdir(parents=True,exist_ok=True,mode=0o700)
 for folder in ['state','models','metadata/v1','video','audio','transcripts','tmp','logs']:safe(data/folder).mkdir(parents=True,exist_ok=True,mode=0o700)
 token=safe(data/'state/api-token')
 if not token.exists():
  with token.open('x') as f:os.chmod(token,0o600);f.write(secrets.token_urlsafe(48)+'\n');f.flush();os.fsync(f.fileno())
 if not token.is_file() or token.stat().st_mode&0o077 or token.stat().st_uid!=os.getuid():raise ValueError('Private owned token file required')
 target=safe(data/'models'/model.name)
 if target.exists():
  if digest(target)!=args.model_sha256:raise ValueError('Existing model differs; retained')
 elif target!=model:
  with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as part:
   temporary=Path(part.name)
   with model.open('rb') as source:shutil.copyfileobj(source,part)
  if digest(temporary)!=args.model_sha256:temporary.unlink();raise ValueError('Model changed during copy')
  temporary.replace(target)
 fingerprint=hashlib.sha256((args.model_sha256+'whisper_cpp:auto:temperature=0.0').encode()).hexdigest()
 config={'bind':args.bind,'base_url':args.base_url or f'http://{args.bind}:{args.port}','generic_port':args.port,'generic_ffmpeg':ffmpeg,'generic_ffprobe':ffprobe,'asr_fingerprint':fingerprint,'output_fingerprint':fingerprint,'model':{'name':args.model_name,'path':str(target),'source':'https://github.com/ggml-org/whisper.cpp','sha256':args.model_sha256},'versions':{},'providers':{'source':{'name':'f2'},'asr':{'name':'whisper_cpp','options':{'base_url':args.asr_url}}},'translation':{'enabled':False}}
 if args.translation_model_dir:
  directory=safe(args.translation_model_dir)
  if not directory.is_absolute() or not args.translation_python or not args.translation_sha256:raise ValueError('Translation directory, Python and verified model SHA256 required')
  if digest(safe(directory/'model.safetensors'))!=args.translation_sha256:raise ValueError('Translation model SHA256 mismatch')
  trpython=safe(args.translation_python) if not args.translation_python.is_symlink() else args.translation_python.resolve()
  if not trpython.is_absolute() or not trpython.is_file():raise ValueError('Translation Python required')
  hashes={p.name:digest(safe(p)) for p in directory.iterdir() if p.is_file() and p.suffix in ('.json','.safetensors','.jinja','.txt')}
  config['translation']={'enabled':True,'source_language':'en','target_language':'zh','model':'Qwen3-4B-Instruct-2507 4bit MLX','source':'https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit','revision':'50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b','sha256':args.translation_sha256,'file_hashes':hashes,'model_directory':str(directory),'python':str(trpython),'script':str(ROOT/'shared/translate_segments_mlx.py'),'quality_revision':3}
  config['output_fingerprint']=hashlib.sha256((fingerprint+json.dumps(config['translation'],sort_keys=True)).encode()).hexdigest()
 path=safe(data/'state/config.json')
 if not path.exists():
  with path.open('x') as f:os.chmod(path,0o600);json.dump(config,f,indent=2);f.flush();os.fsync(f.fileno())
 else:
  previous=json.loads(path.read_text())
  if path.stat().st_mode&0o077 or path.stat().st_uid!=os.getuid():raise ValueError('Private owned config required')
  if previous!=config:raise ValueError('Existing configuration differs; retained. Use a separate data directory or review configuration explicitly')
 return {'status':'initialized','data':str(data),'config':str(path),'token_file':str(token),'translation':'enabled' if config['translation']['enabled'] else 'not configured'}

def application(data,config=None):
 data=safe(data);config=safe(config or data/'state/config.json');settings=json.loads(config.read_text())
 if config.stat().st_mode&0o077 or config.stat().st_uid!=os.getuid():raise ValueError('Private owned configuration required')
 if digest(safe(settings['model']['path']))!=settings['model']['sha256']:raise ValueError('ASR model file hash mismatch')
 token=safe(data/'state/api-token')
 if not token.is_file() or token.stat().st_mode&0o077 or token.stat().st_uid!=os.getuid():raise ValueError('Private owned token file required')
 os.environ['DOUYIN2TEXT_DATA_DIR']=str(data);os.environ['DOUYIN2TEXT_CONFIG']=str(config)
 if settings.get('translation',{}).get('enabled'):
  directory=safe(settings['translation']['model_directory'])
  for name,sha in settings['translation']['file_hashes'].items():
   if '/' in name or name in ('.','..') or digest(safe(directory/name))!=sha:raise ValueError('Translation model files changed')
  os.environ['WIKI_TRANSLATION_MODEL_DIR']=str(directory)
 sys.path.insert(0,str(ROOT/'backend/src'));sys.path.insert(0,str(ROOT))
 from douyin2text import api
 from generic_media import register
 register(api)
 return api.app,settings

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['init','serve']);p.add_argument('--data',type=Path,required=True);p.add_argument('--config',type=Path);p.add_argument('--model-file',type=Path);p.add_argument('--model-sha256');p.add_argument('--model-name',default='medium');p.add_argument('--bind',default='127.0.0.1');p.add_argument('--base-url');p.add_argument('--port',type=int,default=8765);p.add_argument('--asr-url',default='http://127.0.0.1:8767');p.add_argument('--ffmpeg',default='ffmpeg');p.add_argument('--ffprobe',default='ffprobe');p.add_argument('--translation-model-dir',type=Path);p.add_argument('--translation-sha256');p.add_argument('--translation-python',type=Path);a=p.parse_args()
 if a.command=='init':print(json.dumps(initialize(a)));return
 app,settings=application(a.data,a.config)
 import uvicorn
 os.umask(0o077);uvicorn.run(app,host=settings['bind'],port=settings.get('generic_port',8765),workers=1,access_log=False)
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'status':'error','message':str(e)}),file=sys.stderr);raise SystemExit(1)
