"""Build deterministic distributions from explicit code roots, excluding all runtime data."""
import argparse,gzip,hashlib,json,re,subprocess,tarfile,tempfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
COMPONENTS=('cli','wiki-bridge','mini-media','llm-wiki-setup')

def inventory(component):
 if component=='mini-media':return ['services/mini-media'],['distribution/install-mini.py','distribution/native-whisper.py','upstream-nashsu.json']
 if component=='llm-wiki-setup':return ['config/examples'],['distribution/llm-wiki-setup.py','upstream-nashsu.json']
 return ['src','vendor/nashsu','config/examples'],['services/mini-media/transcript-identifiers.json','package.json','requirements-capture.txt','upstream-nashsu.json','.agents/skills/personal-wiki/SKILL.md','docs/contracts/ingestion-cli.md','distribution/pwiki-setup.py']

def build(component,version,output,allow_dirty=False):
 if component not in COMPONENTS:raise ValueError('Invalid component')
 if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?',version):raise ValueError('Invalid release version')
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
 if dirty and not allow_dirty:raise ValueError('Commit source before producing a release')
 output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
 tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))
 name=f'personal-wiki-{component}-{version}'
 with tempfile.TemporaryDirectory() as tmp:
  stage=Path(tmp)/name;stage.mkdir();core=stage/'runtime';core.mkdir()
  roots,paths=inventory(component);files=[ROOT/p for p in paths]
  files.extend(p for d in roots for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc',))
  if component in ('cli','wiki-bridge'):
   files.extend(p for p in (ROOT/'scripts').iterdir() if p.is_file() and (p.suffix in ('.py','.swift') or p.name in ('wiki.mjs','wiki-bridge.mjs','maintain-ingestion.mjs','media-service.mjs')))
  for source in sorted(set(files)):
   if source.relative_to(ROOT).as_posix() not in tracked:continue
   if source.is_symlink() or any(p.is_symlink() for p in source.parents if p!=ROOT.parent):raise ValueError('Source symlink rejected')
   relative=source.relative_to(ROOT);target=core/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
  if component in ('cli','wiki-bridge'):
   for entry in ['install.mjs','manage.mjs']:shutil.copyfile(ROOT/'distribution'/entry,stage/entry)
  elif component=='mini-media':shutil.copyfile(ROOT/'distribution/install-mini.py',stage/'install.py')
  else:
   shutil.copyfile(ROOT/'distribution/llm-wiki-setup.py',stage/'llm-wiki-setup.py');shutil.copyfile(ROOT/'upstream-nashsu.json',stage/'upstream-nashsu.json')
  for doc in ['independent-install.md','llm-wiki-install.md']:
   shutil.copyfile(ROOT/'docs'/doc,stage/doc)
  manifest={'component':component,'version':version,'revision':revision,'source_dirty':dirty,'files':{p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}}
  (stage/'distribution.json').write_text(json.dumps(manifest,indent=2)+'\n')
  target=output/(name+'.tar.gz')
  if target.exists():raise ValueError('Release archive already exists')
  with target.open('xb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as archive:
   archive.add(stage,arcname=name,filter=normalize)
  checksum=hashlib.sha256(target.read_bytes()).hexdigest();(output/(target.name+'.sha256')).write_text(checksum+'  '+target.name+'\n')
 return {'archive':str(target),'sha256':checksum,'component':component,'source_dirty':dirty}

def normalize(info):
 info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.mode=0o755 if info.isdir() else 0o644;return info
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--component',choices=COMPONENTS,required=True);p.add_argument('--version',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-dirty',action='store_true');a=p.parse_args();print(json.dumps(build(a.component,a.version,a.output,a.allow_dirty)))
