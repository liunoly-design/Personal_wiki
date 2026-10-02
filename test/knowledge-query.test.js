import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {openKnowledgeQuery} from '../src/knowledge-query.js';
const chooseAll=prompt=>JSON.stringify({ids:JSON.parse(prompt.split('\n候选JSON：\n')[1]).slice(0,5).map(x=>x.id)});
const scope={SenderId:'u',NativeChannelId:'c'};
test('query reads full evidence with exact citations and continues selected page without writing knowledge',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-query-'));let reads=0;
 const api={search:async()=>({results:[{path:'wiki/sources/sample.md',title:'Sample',snippet:'summary'}]}),read:async()=>{reads++;return '# Sample\n\n正文证据，非摘要。\n'+Array.from({length:100},(_,i)=>`第${i+1}行`).join('\n');},graph:async()=>({nodes:[],edges:[]})};
 try{const q=await openKnowledgeQuery({stateDir:root,api:async()=>api});const result=await q.query(scope,{question:'Sample'});assert.equal(reads,1);assert.match(result.text,/正文证据/);assert.match(result.text,/L1-L80/);assert.match(result.text,/部分读取/);const id=result.sources[0].id;assert.match((await q.read(scope,id,81)).text,/第78行/);await assert.rejects(q.read({...scope,SenderId:'other'},id,1),/not found/);await assert.rejects(q.read(scope,'../../secret',1),/not found/);}finally{await rm(root,{recursive:true,force:true});}
});
test('query excludes private notes and unsafe API paths; aliases deduplicate; no-result and faults stay explicit',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-query-'));const terms=[];
 try{const q=await openKnowledgeQuery({stateDir:root,api:async()=>({search:async t=>{terms.push(t);return{results:[{path:'wiki/queries/user-secret.md',snippet:'secret'},{path:'../../secret'},{path:'wiki/concepts/attention.md',title:'注意力'}]};},read:async()=> '# Attention\n基础解释：模型通用知识，未经核实。',graph:async()=>({nodes:[],edges:[]})}),generate:async({prompt,purpose})=>purpose==='select'?chooseAll(prompt):'猜测 [K-0000000000000000 L1-L1]'});const result=await q.query(scope,{question:'注意力',aliases:['Attention']});assert.deepEqual(terms,['注意力','Attention']);assert.equal(result.results.length,1);assert.match(result.text,/引用未通过校验/);assert.doesNotMatch(result.text,/secret|猜测/);assert.equal((await q.query(scope,{question:'注意力',topic:'不存在'})).sources.length,0);
 const broken=await openKnowledgeQuery({stateDir:root,api:async()=>{throw Error('Nashsu API HTTP 429');}});await assert.rejects(broken.query(scope,{question:'x'}),/429/);
 }finally{await rm(root,{recursive:true,force:true});}
});
test('conflicting dates and own personal notes remain distinct evidence; native graph IDs map to safe page paths',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-query-'));const note='wiki/queries/user-note-'+ 'a'.repeat(64)+'.md';let response='';
 const texts={'wiki/sources/old.md':'# Old\n2024：作者认为效果很好。','wiki/sources/new.md':'# New\n2026：作者认为效果不确定。',[note]:'# 个人备注\n我倾向于旧观点；不是作者证据。','wiki/entities/test.md':'# Entity'};
 try{const q=await openKnowledgeQuery({stateDir:root,notes:async s=>s.SenderId==='u'?[{path:note,source:'wiki/sources/old.md'}]:[],api:async()=>({search:async()=>({results:[{path:'wiki/sources/old.md'},{path:'wiki/sources/new.md'},{path:'wiki/queries/user-note-foreign.md'}]}),read:async p=>texts[p],graph:async()=>({nodes:[{id:'Old',path:'wiki/sources/old.md'},{id:'Entity',path:'wiki/entities/test.md'}],edges:[{source:'Old',target:'Entity'}]})}),generate:async({prompt,purpose})=>{if(purpose==='select')return chooseAll(prompt);response=prompt;return 'no valid citation';}});
 const result=await q.query(scope,{question:'effect'});assert.match(response,/2024/);assert.match(response,/2026/);assert.match(response,/用户个人备注/);assert.equal(result.edges.length,1);const entity=result.results.find(s=>s.path==='wiki/entities/test.md');assert.match((await q.read(scope,entity.id)).text,/Entity/);const own=result.sources.find(s=>s.ownedNote);assert.ok(own);await assert.rejects(q.read({...scope,SenderId:'other'},own.id),/not found/);const other=await q.query({...scope,SenderId:'other'},{question:'effect'});assert.ok(!other.sources.some(s=>s.ownedNote));assert.doesNotMatch(other.text,/倾向于/);
 }finally{await rm(root,{recursive:true,force:true});}
});
test('deep search evidence is read beyond the summary and archived original can be selected safely',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-deep-query-'));const card='# Card\n'+Array.from({length:120},(_,i)=>'background '+i).join('\n')+'\nSpecific datum: 42\n[归档原文](../../raw/sources/sample.md)\n';const seen=[];
 try{const q=await openKnowledgeQuery({stateDir:root,api:async()=>({search:async()=>({results:[{path:'wiki/sources/sample.md',snippet:'Specific datum: 42'}]}),read:async path=>{seen.push(path);return path.startsWith('raw/')?'# Original\nOriginal datum: 42':card;},graph:async()=>({nodes:[],edges:[]})})});const r=await q.query(scope,{question:'Specific datum'});assert.match(r.text,/Specific datum: 42/);assert.ok(r.sources[0].start>80);const original=r.results.find(x=>x.path==='raw/sources/sample.md');assert.ok(original);assert.match((await q.read(scope,original.id)).text,/Original datum: 42/);assert.deepEqual(seen,['wiki/sources/sample.md','raw/sources/sample.md']);}finally{await rm(root,{recursive:true,force:true});}
});
test('Codex selects relevant candidates before reading and receipt shows only cited sources without search noise',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-curated-query-'));const reads=[];let selectedId;const prompts=[];
 const candidates=[{path:'wiki/concepts/medical-fee.md',title:'医疗收费',snippet:'无关'},{path:'wiki/sources/token.md',title:'Token 与 AI 经济',snippet:'Token 经济'},{path:'wiki/concepts/token.md',title:'Token',snippet:'概念'}];
 try{const q=await openKnowledgeQuery({stateDir:root,api:async()=>({search:async()=>({results:candidates}),read:async p=>{reads.push(p);return '# '+(p.includes('sources')?'Token 与 AI 经济':'Token')+'\n证据';},graph:async()=>({nodes:[{id:'fee',path:'wiki/concepts/medical-fee.md'},{id:'token',path:'wiki/sources/token.md'}],edges:[{source:'fee',target:'token'}]})}),generate:async({prompt,purpose})=>{prompts.push(prompt);if(purpose==='select'){const items=JSON.parse(prompt.split('\n候选JSON：\n')[1]);selectedId=items.find(x=>x.path==='wiki/sources/token.md').id;return JSON.stringify({ids:[selectedId,items.find(x=>x.path==='wiki/concepts/token.md').id]});}return `Token 可以作为计量单位。[${selectedId} L1-L2]`;}});
 const r=await q.query(scope,{question:'Token'});assert.deepEqual(reads,['wiki/sources/token.md','wiki/concepts/token.md']);assert.equal(prompts.length,2);assert.match(r.text,/Token 可以作为计量单位/);assert.match(r.text,/Token 与 AI 经济/);assert.match(r.text,new RegExp('阅读：'+selectedId+' 1'));assert.doesNotMatch(r.text,/其余结果|图谱|wiki\/|医疗收费|medical-fee/);assert.equal((r.text.match(/小婕 wk 阅读：/g)||[]).length,1);
 }finally{await rm(root,{recursive:true,force:true});}
});
test('invalid or unavailable Codex selection never reads unfiltered candidates; empty relevance is explicit',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-selection-failure-'));let reads=0;
 const hits=Array.from({length:8},(_,i)=>({path:`wiki/sources/example-${i}.md`,title:`资料${i}`}));
 try{for(const output of ['not json',JSON.stringify({ids:['K-0000000000000000']}),'throw',JSON.stringify({ids:[]})]){
  const q=await openKnowledgeQuery({stateDir:root,api:async()=>({search:async()=>({results:hits}),read:async()=>{reads++;return '# Evidence';},graph:async()=>({nodes:[],edges:[]})}),generate:async()=>{if(output==='throw')throw Error('Quota unavailable');return output;}});
  const r=await q.query(scope,{question:'Token'});assert.equal(reads,0);assert.equal(r.sources.length,0);assert.doesNotMatch(r.text,/wiki\/|其余结果|图谱/);assert.ok((r.text.match(/小婕 wk 阅读：/g)||[]).length<=3);assert.match(r.text,output.includes('[]')?/没有足够相关/:/筛选暂不可用/);
 }
 const q=await openKnowledgeQuery({stateDir:root,api:async()=>({search:async()=>({results:hits}),read:async()=>{reads++;return '# Evidence';},graph:async()=>({nodes:[],edges:[]})}),generate:async({prompt})=>{const ids=JSON.parse(chooseAll(prompt)).ids;return JSON.stringify({ids:[ids[0],ids[0]]});}});assert.match((await q.query(scope,{question:'Token'})).text,/筛选暂不可用/);assert.equal(reads,0);
 }finally{await rm(root,{recursive:true,force:true});}
});
