import json,subprocess,tempfile,unittest,wave,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class MiniSetupTest(unittest.TestCase):
 def test_initialization_is_relocatable_private_and_never_replaces_credentials(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve();model=p/'fixture-model.bin';model.write_bytes(b'synthetic model for mocked ASR boundary tests');sha=hashlib.sha256(model.read_bytes()).hexdigest();data=p/'private-data'
   command=['python3',str(ROOT/'services/mini-media/gateway.py'),'init','--data',str(data),'--model-file',str(model),'--model-sha256',sha,'--ffmpeg','/usr/bin/false','--ffprobe','/usr/bin/false']
   first=subprocess.run(command,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stderr)
   token=data/'state/api-token';self.assertEqual(token.stat().st_mode&0o777,0o600);saved=token.read_bytes();self.assertNotIn(saved.decode().strip(),first.stdout)
   again=subprocess.run(command,capture_output=True,text=True);self.assertEqual(again.returncode,0,again.stderr);self.assertEqual(token.read_bytes(),saved)
   cfg=json.loads((data/'state/config.json').read_text());self.assertEqual(cfg['model']['sha256'],sha);self.assertEqual(Path(cfg['model']['path']).read_bytes(),model.read_bytes());self.assertEqual(cfg['bind'],'127.0.0.1')
if __name__=='__main__':unittest.main()
