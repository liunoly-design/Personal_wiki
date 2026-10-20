"""T1 only: generated audiovisual fixture, real FFmpeg, no ASR or Wiki writes."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.douyin_video import acquire_media, prepare_media, ffmpeg, sha

class MediaRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.source = Path(cls.fixture.name)/'fixture.mp4'
        subprocess.run([ffmpeg(), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=960x540:rate=10',
                        '-f', 'lavfi', '-i', r"aevalsrc=if(lt(t\,2)\,0\,0.5*sin(2*PI*880*t))|0.3*sin(2*PI*440*t):s=44100",
                        '-t', '3', '-c:v', 'libx264', '-crf', '10', '-c:a', 'aac', str(cls.source)], check=True)
    @classmethod
    def tearDownClass(cls): cls.fixture.cleanup()

    def test_interrupted_video_preserves_audio_and_frozen_mode_across_processes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'download.mp4'; shutil.copyfile(self.source,source)
            real_run=subprocess.run
            def interrupted(args, **kwargs):
                if '-vf' in args: raise subprocess.TimeoutExpired(args, 1)
                return real_run(args, **kwargs)
            with patch('subprocess.run', side_effect=interrupted):
                with self.assertRaises(subprocess.TimeoutExpired): prepare_media(root,source,'compressed')
            audio=root/'package/audio.m4a'; before=sha(audio); identity=audio.stat().st_ino
            with self.assertRaisesRegex(ValueError,'config|mode'):
                prepare_media(root,source,'original')
            # A separate process must reuse the verified audio and finish the failed video.
            request={'operation':'media','url':'https://www.douyin.com/video/7691977131957472558', 'root':str(root),'mode':'compressed',
                     'metadata':{'id':'7691977131957472558','url':'https://www.douyin.com/video/7691977131957472558','duration':3,'width':960,'height':540,'expected_size':source.stat().st_size}}
            result=real_run([__import__('sys').executable,'scripts/douyin_video.py'],input=json.dumps(request),capture_output=True,text=True,check=True)
            media=json.loads(result.stdout)
            self.assertEqual(sha(audio),before); self.assertEqual(audio.stat().st_ino,identity)
            self.assertLess(media['video']['bytes'],source.stat().st_size)
            self.assertFalse((root/'package/transcript.md').exists())
            # Last-second marker and both channels survive independent full-audio extraction.
            decoded=real_run([ffmpeg(),'-v','error','-i',str(audio),'-ss','2.5','-t','0.3','-f','f32le','-acodec','pcm_f32le','-'],capture_output=True,check=True).stdout
            import array
            samples=array.array('f');samples.frombytes(decoded)
            self.assertGreater(max(abs(x) for x in samples[0::2]),.3)
            self.assertGreater(max(abs(x) for x in samples[1::2]),.15)

    def test_existing_outputs_cannot_be_claimed_as_a_different_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'download.mp4';shutil.copyfile(self.source,source)
            prepare_media(root,source,'original')
            with source.open('ab') as f:f.write(b'changed source')
            with self.assertRaisesRegex(ValueError,'source|Source'):prepare_media(root,source,'original')

    def test_unknown_mode_is_frozen_before_the_first_download_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);meta={'id':'7691977131957472558','url':'https://www.douyin.com/video/7691977131957472558','media_url':'https://media.douyinvod.com/fixture.mp4','duration':3,'width':960,'height':540,'expected_size':1000}
            def interrupted(*args,**kwargs): raise OSError('network interrupted')
            with self.assertRaisesRegex(OSError,'interrupted'):acquire_media(meta['url'],root,'compressed',meta,download_stream=interrupted)
            with self.assertRaisesRegex(ValueError,'config|mode'):acquire_media(meta['url'],root,'original',meta,download_stream=interrupted)

    def test_interrupted_promotion_recovers_verified_stage_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'download.mp4';shutil.copyfile(self.source,source)
            real_replace=Path.replace
            def interrupted(path, target):
                if path.name=='work-audio.m4a':raise OSError('promotion interrupted')
                return real_replace(path,target)
            with patch.object(Path,'replace',interrupted):
                with self.assertRaisesRegex(OSError,'interrupted'):prepare_media(root,source,'compressed')
            self.assertFalse((root/'package/audio.m4a').exists())
            staged_hash=sha(root/'work-audio.m4a')
            result=prepare_media(root,source,'compressed')
            self.assertEqual(result['audio']['sha256'],staged_hash)

    def test_downloaded_playlist_is_not_interpreted_as_other_local_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'download.mp4'
            source.write_text("ffconcat version 1.0\nfile '"+str(self.source)+"'\n")
            with self.assertRaisesRegex(ValueError,'media|Media|container'):prepare_media(root,source,'compressed')
            self.assertFalse((root/'media.json').exists())

    def test_previous_version_interrupted_audio_is_reconciled_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'download.mp4';shutil.copyfile(self.source,source)
            (root/'package').mkdir();audio=root/'package/audio.m4a'
            subprocess.run([ffmpeg(),'-v','error','-i',str(source),'-vn','-c:a','aac','-b:a','128k',str(audio),'-y'],check=True)
            before=sha(audio);inode=audio.stat().st_ino
            result=prepare_media(root,source,'compressed')
            self.assertEqual(result['audio']['sha256'],before)
            self.assertEqual(audio.stat().st_ino,inode)

    def test_actual_duration_requests_new_confirmation_before_conversion(self):
        with tempfile.TemporaryDirectory() as d,patch('scripts.douyin_video.MAX_DURATION_SECONDS',2):
            root=Path(d);source=root/'download.mp4';shutil.copyfile(self.source,source)
            url='https://www.douyin.com/video/7691977131957472558'
            old={'id':'7691977131957472558','url':url,'duration':1,'width':960,'height':540,'expected_size':source.stat().st_size}
            with self.assertRaisesRegex(ValueError,'confirmation required'):acquire_media(url,root,'compressed',old)
            self.assertFalse((root/'package/audio.m4a').exists())
            fresh=json.loads((root/'metadata.json').read_text());self.assertAlmostEqual(fresh['duration'],3,delta=.1)
            with self.assertRaisesRegex(ValueError,'confirmation required'):acquire_media(url,root,'compressed',old,approved=True)
            result=acquire_media(url,root,'compressed',fresh,approved=True,download_stream=lambda *a,**k:self.fail('must reuse source'))
            self.assertEqual(result['source']['sha256'],sha(source))
