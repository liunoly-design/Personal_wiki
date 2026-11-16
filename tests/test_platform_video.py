import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
class PlatformVideoTest(unittest.TestCase):
 def test_xhs_video_has_bound_download_and_full_description(self):
  from scripts.xiaohongshu_capture import capture
  target='64abcdef0123456789abcdef';url='https://www.xiaohongshu.com/explore/'+target
  note={'noteId':target,'type':'video','desc':'视频完整说明，末尾也必须保留。','imageList':[],'video':{'media':{'stream':{'EF4':[{'masterUrl':'https://sns-video-bd.xhscdn.com/test.mp4','duration':32041,'size':9,'width':720,'height':1280}]}}}}
  def page(url,limit,dest,**kw):dest.write_text('<script>window.__INITIAL_STATE__='+json.dumps({'noteData':{'data':{'noteData':note}}})+'</script>');return url
  def video(url,dest,**kw):dest.parent.mkdir(exist_ok=True);dest.write_bytes(b'synthetic');return {'sha256':'a'*64,'bytes':9,'url':url}
  with tempfile.TemporaryDirectory() as temp,patch('scripts.xiaohongshu_capture.fetch_public',side_effect=page),patch('scripts.xiaohongshu_capture.download_media',side_effect=video):
   r=capture(url,temp);self.assertEqual(r['status'],'complete');m=json.loads((Path(r['directory'])/'manifest.json').read_text());v=m['assets'][0];self.assertEqual(v['source_id'],target);self.assertEqual(v['duration_seconds'],32.041);self.assertEqual(v['status'],'downloaded');self.assertIn('视频完整说明',(Path(r['directory'])/'article.md').read_text())
 def test_x_video_stays_with_its_post_and_thread_tail(self):
  from scripts.x_provider import capture
  first={'type':'status','id':'123','author':{'id':'a','screen_name':'example'},'replying_to':None,'text':'开头视频','media':{'videos':[{'id':'asset1','type':'video','duration':12.1,'url':'https://video.twimg.com/test.mp4','format':'video/mp4','formats':[]}]}}
  tail={'type':'status','id':'124','author':first['author'],'replying_to':{'status':'123','screen_name':'example'},'text':'完整串文最后一帖'}
  def page(url,limit,dest):dest.write_text(json.dumps({'code':200,'thread':[first,tail]}));return url
  def video(url,dest,**kw):dest.parent.mkdir(exist_ok=True);dest.write_bytes(b'synthetic');return {'sha256':'a'*64,'bytes':9,'url':url}
  with tempfile.TemporaryDirectory() as temp,patch('scripts.x_provider.fetch_public',side_effect=page),patch('scripts.x_provider.download_media',side_effect=video):
   r=capture('https://x.com/example/status/123',temp);body=(Path(r['directory'])/'article.md').read_text();self.assertEqual(r['status'],'complete');self.assertLess(body.index('视频转写待处理'),body.index('最后一帖'));m=json.loads((Path(r['directory'])/'manifest.json').read_text());self.assertEqual(m['assets'][0]['source_url'],'https://x.com/example/status/123')
