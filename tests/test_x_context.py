import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from scripts.capture_article import capture

class XContextTest(unittest.TestCase):
 def test_thread_pages_quotes_and_comments_have_distinct_provenance(self):
  pages={
   'https://x.com/a/status/1':'<article data-reply-to=""><a href="/a/status/1">post</a><p>首帖</p><a data-quote href="/b/status/9">引用</a></article><article data-reply-to="1"><a href="/c/status/2">comment</a><p>他人评论</p></article><a rel="next" href="/a/status/1?cursor=next">下一页</a>',
   'https://x.com/a/status/1?cursor=next':'<article data-reply-to="1"><a href="/a/status/3">post</a><p>第二帖</p><img src="https://pbs.twimg.com/three.jpg"></article><article data-reply-to="3"><a href="/a/status/4">post</a><p>第三帖</p></article><article data-reply-to="1"><a href="/a/status/3">post</a><p>第二帖</p></article><article><a href="/a/status/5">post</a><p>无关同作者</p></article>',
   'https://x.com/b/status/9':'<article><a href="/b/status/9">post</a><p>远端引用正文</p></article>'}
  def request(url,hosts,limit,dest):
   if url in pages:dest.write_text(pages[url])
   elif 'pbs.twimg.com' in url:dest.write_bytes(b'image')
   else:raise ValueError('missing')
  with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=request),patch('scripts.attachment_resume.download',side_effect=lambda url,dest,**kwargs:request(url,set(),0,dest)):
   result=capture('https://x.com/a/status/1',temp);directory=Path(result['directory']);body=(directory/'article.md').read_text();manifest=json.loads((directory/'manifest.json').read_text())
   self.assertLess(body.index('首帖'),body.index('第二帖'));self.assertLess(body.index('第二帖'),body.index('第三帖'))
   self.assertIn('远端引用正文',body);self.assertNotIn('他人评论',body);self.assertNotIn('无关同作者',body);self.assertEqual(body.count('第二帖'),1)
   self.assertEqual(manifest['assets'][0]['post_url'],'https://x.com/a/status/3')
 def test_pagination_loop_and_missing_quote_are_visible(self):
  html='<article><a href="/a/status/1">post</a><p>已取得</p><a data-quote href="/b/status/8">quote</a></article><a rel="next" href="/a/status/1">next</a>'
  def request(url,hosts,limit,dest):
   if url=='https://x.com/a/status/1':dest.write_text(html)
   else:raise ValueError('HTTP 404')
  with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=request),patch('scripts.attachment_resume.download',side_effect=lambda url,dest,**kwargs:request(url,set(),0,dest)):
   result=capture('https://x.com/a/status/1',temp);body=(Path(result['directory'])/'article.md').read_text()
   self.assertIn('上下文缺失',body);self.assertEqual(result['contextStatus'],'partial')

 def test_video_metadata_does_not_hide_same_author_thread(self):
  html='<article data-reply-to=""><a href="/a/status/1">post</a><p>首帖</p><video></video></article><article data-reply-to="1"><a href="/a/status/2">post</a><p>后续帖</p></article>'
  def request(url,hosts,limit,dest):dest.write_text(html)
  with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=request),patch('scripts.capture_article.extract_public',return_value={'duration':1900,'formats':[dict(url='https://video.twimg.com/long.mp4',ext='mp4',width=1920,height=1080,vcodec='h264')]}):
   result=capture('https://x.com/a/status/1',temp);self.assertIn('后续帖',(Path(result['directory'])/'article.md').read_text())
