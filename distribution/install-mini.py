"""Independent source installer; models, credentials and state stay outside releases."""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,uuid,plistlib
from pathlib import Path

def safe(path):
 p=Path(path).absolute()
 for part in [p,*p.parents]:
  if part.is_symlink():raise ValueError('Symlink installation path refused')
 return p

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def install(a):
 package=Path(__file__).resolve().parent;manifest=json.loads((package/'distribution.json').read_text())
 if manifest['component']!='mini-media':raise ValueError('Mini distribution required')
 for path,sha in manifest['files'].items():
  if Path(path).is_absolute() or any(s in ('','.','..') for s in path.split('/')):raise ValueError('Unsafe distribution path')
  source=safe(package/path)
  if not source.is_file() or digest(source)!=sha:raise ValueError('Distribution integrity mismatch')
 prefix=safe(a.prefix);prefix.mkdir(parents=True,exist_ok=True,mode=0o700)
 identity=prefix/'.installation.json';owner={'component':'mini-media','prefix':str(prefix)}
 if identity.exists() and json.loads(identity.read_text())!=owner:raise ValueError('Installation identity conflict')
 identity.write_text(json.dumps(owner)+'\n');identity.chmod(0o600)
 version=manifest['version']+'-'+hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()[:16]
 releases=safe(prefix/'releases');releases.mkdir(exist_ok=True,mode=0o700);release=safe(releases/version)
 if not release.exists():
  with tempfile.TemporaryDirectory(prefix='.install-',dir=releases) as temp:
   stage=Path(temp)/'runtime';stage.mkdir()
   for path in manifest['files']:
    if path.startswith('runtime/'):
     target=stage/path[8:];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(package/path,target)
   (stage/'.distribution.json').write_text(json.dumps(manifest));stage.rename(release)
 for path,sha in manifest['files'].items():
  if path.startswith('runtime/') and digest(safe(release/path[8:]))!=sha:raise ValueError('Installed runtime differs; retained')
 python=Path(a.python).absolute();subprocess.run([str(python),'-c','import sys;assert sys.version_info >= (3,11)'],check=True)
 venv=safe(prefix/'venv')
 if not a.skip_dependencies:
  if not venv.exists():subprocess.run([str(python),'-m','venv',str(venv)],check=True)
  subprocess.run([str(venv/'bin/python'),'-m','pip','install','-r',str(release/'services/mini-media/requirements-f2.txt')],check=True,stdout=sys.stderr)
  python=venv/'bin/python'
 else:subprocess.run([str(python),'-c','import fastapi,uvicorn,httpx,psutil'],check=True)
 data=safe(prefix/'data');data.mkdir(exist_ok=True,mode=0o700);bin_dir=safe(prefix/'bin');bin_dir.mkdir(exist_ok=True,mode=0o700)
 from shlex import quote
 launcher=bin_dir/'personal-wiki-media';body=f'#!/bin/sh\nexec {quote(str(python))} {quote(str(prefix/"current/services/mini-media/gateway.py"))} "$@" --data {quote(str(data))}\n'
 if launcher.exists() and launcher.read_text()!=body:raise ValueError('Existing launcher differs; retained')
 launcher.write_text(body);launcher.chmod(0o700)
 current=prefix/'current'
 if current.exists() and not current.is_symlink():raise ValueError('Current must be installer symlink')
 temporary=prefix/('.current-'+uuid.uuid4().hex);temporary.symlink_to(release);temporary.replace(current)
 return {'status':'installed','prefix':str(prefix),'command':str(launcher),'data':str(data),'python':str(python),'next':'Run init with verified model, then serve. ASR server and English translator are separate prerequisites; see guide.'}

def lifecycle(a):
 prefix=safe(a.prefix);owner=json.loads((prefix/'.installation.json').read_text())
 if owner!={'component':'mini-media','prefix':str(prefix)}:raise ValueError('Installation identity mismatch')
 launcher=prefix/'bin/personal-wiki-media';plist=safe(Path.home()/'Library/LaunchAgents/com.personal-wiki.distribution.mini-media.plist')
 body={'Label':'com.personal-wiki.distribution.mini-media','ProgramArguments':[str(launcher),'serve'],'KeepAlive':True,'RunAtLoad':True,'StandardOutPath':str(prefix/'data/logs/service.log'),'StandardErrorPath':str(prefix/'data/logs/error.log')}
 if a.action=='worker-install':
  if sys.platform!='darwin':raise ValueError('launchd requires macOS')
  if plist.exists() and plistlib.loads(plist.read_bytes())!=body:raise ValueError('Another installation owns this worker')
  plist.parent.mkdir(parents=True,exist_ok=True);plist.write_bytes(plistlib.dumps(body));plist.chmod(0o600);running=subprocess.run(['/bin/launchctl','print','gui/'+str(os.getuid())+'/'+body['Label']],capture_output=True).returncode==0
  if not running:subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(plist)],check=True)
 else:
  if plist.exists():
   if plistlib.loads(plist.read_bytes())!=body:raise ValueError('Another installation owns this worker')
   subprocess.run(['/bin/launchctl','bootout','gui/'+str(os.getuid()),str(plist)],capture_output=True);plist.unlink()
  if a.action=='uninstall' and launcher.exists():
   safe(launcher)
   if str(prefix/'current/services/mini-media/gateway.py') not in launcher.read_text():raise ValueError('Edited launcher retained')
   launcher.unlink()
 return {'status':'ok','action':a.action,'retained':'data, models, configuration, releases and venv'}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--prefix',required=True);p.add_argument('--python',default=sys.executable);p.add_argument('--skip-dependencies',action='store_true',help='Use explicitly supplied Python with installed dependencies');p.add_argument('--action',choices=['install','worker-install','worker-uninstall','uninstall'],default='install');a=p.parse_args()
 try:
  if not Path(a.prefix).is_absolute():raise ValueError('Absolute prefix required')
  print(json.dumps(install(a) if a.action=='install' else lifecycle(a)))
 except Exception as e:print(json.dumps({'status':'error','message':str(e)}),file=sys.stderr);raise SystemExit(1)
