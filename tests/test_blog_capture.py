import unittest, tempfile
from pathlib import Path
from unittest.mock import patch
from scripts.capture_article import capture

class BlogCaptureTest(unittest.TestCase):
 def test_complete_structure_and_missing_image_are_reported(self):
  html='<html><title>Public blog</title><nav>unrelated</nav><article><h1>Public blog</h1><p>First paragraph with <a href="/ref">reference</a>.</p><img src="/photo.png"><h2>Last section</h2><table><tr><th>A</th></tr><tr><td>B</td></tr></table><pre><code>x = 1</code></pre><p>Final evidence.</p></article></html>'
  def fetch(url,limit,dest):
   if url.endswith('.png'):raise OSError('image missing')
   dest.write_bytes(html.encode());return 'https://example.org/blog'
  with tempfile.TemporaryDirectory() as temp,patch('scripts.blog_capture.fetch_public',side_effect=fetch):
   result=capture('https://example.org/start',temp)
   body=(Path(result['directory'])/'article.md').read_text()
   self.assertIn('Final evidence.',body);self.assertIn('## Last section',body);self.assertIn('https://example.org/ref',body);self.assertIn('x = 1',body);self.assertNotIn('unrelated',body)
   self.assertEqual(result['status'],'partial');self.assertEqual(len(result['missingAssets']),1)
 def test_public_url_rejects_private_and_mixed_dns(self):
  from scripts.blog_capture import public_addresses
  for url in ['http://example.org','https://user:pass@example.org','https://127.0.0.1','https://example.org:8443']:
   with self.assertRaises(ValueError):public_addresses(url)
  with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]):
   with self.assertRaises(ValueError):public_addresses('https://example.org')
 def test_redirect_to_private_address_never_opens_connection(self):
  from scripts.blog_capture import fetch_public
  class Response:
   status=302
   def getheader(self,name):return 'https://127.0.0.1/private'
  class Connection:
   def request(self,*args,**kwargs):pass
   def getresponse(self):return Response()
   def close(self):pass
  def addresses(host,port,**kwargs):return [(2,1,6,'',('127.0.0.1' if host=='127.0.0.1' else '93.184.216.34',443))]
  with tempfile.TemporaryDirectory() as temp,patch('socket.getaddrinfo',side_effect=addresses),patch('scripts.blog_capture.PinnedHTTPS',return_value=Connection()) as connection:
   with self.assertRaises(ValueError):fetch_public('https://example.org/start',1000,Path(temp)/'body')
   self.assertEqual(connection.call_count,1)
 def test_public_redirect_keeps_validated_hostname_and_pinned_ip(self):
  from scripts.blog_capture import fetch_public
  class Response:
   def __init__(self,status):self.status=status
   def getheader(self,name):return '/final' if name=='Location' else '5'
   def read(self,limit):return b'hello'
  class Connection:
   def __init__(self,status):self.status=status
   def request(self,*args,**kwargs):pass
   def getresponse(self):return Response(self.status)
   def close(self):pass
  with tempfile.TemporaryDirectory() as temp,patch('socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))]),patch('scripts.blog_capture.PinnedHTTPS',side_effect=[Connection(302),Connection(200)]) as connection:
   dest=Path(temp)/'body';self.assertEqual(fetch_public('https://example.org/start',1000,dest),'https://example.org/final');self.assertEqual(dest.read_bytes(),b'hello');self.assertEqual(connection.call_args.args,('example.org','93.184.216.34'))
