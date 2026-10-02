import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {openKnowledgeQuery} from '../src/knowledge-query.js';
const scope={SenderId:'u',NativeChannelId:'c'};
test('query reads full evidence with exact citations and continues selected page without writing knowledge',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-query-'));let reads=0;
 const api={search:async()=>({results:[{path:'wiki/sources/sample.md',title:'Sample',snippet:'summary'}]}),read:async()=>{reads++;return '# Sample\n\n正文证据，非摘要。\n'+Array.from({length:100},(_,i)=>`第${i+1}行`).join('\n');},graph:async()=>({nodes:[],edges:[]})};
 try{const q=await openKnowledgeQuery({stateDir:root,api:async()=>api});const result=await q.query(scope,{question:'Sample'});assert.equal(reads,1);assert.match(result.text,/正文证据/);assert.match(result.text,/L1-L80/);assert.match(result.text,/部分读取/);const id=result.sources[0].id;assert.match((await q.read(scope,id,81)).text,/第78行/);await assert.rejects(q.read({...scope,SenderId:'other'},id,1),/not found/);await assert.rejects(q.read(scope,'../../secret',1),/not found/);}finally{await rm(root,{recursive:true,force:true});}
});
test('query excludes private notes and unsafe API paths; aliases deduplicate; no-result and faults stay explicit',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-query-'));const terms=[];
 try{const q=await openKnowledgeQuery({stateDir:root,api:async()=>({search:async t=>{terms.push(t);return{results:[{path:'wiki/queries/user-secret.md',snippet:'secret'},{path:'../../secret'},{path:'wiki/concepts/attention.md',title:'注意力'}]};},read:async()=> '# Attention\n基础解释：模型通用知识，未经核实。',graph:async()=>({nodes:[],edges:[]})}),generate:async()=> '猜测 [K-0000000000000000 L1-L1]'});const result=await q.query(scope,{question:'注意力',aliases:['Attention']});assert.deepEqual(terms,['注意力','Attention']);assert.equal(result.results.length,1);assert.match(result.text,/引用未通过校验/);assert.doesNotMatch(result.text,/secret|猜测/);assert.equal((await q.query(scope,{question:'注意力',topic:'不存在'})).sources.length,0);
 const broken=await openKnowledgeQuery({stateDir:root,api:async()=>{throw Error('Nashsu API HTTP 429');}});await assert.rejects(broken.query(scope,{question:'x'}),/429/);
 }finally{await rm(root,{recursive:true,force:true});}
});
test('conflicting dates and own personal notes remain distinct evidence; native graph IDs map to safe page paths',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-query-'));const note='wiki/queries/user-note-'+ 'a'.repeat(64)+'.md';let response='';
 const texts={'wiki/sources/old.md':'# Old\n2024：作者认为效果很好。','wiki/sources/new.md':'# New\n2026：作者认为效果不确定。',[note]:'# 个人备注\n我倾向于旧观点；不是作者证据。','wiki/entities/test.md':'# Entity'};
 try{const q=await openKnowledgeQuery({stateDir:root,notes:async s=>s.SenderId==='u'?[{path:note,source:'wiki/sources/old.md'}]:[],api:async()=>({search:async()=>({results:[{path:'wiki/sources/old.md'},{path:'wiki/sources/new.md'},{path:'wiki/queries/user-note-foreign.md'}]}),read:async p=>texts[p],graph:async()=>({nodes:[{id:'Old',path:'wiki/sources/old.md'},{id:'Entity',path:'wiki/entities/test.md'}],edges:[{source:'Old',target:'Entity'}]})}),generate:async({prompt})=>{response=prompt;return 'no valid citation';}});
 const result=await q.query(scope,{question:'effect'});assert.match(response,/2024/);assert.match(response,/2026/);assert.match(response,/用户个人备注/);assert.equal(result.edges.length,1);const entity=result.results.find(s=>s.path==='wiki/entities/test.md');assert.match((await q.read(scope,entity.id)).text,/Entity/);const own=result.sources.find(s=>s.ownedNote);assert.ok(own);await assert.rejects(q.read({...scope,SenderId:'other'},own.id),/not found/);const other=await q.query({...scope,SenderId:'other'},{question:'effect'});assert.ok(!other.sources.some(s=>s.ownedNote));assert.doesNotMatch(other.text,/倾向于/);
 }finally{await rm(root,{recursive:true,force:true});}
});
