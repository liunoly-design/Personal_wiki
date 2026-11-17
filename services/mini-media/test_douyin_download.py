"""Synthetic public source metadata: a failed top rendition can use a lower one."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.src.douyin2text.providers.f2 import F2Source


class DownloadFallbackTests(unittest.TestCase):
    def test_http_cdn_candidates_are_upgraded_without_accepting_other_hosts(self):
        media_id = '7691977131957472558'
        raw = {'aweme_detail': {
            'aweme_id': media_id, 'author': {'nickname': 'Synthetic'},
            'create_time': 1700000000, 'desc': 'Synthetic video',
            'video': {'duration': 3000, 'width': 720, 'height': 1280,
                      'cover': {'url_list': ['http://cover.douyinpic.com/a.jpg']},
                      'bit_rate': [{'gear_name': '720p', 'bit_rate': 500,
                                    'play_addr': {'width': 720, 'height': 1280,
                                                  'url_list': ['http://video.douyinvod.com/a.mp4']}}]}}}
        info = F2Source.normalize(media_id, raw)
        self.assertEqual(info.video_urls, ('https://video.douyinvod.com/a.mp4',))
        self.assertEqual(info.cover_urls, ('https://cover.douyinpic.com/a.jpg',))
        raw['aweme_detail']['video']['bit_rate'][0]['play_addr']['url_list'] = [
            'http://private.invalid/a.mp4']
        with self.assertRaises(ValueError):
            F2Source.normalize(media_id, raw)

    def test_lower_verified_rendition_remains_available_when_top_download_fails(self):
        media_id = '7691977131957472558'
        top = 'https://top.douyinvod.com/video.mp4'
        lower = 'https://lower.douyinvod.com/video.mp4'
        raw = {'aweme_detail': {
            'aweme_id': media_id, 'author': {'nickname': 'Synthetic'},
            'create_time': 1700000000, 'desc': 'Synthetic video',
            'video': {'duration': 3000, 'width': 1080, 'height': 1920,
                      'cover': {'url_list': ['https://cover.douyinpic.com/a.jpg']},
                      'bit_rate': [
                          {'gear_name': 'top', 'bit_rate': 1000,
                           'play_addr': {'width': 1080, 'height': 1920, 'url_list': [top]}},
                          {'gear_name': 'lower', 'bit_rate': 500,
                           'play_addr': {'width': 720, 'height': 1280, 'url_list': [lower]}},
                      ]}}}
        info = F2Source.normalize(media_id, raw)
        self.assertEqual(info.video_urls, (top, lower))
        self.assertEqual([v['gear'] for v in info.selection['variants']], ['top', 'lower'])

        async def check():
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'video.mp4'
                attempted = []

                async def fake_fetch(url, destination, headers):
                    attempted.append(url)
                    if url == top:
                        request = httpx.Request('GET', url)
                        raise httpx.HTTPStatusError('unavailable rendition', request=request,
                                                    response=httpx.Response(400, request=request))
                    destination.write_bytes(b'synthetic lower rendition')

                with patch('backend.src.douyin2text.pipeline.fetch', fake_fetch):
                    from backend.src.douyin2text.pipeline import fetch_candidates
                    selected = await fetch_candidates(info.video_urls, path, {})
                self.assertEqual(selected, lower)
                self.assertEqual(attempted, [top, lower])
                self.assertEqual(path.read_bytes(), b'synthetic lower rendition')

                class SyntheticSource:
                    name = 'synthetic'
                    async def resolve_id(self, url):
                        return media_id
                    async def describe(self, resolved, max_short_edge=1080):
                        return info
                    def headers(self):
                        return {}

                class StopAtProbe(Exception):
                    pass

                from backend.src.douyin2text import pipeline
                with patch.object(pipeline, 'fetch', fake_fetch), patch.object(
                        pipeline, 'probe', side_effect=StopAtProbe):
                    with self.assertRaises(StopAtProbe):
                        await pipeline.process(
                            {'id': 'synthetic-job', 'url': f'https://www.douyin.com/video/{media_id}'},
                            lambda stage, **details: None,
                            source=SyntheticSource(), transcriber=object())
                selection = json.loads((pipeline.DATA / 'metadata' /
                                        f'{media_id}.selection.json').read_text())
                self.assertEqual(selection['gear'], 'lower')
                self.assertEqual(selection['downloaded_id'], media_id)
                saved_video = (pipeline.DATA / 'video' / f'{media_id}.mp4').read_bytes()
                with (patch.object(pipeline, 'fetch', side_effect=AssertionError('redownloaded')),
                      patch.object(pipeline, 'probe', side_effect=StopAtProbe)):
                    with self.assertRaises(StopAtProbe):
                        await pipeline.process(
                            {'id': 'synthetic-job', 'url': f'https://www.douyin.com/video/{media_id}'},
                            lambda stage, **details: None,
                            source=SyntheticSource(), transcriber=object())
                self.assertEqual((pipeline.DATA / 'video' / f'{media_id}.mp4').read_bytes(), saved_video)

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text(json.dumps({'asr_fingerprint': 'synthetic'}))
            with patch.dict(os.environ, {'DOUYIN2TEXT_CONFIG': str(config),
                                         'DOUYIN2TEXT_DATA_DIR': directory}):
                asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
