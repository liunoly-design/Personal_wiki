"""Pinned upstream app bootstrap. Never rewrites app-state or bypasses macOS security."""
import argparse,hashlib,json,os,plistlib,shutil,tarfile,tempfile,urllib.request
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parent

def safe(path):
 p=Path(path).absolute()
 for part in [p,*p.parents]:
  if part.is_symlink():raise ValueError('Symlink installation path refused')
 return p

def install(a):
 manifest=json.loads(Path(a.manifest or (ROOT/'upstream-nashsu.json' if (ROOT/'upstream-nashsu.json').is_file() else ROOT.parent/'upstream-nashsu.json')).read_text())
 url=manifest['asset'];sha=manifest['downloaded_sha256'];tag=manifest['tag']
 expected='https://github.com/nashsu/llm_wiki/releases/download/'+tag+'/LLM.Wiki_aarch64.app.tar.gz'
 if url!=expected or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid upstream pin')
 destination=safe(a.destination);destination.mkdir(parents=True,exist_ok=True)
 target=safe(destination/'LLM Wiki.app')
 if target.exists():raise ValueError('Existing application retained; choose an empty destination for upgrade review')
 with tempfile.TemporaryDirectory(prefix='.llm-wiki-',dir=destination) as temporary:
  stage=Path(temporary);archive=Path(a.archive) if a.archive else stage/'upstream.tar.gz'
  if not a.archive:
   with urllib.request.urlopen(url,timeout=60) as response,archive.open('xb') as out:
    size=0
    while True:
     chunk=response.read(1024*1024)
     if not chunk:break
     size+=len(chunk)
     if size>1024*1024*1024:raise ValueError('Archive exceeds 1 GB')
     out.write(chunk)
  h=hashlib.sha256()
  with archive.open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  if h.hexdigest()!=sha:raise ValueError('Upstream archive SHA256 mismatch')
  extracted=stage/'app';extracted.mkdir()
  with tarfile.open(archive) as bundle:
   total=0
   for member in bundle:
    path=PurePosixPath(member.name)
    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0]!='LLM Wiki.app':raise ValueError('Unsafe archive path')
    total+=member.size
    if total>2*1024**3 or not(member.isdir() or member.isfile()):raise ValueError('Unsafe archive type or size')
    target_file=extracted.joinpath(*path.parts)
    if member.isdir():target_file.mkdir(parents=True,exist_ok=True)
    else:
     target_file.parent.mkdir(parents=True,exist_ok=True)
     with bundle.extractfile(member) as src,target_file.open('xb') as out:shutil.copyfileobj(src,out)
     target_file.chmod(member.mode&0o755)
  app=extracted/'LLM Wiki.app';info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
  if info.get('CFBundleIdentifier')!='com.llmwiki.app' or info.get('CFBundleShortVersionString')!=tag.removeprefix('v'):raise ValueError('Application identity differs from pinned release')
  app.rename(target)
 return {'status':'installed','application':str(target),'version':tag,'sha256':sha,'custom_manifest':bool(a.manifest),'next':'Open the app normally, configure project and API; see installation guide. No app-state was changed.'}

def doctor(a):
 state=json.loads(safe(a.state).read_text());vault=safe(a.vault).resolve()
 projects=[(key,p) for key,p in state.get('projectRegistry',{}).items() if Path(p['path']).resolve()==vault]
 if len(projects)!=1:raise ValueError('Register exactly one target Vault in LLM Wiki')
 key,_=projects[0]
 checks={'registered':True,'api_enabled':state.get('apiConfig',{}).get('enabled') is True,'duplicate_auto_ingest_disabled':state.get('sourceWatchConfig',{}).get(key,{}).get('autoIngest') is False,'vector_search_disabled':state.get('embeddingConfig',{}).get('enabled') is not True}
 return {'status':'ready' if all(checks.values()) else 'needs_configuration','vault':str(vault),'project_id':key,'checks':checks,'next':'Use installed wiki-bridge doctor for live API/model validation. Tokens are never printed.'}

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 i=sub.add_parser('install');i.add_argument('--archive');i.add_argument('--manifest');i.add_argument('--destination',default=str(Path.home()/'Applications'))
 d=sub.add_parser('doctor');d.add_argument('--state',default=str(Path.home()/'Library/Application Support/com.llmwiki.app/app-state.json'));d.add_argument('--vault',required=True)
 a=p.parse_args();print(json.dumps(install(a) if a.command=='install' else doctor(a)))
if __name__=='__main__':
 try:main()
 except Exception as error:print(json.dumps({'status':'error','message':str(error)}));raise SystemExit(1)
