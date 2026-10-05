import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCommand} from '../src/wk.js';
test('explicit original quality in a Douyin share freezes a mode without becoming personal background',()=>{
 const parsed=parseCommand('小婕 wk 记录：原画质 7.99 复制打开抖音 https://v.douyin.com/Example/ :7pm');
 assert.equal(parsed.videoMode,'original');
 assert.equal(parsed.items[0].url,'https://v.douyin.com/Example/');
 assert.equal(parsed.background,'');assert.match(parsed.shareText,/7.99 复制打开抖音/);
});
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {collectDouyin} from '../src/douyin.js';
test('one video publishes media and full transcript through canonical collection, verifies search, then only cleans allowed work',async()=>{
 const root=await mkdtemp(join(await realpath(tmpdir()),'douyin-flow-')),vault=join(root,'vault');await mkdir(vault);
 const ops=[];let modelCalls=0;
 const pipeline=async req=>{
  ops.push(req.operation);
  if(req.operation==='metadata')return {id:'7691977131957472558',url:'https://www.douyin.com/video/7691977131957472558',title:'测试抖音',author:'合成作者',duration:3};
  const packageDir=join(req.root,'package');await mkdir(packageDir,{recursive:true});
  if(req.operation==='media'){await writeFile(join(packageDir,'video.mp4'),'video');await writeFile(join(packageDir,'audio.m4a'),'audio');return {mode:req.mode,source:{sha256:'a'},video:{width:320,height:240},audio:{duration:3}};}
  if(req.operation==='transcribe'){await writeFile(join(packageDir,'transcript.md'),'嗯，不应删除否定词，末尾唯一短语凤凰验收。');return {transcript:join(packageDir,'transcript.md'),segments:1};}
  if(req.operation==='cleanup')return {status:'complete',bytes:100};
 };
 const input={url:'https://v.douyin.com/Example/',vault,workspace:join(root,'work'),stateDir:join(root,'state'),python:'/usr/bin/python3',pipeline,
 translate:async({text})=>text,flash:{extract:async()=>({slug:'douyin-example',terms:[]}),explain:async()=>[]},generate:async({stage})=>{modelCalls++;return stage==='analysis'?'分析':'---FILE: wiki/sources/douyin-example.md---\n# 资料卡\n摘要。\n---END FILE---';},api:{read:p=>readFile(join(vault,p),'utf8'),search:async()=>({results:[{path:'wiki/sources/douyin-example.md'}]})}};
 try{
  const {collectCanonical}=await import('../src/canonical-library.js');
  const r=await collectDouyin(input,collectCanonical);
  assert.equal(r.status,'complete');assert.equal(r.video.mode,'compressed');assert.match(await readFile(r.source,'utf8'),/末尾唯一短语凤凰验收/);
  assert.equal(r.video.cleanup.bytes,100);assert.equal(ops.at(-1),'cleanup');
  const prior=modelCalls;await collectDouyin({...input,workspace:join(root,'work2'),url:'https://www.douyin.com/video/7691977131957472558'},collectCanonical);assert.equal(modelCalls,prior);
  const noteA=await collectDouyin({...input,background:'第一份个人背景',requestId:'a'.repeat(64)},collectCanonical);
  const noteB=await collectDouyin({...input,background:'第二份个人背景',requestId:'b'.repeat(64)},collectCanonical);
  assert.notEqual(noteA.userRecord,noteB.userRecord);assert.match(await readFile(noteB.userRecord,'utf8'),/第二份个人背景/);
  const bare=await collectDouyin(input,collectCanonical);assert.equal(bare.userRecord,undefined);assert.equal(modelCalls,prior);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('a failed search leaves downloaded work and recovery reuses an existing publication',async()=>{
 const root=await mkdtemp(join(await realpath(tmpdir()),'douyin-search-')),vault=join(root,'v');await mkdir(vault);let unavailable=true,cleanup=0,calls=0;
 const pipeline=async req=>{
  if(req.operation==='metadata')return{id:'7691977131957472558',url:'https://www.douyin.com/video/7691977131957472558',title:'公开合成',author:'',duration:2};
  const p=join(req.root,'package');await mkdir(p,{recursive:true});
  if(req.operation==='media'){await writeFile(join(p,'video.mp4'),'video');await writeFile(join(p,'audio.m4a'),'audio');return {mode:req.mode,video:{width:320,height:240},audio:{duration:2}};}
  if(req.operation==='transcribe'){calls++;await writeFile(join(p,'transcript.md'),'完整末尾短语。');return{transcript:join(p,'transcript.md')};}
  if(req.operation==='cleanup'){cleanup++;return{status:'complete',bytes:0};}
 };
 const options={url:'https://www.douyin.com/video/7691977131957472558',vault,workspace:join(root,'w'),stateDir:join(root,'s'),python:'/usr/bin/python3',pipeline,translate:async({text})=>text,flash:{extract:async()=>({slug:'douyin-search',terms:[]}),explain:async()=>[]},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/douyin-search.md---\n# 测试\n摘要。\n---END FILE---',api:{read:p=>readFile(join(vault,p),'utf8'),search:async()=>({results:unavailable?[]:[{path:'wiki/sources/douyin-search.md'}]})}};
 try{
  const {collectCanonical}=await import('../src/canonical-library.js');await assert.rejects(collectDouyin(options,collectCanonical),/search verification/);assert.equal(cleanup,0);unavailable=false;
  const r=await collectDouyin(options,collectCanonical);assert.equal(calls,1);assert.equal(r.status,'complete');
  const source=r.source;const variant=await collectDouyin({...options,videoMode:'original'},collectCanonical);assert.equal(variant.source,source);assert.equal(calls,1);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('oversized video pauses until an exact frozen video confirmation is supplied',async()=>{
 const root=await mkdtemp(join(await realpath(tmpdir()),'douyin-limit-'));let downloads=0;
 try{
  const r=await collectDouyin({url:'https://www.douyin.com/video/7691977131957472558',vault:root,workspace:join(root,'w'),stateDir:join(root,'s'),python:'/usr/bin/python3',api:{},pipeline:async req=>{if(req.operation==='metadata')return {id:'7691977131957472558',url:'https://www.douyin.com/video/7691977131957472558',duration:1801,width:1080,height:1920};downloads++;throw Error('must not download');}},async()=>{});
  assert.equal(r.status,'partial');assert.equal(r.missingAssets[0].status,'waiting_confirmation');assert.equal(downloads,0);assert.match(r.missingAssets[0].fingerprint,/^[a-f0-9]{64}$/);
 }finally{await rm(root,{recursive:true,force:true});}
});
import {openCanonicalRuntime} from '../openclaw/canonical-runtime.js';
test('authenticated record ingress freezes original mode and never accepts a forged source',async()=>{
 const root=await mkdtemp(join(await realpath(tmpdir()),'douyin-ingress-'));const seen=[];const scope={Provider:'feishu',AccountId:'a',SenderId:'s',NativeChannelId:'c'};
 const message={message_id:'om_video',chat_id:'c',sender:{id:'s',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:'小婕 wk 记录：原画质 https://v.douyin.com/Example/'})}};
 const runtime=await openCanonicalRuntime({config:{accountId:'a',allowedSenderIds:['s'],allowedConversationIds:['c'],vault:join(root,'v'),stateDir:join(root,'state'),python:'/usr/bin/python3'},hostConfig:{},flash:{},feishu:{getMessage:async()=>message,reply:async()=>({message_id:'om_reply',chat_id:'c'})},collect:async args=>{seen.push(args);throw Error('ASR unknown cloud result: timeout');}});
 try{const r=await runtime.acceptMessage(scope,'om_video');await runtime.processJobs();assert.equal(seen[0].videoMode,'original');assert.equal((await runtime.status(scope,r.jobId)).status,'waiting_unknown');assert.equal((await runtime.acceptMessage(scope,'om_video')).duplicate,true);message.sender.id='forged';await assert.rejects(runtime.acceptMessage(scope,'om_video'),/Source mismatch/);}finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});

test('restored Codex authentication resumes via explicit continue without authorizing browser cookies',async()=>{
 const root=await mkdtemp(join(await realpath(tmpdir()),'douyin-auth-'));const scope={Provider:'feishu',AccountId:'a',SenderId:'s',NativeChannelId:'c'};let text='小婕 wk 记录：https://v.douyin.com/Example/';let restored=false,recovery;
 const runtime=await openCanonicalRuntime({config:{accountId:'a',allowedSenderIds:['s'],allowedConversationIds:['c'],vault:join(root,'v'),stateDir:join(root,'state'),python:'/usr/bin/python3'},hostConfig:{},flash:{},feishu:{getMessage:async id=>({message_id:id,chat_id:'c',sender:{id:'s',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text})}}),reply:async()=>({message_id:'om_reply',chat_id:'c'})},collect:async args=>{await args.onStage('video_audio_archived',{video:{mode:'compressed',video:'complete',audio:'complete',transcript:'pending',knowledge:'pending'}});if(!restored)throw Error('ASR login required: HTTP 401');recovery=args.videoRecovery;assert.equal(args.browserProfile,undefined);return {status:'complete',source:'synthetic-source'};}});
 try{const accepted=await runtime.acceptMessage(scope,'om_record');await runtime.processJobs();assert.equal((await runtime.status(scope,accepted.jobId)).status,'waiting_asr_auth');restored=true;text='小婕 wk 继续：'+accepted.jobId;await runtime.acceptMessage(scope,'om_continue');await runtime.processJobs();assert.equal((await runtime.status(scope,accepted.jobId)).status,'done');assert.equal(recovery.messageId,'om_continue');}finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});
