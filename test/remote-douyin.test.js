import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCommand} from '../src/wk.js';

test('complete Douyin share extracts URL and preserves share text separately from explicit notes',()=>{
 const text='小婕 wk 记录：8.46 复制打开抖音，看看【evan.的作品】Claude Code 的工程师刚发布了一段 28... https://v.douyin.com/emjiIYoJWK8/ 02/28 :1pm y@G.VY pDU:/\n备注：关注工程实践';
 const parsed=parseCommand(text);
 assert.equal(parsed.items[0].url,'https://v.douyin.com/emjiIYoJWK8/');assert.equal(parsed.background,'关注工程实践');assert.match(parsed.shareText,/8.46 复制打开抖音/);
});
import {createServer} from 'node:http';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath,readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {collectCanonical} from '../src/canonical-library.js';

test('remote video publishes Chinese sentences, keeps original separately, resumes and protects human edits',async t=>{
 const root=await mkdtemp(join(await realpath(tmpdir()),'remote-wiki-'));t.after(()=>rm(root,{recursive:true,force:true}));
 const vault=join(root,'vault');await mkdir(vault);const token=join(root,'token');await writeFile(token,'fixture-token',{mode:0o600});
 let body='# 合成公开视频\n\n## 完整中文译文（本地机器翻译）\n\n[00:00] 完整末尾凤凰校验。\n\n## 完整原始转写（english）\n\n[00:00] Complete original.\n';
 const manifest={api_version:'1',job_id:'remote_1',source:{platform:'douyin',id:'7691977131957472558',url:'https://www.douyin.com/video/7691977131957472558',title:'合成视频',author:'合成作者',published_at:null,duration_seconds:3},transcription:{engine:'whisper.cpp',model:'small',model_sha256:'a'.repeat(64),language:'en'},translation:{kind:'derived_machine_translation',source_language:'en',target_language:'zh',model:'synthetic',model_sha256:'b'.repeat(64),coverage:{source_segments:1,all_source_segments_present:true}},markdown:{sha256:createHash('sha256').update(body).digest('hex')},media:Object.fromEntries(['video','audio','cover'].map(kind=>[kind,{path:'/v1/media/'+kind+'_1/'+kind,sha256:'c'.repeat(64),bytes:1000,mime:{video:'video/mp4',audio:'audio/mp4',cover:'image/jpeg'}[kind]}]))};
 let submissions=0,modelCalls=0,searchOffline=true;
 const server=createServer(async(req,res)=>{
  assert.equal(req.headers.authorization,'Bearer fixture-token');
  if(req.url==='/v1/jobs'){submissions++;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({api_version:'1',job_id:'remote_1',status:'succeeded',reused:false}));return;}
  if(req.url.endsWith('/markdown')){res.setHeader('Content-Type','text/markdown');res.end(body);return;}
  if(req.url.startsWith('/v1/media/')){if(!Object.values(manifest.media).some(m=>m.path===req.url)){res.writeHead(404);res.end();return;}res.writeHead(206,{'Content-Range':'bytes 0-15/1000'});res.end('0123456789abcdef');return;}
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify(req.url.endsWith('/manifest')?manifest:{api_version:'1',job_id:'remote_1',status:'succeeded'}));
 });await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));
 const options={url:'https://v.douyin.com/Example/',mediaServiceUrl:`http://127.0.0.1:${server.address().port}`,mediaServiceTokenFile:token,vault,stateDir:join(root,'state'),workspace:join(root,'work'),python:'/usr/bin/python3',pipeline:async()=>{throw Error('Local backend must not run');},translate:async()=>{throw Error('Already translated remote text must not be translated again');},flash:{extract:async()=>({slug:'remote-video-example',terms:[]}),explain:async()=>[]},generate:async({stage})=>{modelCalls++;return stage==='analysis'?'分析':'---FILE: wiki/sources/remote-video-example.md---\n# 资料卡\n来源摘要。\n---END FILE---';},api:{read:path=>readFile(join(vault,path),'utf8'),search:async()=>({results:searchOffline?[]:[{path:'wiki/sources/remote-video-example.md'}]})}};
 await assert.rejects(collectCanonical(options),/search verification failed/);const afterFailure=modelCalls;searchOffline=false;
 const result=await collectCanonical(options);assert.equal(modelCalls,afterFailure);assert.equal(submissions,1);
 assert.equal(result.status,'complete');assert.equal(result.video.mode,'remote');assert.equal(result.video.remoteJobId,'remote_1');
 const page=await readFile(result.source,'utf8');assert.match(page,/完整末尾凤凰校验/);assert.doesNotMatch(page,/Complete original/);assert.match(page,/完整原始转写与来源资料/);
 const rawTranscript=await readFile(join(vault,'raw/assets',result.sourceId,'transcript.md'),'utf8');assert.match(rawTranscript,/Complete original/);assert.match(rawTranscript,/完整末尾凤凰校验/);
 assert.ok(!JSON.stringify(result).includes('fixture-token'));
 await writeFile(result.source,page+'\n人工校订保留。');const before=modelCalls;
 const again=await collectCanonical({...options,workspace:join(root,'work2')});assert.equal(again.source,result.source);assert.equal(submissions,1);assert.equal(modelCalls,before);assert.match(await readFile(result.source,'utf8'),/人工校订保留/);
 const assets=await readdir(join(vault,'raw/assets',result.sourceId));assert.ok(!assets.some(name=>/\.(mp4|m4a|wav)$/.test(name)));
 body=body.replace('[00:00] Complete original.','[00:00] Complete original.\n\n[00:02] Second original sentence.');manifest.translation.coverage.source_segments=2;
 manifest.markdown.sha256=createHash('sha256').update(body).digest('hex');
 await assert.rejects(collectCanonical({...options,workspace:join(root,'work3')}),/Chinese sentence alignment incomplete/);
 assert.equal(submissions,1);assert.equal(modelCalls,before);
 body='# 合成公开视频\n\n## 完整中文译文（本地机器翻译）\n\n[00:00] 完整末尾凤凰校验。\n\n## 完整原始转写（english）\n\n[00:00] Complete original.\n\n## 完整原始转写（english）\n\n[00:00] Conflicting original.\n';manifest.translation.coverage.source_segments=1;manifest.markdown.sha256=createHash('sha256').update(body).digest('hex');
 await assert.rejects(collectCanonical({...options,workspace:join(root,'ambiguous-work')}),/original transcript section missing or ambiguous/);
 body='# 合成公开视频\n\n## 完整中文译文（本地机器翻译）\n\n[00:00]   \n\n没有时间戳的中文摘要。\n\n## 完整原始转写（english）\n\n[00:00] Complete original.\n';manifest.markdown.sha256=createHash('sha256').update(body).digest('hex');
 await assert.rejects(collectCanonical({...options,workspace:join(root,'empty-segment-work')}),/Chinese timestamped transcript missing/);
 body='# 合成公开视频\n\n## 完整中文译文（本地机器翻译）\n\n[00:00] 完整末尾凤凰校验。\n\n## 完整原始转写（english）\n\n[00:00]    \n';manifest.markdown.sha256=createHash('sha256').update(body).digest('hex');
 await assert.rejects(collectCanonical({...options,workspace:join(root,'empty-original-work')}),/original timestamped transcript missing/);
 body='# 合成公开视频\n\n## 完整原始转写（english）\n\n[00:00] Complete original.\n';manifest.markdown.sha256=createHash('sha256').update(body).digest('hex');
 await assert.rejects(collectCanonical({...options,workspace:join(root,'work4')}),/Chinese transcript section missing/);
 assert.match(await readFile(result.source,'utf8'),/人工校订保留/);
});

test('share URL extraction trims adjacent closing punctuation and deduplicates copied links',()=>{
 const p=parseCommand('小婕 wk 记录：复制打开抖音 https://v.douyin.com/emjiIYoJWK8/）。 https://v.douyin.com/emjiIYoJWK8/');
 assert.deepEqual(p.items,[{url:'https://v.douyin.com/emjiIYoJWK8/'}]);
});

import {openCanonicalRuntime} from '../openclaw/canonical-runtime.js';
test('authenticated Feishu share passes remote settings and reports remote authentication recovery',async t=>{
 const root=await mkdtemp(join(await realpath(tmpdir()),'remote-ingress-'));t.after(()=>rm(root,{recursive:true,force:true}));
 const scope={Provider:'feishu',AccountId:'a',SenderId:'s',NativeChannelId:'c'};const replies=[];let seen;
 const message={message_id:'om_share',chat_id:'c',sender:{id:'s',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:'小婕 wk 记录：8.46 复制打开抖音 https://v.douyin.com/emjiIYoJWK8/ 02/28 :1pm'})}};
 const runtime=await openCanonicalRuntime({config:{accountId:'a',allowedSenderIds:['s'],allowedConversationIds:['c'],vault:join(root,'v'),stateDir:join(root,'s'),python:'/usr/bin/python3',mediaServiceUrl:'http://192.168.31.136:8765',mediaServiceTokenFile:'/private/token'},hostConfig:{},flash:{},feishu:{getMessage:async()=>message,reply:async args=>{replies.push(args.text);return {message_id:'om_reply',chat_id:'c'};}},collect:async args=>{seen=args;await args.onStage('remote_waiting',{video:{mode:'remote',remoteJobId:'remote_1'}});throw Error('Media service HTTP 401');}});
 try{
  const job=await runtime.acceptMessage(scope,'om_share');await runtime.processJobs();
  assert.equal(seen.url,'https://v.douyin.com/emjiIYoJWK8/');assert.equal(seen.mediaServiceUrl,'http://192.168.31.136:8765');assert.equal(seen.mediaServiceTokenFile,'/private/token');assert.match(seen.shareText,/8.46/);assert.equal(seen.background,'');
  assert.equal((await runtime.status(scope,job.jobId)).status,'waiting_remote_auth');assert.match(replies[0],/Mac mini媒体处理待恢复/);assert.ok(!replies[0].includes('本机专用Wiki浏览器'));
  message.sender.id='forged';await assert.rejects(runtime.acceptMessage(scope,'om_share'),/Source mismatch/);
 }finally{await runtime.close();}
});
