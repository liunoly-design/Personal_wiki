import json, subprocess, sys, tempfile, unittest
from pathlib import Path
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/import_capture.py'
class CaptureTest(unittest.TestCase):
 def test_concurrent_collection_produces_one_source(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);snap=root/'snapshot';snap.mkdir();(snap/'article.md').write_text('# Same source')
   args=[sys.executable,str(SCRIPT),'--vault',str(root/'vault'),'--snapshot',str(snap),'--message','小婕收集 https://x.com/example/status/123']
   jobs=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
   results=[]
   for job in jobs:
    out,err=job.communicate(timeout=10);self.assertEqual(job.returncode,0,err);results.append(json.loads(out))
   self.assertEqual({x['status'] for x in results},{'existing','archived'})
   self.assertEqual(len(list((root/'vault/raw/sources').glob('*.md'))),1)
 def test_duplicate_collection_keeps_original_and_local_media(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp); snap=root/'snapshot';snap.mkdir();(snap/'images').mkdir()
   (snap/'article.md').write_text('# 示例\n\n![图](images/a.png)\n')
   (snap/'raw.html').write_text('<article>原件</article>');(snap/'images/a.png').write_bytes(b'image')
   args=[sys.executable,str(SCRIPT),'--vault',str(root/'vault'),'--snapshot',str(snap),'--message','小婕收集 https://x.com/example/status/123?s=20']
   first=subprocess.run(args,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stderr)
   a=json.loads(first.stdout);self.assertEqual(a['status'],'archived')
   (snap/'raw.html').write_text('修改后的输入')
   second=subprocess.run(args,capture_output=True,text=True);self.assertEqual(second.returncode,0,second.stderr)
   b=json.loads(second.stdout);self.assertEqual(b['status'],'existing');self.assertEqual(a['id'],b['id'])
   self.assertEqual((Path(a['archive'])/'raw.html').read_text(),'<article>原件</article>')
   source=Path(a['source']);self.assertIn('../assets/',source.read_text())
   self.assertEqual(len(list((root/'vault/raw/sources').glob('*.md'))),1)
   (Path(a['archive'])/'images/a.png').unlink()
   damaged=subprocess.run(args,capture_output=True,text=True)
   self.assertNotEqual(damaged.returncode,0)
   self.assertIn('integrity',damaged.stderr)
 def test_refresh_preserves_old_snapshot_and_rejects_tampering(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);snap=root/'snapshot';snap.mkdir()
   (snap/'article.md').write_text('# First version')
   args=[sys.executable,str(SCRIPT),'--vault',str(root/'vault'),'--snapshot',str(snap),'--message','小婕收集 https://x.com/example/status/123']
   a=json.loads(subprocess.check_output(args,text=True))
   (snap/'article.md').write_text('# Second version')
   b=json.loads(subprocess.check_output(args+['--refresh'],text=True))
   self.assertNotEqual(a['id'],b['id'])
   self.assertEqual((Path(a['archive'])/'article.md').read_text(),'# First version')
   self.assertEqual(len(list((root/'vault/raw/sources').glob('*.md'))),2)
   (Path(b['archive'])/'article.md').write_text('Unexpected edit')
   failed=subprocess.run(args+['--refresh'],capture_output=True,text=True)
   self.assertNotEqual(failed.returncode,0)
   self.assertIn('refusing to overwrite',failed.stderr)
if __name__=='__main__': unittest.main()
