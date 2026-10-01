import test from 'node:test';
import assert from 'node:assert/strict';
import {parseCommand} from '../src/wk.js';
test('collection alias separates multiple sources and personal background',()=>{
 const parsed=parseCommand('小婕收集： https://example.org/a\nhttps://example.org/b\n备注：用于学习');
 assert.equal(parsed.action,'record');assert.equal(parsed.items.length,2);assert.equal(parsed.background,'用于学习');
 assert.equal(parsed.items[0].url,'https://example.org/a');
});
import {mkdtemp,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {openCanonicalRuntime} from '../openclaw/canonical-runtime.js';
test('verified multi-link message creates independent tasks and retains a failing item',async()=>{
 const root=await mkdtemp(join(tmpdir(),'input-'));const scope={Provider:'feishu',AccountId:'a',SenderId:'s',NativeChannelId:'c'};const seen=[];
 const runtime=await openCanonicalRuntime({config:{accountId:'a',allowedSenderIds:['s'],allowedConversationIds:['c'],vault:join(root,'v'),stateDir:join(root,'state'),python:'/usr/bin/python3'},hostConfig:{},flash:{},feishu:{getMessage:async()=>({message_id:'om_test',chat_id:'c',sender:{id:'s',id_type:'open_id',sender_type:'user'},body:{content:JSON.stringify({text:'小婕收集 https://example.org/a https://example.org/b\n备注：我的背景'})}}),reply:async()=>({message_id:'om_reply',chat_id:'c'})},collect:async input=>{seen.push(input);if(input.url.endsWith('/a'))throw Error('login required');return{status:'complete',source:'saved.md'};}});
 try{const accepted=await runtime.acceptMessage(scope,'om_test');assert.equal(accepted.jobs.length,2);await runtime.processJobs();assert.equal((await runtime.status(scope,accepted.jobs[0].jobId)).status,'waiting_login');assert.equal((await runtime.status(scope,accepted.jobs[1].jobId)).status,'done');assert.equal(seen[1].background,'我的背景');assert.equal((await runtime.acceptMessage(scope,'om_test')).duplicate,true);}finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});
