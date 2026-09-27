import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile,readdir,writeFile} from 'node:fs/promises';import {join} from 'node:path';import {tmpdir} from 'node:os';
import {createPlugin} from '../openclaw/index.js';import {openRuntime} from '../openclaw/runtime.js';
const scope={enabled:true,accountId:'default',entryAgentId:'xiaojie',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test']};
const message={Provider:'feishu',AccountId:'default',AgentId:'xiaojie',SenderId:'ou_test',NativeChannelId:'oc_test',MessageSid:'om_test',rawText:'小婕 wk 记录：https://x.com/a/status/123'};
test('hook reserves query, ignores GTD and unauthorized sender, does not process suppressed delivery',async()=>{
 let hook,calls=0;const replies=[];const api={pluginConfig:scope,config:{},logger:{warn(){}},registerService(){},on(n,f){hook=f;}};
 const ctx={dispatcher:{sendFinalReply(p){replies.push(p.text);return true;},getQueuedCounts(){return{};}},recordProcessed(){},markIdle(){}};
 createPlugin({openRuntime:async()=>({accept:async()=>{calls++;return{duplicate:false};}})}).register(api);
 assert.equal(await hook({ctx:{...message,rawText:'小婕 GTD 收集：买菜'},sendPolicy:'allow'},ctx),undefined);
 assert.equal(await hook({ctx:{...message,SenderId:'ou_other'},sendPolicy:'allow'},ctx),undefined);
 await hook({ctx:{...message,rawText:'小婕 wk 查询：Canvas'},sendPolicy:'allow'},ctx);assert.match(replies[0],/暂未开放/);assert.equal(calls,0);
 await hook({ctx:{...message,rawText:'小婕 wk 讨论：Canvas'},sendPolicy:'allow'},ctx);assert.match(replies.at(-1),/暂未开放/);assert.equal(calls,0);
 await hook({ctx:message,sendPolicy:'deny'},ctx);assert.equal(calls,0);
 await hook({ctx:message,sendPolicy:'allow'},ctx);assert.equal(calls,1);assert.match(replies.at(-1),/收到/);
});

test('failed processing produces one failure receipt and duplicate delivery does not rerun work',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'wk-failure-'));let attempts=0;const sent=[];
 const config={...scope,stateDir:join(dir,'state'),vault:join(dir,'vault'),python:'/usr/bin/python3'};
 const original={message_id:'om_test',chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:message.rawText})}};
 const runtime=await openRuntime({config,hostConfig:{},flash:{},feishu:{getMessage:async()=>original,reply:async r=>{sent.push(r);return{message_id:'om_failure',chat_id:'oc_test'};}},
  makeAdapters:()=>({capture:async()=>{attempts++;throw Error('synthetic network failure');}})});
 try{
  await runtime.accept(message,'https://x.com/a/status/123');await runtime.processJobs();
  assert.equal((await runtime.accept(message,'https://x.com/a/status/123')).duplicate,true);await runtime.processJobs();
  assert.equal(attempts,1);assert.equal(sent.length,1);assert.match(sent[0].text,/未全部完成/);assert.doesNotMatch(sent[0].text,/synthetic network failure/);
 }finally{await runtime.close();await rm(dir,{recursive:true,force:true});}
});
test('durable job verifies original message, runs once and replies to the same chat',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'wk-plugin-'));const config={...scope,stateDir:join(dir,'state'),vault:join(dir,'vault'),python:'/usr/bin/python3'};let runs=0,sent=0;
 const original={message_id:'om_test',chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:message.rawText})}};
 const runtime=await openRuntime({config,hostConfig:{},feishu:{getMessage:async()=>original,reply:async r=>{assert.equal(r.replyTo,'om_test');sent++;return{message_id:'om_reply',chat_id:'oc_test'};}},flash:{},makeAdapters:()=>({capture:async()=>{runs++;return{directory:'/snapshot',text:'Article'};},extract:async()=>({slug:'sample',terms:[]}),importAndCompile:async()=>({status:'complete',source:'wiki/sources/sample.md'})})});
 try{await writeFile(join(dir,'state/jobs/000-broken.json'),'{');assert.equal((await runtime.accept(message,'https://x.com/a/status/123')).duplicate,false);assert.equal((await runtime.accept(message,'https://x.com/a/status/123')).duplicate,true);await runtime.processJobs();await runtime.processJobs();assert.equal(runs,1);assert.equal(sent,1);assert.ok((await readdir(join(dir,'state/jobs'))).includes('000-broken.json.corrupt'));const files=await readdir(join(dir,'state/jobs'));assert.equal(JSON.parse(await readFile(join(dir,'state/jobs',files.find(n=>n.endsWith('.json'))),'utf8')).status,'done');}finally{await runtime.close();await rm(dir,{recursive:true,force:true});}
});
