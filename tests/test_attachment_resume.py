import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

class AttachmentResumeTest(unittest.TestCase):
 def test_selected_failed_image_resume_preserves_successful_files_and_body(self):
  from scripts.attachment_resume import resume_assets, identify
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'images').mkdir();(root/'images/good.jpg').write_bytes(b'original');(root/'article.md').write_text('正文')
   good=dict(kind='image',url='https://pbs.twimg.com/good.jpg',path='images/good.jpg',status='downloaded')
   bad=identify(dict(kind='image',url='https://pbs.twimg.com/bad.jpg',path='images/bad.jpg',status='failed'), 'https://x.com/a/status/1')
   (root/'manifest.json').write_text(json.dumps(dict(source_url='https://x.com/a/status/1',assets=[good,bad])))
   def fetch(url,dest,**kwargs):dest.write_bytes(b'recovered')
   with patch('scripts.attachment_resume.download',side_effect=fetch):result=resume_assets(root,bad['id'],{})
   self.assertEqual(result['status'],'complete');self.assertEqual((root/'images/good.jpg').read_bytes(),b'original');self.assertEqual((root/'article.md').read_text(),'正文');self.assertEqual((root/'images/bad.jpg').read_bytes(),b'recovered')
 def test_long_video_requires_exact_fingerprint_and_never_allows_high_resolution(self):
  from scripts.attachment_resume import resume_assets, identify
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   asset=identify(dict(kind='video',url='https://video.twimg.com/long.mp4',path='videos/long.mp4',status='waiting',duration=1900,width=1920,height=1080), 'https://x.com/a/status/1')
   (root/'manifest.json').write_text(json.dumps(dict(source_url='https://x.com/a/status/1',assets=[asset])))
   with patch('scripts.attachment_resume.download') as net:
    result=resume_assets(root,asset['id'],{});self.assertEqual(result['missingAssets'][0]['status'],'waiting_confirmation');net.assert_not_called()
    result=resume_assets(root,asset['id'],{asset['id']:{'fingerprint':'wrong'}});net.assert_not_called()
    asset.update(width=3840,height=2160);asset=identify(asset,'https://x.com/a/status/1');(root/'manifest.json').write_text(json.dumps(dict(source_url='https://x.com/a/status/1',assets=[asset])))
    result=resume_assets(root,asset['id'],{asset['id']:{'fingerprint':asset['fingerprint']}});self.assertEqual(result['missingAssets'][0]['status'],'waiting_metadata');net.assert_not_called()

 def test_unknown_length_stops_at_threshold_then_resumes_only_with_matching_etag(self):
  from scripts.attachment_resume import download, ConfirmationRequired
  import io
  responses=[];requests=[]
  class Response:
   def __init__(self,status,data,headers):self.status=status;self.data=io.BytesIO(data);self.headers=headers
   def getheader(self,key):return self.headers.get(key)
   def read(self,n):return self.data.read(n)
  class Connection:
   def __init__(self,*args):pass
   def request(self,*args,**kwargs):requests.append(kwargs.get('headers',{}))
   def getresponse(self):return responses.pop(0)
   def close(self):pass
  with tempfile.TemporaryDirectory() as temp,patch('scripts.attachment_resume.public_addresses',return_value=(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit('https://video.twimg.com/a.mp4'),['8.8.8.8'])),patch('scripts.attachment_resume.PinnedHTTPS',Connection):
   dest=Path(temp)/'video.mp4';responses.append(Response(200,b'abcdefghij',{'ETag':'"same"'}))
   with self.assertRaises(ConfirmationRequired):download('https://video.twimg.com/a.mp4',dest,limit=5)
   self.assertFalse(dest.exists());self.assertEqual(dest.with_suffix('.mp4.part').read_bytes(),b'abcde')
   responses.append(Response(206,b'fghij',{'ETag':'"same"','Content-Range':'bytes 5-9/10','Content-Length':'5'}));download('https://video.twimg.com/a.mp4',dest,limit=5,approved=True)
   self.assertEqual(dest.read_bytes(),b'abcdefghij');self.assertEqual(requests[-1]['Range'],'bytes=5-')
 def test_preflight_length_stops_before_body_and_changed_validator_cannot_append(self):
  from scripts.attachment_resume import download, ConfirmationRequired
  import io
  response=type('Response',(),{'status':200,'getheader':lambda self,k:{'Content-Length':'11'}.get(k),'read':lambda self,n:(_ for _ in ()).throw(AssertionError('body read before confirmation'))})()
  connection=type('Connection',(),{'request':lambda *args,**kwargs:None,'getresponse':lambda self:response,'close':lambda self:None})()
  with tempfile.TemporaryDirectory() as temp,patch('scripts.attachment_resume.public_addresses',return_value=(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit('https://video.twimg.com/a.mp4'),['8.8.8.8'])),patch('scripts.attachment_resume.PinnedHTTPS',return_value=connection):
   with self.assertRaises(ConfirmationRequired):download('https://video.twimg.com/a.mp4',Path(temp)/'video.mp4',limit=10)

 def test_failed_video_metadata_can_recover_without_fetching_article(self):
  from scripts.attachment_resume import resume_assets,identify
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);asset=identify(dict(kind='video',url='https://x.com/a/status/1',post_url='https://x.com/a/status/1',path='videos/recovered.mp4',status='waiting_metadata'),'https://x.com/a/status/1');(root/'manifest.json').write_text(json.dumps(dict(source_url='https://x.com/a/status/1',assets=[asset])))
   info=dict(duration=20,formats=[dict(url='https://video.twimg.com/recovered.mp4',ext='mp4',width=1920,height=1080,vcodec='h264')])
   with patch('scripts.media_download.extract_public',return_value=info),patch('scripts.attachment_resume.download',side_effect=lambda url,dest,**kwargs:dest.write_bytes(b'video')),patch('scripts.attachment_resume.verify_video'):
    result=resume_assets(root,asset['id'],{})
   self.assertEqual(result['status'],'complete');self.assertEqual((root/'videos/recovered.mp4').read_bytes(),b'video')

 def test_changed_etag_discards_only_resume_marker_then_restarts_failed_attachment(self):
  from scripts.attachment_resume import download
  import io
  responses=[];requests=[]
  class Response:
   def __init__(self,status,data,headers):self.status=status;self.data=io.BytesIO(data);self.headers=headers
   def getheader(self,k):return self.headers.get(k)
   def read(self,n):return self.data.read(n)
  class Connection:
   def __init__(self,*args):pass
   def request(self,*args,**kwargs):requests.append(kwargs.get('headers',{}))
   def getresponse(self):return responses.pop(0)
   def close(self):pass
  with tempfile.TemporaryDirectory() as temp,patch('scripts.attachment_resume.public_addresses',return_value=(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit('https://video.twimg.com/a.mp4'),['8.8.8.8'])),patch('scripts.attachment_resume.PinnedHTTPS',Connection):
   dest=Path(temp)/'video.mp4';partial=dest.with_suffix('.mp4.part');partial.write_bytes(b'old');progress=partial.with_suffix('.part.json');progress.write_text(json.dumps(dict(url='https://video.twimg.com/a.mp4',validator='"old"')))
   responses.append(Response(206,b'new',{'ETag':'"new"','Content-Range':'bytes 3-5/6'}))
   with self.assertRaises(ValueError):download('https://video.twimg.com/a.mp4',dest,approved=True)
   self.assertEqual(partial.read_bytes(),b'old');self.assertFalse(progress.exists())
   responses.append(Response(200,b'replacement',{'ETag':'"new"','Content-Length':'11'}));download('https://video.twimg.com/a.mp4',dest,approved=True)
   self.assertNotIn('Range',requests[-1]);self.assertEqual(dest.read_bytes(),b'replacement')
