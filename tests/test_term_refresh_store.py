import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from scripts.protected_store import Root, refresh_terms, sha
import os

class RefreshProtectionTest(unittest.TestCase):
 def test_last_moment_edit_is_restored_and_retained(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'glossary/a.md';path.parent.mkdir();path.write_bytes(b'old')
   root=Root(temp);real=os.rename
   def race(src,dst,**kw):
    path.write_bytes(b'last moment handwritten edit')
    return real(src,dst,**kw)
   try:
    with patch('scripts.protected_store.os.rename',side_effect=race):
     result=refresh_terms(root,{'runId':'a'*20,'changes':[{'path':'glossary/a.md','expectedHash':sha(b'old'),'content':'new'}]})
    self.assertEqual(path.read_bytes(),b'last moment handwritten edit')
    self.assertEqual(result['conflicts'],['glossary/a.md'])
   finally:os.close(root.fd)
 def test_edit_using_old_open_descriptor_remains_in_recovery(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'glossary/a.md';path.parent.mkdir();path.write_bytes(b'old')
   root=Root(temp)
   try:
    with path.open('r+b') as writer:
     result=refresh_terms(root,{'runId':'b'*20,'changes':[{'path':'glossary/a.md','expectedHash':sha(b'old'),'content':'new'}]})
     writer.seek(0);writer.write(b'late edit');writer.truncate();writer.flush()
    recovery=Path(result['recovery'])/'glossary/a.md'
    self.assertEqual(recovery.read_bytes(),b'late edit')
    self.assertEqual(path.read_bytes(),b'new')
   finally:os.close(root.fd)
