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
