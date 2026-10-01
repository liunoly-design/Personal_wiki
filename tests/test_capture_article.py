import unittest
try:
    from scripts.capture_article import select_target_article
    from bs4 import BeautifulSoup
except ImportError:
    select_target_article = None

@unittest.skipUnless(select_target_article, 'capture dependencies required')
class TargetTest(unittest.TestCase):
    def test_long_comment_and_nested_quote(self):
        soup=BeautifulSoup('<article><a href="/a/status/1">target</a>body<article><a href="/b/status/2">quote</a>quoted text</article></article><article><a href="/c/status/3">comment</a>'+('long comment '*100)+'</article>','html.parser')
        article=select_target_article(soup,'https://x.com/a/status/1?s=20')
        self.assertIn('quoted text',article.get_text())
        self.assertNotIn('long comment',article.get_text())
    def test_equivalent_responsive_copies(self):
        soup=BeautifulSoup('<article class="mobile"><a href="/a/status/1">post</a></article><article class="desktop"><a href="/a/status/1">post</a></article>','html.parser')
        self.assertEqual(select_target_article(soup,'https://x.com/a/status/1').get_text(),'post')
    def test_same_target_copy_with_embedded_quote_is_preferred(self):
        soup=BeautifulSoup('<article><a href="/a/status/1">target</a>body</article><article><a href="/a/status/1">target</a>body<article><a href="/b/status/2">quote</a>quoted text</article></article>','html.parser')
        self.assertIn('quoted text',select_target_article(soup,'https://x.com/a/status/1').get_text())
    def test_different_target_bodies_remain_ambiguous(self):
        soup=BeautifulSoup('<article><a href="/a/status/1">target</a>one</article><article><a href="/a/status/1">target</a>two</article>','html.parser')
        with self.assertRaises(ValueError):select_target_article(soup,'https://x.com/a/status/1')
    def test_author_case_does_not_hide_requested_post(self):
        soup=BeautifulSoup('<article><a href="/ai_Goge/status/123">target</a>desired</article><article><a href="/ai_Goge/status/456">comment</a>wrong</article>','html.parser')
        self.assertIn('desired',select_target_article(soup,'https://x.com/ai_goge/status/123?s=46').get_text())

    def test_unknown_target_fails(self):
        with self.assertRaises(ValueError):
            select_target_article(BeautifulSoup('<article>unidentified</article>','html.parser'),'https://x.com/a/status/1')

class CaptureMediaTest(unittest.TestCase):
 def test_x_image_and_video_capture_produces_local_markdown_links(self):
  import tempfile, subprocess, json
  from pathlib import Path
  from unittest.mock import patch
  import imageio_ffmpeg
  from scripts.capture_article import capture
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);sample=root/'sample.mp4'
   subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-f','lavfi','-i','color=c=black:s=160x90:d=0.1','-c:v','libx264',str(sample)],check=True,capture_output=True)
   html='<article><a href="/a/status/123">Post</a><p>Media sample</p><img src="https://pbs.twimg.com/sample.jpg"><video src="https://video.twimg.com/sample.mp4"></video><p>After the video</p></article>'
   def request(url,hosts,limit,dest):
    if url.startswith('https://x.com'):dest.write_text(html)
    elif 'pbs.twimg.com' in url:dest.write_bytes(b'synthetic image')
    else:dest.write_bytes(sample.read_bytes())
   info={'duration':0.1,'formats':[{'url':'https://video.twimg.com/sample.mp4','ext':'mp4','width':160,'height':90,'vcodec':'h264','protocol':'https'}]}
   with patch('scripts.capture_article.request',side_effect=request),patch('scripts.capture_article.extract_public',return_value=info),patch('scripts.attachment_resume.download',side_effect=lambda url,dest,**kwargs:request(url,set(),0,dest)):
    result=capture('https://x.com/a/status/123',root/'capture')
   self.assertEqual(result['status'],'complete')
   body=(Path(result['directory'])/'article.md').read_text()
   self.assertLess(body.index('videos/video-01.mp4'),body.index('After the video'));self.assertIn('images/image-01.jpg',body);self.assertIn('videos/video-01.mp4',body)
   self.assertEqual((Path(result['directory'])/'videos/video-01.mp4').read_bytes(),sample.read_bytes())

class WechatVideoTest(unittest.TestCase):
 def test_script_templates_are_not_actual_pending_videos(self):
  from scripts.capture_article import wechat_video_pending
  self.assertFalse(wechat_video_pending({},'<script>for(i=0;i<videoPageInfos.length;i++){};player="?vid="</script><div id="js_content">Article</div>'))
  self.assertTrue(wechat_video_pending({},'<div id="js_content"><iframe class="video_iframe" data-src="https://v.qq.com/iframe/player.html?vid=abc"></iframe></div>'))
