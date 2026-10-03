import hashlib, json, pathlib, subprocess, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]

class TopicStoreTest(unittest.TestCase):
 def call(self, vault, operation, **fields):
  request = dict(vault=str(vault), operation=operation, scope='a'*64, discussionId='D-'+'b'*16, **fields)
  p = subprocess.run(['python3', str(ROOT/'scripts/review_store.py')], input=json.dumps(request), text=True, capture_output=True)
  if p.returncode: raise RuntimeError(p.stderr)
  return json.loads(p.stdout)
 def append(self, v, key, content, cursor=1, **fields):
  return self.call(v, 'topic-append', key=key*64, content=content, cursor=cursor, **fields)
 def finish(self, v, key, result):
  return self.call(v, 'topic-finalize', key=key*64, hash=result['hash'])
 def test_history_manual_text_idempotency_pending_and_new_record(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);one=self.append(v,'c','old dated view');self.finish(v,'c',one)
   target=v/one['path'];target.write_text(target.read_text()+'\n手写保留\n');old=target.read_bytes()
   two=self.append(v,'d','new conflicting view',2);self.assertEqual(two['path'],one['path']);self.assertTrue(target.read_bytes().startswith(old))
   self.assertEqual((v/two['history']/'before.md').read_bytes(),old)
   with self.assertRaisesRegex(RuntimeError,'尚未核验'):self.append(v,'e','third view',3)
   self.assertEqual(self.append(v,'d','new conflicting view',2),two);self.finish(v,'d',two)
   self.assertEqual(target.read_text().count('new conflicting view'),1)
   with self.assertRaisesRegex(RuntimeError,'request changed'):self.append(v,'d','changed',2)
   new=self.append(v,'e','new document',2,newRecord=True);self.finish(v,'e',new);self.assertNotEqual(new['path'],two['path']);self.assertTrue(target.read_bytes().startswith(old))
   self.assertEqual(self.call(v,'topic-info')['path'],new['path'])
 def test_editor_after_publish_and_late_displaced_inode_are_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);one=self.append(v,'c','first');self.finish(v,'c',one);target=v/one['path']
   with target.open('ab') as editor:
    two=self.append(v,'d','second',2);editor.write(b'late edit');editor.flush()
   with self.assertRaisesRegex(RuntimeError,'Concurrent edit'):self.finish(v,'d',two)
   self.assertIn(b'late edit',(v/two['history']/'displaced.md').read_bytes())
   target.write_text('new concurrent file')
   with self.assertRaisesRegex(RuntimeError,'Concurrent'):self.append(v,'d','second',2)
   self.assertEqual(target.read_text(),'new concurrent file')
 def test_process_kill_after_move_recovers_and_missing_binding_refuses(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);one=self.append(v,'c','first');self.finish(v,'c',one)
   request=dict(vault=d, operation='topic-append',scope='a'*64,discussionId='D-'+'b'*16,key='d'*64,content='second',cursor=2)
   program='''import json,os,signal,sys
sys.path.insert(0,sys.argv[1])
from protected_store import Root
from review_store import append_topic
r=json.loads(sys.argv[2]);root=Root(r['vault']);lock=root.lock();original=Root.put
def kill(self,path,data,replace=False):
 if path.startswith('wiki/topics/'):os.kill(os.getpid(),signal.SIGKILL)
 return original(self,path,data,replace)
Root.put=kill
append_topic(root,r)
'''
   child=subprocess.run(['python3','-c',program,str(ROOT/'scripts'),json.dumps(request)],capture_output=True);self.assertEqual(child.returncode,-9)
   self.assertFalse((v/one['path']).exists());two=self.append(v,'d','second',2);self.finish(v,'d',two)
   self.assertEqual((v/two['path']).read_text().count('second'),1);(v/two['path']).unlink()
   with self.assertRaisesRegex(RuntimeError,'missing'):self.append(v,'e','third',3)
 def test_legacy_path_retained_and_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);p=v/'wiki/topics/discussion-cccccccccccccccc.md';p.parent.mkdir(parents=True);p.write_text('legacy old judgment')
   r=self.append(v,'d','additional',2,legacyPath=str(p.relative_to(v)));self.assertEqual(r['path'],str(p.relative_to(v)));self.finish(v,'d',r)
   self.assertTrue(p.read_text().startswith('legacy old judgment'));p.unlink();p.symlink_to(v/'.personal-wiki/protected.lock')
   with self.assertRaises(RuntimeError):self.append(v,'e','cannot replace',3)
 def test_quoted_reply_unknown_completion_reconciles_after_later_conclusion_advances_cursor(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);first=self.append(v,'c','first',1);self.finish(v,'c',first)
   fields=dict(key='d'*64,message=dict(message_id='om_reply',body=dict(content='original')),text='original',savedAt='2026-10-03T00:00:00Z')
   quote=self.call(v,'quoted-reply',**fields);self.finish(v,'d',quote)
   second=self.append(v,'e','second',2);self.finish(v,'e',second)
   replay=self.call(v,'quoted-reply',**fields);self.assertEqual(replay['path'],quote['path']);self.assertEqual(replay['hash'],second['hash']);self.finish(v,'d',replay)
   self.assertEqual((v/quote['path']).read_text().count('## 原回复正文'),1);self.assertEqual(self.call(v,'topic-info')['cursor'],2)
