"""Versioned additive deployment; preserves the active gateway and its config.

Run on Mini after copying this directory. Requires the expected release ID;
activation refuses a busy queue and never modifies an existing release.
"""
import argparse,hashlib,json,os,shutil,sqlite3,time,signal
from pathlib import Path

def deploy(service,expected,activate=False):
 active=service/'active-release.json';prior=json.loads(active.read_text())
 if prior['release_id']!=expected:raise RuntimeError('Active release changed; inspect before deploy')
 base=Path(prior['release']);extension=Path(__file__).with_name('generic_media.py');body=extension.read_bytes();translator=extension.with_name('translate_generic.py');translation_body=translator.read_bytes();policy=extension.with_name('transcript-identifiers.json');policy_body=policy.read_bytes();json.loads(policy_body)
 release_id='0.8.0-file-'+hashlib.sha256(body+translation_body+policy_body).hexdigest()[:12];target=service/'releases'/release_id
 gateway=(base/'gateway.py').read_text()
 anchor='import ai_articles\n'
 if gateway.count(anchor)!=1:raise RuntimeError('Unknown gateway integration point')
 if 'register_file_media(api,ai_articles)' not in gateway:gateway=gateway.replace(anchor,anchor+"sys.path.insert(0,str(RELEASE))\nfrom generic_media import register as register_file_media\nregister_file_media(api,ai_articles)\n")
 compile(body,str(extension),'exec');compile(translation_body,str(translator),'exec');compile(gateway,'gateway.py','exec')
 if not target.exists():
  shutil.copytree(base,target)
  (target/'generic_media.py').write_bytes(body);(target/'translate_generic.py').write_bytes(translation_body);(target/'transcript-identifiers.json').write_bytes(policy_body);(target/'gateway.py').write_text(gateway)
  meta=json.loads((target/'release.json').read_text());meta.update(version='0.8.0',release_id=release_id,build_sha256=hashlib.sha256(body+translation_body+policy_body+gateway.encode()).hexdigest(),generic_base_release=expected)
  (target/'release.json').write_text(json.dumps(meta,indent=2)+'\n')
 elif (target/'generic_media.py').read_bytes()!=body or (target/'translate_generic.py').read_bytes()!=translation_body or (target/'transcript-identifiers.json').read_bytes()!=policy_body or (target/'gateway.py').read_text()!=gateway:raise RuntimeError('Release collision')
 if activate:
  data=Path(os.environ.get('DOUYIN2TEXT_DATA_DIR','/Users/mac/Documents/Personal-Wiki-Media'))
  c=sqlite3.connect((data/'state/v1.sqlite3').as_uri()+'?mode=ro',uri=True)
  try:busy=c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','downloading','extracting','transcribing')").fetchone()[0]
  finally:c.close()
  if busy:raise RuntimeError('Queue busy; retry after existing work finishes')
  backup=data/'state'/'backups'/('before-'+release_id+'-'+str(int(time.time())));backup.mkdir(parents=True,mode=0o700)
  shutil.copy2(service/'api_v1.py',backup/'api_v1.py');shutil.copy2(active,backup/'active-release.json')
  c=sqlite3.connect(data/'state/v1.sqlite3');dest=sqlite3.connect(backup/'v1.sqlite3')
  try:c.backup(dest)
  finally:c.close();dest.close()
  for path,value in [(service/'api_v1.py',f'import runpy\nrunpy.run_path({str(target / "gateway.py")!r},run_name="__main__")\n'),(active,json.dumps({'release':str(target),'release_id':release_id,'previous_release_id':expected,'backup':str(backup)},indent=2)+'\n')]:
   temporary=path.with_suffix('.deploy-part');temporary.write_text(value);temporary.chmod(0o600);temporary.replace(path)
 return {'release_id':release_id,'path':str(target),'activated':activate}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--service-dir',type=Path,required=True);p.add_argument('--expected-release',required=True);p.add_argument('--activate',action='store_true');a=p.parse_args();print(json.dumps(deploy(a.service_dir,a.expected_release,a.activate)))
