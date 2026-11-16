"""HTTP behavior; external ASR is the replaceable system boundary."""
import contextlib,hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI,HTTPException,Request
from fastapi.testclient import TestClient
from generic_media import register,coverage,immutable,chinese_delivery

class UploadTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name);self.db=self.data/'jobs.db'
  @contextlib.contextmanager
  def connect():
   c=sqlite3.connect(self.db);c.row_factory=sqlite3.Row
   try:
    with c:yield c
   finally:c.close()
  with connect() as c:
   c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,url TEXT,request_json TEXT,request_hash TEXT,config_hash TEXT,status TEXT,media_id TEXT,artifact_id TEXT,error TEXT,created REAL,updated REAL,stage TEXT)')
   c.execute('CREATE TABLE idempotency(key TEXT PRIMARY KEY,request_hash TEXT,job_id TEXT)')
  def fail(status,code,message,retryable=False):raise HTTPException(status,{'code':code})
  def auth(request:Request):
   if request.headers.get('authorization')!='Bearer test-secret':fail(401,'AUTH_REQUIRED','')
  def get(jid):
   with connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
   if not r:fail(404,'NOT_FOUND','')
   return dict(r)
  self.api=SimpleNamespace(app=FastAPI(),DATA=self.data,connect=connect,auth=auth,fail=fail,get=get,CONFIG={'asr_fingerprint':'model-a','output_fingerprint':'output-a'},process=None,evidence=None,snapshot=None)
  register(self.api)
  self.client=TestClient(self.api.app);self.headers={'Authorization':'Bearer test-secret','Idempotency-Key':'test-key'}
  self.content=b'synthetic original bytes'
  self.body={'source':{'platform':'file','id':hashlib.sha256(self.content).hexdigest(),'url':'https://file.personal-wiki.invalid/'+hashlib.sha256(self.content).hexdigest(),'asset_id':'original','title':'synthetic.wav'},'file':{'sha256':hashlib.sha256(self.content).hexdigest(),'bytes':len(self.content),'extension':'.wav'}}
 def tearDown(self):self.client.close();self.tmp.cleanup()
 def submit(self):return self.client.post('/v1/file-jobs',headers=self.headers,json=self.body)
 def test_authentication_and_hash_binding_before_queue(self):
  self.assertEqual(self.client.post('/v1/file-jobs',json=self.body).status_code,401)
  response=self.submit();self.assertEqual(response.status_code,202);jid=response.json()['job_id']
  self.assertEqual(response.json()['status'],'waiting_upload')
  bad=self.client.put('/v1/file-jobs/'+jid+'/content',headers=self.headers,content=b'bad')
  self.assertEqual(bad.status_code,422);self.assertEqual(self.api.get(jid)['status'],'waiting_upload')
  good=self.client.put('/v1/file-jobs/'+jid+'/content',headers=self.headers,content=self.content)
  self.assertEqual(good.status_code,200);self.assertEqual(self.api.get(jid)['status'],'queued')
  self.assertEqual(self.submit().json()['job_id'],jid)
  self.assertEqual(self.client.put('/v1/file-jobs/'+jid+'/content',headers=self.headers,content=self.content).status_code,200)
  self.assertEqual(next((self.data/'file-jobs'/jid).glob('source.*')).read_bytes(),self.content)
 def test_symlink_directory_cannot_write_outside_data(self):
  jid=self.submit().json()['job_id'];(self.data/'file-jobs').mkdir(exist_ok=True)
  with tempfile.TemporaryDirectory() as outside:
   (self.data/'file-jobs'/jid).symlink_to(outside,target_is_directory=True)
   r=self.client.put('/v1/file-jobs/'+jid+'/content',headers=self.headers,content=self.content)
   self.assertEqual(r.status_code,409);self.assertEqual(list(Path(outside).iterdir()),[])
 def test_upload_part_symlink_preserves_external_original(self):
  jid=self.submit().json()['job_id'];p=self.data/'file-jobs'/jid;p.mkdir(parents=True)
  with tempfile.TemporaryDirectory() as outside:
   original=Path(outside)/'human.wav';original.write_bytes(b'human original');(p/'upload.part').symlink_to(original)
   r=self.client.put('/v1/file-jobs/'+jid+'/content',headers=self.headers,content=self.content)
   self.assertEqual(r.status_code,409);self.assertEqual(original.read_bytes(),b'human original')
 def test_conflicts_limits_and_source_identity(self):
  self.assertEqual(self.submit().status_code,202)
  self.body['source']['title']='different';self.assertEqual(self.submit().status_code,409)
  self.body['file']['bytes']=1_000_000_001;self.assertEqual(self.submit().status_code,413)
  self.body['file']['bytes']=len(self.content);self.body['source']['url']='http://127.0.0.1/private'
  self.assertEqual(self.submit().status_code,400)
class ProofTests(unittest.TestCase):
 def test_empty_truncated_and_disordered_transcripts_are_rejected(self):
  for raw in [{}, {'text':'[Music]','segments':[{'start':0,'end':39,'text':'[Music]'}]}, {'text':'尾段','segments':[{'start':30,'end':40,'text':'尾段'}]}, {'text':'开头','segments':[{'start':0,'end':4,'text':'开头'}]}, {'text':'乱序','segments':[{'start':0,'end':18,'text':'一'},{'start':4,'end':20,'text':'二'}]}]:
   with self.assertRaises(ValueError):coverage(raw,40)
  self.assertTrue(coverage({'text':'完整','segments':[{'start':0,'end':39,'text':'完整'}]},40)['head_tail_verified'])
 def test_mixed_language_cannot_be_labelled_complete_chinese(self):
  with self.assertRaisesRegex(ValueError,'incomplete'):chinese_delivery([{'text':'中文开头。'},{'text':'This whole sentence has not been translated.'}])
  chinese_delivery([{'text':'完整中文，包括 AI 等技术标识。'}])
  original=[{'start':0,'end':1,'text':'中文。'},{'start':1,'end':2,'text':'ChatGPT'}];self.assertEqual(chinese_delivery(original,original)[0]['token'],'ChatGPT')
  with self.assertRaises(ValueError):chinese_delivery(original,[original[0],{'start':1,'end':2,'text':'AnotherWord'}])
  self.assertTrue(chinese_delivery([{'start':0,'end':2,'text':'用ChatGPT。'}],[{'start':0,'end':2,'text':'Use ChatGPT.'}]))
  phonetic=chinese_delivery([{'start':0,'end':2,'text':'它读作“fran-ja-pan”。'}],[{'start':0,'end':2,'text':'It is pronounced \"fran-ja-pan.\"'}]);self.assertEqual(phonetic[0]['kind'],'pronunciation')
 def test_immutable_artifact_replay_preserves_human_bytes(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'original.json';immutable(p,b'original');immutable(p,b'original')
   with self.assertRaises(ValueError):immutable(p,b'replacement')
   self.assertEqual(p.read_bytes(),b'original')
if __name__=='__main__':unittest.main()
