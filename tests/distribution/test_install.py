import json,subprocess,tempfile,unittest,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class InstallTest(unittest.TestCase):
 def test_clean_install_runs_without_checkout_and_preserves_private_config(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();out=root/'archives';prefix=root/'installed';config=root/'private/config.json'
   subprocess.run(['python3',str(ROOT/'distribution/build.py'),'--component','cli','--version','0.9.0-test','--output',str(out),'--allow-dirty'],check=True,capture_output=True)
   with tarfile.open(next(out.glob('*.tar.gz'))) as archive:archive.extractall(root/'unpacked',filter='data')
   package=next((root/'unpacked').iterdir())
   def install():return subprocess.run(['node',str(package/'install.mjs'),'--prefix',str(prefix),'--config',str(config)],capture_output=True,text=True)
   first=install();self.assertEqual(first.returncode,0,first.stderr)
   launcher=prefix/'bin/personal-wiki';self.assertTrue(launcher.is_file())
   help=subprocess.run([str(launcher),'--help'],capture_output=True,text=True);self.assertEqual(help.returncode,0,help.stderr);self.assertIn('--file',help.stdout)
   original=config.read_bytes();self.assertEqual(config.stat().st_mode&0o777,0o600)
   self.assertEqual(install().returncode,0);self.assertEqual(config.read_bytes(),original)
   done=subprocess.run([str(launcher),'convert','--text','安装隔离测试，全文原样保留。'],capture_output=True,text=True)
   self.assertEqual(done.returncode,0,done.stderr);result=json.loads(done.stdout);self.assertEqual(result['status'],'converted');self.assertEqual(Path(result['bundle']['markdown']).read_text(),'安装隔离测试，全文原样保留。')
   self.assertFalse((prefix/'state'/'Vault').exists())
if __name__=='__main__':unittest.main()
