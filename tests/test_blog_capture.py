import unittest, tempfile
from urllib.error import URLError
from pathlib import Path
from unittest.mock import patch
from scripts.capture_article import capture

class BlogCaptureTest(unittest.TestCase):
 def test_fake_ip_dns_transport_failure_recovers_and_keeps_required_image(self):
  html=b'<article><h1>Public article</h1><p>First section.</p><img src="https://cdn.example.org/chart.webp"><p>Final evidence.</p></article>'
  image=b'RIFF\x10\x00\x00\x00WEBPVP8 synthetic image'
  class DNS:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,limit):return b'{"Status":0,"Answer":[{"type":1,"data":"93.184.216.34"}]}'
  class Response:
   status=200
   def __init__(self,data):self.data=data
   def getheader(self,name):return None
   def read(self,limit):return self.data
  class Connection:
   def request(self,method,target,headers):self.target=target
   def getresponse(self):return Response(image if self.target=='/chart.webp' else html)
   def close(self):pass
  def dns(request,timeout):
   if 'cdn.example.org' in request.full_url and 'dns.google' in request.full_url:
    raise URLError('synthetic TLS EOF')
   return DNS()
  with tempfile.TemporaryDirectory() as temp,patch('socket.getaddrinfo',return_value=[(2,1,6,'',('198.18.0.8',443))]),patch('urllib.request.urlopen',side_effect=dns) as doh,patch('scripts.blog_capture.PinnedHTTPS',side_effect=lambda *args:Connection()):
   result=capture('https://example.org/article',temp)
   package=Path(result['directory'])
   self.assertEqual(result['status'],'complete')
   self.assertIn('Final evidence.',(package/'article.md').read_text())
   self.assertIn('images/image-001.webp',(package/'article.md').read_text())
   self.assertEqual((package/'images/image-001.webp').read_bytes(),image)
   self.assertTrue(any('dns.alidns.com' in call.args[0].full_url for call in doh.call_args_list))
 def test_unrecognized_image_bytes_stay_in_pending_materials(self):
  original=b'\x00\x00\x00\x20ftypavifsynthetic-unrecognized-image'
  def fetch(url,limit,dest,**kwargs):
   dest.write_bytes(original if url.endswith('/image') else b'<article><p>Complete article with a required image.</p><img src="/image"></article>');return url
  with tempfile.TemporaryDirectory() as temp,patch('scripts.blog_capture.fetch_public',side_effect=fetch):
   result=capture('https://example.org/article',temp);package=Path(result['directory'])
   self.assertEqual(result['status'],'partial');self.assertEqual((package/result['missingAssets'][0]['retained_path']).read_bytes(),original)
 def test_login_form_and_explicit_truncation_do_not_publish_as_articles(self):
  for html in ['<main><h1>Account</h1><form><input type="password"></form><p>Sign in to read the full article.</p></main>','<article data-truncated="true"><h1>Preview</h1><p>Only the beginning is available here.</p></article>']:
   def fetch(url,limit,dest,**kwargs):dest.write_text(html);return url
   with tempfile.TemporaryDirectory() as temp,patch('scripts.blog_capture.fetch_public',side_effect=fetch):
    with self.assertRaisesRegex(ValueError,'incomplete'):capture('https://example.org/gated',temp)
 def test_extensionless_body_image_remains_local_and_available_for_ocr(self):
  def fetch(url,limit,dest,**kwargs):
   dest.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic' if url.endswith('/image') else b'<article><h1>Image evidence</h1><p>Complete body and final paragraph.</p><img src="/image"></article>');return url
  with tempfile.TemporaryDirectory() as temp,patch('scripts.blog_capture.fetch_public',side_effect=fetch):
   result=capture('https://example.org/article',temp);package=Path(result['directory'])
   self.assertEqual(result['status'],'complete');self.assertIn('images/image-001.png',(package/'article.md').read_text());self.assertTrue((package/'images/image-001.png').exists())
 def test_render_fallback_converts_script_article_and_keeps_both_originals(self):
  html='<html><meta charset="utf-8"><title>Dynamic article</title><main>Loading...</main><script>document.querySelector("main").innerHTML="<article><h1>动态正文</h1><p>这是动态渲染后的完整文章正文，保留脚本生成的最后一句证据。</p></article>"</script></html>'
  def fetch(url,limit,dest,**kwargs):
   dest.write_bytes(html.encode());kwargs.get('response_metadata',{}).update(content_type='text/html');return url
  with tempfile.TemporaryDirectory() as temp,patch('scripts.blog_capture.fetch_public',side_effect=fetch):
   with self.assertRaisesRegex(ValueError,'incomplete'):capture('https://example.org/dynamic',str(Path(temp)/'static'))
   result=capture('https://example.org/dynamic',str(Path(temp)/'rendered'),render=True)
   package=Path(result['directory']);self.assertEqual(result['status'],'complete');self.assertIn('最后一句证据',(package/'article.md').read_text())
   self.assertTrue((package/'original.html').exists());self.assertTrue((package/'rendered.html').exists())
 def test_fake_ip_resolver_uses_only_validated_public_answers_and_still_rejects_private_dns(self):
  from scripts.blog_capture import fetch_public
  class DNS:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,limit):return b'{"Status":0,"Answer":[{"type":1,"data":"93.184.216.34"}]}'
  class Response:
   status=200
   def getheader(self,name):return None
   def read(self,limit):return b'public'
  class Connection:
   def request(self,*args,**kwargs):pass
   def getresponse(self):return Response()
   def close(self):pass
  with tempfile.TemporaryDirectory() as temp,patch('socket.getaddrinfo',return_value=[(2,1,6,'',('198.18.0.8',443))]),patch('urllib.request.urlopen',return_value=DNS()),patch('scripts.blog_capture.PinnedHTTPS',return_value=Connection()) as connection:
   fetch_public('https://example.org/article',1000,Path(temp)/'body')
   self.assertEqual(connection.call_args.args,('example.org','93.184.216.34'))
  with tempfile.TemporaryDirectory() as temp,patch('socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]),patch('urllib.request.urlopen') as dns:
   with self.assertRaises(ValueError):fetch_public('https://example.org/article',1000,Path(temp)/'body')
   dns.assert_not_called()
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
