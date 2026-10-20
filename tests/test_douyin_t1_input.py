"""T1 input, metadata and persisted download budget contract."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.douyin_video import metadata, acquire_media, douyin_addresses

ID='7691977131957472558'
URL='https://www.douyin.com/video/'+ID
META={'id':ID,'url':URL,'media_url':'https://media.douyinvod.com/synthetic.mp4','duration':3,'width':1920,'height':1080,'expected_size':1000}

def page(detail, final=URL):
    return lambda _: (final, '<script>window._ROUTER_DATA = '+json.dumps({'detail':detail})+'</script>')

def detail():
    return {'aweme_id':ID,'aweme_type':0,'video':{'duration':3000,'width':640,'height':360,'play_addr':{'url_list':['https://media.douyinvod.com/low.mp4']},'bit_rate':[
        {'bit_rate':1000,'play_addr':{'width':1920,'height':1080,'url_list':['https://media.douyinvod.com/1080.mp4']}},
        {'bit_rate':9000,'play_addr':{'width':3840,'height':2160,'url_list':['https://media.douyinvod.com/4k.mp4']}}]}}

class InputTests(unittest.TestCase):
    def test_short_and_long_links_select_same_highest_allowed_stream(self):
        a=metadata('https://v.douyin.com/Synthetic/',fetch=page(detail()))
        b=metadata(URL,fetch=page(detail()))
        self.assertEqual(a,b);self.assertEqual(a['media_url'],'https://media.douyinvod.com/1080.mp4')

    def test_non_single_targets_and_non_video_metadata_are_rejected(self):
        for final in [URL+'/collection', 'https://www.douyin.com/user/123', 'https://www.douyin.com/live/123']:
            with self.subTest(final=final),self.assertRaises(ValueError):metadata('https://v.douyin.com/Synthetic/',fetch=page(detail(),final))
        slides=detail();slides['images']=[{}]
        with self.assertRaises(ValueError):metadata(URL,fetch=page(slides))
        wrong=detail();wrong['aweme_id']='1111111111111111111'
        with self.assertRaises(ValueError):metadata(URL,fetch=page(wrong))

    def test_metadata_cannot_switch_a_frozen_source_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'metadata.json').write_text(json.dumps(META))
            other={**META,'id':'1111111111111111111','url':'https://www.douyin.com/video/1111111111111111111'}
            with self.assertRaisesRegex(ValueError,'identity'):
                acquire_media(other['url'],root,'compressed',other,download_stream=lambda *a,**k:self.fail('wrong identity downloaded'))

    def test_limits_disk_and_five_attempt_budget_survive_reentry(self):
        def fail(*args,**kwargs):raise OSError('synthetic network interruption')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for n in range(5):
                with self.assertRaisesRegex(OSError,'interruption'):acquire_media(URL,root,'compressed',META,download_stream=fail)
            with self.assertRaisesRegex(ValueError,'budget exhausted'):acquire_media(URL,root,'compressed',META,download_stream=lambda *a,**k:self.fail('sixth attempt'))
        for changed in [{'duration':1801},{'expected_size':1000000000}]:
            with tempfile.TemporaryDirectory() as d,self.assertRaisesRegex(ValueError,'confirmation required'):
                acquire_media(URL,Path(d),'compressed',{**META,**changed},download_stream=lambda *a,**k:self.fail('unconfirmed download'))
        with tempfile.TemporaryDirectory() as d,patch('shutil.disk_usage',return_value=__import__('collections').namedtuple('Usage','total used free')(1000,999,1)):
            with self.assertRaisesRegex(ValueError,'disk space'):acquire_media(URL,Path(d),'compressed',META,download_stream=lambda *a,**k:self.fail('no space'))

    def test_private_dns_targets_rejected_without_cookie_or_proxy_fallback(self):
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaisesRegex(ValueError,'Private|non-public'):douyin_addresses(META['media_url'])

    def test_larger_download_total_updates_pending_scope_and_invalidates_old_approval(self):
        from scripts.attachment_resume import ConfirmationRequired
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old={**META,'expected_size':1100000000}
            def too_large(*args,**kwargs):
                self.assertEqual(kwargs['approved_limit'],1100000000)
                raise ConfirmationRequired('confirmation required',2200000000)
            with self.assertRaises(ConfirmationRequired):acquire_media(URL,root,'compressed',old,approved=True,download_stream=too_large)
            fresh=json.loads((root/'metadata.json').read_text())
            self.assertEqual(fresh['expected_size'],2200000000)
            with self.assertRaisesRegex(ValueError,'confirmation required'):
                acquire_media(URL,root,'compressed',old,approved=True,download_stream=lambda *a,**k:self.fail('stale approval'))
