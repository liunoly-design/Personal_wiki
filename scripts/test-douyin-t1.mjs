// Offline T1 contract: generated media and synthetic network/message boundaries only.
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
const cwd=resolve(import.meta.dirname,'..');
const checks=[
 [process.env.WIKI_TEST_PYTHON??'python3',['-m','unittest','-v',
  'tests.test_douyin_t1_input','tests.test_douyin_t1_download','tests.test_douyin_t1_media',
  'tests.test_douyin.DouyinMediaTests.test_complete_audio_and_compressed_video_preserve_duration_and_do_not_upscale',
  'tests.test_douyin.DouyinMediaTests.test_original_quality_retains_exact_source_bytes',
  'tests.test_douyin.DouyinMediaTests.test_portrait_1080p_compresses_to_720p_short_edge_and_restore_preserves_hashes',
  'tests.test_douyin.DouyinMediaTests.test_expired_stream_refreshes_only_same_verified_video_without_replaying_download',
  'tests.test_douyin.DouyinMediaTests.test_approved_old_size_never_authorizes_larger_refreshed_metadata',
  'tests.test_attachment_resume']],
 [process.execPath,['--test','--test-name-pattern=mode|authenticated record ingress|oversized',
  'test/douyin.test.js','test/remote-douyin.test.js']],
];
for(const [command,args] of checks){
 const result=spawnSync(command,args,{cwd,stdio:'inherit'});
 if(result.error){console.error(result.error.message);process.exit(1);}
 if(result.status!==0)process.exit(result.status??1);
}
