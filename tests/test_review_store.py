import unittest, tempfile, pathlib, json, subprocess, hashlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ReviewStoreTest(unittest.TestCase):
 def call(self, vault, operation, **fields):
  if operation=='apply' and 'metadataHash' not in fields:
   metadata=vault/f'.personal-wiki/review-proposals/{fields["id"]}.json'
   fields['metadataHash']=hashlib.sha256(metadata.read_bytes()).hexdigest() if metadata.exists() else None
  p=subprocess.run(['python3',str(ROOT/'scripts/review_store.py')],input=json.dumps(dict(vault=str(vault),operation=operation,**fields)),text=True,capture_output=True)
  if p.returncode: raise RuntimeError(p.stderr)
  return json.loads(p.stdout)
 def test_explicit_application_preserves_original_and_baseline_then_repeats_without_appending(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);(v/'wiki/queries').mkdir(parents=True);(v/'wiki/concepts').mkdir();(v/'raw/sources').mkdir(parents=True)
   raw=v/'raw/sources/original.md';raw.write_bytes(b'original')
   old=b'# Existing\n\nHandwritten KEEP\n';target=v/'wiki/concepts/test.md';target.write_bytes(old)
   rid='a'*16;file=f'wiki/queries/review-{rid}.md';proposal='# Proposal\nNew sourced view';(v/file).write_text(proposal)
   (v/'.personal-wiki/review-proposals').mkdir(parents=True)
   meta=dict(id=rid,path='wiki/concepts/test.md',previousHash=hashlib.sha256(old).hexdigest(),candidate='New sourced view',sourceUrl='https://example.test',sourceId='b'*20,proposalHash=hashlib.sha256(proposal.encode()).hexdigest())
   (v/f'.personal-wiki/review-proposals/{rid}.json').write_text(json.dumps(meta))
   found=self.call(v,'list');self.assertEqual(found['reviews'][0]['id'],rid)
   result=self.call(v,'apply',id=rid,proposalHash=meta['proposalHash']);self.assertEqual(result['status'],'verification_pending');self.assertTrue(target.read_bytes().startswith(old));self.assertEqual(raw.read_bytes(),b'original')
   content=target.read_bytes();self.call(v,'apply',id=rid,proposalHash=meta['proposalHash']);self.assertEqual(target.read_bytes(),content)
   self.assertEqual((v/f'.personal-wiki/review-actions/{rid}/before.md').read_bytes(),old)
 def sample(self, v):
  (v/'wiki/queries').mkdir(parents=True);(v/'wiki/concepts').mkdir();(v/'.personal-wiki/review-proposals').mkdir(parents=True)
  rid='c'*16; old=b'# Handwritten\nKEEP\n'; target=v/'wiki/concepts/test.md';target.write_bytes(old)
  body='proposed evidence\nNew perspective';(v/f'wiki/queries/review-{rid}.md').write_text(body)
  h=hashlib.sha256(body.encode()).hexdigest();m=dict(id=rid,path='wiki/concepts/test.md',previousHash=hashlib.sha256(old).hexdigest(),candidate='New perspective',sourceUrl='https://example.test',sourceId='d'*20,proposalHash=h)
  (v/f'.personal-wiki/review-proposals/{rid}.json').write_text(json.dumps(m));return rid,h,target,old
 def test_stale_and_changed_proposal_and_symlink_refuse_without_overwriting(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);rid,h,target,old=self.sample(v);target.write_text('manual change')
   with self.assertRaisesRegex(RuntimeError,'Stale'):self.call(v,'apply',id=rid,proposalHash=h)
   self.assertEqual(target.read_text(),'manual change');target.write_bytes(old)
   (v/f'wiki/queries/review-{rid}.md').write_text('changed proposal')
   with self.assertRaisesRegex(RuntimeError,'Proposal changed'):self.call(v,'apply',id=rid,proposalHash=h)
   target.unlink();target.symlink_to(v/f'wiki/queries/review-{rid}.md')
   with self.assertRaises(RuntimeError):self.call(v,'apply',id=rid,proposalHash=hashlib.sha256(b'changed proposal').hexdigest())
 def test_interrupted_move_recovers_and_concurrent_new_target_is_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);rid,h,target,old=self.sample(v);first=self.call(v,'apply',id=rid,proposalHash=h);output=target.read_bytes();target.unlink()
   second=self.call(v,'apply',id=rid,proposalHash=h);self.assertEqual(target.read_bytes(),output);self.assertEqual(first,second)
   target.write_text('new manual content')
   with self.assertRaisesRegex(RuntimeError,'Concurrent'):self.call(v,'apply',id=rid,proposalHash=h)
   self.assertEqual(target.read_text(),'new manual content')
   with self.assertRaisesRegex(RuntimeError,'changed before verification'):self.call(v,'finalize',id=rid,hash=first['hash'])
 def test_late_edit_through_displaced_inode_is_preserved_and_not_finalized(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);rid,h,target,old=self.sample(v)
   with target.open('ab') as editor:
    result=self.call(v,'apply',id=rid,proposalHash=h);editor.write(b'late manual edit');editor.flush()
   with self.assertRaisesRegex(RuntimeError,'Concurrent edit'):self.call(v,'finalize',id=rid,hash=result['hash'])
   self.assertIn(b'late manual edit',(v/f'.personal-wiki/review-actions/{rid}/displaced.md').read_bytes())
 def test_legacy_and_raw_target_cannot_apply(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);rid,h,target,old=self.sample(v);meta=v/f'.personal-wiki/review-proposals/{rid}.json';m=json.loads(meta.read_text());m['path']='raw/sources/test.md';meta.write_text(json.dumps(m))
   with self.assertRaisesRegex(RuntimeError,'Missing safe baseline'):self.call(v,'apply',id=rid,proposalHash=h)
   meta.unlink()
   with self.assertRaisesRegex(RuntimeError,'Missing safe baseline'):self.call(v,'apply',id=rid,proposalHash=h)
   self.assertEqual(target.read_bytes(),old)
 def test_process_sigkill_after_displacement_recovers_without_duplicate_or_lost_history(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);rid,h,target,old=self.sample(v);meta=v/f'.personal-wiki/review-proposals/{rid}.json'
   program='''import sys,json,os,signal
sys.path.insert(0,sys.argv[1])
from protected_store import Root,sha
from review_store import apply
root=Root(sys.argv[2]);lock=root.lock();original=Root.put
def killed(self,path,data,replace=False):
 if path=='wiki/concepts/test.md':os.kill(os.getpid(),signal.SIGKILL)
 return original(self,path,data,replace)
Root.put=killed
apply(root,dict(id=sys.argv[3],proposalHash=sys.argv[4],metadataHash=sha(open(sys.argv[5],'rb').read())))
'''
   child=subprocess.run(['python3','-c',program,str(ROOT/'scripts'),str(v),rid,h,str(meta)],capture_output=True)
   self.assertEqual(child.returncode,-9);self.assertFalse(target.exists())
   result=self.call(v,'apply',id=rid,proposalHash=h);self.assertTrue(target.read_bytes().startswith(old));self.assertEqual((v/f'.personal-wiki/review-actions/{rid}/before.md').read_bytes(),old)
   self.call(v,'finalize',id=rid,hash=result['hash']);content=target.read_bytes();self.call(v,'apply',id=rid,proposalHash=h);self.assertEqual(target.read_bytes(),content)
 def test_changed_hidden_metadata_cannot_reuse_displayed_approval(self):
  with tempfile.TemporaryDirectory() as d:
   v=pathlib.Path(d);rid,h,target,old=self.sample(v);meta=v/f'.personal-wiki/review-proposals/{rid}.json';approved=hashlib.sha256(meta.read_bytes()).hexdigest();data=json.loads(meta.read_text());data['sourceUrl']='https://changed.invalid';meta.write_text(json.dumps(data))
   with self.assertRaisesRegex(RuntimeError,'metadata changed'):self.call(v,'apply',id=rid,proposalHash=h,metadataHash=approved)
   self.assertEqual(target.read_bytes(),old)
