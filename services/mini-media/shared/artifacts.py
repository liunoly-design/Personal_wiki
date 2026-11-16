"""Local translation output utilities; original ASR is never changed."""
import hashlib,json,os,secrets
from pathlib import Path
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def atomic_json(path,value):
 path=Path(path);temporary=path.with_name(path.name+'.'+secrets.token_hex(8)+'.part')
 with temporary.open('x') as f:
  os.chmod(temporary,0o600);json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 temporary.replace(path)
