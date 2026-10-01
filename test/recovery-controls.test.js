import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm,access} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {openCanonicalRuntime} from '../openclaw/canonical-runtime.js';import {parseCommand} from '../src/wk.js';

test('video confirmation requires verified user message, task ownership and current attachment fingerprint across restart',async()=>{
 const root=await mkdtemp(join(tmpdir(),'confirm-')),stateDir=join(root,'state');let content='小婕收集：https://x.com/a/status/123',messageId='om_collect',runs=0;const replies=[];
 const asset={id:'b'.repeat(16),fingerprint:'c'.repeat(64),kind:'video',status:'waiting_confirmation'};
 const config={accountId:'default',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test','oc_other'],vault:join(root,'v'),stateDir,python:'/usr/bin/python3'};
 const scope={Provider:'feishu',AccountId:'default',SenderId:'ou_test',NativeChannelId:'oc_test'};
 const options={config,hostConfig:{},flash:{},feishu:{getMessage:async()=>({message_id:messageId,chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:content})}}),reply:async request=>{replies.push(request.text);return{message_id:'om_reply',chat_id:'oc_test'};}},collect:async args=>{runs++;return args.mediaApprovals?.[asset.id]?.fingerprint===asset.fingerprint?{status:'complete',attachmentStatus:'complete',files:{},assets:{}}:{status:'partial',resumableMedia:true,source:'wiki/sources/test.md',missingAssets:[asset],files:{},assets:{}};}};
 let runtime=await openCanonicalRuntime(options);
 try{
  const {jobId}=await runtime.acceptMessage(scope,messageId);await runtime.processJobs();assert.equal((await runtime.status(scope,jobId)).status,'waiting_confirmation');assert.match(replies[0],/确认视频/);await runtime.close();runtime=await openCanonicalRuntime(options);await runtime.processJobs();assert.equal(runs,1);
  messageId='om_bad';content=`小婕 wk 确认视频：${jobId} ${asset.id} ${'d'.repeat(64)}`;await assert.rejects(runtime.acceptMessage(scope,messageId),/does not match/);
  messageId='om_good';content=`小婕 wk 确认视频：${jobId} ${asset.id} ${asset.fingerprint}`;await assert.rejects(runtime.acceptMessage({...scope,NativeChannelId:'oc_other'},messageId),/Source mismatch/);
  await runtime.acceptMessage(scope,messageId);await runtime.acceptMessage(scope,messageId);await runtime.processJobs();assert.equal(runs,2);assert.equal((await runtime.status(scope,jobId)).status,'done');await assert.rejects(access(join(stateDir,'work',jobId)));
 }finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});

test('recovery command parsing rejects missing IDs and extra approval scope',()=>{
 const job='a'.repeat(64),asset='b'.repeat(16),fp='c'.repeat(64);
 assert.equal(parseCommand(`小婕 wk 确认视频：${job} ${asset} ${fp}`).mode,'确认视频');
 assert.equal(parseCommand(`小婕 wk 确认视频：${job} ${asset}`).action,'invalid');
 assert.equal(parseCommand(`小婕 wk 继续：${job} ${asset}`).action,'invalid');
});

test('scoped recovery tool exposes only verified message IDs and status hook returns actual state',async()=>{
 const {createPlugin}=await import('../openclaw/index.js');let factory;
 const config={enabled:true,accountId:'default',entryAgentId:'xiaojie',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test']};
 createPlugin({openRuntime:async()=>({acceptMessage:async(_scope,id)=>({jobId:'a'.repeat(64),status:id==='om_test'?'waiting_media':'invalid'})})}).register({pluginConfig:config,config:{},registerTool:f=>factory=f,registerService(){},on(){}});
 const tool=factory({agentId:'wiki',messageChannel:'feishu',agentAccountId:'default',nativeChannelId:'oc_test',requesterSenderId:'ou_test'}).find(t=>t.name==='wiki_resume');
 assert.ok(tool);assert.equal(tool.parameters.required[0],'messageId');assert.equal(JSON.parse((await tool.execute('call',{messageId:'om_test'})).content[0].text).status,'waiting_media');
});

test('login recovery grants only the owning task a dedicated profile and cannot be requested as ordinary continue',async()=>{
 const root=await mkdtemp(join(tmpdir(),'session-scope-'));let text='小婕收集：https://x.com/a/status/123',messageId='om_collect',attempts=0;
 const config={accountId:'default',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test'],vault:join(root,'v'),stateDir:join(root,'s'),python:'/usr/bin/python3'};
 const scope={Provider:'feishu',AccountId:'default',SenderId:'ou_test',NativeChannelId:'oc_test'};
 const runtime=await openCanonicalRuntime({config,hostConfig:{},flash:{},feishu:{getMessage:async()=>({message_id:messageId,chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text})}}),reply:async()=>({message_id:'om_reply',chat_id:'oc_test'})},collect:async args=>{attempts++;if(!args.browserProfile)throw Error('captcha required');assert.match(args.browserProfile,/browser\/[a-f0-9]{16}\/x.com$/);return{status:'complete',files:{},assets:{}};}});
 try{const {jobId}=await runtime.acceptMessage(scope,messageId);await runtime.processJobs();messageId='om_plain';text=`小婕 wk 继续：${jobId}`;await assert.rejects(runtime.acceptMessage(scope,messageId),/登录继续/);assert.equal(attempts,1);messageId='om_login';text=`小婕 wk 登录继续：${jobId}`;await runtime.acceptMessage(scope,messageId);await runtime.processJobs();assert.equal((await runtime.status(scope,jobId)).status,'done');}finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});

test('concurrent confirmations retain both approvals and execute each pending attachment once',async()=>{
 const root=await mkdtemp(join(tmpdir(),'confirm-concurrent-'));const originals=new Map();const assets=[{id:'b'.repeat(16),fingerprint:'c'.repeat(64),kind:'video',status:'waiting_confirmation'},{id:'d'.repeat(16),fingerprint:'e'.repeat(64),kind:'video',status:'waiting_confirmation'}];const completed=new Set(),selected=[];
 const config={accountId:'default',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test'],vault:join(root,'v'),stateDir:join(root,'s'),python:'/usr/bin/python3'};const scope={Provider:'feishu',AccountId:'default',SenderId:'ou_test',NativeChannelId:'oc_test'};
 const runtime=await openCanonicalRuntime({config,hostConfig:{},flash:{},feishu:{getMessage:async id=>({message_id:id,chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:originals.get(id)})}}),reply:async()=>({message_id:'om_reply',chat_id:'oc_test'})},collect:async args=>{if(args.mediaAction){const id=args.mediaAction.assetId;assert.equal(args.mediaApprovals[id].fingerprint,assets.find(a=>a.id===id).fingerprint);completed.add(id);selected.push(id);}return {status:completed.size===2?'complete':'partial',resumableMedia:true,missingAssets:assets.filter(a=>!completed.has(a.id)),files:{},assets:{}};}});
 try{originals.set('om_collect','小婕收集：https://x.com/a/status/123');const {jobId}=await runtime.acceptMessage(scope,'om_collect');await runtime.processJobs();assets.forEach((a,i)=>originals.set('om_confirm'+i,`小婕 wk 确认视频：${jobId} ${a.id} ${a.fingerprint}`));await Promise.all(assets.map((_,i)=>runtime.acceptMessage(scope,'om_confirm'+i)));await runtime.processJobs();assert.deepEqual(selected,assets.map(a=>a.id));const done=await runtime.status(scope,jobId);assert.equal(done.status,'done');assert.equal(Object.keys(done.mediaApprovals).length,2);}finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});
