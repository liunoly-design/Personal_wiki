import json,subprocess,tarfile,tempfile,unittest,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class Boundaries(unittest.TestCase):
 def build(self,p,component):
  subprocess.run(['python3',str(ROOT/'distribution/build.py'),'--component',component,'--version','0.9.0-test','--output',str(p/'out'),'--allow-dirty'],capture_output=True,check=True)
  with tarfile.open(next((p/'out').glob('*.tar.gz'))) as tar:tar.extractall(p/'unpacked',filter='data')
  return next((p/'unpacked').iterdir())
 def test_ignored_runtime_material_is_never_distributed(self):
  marker=ROOT/'services/mini-media/.env.distribution-test'
  self.assertFalse(marker.exists());marker.write_text('SYNTHETIC_PRIVATE_TOKEN=must-not-ship')
  try:
   with tempfile.TemporaryDirectory() as tmp:
    package=self.build(Path(tmp).resolve(),'mini-media');self.assertFalse((package/'runtime/services/mini-media/.env.distribution-test').exists())
  finally:marker.unlink()
 def test_mini_installer_refuses_identity_symlink_before_mutation(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve();package=self.build(p,'mini-media');prefix=p/'install';prefix.mkdir();outside=p/'outside.json';outside.write_text(json.dumps({'component':'mini-media','prefix':str(prefix)})+'\n');outside.chmod(0o644);(prefix/'.installation.json').symlink_to(outside)
   r=subprocess.run(['python3',str(package/'install.py'),'--prefix',str(prefix),'--skip-dependencies'],capture_output=True,text=True)
   self.assertNotEqual(r.returncode,0);self.assertIn('Symlink',r.stderr);self.assertEqual(outside.stat().st_mode&0o777,0o644)
if __name__=='__main__':unittest.main()

class MiniVersionBoundary(unittest.TestCase):
 build=Boundaries.build
 def test_mini_manifest_cannot_escape_release_directory(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve();package=self.build(p,'mini-media');manifest=package/'distribution.json';m=json.loads(manifest.read_text());m['version']='../../outside';manifest.write_text(json.dumps(m))
   r=subprocess.run(['python3',str(package/'install.py'),'--prefix',str(p/'install'),'--skip-dependencies'],capture_output=True,text=True);self.assertNotEqual(r.returncode,0);self.assertIn('Invalid release version',r.stderr);self.assertFalse((p/'install').exists())
 def test_mini_launcher_symlink_is_rejected_before_installer_writes(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve();package=self.build(p,'mini-media');prefix=p/'install';(prefix/'bin').mkdir(parents=True);outside=p/'outside';outside.write_text('human');(prefix/'bin/personal-wiki-media').symlink_to(outside)
   r=subprocess.run(['python3',str(package/'install.py'),'--prefix',str(prefix),'--skip-dependencies'],capture_output=True,text=True);self.assertNotEqual(r.returncode,0);self.assertIn('Symlink',r.stderr);self.assertEqual(outside.read_text(),'human');self.assertFalse((prefix/'.installation.json').exists())
