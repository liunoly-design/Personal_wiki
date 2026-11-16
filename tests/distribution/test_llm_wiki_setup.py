import hashlib,json,plistlib,subprocess,tarfile,tempfile,unittest,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class AppInstallTest(unittest.TestCase):
 def test_verified_archive_installs_to_explicit_location_and_preserves_existing_app(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve();app=p/'source/LLM Wiki.app/Contents';app.mkdir(parents=True);(app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.llmwiki.app','CFBundleShortVersionString':'0.6.11'}))
   archive=p/'app.tar.gz'
   with tarfile.open(archive,'w:gz') as out:out.add(app.parent,arcname='LLM Wiki.app')
   manifest=p/'manifest.json';manifest.write_text(json.dumps({'repository':'https://github.com/nashsu/llm_wiki','tag':'v0.6.11','asset':'https://github.com/nashsu/llm_wiki/releases/download/v0.6.11/LLM.Wiki_aarch64.app.tar.gz','downloaded_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
   args=['python3',str(ROOT/'distribution/llm-wiki-setup.py'),'install','--archive',str(archive),'--manifest',str(manifest),'--destination',str(p/'Applications')]
   r=subprocess.run(args,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((p/'Applications/LLM Wiki.app/Contents/Info.plist').is_file())
   (p/'Applications/LLM Wiki.app/human.txt').write_text('keep');again=subprocess.run(args,capture_output=True,text=True);self.assertNotEqual(again.returncode,0);self.assertEqual((p/'Applications/LLM Wiki.app/human.txt').read_text(),'keep')
if __name__=='__main__':unittest.main()

class PackagedBootstrapTest(unittest.TestCase):
 def test_packaged_bootstrap_finds_the_pinned_manifest_without_checkout(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();out=root/'out'
   subprocess.run(['python3',str(ROOT/'distribution/build.py'),'--component','llm-wiki-setup','--version','0.9.0-test','--output',str(out),'--allow-dirty'],check=True,capture_output=True)
   with tarfile.open(next(out.glob('*.tar.gz'))) as archive:archive.extractall(root/'unpacked',filter='data')
   package=next((root/'unpacked').iterdir());bad=root/'bad.tar.gz';bad.write_bytes(b'wrong artifact')
   result=subprocess.run(['python3',str(package/'llm-wiki-setup.py'),'install','--archive',str(bad),'--destination',str(root/'apps')],capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0);self.assertIn('SHA256 mismatch',result.stdout);self.assertFalse((root/'apps/LLM Wiki.app').exists())
