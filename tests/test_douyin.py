import tempfile
import unittest
from pathlib import Path
from scripts.douyin_video import prepare_media, media_probe, ffmpeg, clean_verified
import subprocess

class DouyinMediaTests(unittest.TestCase):
    def test_complete_audio_and_compressed_video_preserve_duration_and_do_not_upscale(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'source.mp4'
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','testsrc2=size=960x540:rate=10','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','3','-c:v','libx264','-crf','10','-c:a','aac',str(source)],check=True)
            result=prepare_media(root,source,'compressed')
            self.assertEqual(result['video']['width'],960)
            self.assertEqual(result['video']['height'],540)
            self.assertLess(result['video']['bytes'],source.stat().st_size)
            self.assertAlmostEqual(result['audio']['duration'],3,delta=.15)
            self.assertTrue(source.exists())
            self.assertEqual(prepare_media(root,source,'compressed'),result)

    def test_cleanup_requires_verified_publication_and_refuses_changed_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'download.mp4'
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=10','-f','lavfi','-i','sine','-t','2','-c:v','libx264','-crf','10','-c:a','aac',str(source)],check=True)
            prepare_media(root,source,'compressed')
            with self.assertRaisesRegex(ValueError,'verification'):clean_verified(root)
            original=source.read_bytes();source.unlink();source.write_bytes(original)
            with self.assertRaisesRegex(ValueError,'identity'):clean_verified(root,True)
            self.assertTrue((root/'package/video.mp4').exists())

    def test_original_quality_retains_exact_source_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'download.mp4'
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=10','-f','lavfi','-i','sine','-t','2','-c:v','libx264','-c:a','aac',str(source)],check=True)
            r=prepare_media(root,source,'original')
            self.assertEqual(r['source']['sha256'],r['video']['sha256'])
            self.assertEqual(clean_verified(root,True)['status'],'retained_original')
            self.assertTrue(source.exists())

    def test_segment_success_is_durable_and_unknown_result_requires_explicit_recovery(self):
        from scripts.douyin_video import transcribe_audio
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'package').mkdir()
            audio=root/'package/audio.m4a'
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','sine','-t','3','-c:a','aac',str(audio)],check=True)
            calls=[]
            def backend(path):calls.append(path);return {'text':'嗯，不应该删除否定词，最后一句完整。'}
            result=transcribe_audio(root,backend=backend)
            self.assertIn('最后一句完整',Path(result['transcript']).read_text())
            self.assertEqual(transcribe_audio(root,backend=lambda _:self.fail('success must be reused')),result)
            self.assertEqual(len(calls),1)

    def test_unknown_cloud_result_is_not_automatically_replayed_after_restart(self):
        from scripts.douyin_video import transcribe_audio, ASRFailure
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'package').mkdir()
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','sine','-t','1','-c:a','aac',str(root/'package/audio.m4a')],check=True)
            def unknown(_):raise ASRFailure('ASR unknown cloud result: timeout',True)
            with self.assertRaises(ASRFailure):transcribe_audio(root,backend=unknown)
            with self.assertRaisesRegex(ASRFailure,'explicit continue'):transcribe_audio(root,backend=lambda _:self.fail('must not replay'))
            result=transcribe_audio(root,backend=lambda _:{'text':'最后一段。'},recovery=True)
            self.assertIn('最后一段',Path(result['transcript']).read_text())

    def test_cleanup_is_idempotent_and_never_touches_formal_audio_or_human_notes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'download.mp4'
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=10','-f','lavfi','-i','sine','-t','2','-c:v','libx264','-crf','10','-c:a','aac',str(source)],check=True)
            prepare_media(root,source,'compressed');note=root/'package/human-correction.md';note.write_text('保留，人工校订。')
            r=clean_verified(root,True);self.assertEqual(clean_verified(root,True),r)
            self.assertFalse(source.exists());self.assertTrue((root/'package/audio.m4a').exists());self.assertEqual(note.read_text(),'保留，人工校订。')

    def test_input_paths_and_metadata_redirects_cannot_expand_to_profiles_or_private_urls(self):
        from scripts.douyin_video import source_url,check_url
        for url in ['https://www.douyin.com/user/private','https://127.0.0.1/video/1234567890','file:///etc/passwd','https://user:pass@www.douyin.com/video/1234567890','https://www.douyin.com.evil.test/video/1234567890']:
            with self.assertRaises(ValueError):source_url(url)
        with self.assertRaises(ValueError):check_url('https://localhost/video.mp4',True)

    def test_five_call_asr_budget_survives_explicit_recovery_and_process_reentry(self):
        from scripts.douyin_video import transcribe_audio, ASRFailure
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'package').mkdir()
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','sine','-t','1','-c:a','aac',str(root/'package/audio.m4a')],check=True)
            calls=[]
            def unavailable(_):calls.append(1);raise ASRFailure('ASR backend HTTP 503')
            for _ in range(5):
                with self.assertRaises(ASRFailure):transcribe_audio(root,backend=unavailable)
            with self.assertRaisesRegex(ASRFailure,'budget exhausted'):transcribe_audio(root,backend=unavailable,recovery={'messageId':'continue'})
            self.assertEqual(len(calls),5)

    def test_empty_voiced_response_is_partial_but_silence_does_not_invent_words(self):
        from scripts.douyin_video import transcribe_audio, ASRFailure
        for silent in [False,True]:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);(root/'package').mkdir()
                subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','anullsrc=r=16000:cl=mono' if silent else 'sine','-t','1','-c:a','aac',str(root/'package/audio.m4a')],check=True)
                if silent:
                    result=transcribe_audio(root,backend=lambda _:self.fail('silent segment must not upload'))
                    self.assertIn('静音段',Path(result['transcript']).read_text())
                else:
                    with self.assertRaisesRegex(ASRFailure,'empty voiced'):transcribe_audio(root,backend=lambda _:{'text':''})
                    self.assertFalse((root/'package/transcript.md').exists())

    def test_portrait_1080p_compresses_to_720p_short_edge_and_restore_preserves_hashes(self):
        from scripts.douyin_video import sha
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);work=root/'work';work.mkdir();source=work/'download.mp4'
            subprocess.run([ffmpeg(),'-v','error','-f','lavfi','-i','testsrc2=size=1080x1920:rate=5','-f','lavfi','-i','sine','-t','1','-c:v','libx264','-crf','12','-c:a','aac',str(source)],check=True)
            result=prepare_media(work,source,'compressed');self.assertEqual((result['video']['width'],result['video']['height']),(720,1280))
            clean_verified(work,True);shutil.copytree(work/'package',root/'restored')
            for name,key in [('video.mp4','video'),('audio.m4a','audio')]:self.assertEqual(sha(root/'restored'/name),result[key]['sha256'])
            self.assertFalse(source.exists())

    def test_cleanup_rejects_symlink_and_other_jobs_even_with_a_tampered_manifest(self):
        from scripts.douyin_video import freeze_file
        import json
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'media.json').write_text('{"mode":"compressed"}');target=root/'human.md';target.write_text('keep')
            entry=freeze_file(root,target);(root/'cleanup.json').write_text(json.dumps({'files':[entry],'deleted':[]}))
            with self.assertRaisesRegex(ValueError,'Unsafe cleanup'):clean_verified(root,True)
            target.rename(root/'download.mp4');entry=freeze_file(root,root/'download.mp4');(root/'download.mp4').unlink();(root/'download.mp4').symlink_to(target)
            (root/'cleanup.json').write_text(json.dumps({'files':[entry],'deleted':[]}))
            with self.assertRaisesRegex(ValueError,'symlink'):clean_verified(root,True)
            self.assertTrue((root/'download.mp4').is_symlink())

    def test_public_single_video_metadata_keeps_source_and_download_url_distinct(self):
        from scripts.douyin_video import metadata
        import json
        vid='7691977131957472558';detail={'aweme_id':vid,'desc':'平台标题','author':{'nickname':'作者'},'video':{'duration':3000,'width':1920,'height':1080,'play_addr':{'url_list':['https://media.douyinvod.com/video.mp4'],'data_size':1000}}}
        def public_page(url):return ('https://www.iesdouyin.com/share/video/'+vid+'/', '<script>window._ROUTER_DATA = '+json.dumps({'detail':detail})+'</script>')
        result=metadata('https://v.douyin.com/Example/',fetch=public_page)
        self.assertEqual(result['url'],'https://www.douyin.com/video/'+vid)
        self.assertEqual(result['media_url'],'https://media.douyinvod.com/video.mp4')
        self.assertEqual(result['duration'],3)

    def test_expired_stream_refreshes_only_same_verified_video_without_replaying_download(self):
        from scripts.douyin_video import acquire_media
        import json
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);meta={'id':'7691977131957472558','url':'https://www.douyin.com/video/7691977131957472558','media_url':'https://media.douyinvod.com/expired.mp4','duration':1,'width':320,'height':240,'expected_size':1000};calls=[]
            def expired(url,*args,**kwargs):calls.append(url);raise OSError('HTTP 410')
            fresh={**meta,'media_url':'https://media.douyinvod.com/refreshed.mp4'}
            with self.assertRaisesRegex(OSError,'address refreshed'):acquire_media(meta['url'],root,'compressed',meta,fetch_metadata=lambda _:fresh,download_stream=expired)
            self.assertEqual(len(calls),1)
            self.assertEqual(json.loads((root/'metadata.json').read_text())['media_url'],fresh['media_url'])
            self.assertEqual(json.loads((root/'download-state.json').read_text())['attempts'],1)

    def test_interrupted_publication_link_reconciles_only_archive_inode(self):
        from scripts.publish_bundle import publish
        import os
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);vault=root/'vault';package=root/'package';vault.mkdir();package.mkdir()
            (package/'video.mp4').write_bytes(b'fixture-video');(package/'audio.m4a').write_bytes(b'fixture-audio')
            request={'operation':'douyin-media','vault':str(vault),'directory':str(package),'videoId':'7691977131957472558','mode':'compressed','media':{'version':'fixture'}}
            first=publish(request);archive=vault/'raw/assets/douyin-7691977131957472558/compressed/video.mp4'
            os.link(archive,package/'.shared-video.mp4')
            self.assertEqual(publish(request),first)
            self.assertFalse((package/'.shared-video.mp4').exists())
            (package/'.shared-video.mp4').write_bytes(b'other-owner')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):publish(request)
            self.assertEqual(archive.read_bytes(),b'fixture-video')

    def test_approved_old_size_never_authorizes_larger_refreshed_metadata(self):
        from scripts.douyin_video import acquire_media
        import json
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old={'id':'7691977131957472558','url':'https://www.douyin.com/video/7691977131957472558','media_url':'https://media.douyinvod.com/old.mp4','duration':1,'width':320,'height':240,'expected_size':1_100_000_000}
            fresh={**old,'expected_size':2_200_000_000,'media_url':'https://media.douyinvod.com/new.mp4'};(root/'metadata.json').write_text(json.dumps(fresh))
            calls=[]
            def download(*args,**kwargs):calls.append(kwargs.get('approved'));raise OSError('must not download using stale approval')
            with self.assertRaisesRegex(ValueError,'confirmation required'):acquire_media(old['url'],root,'compressed',old,approved=True,download_stream=download)
            self.assertEqual(calls,[])
