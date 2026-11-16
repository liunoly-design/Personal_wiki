"""Opt-in public HTTP acceptance; does not start/stop services or disclose credentials.

Run against an isolated Mini gateway, supplying an explicitly selected audio file.
A restart between runs verifies durable identity and artifact reuse.
"""
import argparse,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--token-file',type=Path,required=True);p.add_argument('--file',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
 stat=a.token_file.stat()
 if stat.st_mode&0o077:raise ValueError('Private token file required')
 token=a.token_file.read_text().strip();file=a.file.read_bytes();sha=hashlib.sha256(file).hexdigest()
 source={'platform':'file','id':sha,'url':'https://file.personal-wiki.invalid/'+sha,'asset_id':'original','title':'合成语音独立包验收'}
 body={'source':source,'file':{'sha256':sha,'bytes':len(file),'extension':a.file.suffix}}
 def request(path,method='GET',body=None,headers=None,authorize=True):
  h={'Authorization':'Bearer '+token} if authorize else {}
  h.update(headers or {});r=urllib.request.Request(a.url+path,data=body,method=method,headers=h)
  with urllib.request.urlopen(r,timeout=60) as response:return response.status,dict(response.headers),response.read()
 try:request('/v1/file-jobs',method='POST',body=json.dumps(body).encode(),headers={'Content-Type':'application/json'},authorize=False);raise AssertionError('Unauthenticated submit accepted')
 except urllib.error.HTTPError as e:assert e.code==401,e.code
 headers={'Content-Type':'application/json','Idempotency-Key':'distribution-http-'+sha[:32]}
 first=json.loads(request('/v1/file-jobs','POST',json.dumps(body).encode(),headers)[2]);second=json.loads(request('/v1/file-jobs','POST',json.dumps(body).encode(),headers)[2]);assert first['job_id']==second['job_id'] and second['reused'] is True
 jid=first['job_id']
 if first['status']=='waiting_upload':request('/v1/file-jobs/'+jid+'/content','PUT',file,{'Content-Type':'application/octet-stream','Content-Length':str(len(file))})
 for _ in range(300):
  job=json.loads(request('/v1/jobs/'+jid)[2])
  if job['status']=='succeeded':break
  if job['status'] in ('failed','partial_failed','waiting_confirmation'):raise AssertionError(job['status'])
  time.sleep(2)
 else:raise AssertionError('Transcription did not complete')
 manifest=json.loads(request('/v1/file-jobs/'+jid+'/manifest')[2]);markdown=request('/v1/file-jobs/'+jid+'/markdown')[2]
 assert hashlib.sha256(markdown).hexdigest()==manifest['markdown']['sha256'];assert manifest['verification']['input_sha256']==sha
 status,h,data=request('/v1/file-media/'+jid+'/original',headers={'Range':'bytes=0-15'});assert status==206 and data==file[:16]
 receipt={'status':'passed','job_id':jid,'markdown_sha256':manifest['markdown']['sha256'],'segments':len(manifest['segments']),'reused':first['reused'],'authentication':True,'duplicate_identity':True,'range':True,'hashes':True}
 if a.receipt.exists():
  previous=json.loads(a.receipt.read_text());assert previous['job_id']==jid and previous['markdown_sha256']==receipt['markdown_sha256'];receipt['restart_reuse_verified']=True
 a.receipt.write_text(json.dumps(receipt,indent=2)+'\n');a.receipt.chmod(0o600);print(json.dumps(receipt))
if __name__=='__main__':main()
