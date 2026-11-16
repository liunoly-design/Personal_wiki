import json,subprocess,tarfile,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class Lifecycle(unittest.TestCase):
 def test_config_skill_and_uninstall_preserve_user_state(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve();subprocess.run(['python3',str(ROOT/'distribution/build.py'),'--component','cli','--version','0.9.0-test','--output',str(p/'out'),'--allow-dirty'],check=True,capture_output=True)
   with tarfile.open(next((p/'out').glob('*.tar.gz'))) as tar:tar.extractall(p/'unpacked',filter='data')
   package=next((p/'unpacked').iterdir());prefix=p/'install';config=p/'config.json'
   install=subprocess.run(['node',str(package/'install.mjs'),'--prefix',str(prefix),'--config',str(config)],capture_output=True,text=True);self.assertEqual(install.returncode,0,install.stderr)
   def manage(*args):return subprocess.run(['node',str(package/'manage.mjs'),'--prefix',str(prefix),'--config',str(config),*args],capture_output=True,text=True)
   update=manage('configure','--vault',str(p/'Vault'));self.assertEqual(update.returncode,0,update.stderr);self.assertEqual(json.loads(config.read_text())['vault'],str(p/'Vault'))
   skill=manage('skill-install','--skills-dir',str(p/'skills'));self.assertEqual(skill.returncode,0,skill.stderr);self.assertIn(str(prefix/'bin/personal-wiki'),(p/'skills/personal-wiki/SKILL.md').read_text())
   state=prefix/'state/human.txt';state.write_text('keep');original=config.read_bytes();remove=manage('uninstall');self.assertEqual(remove.returncode,0,remove.stderr);self.assertFalse((prefix/'bin/personal-wiki').exists());self.assertEqual(state.read_text(),'keep');self.assertEqual(config.read_bytes(),original)
if __name__=='__main__':unittest.main()
