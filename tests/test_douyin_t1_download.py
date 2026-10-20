"""Synthetic HTTP boundary tests; no platform, credentials or private media."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
from scripts.attachment_resume import download

URL = 'https://media.douyinvod.com/fixture.mp4'

class Response:
    def __init__(self, status, body, headers):
        self.status, self.body, self.headers = status, io.BytesIO(body), headers
    def getheader(self, name): return self.headers.get(name)
    def read(self, size): return self.body.read(size)

class DownloadRecoveryTests(unittest.TestCase):
    def test_subrange_never_becomes_a_completed_file(self):
        responses = [Response(206, b'def', {'ETag': '"same"', 'Content-Range': 'bytes 3-5/10', 'Content-Length': '3'}),
                     Response(206, b'ghij', {'ETag': '"same"', 'Content-Range': 'bytes 6-9/10', 'Content-Length': '4'})]
        class Connection:
            def __init__(self, *args): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return responses.pop(0)
            def close(self): pass
        with tempfile.TemporaryDirectory() as d, patch('scripts.attachment_resume.PinnedHTTPS', Connection):
            dest = Path(d)/'download.mp4'
            partial = dest.with_suffix('.mp4.part'); partial.write_bytes(b'abc')
            partial.with_suffix('.part.json').write_text(json.dumps({'url': URL, 'validator': '"same"'}))
            resolve = lambda url: (urlsplit(url), ['8.8.8.8'])
            with self.assertRaisesRegex(OSError, 'Incomplete'):
                download(URL, dest, resolve_addresses=resolve)
            self.assertFalse(dest.exists())
            self.assertEqual(partial.read_bytes(), b'abcdef')
            download(URL, dest, resolve_addresses=resolve)
            self.assertEqual(dest.read_bytes(), b'abcdefghij')

    def test_sidecar_symlink_cannot_overwrite_unrelated_file(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); dest=root/'download.mp4'; unrelated=root/'keep.txt'; unrelated.write_bytes(b'keep')
            dest.with_suffix('.mp4.part').symlink_to(unrelated)
            with self.assertRaisesRegex(ValueError, 'symlink|regular'):
                download(URL, dest, resolve_addresses=lambda _: self.fail('unsafe path reached network'))
            self.assertEqual(unrelated.read_bytes(), b'keep')

    def test_approval_is_a_finite_byte_scope_not_an_unlimited_download(self):
        from scripts.attachment_resume import ConfirmationRequired
        class Connection:
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):pass
            def getresponse(self):return response
            def close(self):pass
        with tempfile.TemporaryDirectory() as d,patch('scripts.attachment_resume.PinnedHTTPS',Connection):
            dest=Path(d)/'download.mp4';resolve=lambda url:(urlsplit(url),['8.8.8.8'])
            response=Response(200,b'abcdefghij',{'Content-Length':'10'})
            with self.assertRaises(ConfirmationRequired) as error:
                download(URL,dest,approved=True,approved_limit=6,resolve_addresses=resolve)
            self.assertEqual(error.exception.expected_size,10)
            self.assertEqual(response.body.tell(),0)
            response=Response(200,b'abcdefghij',{'ETag':'"same"'})
            with self.assertRaises(ConfirmationRequired):download(URL,dest,approved=True,approved_limit=6,resolve_addresses=resolve)
            self.assertEqual(dest.with_suffix('.mp4.part').read_bytes(),b'abcdef');self.assertFalse(dest.exists())
            response=Response(206,b'ghij',{'ETag':'"same"','Content-Range':'bytes 6-9/10','Content-Length':'4'})
            download(URL,dest,approved=True,approved_limit=10,resolve_addresses=resolve)
            self.assertEqual(dest.read_bytes(),b'abcdefghij')
