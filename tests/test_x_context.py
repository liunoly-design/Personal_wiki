import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from scripts.capture_article import capture

class XContextTest(unittest.TestCase):
 def test_quote_relationship_survives_duplicate_order(self):
  marked='<article><a href="/a/status/1">post</a><p>目标正文</p><a data-quote href="/b/status/9">引用</a></article>'
  unmarked=marked.replace(' data-quote','')
  for html in [marked+unmarked,unmarked+marked]:
   def request(url,hosts,limit,dest):
    if url=='https://x.com/a/status/1':dest.write_text(html)
    elif url=='https://x.com/b/status/9':dest.write_text('<article><a href="/b/status/9">post</a><p>引用正文</p></article>')
    else:raise ValueError('Unexpected request')
   with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=request):
    result=capture('https://x.com/a/status/1',temp)
    self.assertIn('引用正文',(Path(result['directory'])/'article.md').read_text())
 def test_unrelated_ambiguous_comments_do_not_block_target(self):
  html='<article data-reply-to=""><a href="/a/status/1">post</a><p>目标正文</p></article><article data-reply-to="1"><a href="/b/status/2">comment</a>short</article><article data-reply-to="1"><a href="/b/status/2">comment</a>long comment</article>'
  with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=lambda url,hosts,limit,dest:dest.write_text(html)):
   result=capture('https://x.com/a/status/1',temp);body=(Path(result['directory'])/'article.md').read_text()
   self.assertEqual(result['status'],'complete');self.assertIn('目标正文',body);self.assertNotIn('comment',body);self.assertEqual(result['contextStatus'],'complete')
 def test_ambiguous_same_author_child_retains_target_and_reports_gap(self):
  html='<article data-reply-to=""><a href="/a/status/1">post</a><p>目标正文</p></article><article data-reply-to="1"><a href="/a/status/2">post</a>short</article><article data-reply-to="1"><a href="/a/status/2">post</a>different body</article>'
  with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=lambda url,hosts,limit,dest:dest.write_text(html)):
   result=capture('https://x.com/a/status/1',temp);body=(Path(result['directory'])/'article.md').read_text()
   self.assertIn('目标正文',body);self.assertNotIn('different body',body);self.assertEqual(result['contextStatus'],'partial');self.assertIn('副本歧义',' '.join(result['contextGaps']))
 def test_responsive_copy_keeps_visible_url_in_final_capture_and_cache(self):
  plain='<article><a href="/a/status/1">post</a><p>课程正文</p><img src="https://pbs.twimg.com/cover.jpg"></article>'
  complete='<article><a href="/a/status/1">post</a><p>课程正文</p><a href="https://example.edu/">https://example.edu/</a><img src="https://pbs.twimg.com/cover.jpg"></article>'
  html=plain+complete
  def request(url,hosts,limit,dest):
   if url=='https://x.com/a/status/1':dest.write_text(html)
   elif url=='https://pbs.twimg.com/cover.jpg':dest.write_bytes(b'synthetic cover')
   else:raise ValueError('Unexpected unrelated request')
  with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=request),patch('scripts.attachment_resume.download',side_effect=lambda url,dest,**kwargs:request(url,set(),0,dest)),patch('scripts.capture_article.extract_public',side_effect=OSError('No media fallback for duplicate articles')):
   result=capture('https://x.com/a/status/1',temp);directory=Path(result['directory']);body=(directory/'article.md').read_text()
   self.assertEqual(result['status'],'complete');self.assertEqual(body.count('课程正文'),1);self.assertIn('https://example.edu/',body)
   self.assertEqual((directory/'raw.html').read_text(),html);self.assertEqual((directory/'images/image-01.jpg').read_bytes(),b'synthetic cover')
   self.assertEqual(result['contextStatus'],'partial');self.assertIn('平台未提供回复关系，无法确认完整串文',result['contextGaps'])
   self.assertEqual(capture('https://x.com/a/status/1',temp),result)
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

 def test_interrupted_manifest_replace_preserves_checkpoint_and_cached_html(self):
  html='<article data-reply-to=""><a href="/a/status/1">post</a><p>持久正文</p></article>'
  with tempfile.TemporaryDirectory() as temp,patch('scripts.capture_article.request',side_effect=lambda url,hosts,limit,dest:dest.write_text(html)) as network:
   result=capture('https://x.com/a/status/1',temp);manifest=Path(result['directory'])/'manifest.json';old=manifest.read_bytes();(Path(temp)/'capture-result.json').unlink()
   original=Path.replace
   def interrupted(path,target):
    if Path(target).resolve()==manifest.resolve():raise OSError('synthetic interruption before rename')
    return original(path,target)
   with patch.object(Path,'replace',interrupted):
    with self.assertRaises(OSError):capture('https://x.com/a/status/1',temp)
   self.assertEqual(manifest.read_bytes(),old)
   recovered=capture('https://x.com/a/status/1',temp);self.assertEqual(recovered['status'],'complete');self.assertEqual(network.call_count,1)
