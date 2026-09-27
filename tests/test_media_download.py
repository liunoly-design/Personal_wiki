import unittest
from scripts.media_download import video_assets

class MediaTest(unittest.TestCase):
 def test_selects_1080p_before_downloading_and_stops_large_unknown_or_long(self):
  formats=[dict(url='https://video.twimg.com/720.mp4',ext='mp4',protocol='https',vcodec='h264',width=1280,height=720),dict(url='https://video.twimg.com/1080.mp4',ext='mp4',protocol='https',vcodec='h264',width=1920,height=1080),dict(url='https://video.twimg.com/4k.mp4',ext='mp4',protocol='https',vcodec='h264',width=3840,height=2160)]
  self.assertEqual(video_assets(dict(duration=30,formats=formats))[0]['url'],'https://video.twimg.com/1080.mp4')
  self.assertEqual(video_assets(dict(duration=1801,formats=formats))[0]['status'],'waiting')
  self.assertEqual(video_assets(dict(formats=formats))[0]['status'],'waiting')
  for f in formats:f['filesize']=1000000001
  self.assertEqual(video_assets(dict(duration=30,formats=formats))[0]['status'],'waiting')
 def test_mp4_probe_extracts_duration_and_dimensions_and_rejects_incomplete(self):
  import struct
  from scripts.media_download import mp4_metadata, direct_video_asset
  def box(kind,payload):return struct.pack('>I4s',len(payload)+8,kind)+payload
  movie=box(b'mvhd',bytes(12)+struct.pack('>II',1000,42000))
  track=box(b'trak',box(b'tkhd',bytes(76)+struct.pack('>II',1920*65536,1080*65536)))
  data=box(b'moov',movie+track)
  self.assertEqual(mp4_metadata([b'prefix'+data]),(42,1920,1080))
  with self.assertRaises(ValueError):mp4_metadata([data[:30]])
  with self.assertRaises(ValueError):direct_video_asset('https://localhost/private.mp4')
