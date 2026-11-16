import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class XiaohongshuCaptureTest(unittest.TestCase):
 def test_mobile_detail_is_complete_but_preload_cards_are_not(self):
  from scripts.xiaohongshu_capture import capture
  target='64abcdef0123456789abcdef'
  note={'noteId':target,'type':'normal','desc':'移动页完整详情的第一段。\n这是末段。','imageList':[]}
  for full in [True,False]:
   mobile={'hasError':False,'data':{'noteData':note} if full else {},'normalNotePreloadData':{'desc':'预览'}}
   def fetch(url,limit,dest,**kwargs):dest.write_text('<script>window.__INITIAL_STATE__='+json.dumps({'noteData':mobile})+'</script>');return url
   with tempfile.TemporaryDirectory() as temp,patch('scripts.xiaohongshu_capture.fetch_public',side_effect=fetch):
    if full:
     result=capture('https://www.xiaohongshu.com/explore/'+target,temp);self.assertEqual(result['status'],'complete');self.assertIn('这是末段',(Path(result['directory'])/'article.md').read_text())
    else:
     with self.assertRaisesRegex(ValueError,'identity'):capture('https://www.xiaohongshu.com/explore/'+target,temp)
 def test_wrong_note_preview_and_truncated_state_never_become_complete(self):
  from scripts.xiaohongshu_capture import capture
  target='64abcdef0123456789abcdef'
  pages=[('<meta property="og:description" content="只有摘要">','full note state'),('<script>window.__INITIAL_STATE__={"note":','truncated'),('<script>window.__INITIAL_STATE__={"note":{"noteDetailMap":{"other":{"note":{"noteId":"other"}}}}}</script>','identity')]
  for html,reason in pages:
   def fetch(url,limit,dest,**kwargs):dest.write_text(html);return url
   with tempfile.TemporaryDirectory() as temp,patch('scripts.xiaohongshu_capture.fetch_public',side_effect=fetch):
    with self.assertRaisesRegex(ValueError,reason):capture('https://www.xiaohongshu.com/explore/'+target,temp)
 def test_short_share_resolves_target_and_video_or_missing_image_stays_partial(self):
  from scripts.xiaohongshu_capture import capture
  target='64abcdef0123456789abcdef';url='https://www.xiaohongshu.com/discovery/item/'+target+'?xsec_token=synthetic'
  for kind in ['normal','video']:
   note={'noteId':target,'type':kind,'desc':'视频说明不能代替完整转写。','imageList':[{'urlDefault':'https://example.org/unavailable'}]}
   html='<script>window.__INITIAL_STATE__='+json.dumps({'note':{'noteDetailMap':{target:{'note':note}}}})+'</script>'
   def fetch(remote,limit,dest,**kwargs):
    if remote.startswith('https://example.org'):raise OSError('missing image')
    dest.write_text(html);return url
   with tempfile.TemporaryDirectory() as temp,patch('scripts.xiaohongshu_capture.fetch_public',side_effect=fetch):
    result=capture('https://xhslink.cn/o/synthetic',temp);self.assertEqual(result['status'],'partial');self.assertEqual(result['url'],'https://www.xiaohongshu.com/explore/'+target)
    if kind=='video':self.assertTrue(any(a['kind']=='video' for a in result['missingAssets']))
 def test_single_note_keeps_full_text_and_ordered_images_without_executing_state(self):
  from scripts.xiaohongshu_capture import capture
  note_id='64abcdef0123456789abcdef'
  note={'noteId':note_id,'type':'normal','title':'图文笔记','desc':'第一段包含 undefined 字样。\n最后一段完整证据。','user':{'nickname':'作者'},'imageList':[{'urlDefault':'https://images.example.org/second'},{'urlDefault':'https://images.example.org/first'}]}
  html='<script>window.__INITIAL_STATE__='+json.dumps({'note':{'noteDetailMap':{note_id:{'note':note}}}},ensure_ascii=False)[:-1]+',"unused":undefined}</script>'
  def fetch(url,limit,dest,**kwargs):
   dest.write_bytes(html.encode() if 'xiaohongshu.com' in url else b'\xff\xd8\xffsynthetic-image');return url
  with tempfile.TemporaryDirectory() as temp,patch('scripts.xiaohongshu_capture.fetch_public',side_effect=fetch):
   result=capture('https://www.xiaohongshu.com/explore/'+note_id+'?xsec_token=synthetic',temp)
   package=Path(result['directory']);body=(package/'article.md').read_text();metadata=json.loads((package/'metadata.json').read_text())
   self.assertEqual(result['status'],'complete');self.assertIn('第一段包含 undefined 字样。',body);self.assertIn('最后一段完整证据。',body)
   self.assertEqual([a['url'] for a in metadata['assets']],['https://images.example.org/second','https://images.example.org/first'])
   self.assertLess(body.index('image-001.jpg'),body.index('image-002.jpg'));self.assertNotIn('xsec_token',body)
   self.assertTrue((package/'original.html').exists());self.assertTrue((package/'initial-state.json').exists())
