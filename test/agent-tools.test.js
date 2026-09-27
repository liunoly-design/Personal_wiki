import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createPlugin} from '../openclaw/index.js';
import {openRuntime} from '../openclaw/runtime.js';

test('scoped Agent tools record a verified source message and expose only its conversation progress',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-tools-'));
 const config={enabled:true,accountId:'default',entryAgentId:'xiaojie',wikiAgentId:'wiki',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test','oc_other'],vault:join(root,'vault'),stateDir:join(root,'state'),python:'/usr/bin/python3'};
 const original={message_id:'om_test',chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:'小婕 wk 记录：https://x.com/a/status/123'})}};
 const runtime=await openRuntime({config,hostConfig:{},feishu:{getMessage:async()=>original},flash:{}});
 try{
  let factory;createPlugin({openRuntime:async()=>runtime}).register({pluginConfig:config,config:{},registerService(){},on(){},registerTool(f){factory=f;}});
  assert.equal(typeof factory,'function');
  const context={agentId:'wiki',messageChannel:'feishu',agentAccountId:'default',nativeChannelId:'oc_test',requesterSenderId:'ou_test'};
  assert.equal(factory({...context,requesterSenderId:'ou_intruder'}),null);
  const tools=factory(context),record=tools.find(t=>t.name==='wiki_record'),status=tools.find(t=>t.name==='wiki_status');
  const receipt=await record.execute('call-1',{messageId:'om_test'});
  const accepted=JSON.parse(receipt.content[0].text);assert.equal(accepted.duplicate,false);assert.match(accepted.jobId,/^[a-f0-9]{64}$/u);
  const current=JSON.parse((await status.execute('call-2',{jobId:accepted.jobId})).content[0].text);assert.equal(current.status,'queued');
  const other=factory({...context,nativeChannelId:'oc_other'}).find(t=>t.name==='wiki_status');
  await assert.rejects(other.execute('call-3',{jobId:accepted.jobId}),/not found/);
 }finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});

test('completed collection reports title, summary, attachment outcome and review numbers',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-receipt-'));const sent=[];
 const config={accountId:'default',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test'],vault:join(root,'vault'),stateDir:join(root,'state'),python:'/usr/bin/python3'};
 const scope={Provider:'feishu',AccountId:'default',SenderId:'ou_test',NativeChannelId:'oc_test'};
 const runtime=await openRuntime({config,hostConfig:{},flash:{},feishu:{getMessage:async()=>({message_id:'om_test',chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:'小婕 wk 记录：https://x.com/a/status/123'})}}),reply:async request=>{sent.push(request.text);return{message_id:'om_reply',chat_id:'oc_test'};}},makeAdapters:()=>({capture:async()=>({text:'Synthetic source',directory:'/synthetic',status:'partial'}),extract:async()=>({slug:'evidence',terms:[]}),importAndCompile:async()=>({status:'complete',title:'合成实验',summary:'仅能说明本次样本的结果。',source:'wiki/sources/evidence.md',reviews:[{id:'R-123'}]})})});
 try{
  const accepted=await runtime.acceptMessage(scope,'om_test');await runtime.processJobs();
  assert.match(sent[0],/合成实验/);assert.match(sent[0],/仅能说明本次样本的结果/);assert.match(sent[0],/R-123/);assert.match(sent[0],/部分完成/);
  const state=await runtime.status(scope,accepted.jobId);assert.equal(state.receiptConfirmed,true);
 }finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});
