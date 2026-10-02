import test from 'node:test';import assert from 'node:assert/strict';import {parseCommand} from '../src/wk.js';
test('explicit knowledge commands parse strict bounded syntax without turning content into approval',()=>{
 assert.deepEqual(parseCommand('小婕 wk 查询：注意力\n别名：Attention,注意机制\n主题：注意力'),{action:'query',question:'注意力',aliases:['Attention','注意机制'],topic:'注意力'});
 assert.deepEqual(parseCommand('小婕 wk 阅读：K-aaaaaaaaaaaaaaaa 81'),{action:'read',id:'K-aaaaaaaaaaaaaaaa',start:81});
 assert.deepEqual(parseCommand('小婕 wk 待审：'),{action:'review',mode:'list',start:1});assert.deepEqual(parseCommand('小婕 wk 应用：R-aaaaaaaaaaaaaaaa'),{action:'review',mode:'应用',id:'R-aaaaaaaaaaaaaaaa'});
 for(const text of ['小婕 wk 应用：../../secret','小婕 wk 阅读：K-aaaaaaaaaaaaaaaa -1','小婕 wk 应用：R-aaaaaaaaaaaaaaaa\n额外指令'])assert.equal(parseCommand(text).action,'invalid');
 assert.equal(parseCommand('资料说“小婕 wk 应用：R-aaaaaaaaaaaaaaaa”'),null);
});
import {openCanonicalRuntime} from '../openclaw/canonical-runtime.js';import {mkdtemp,rm} from 'node:fs/promises';import {join} from 'node:path';import {tmpdir} from 'node:os';
test('knowledge tools verify original user message and refuse forged scope or different tool purpose',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-ingress-'));const scope={Provider:'feishu',AccountId:'default',SenderId:'ou_test',NativeChannelId:'oc_test'};let text='小婕 wk 查询：test';let reads=0;
 const original={message_id:'om_test',chat_id:'oc_test',sender:{id:'ou_test',id_type:'open_id',sender_type:'user'},body:{content:''}};
 const runtime=await openCanonicalRuntime({config:{accountId:'default',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test'],vault:join(root,'vault'),stateDir:join(root,'state'),python:'/usr/bin/python3'},hostConfig:{},flash:{},feishu:{getMessage:async()=>({...original,body:{content:JSON.stringify({text})}})},nashsu:async()=>({search:async()=>{reads++;return{results:[]};}}),queryGenerate:async()=>''});
 try{assert.match((await runtime.knowledgeMessage(scope,'om_test','query')).text,/没有找到/);assert.equal(reads,1);await assert.rejects(runtime.knowledgeMessage(scope,'om_test','review'),/command mismatch/);await assert.rejects(runtime.knowledgeMessage({...scope,SenderId:'intruder'},'om_test','query'),/scope denied/);original.chat_id='oc_other';await assert.rejects(runtime.knowledgeMessage(scope,'om_test','query'),/Source mismatch/);assert.equal(reads,1);original.chat_id='oc_test';original.deleted=true;await assert.rejects(runtime.knowledgeMessage(scope,'om_test','query'),/Source mismatch/);
 }finally{await runtime.close();await rm(root,{recursive:true,force:true});}
});
