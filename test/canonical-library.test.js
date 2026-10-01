import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,access} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {collectCanonical} from '../src/canonical-library.js';

test('one canonical Chinese article is readable through nashsu; retry reuses model results after API outage',async()=>{
 const root=await mkdtemp(join(tmpdir(),'canonical-'));const vault=join(root,'vault'),workspace=join(root,'work');let calls=0,offline=true;
 const input={url:'https://x.com/a/status/123',vault,workspace,python:'/usr/bin/python3',
 capture:async()=>{calls++;const dir=join(workspace,'capture');await mkdir(dir,{recursive:true});await writeFile(join(dir,'article.md'),'# 示例\n\n完整中文正文。');return{directory:dir,text:'# 示例\n\n完整中文正文。',status:'complete'};},
 flash:{extract:async()=>{calls++;return{slug:'example',terms:[]};},explain:async()=>[]},
 generate:async({stage})=>{calls++;return stage==='analysis'?'分析':'---FILE: wiki/sources/example.md---\n# 示例\n摘要。\n---END FILE---';},
 api:{read:async path=>{if(offline)throw Error('API unavailable');return readFile(join(vault,path),'utf8');}}};
 try{
  await mkdir(vault);
  await assert.rejects(collectCanonical(input),/API unavailable/);const prior=calls;offline=false;
  const result=await collectCanonical(input);assert.equal(calls,prior);assert.equal(result.status,'complete');
  assert.match(await readFile(result.source,'utf8'),/完整中文正文。/);assert.match(result.source,/wiki\/sources\/example.md$/);
  assert.match(await readFile(join(vault,'raw/sources/example.md'),'utf8'),/完整中文正文。/);
  for(const path of ['reading','raw/inputs','glossary'])await assert.rejects(access(join(vault,path)));
  assert.equal(await readFile(join(vault,'raw/assets',result.sourceId,'article.md'),'utf8'),'# 示例\n\n完整中文正文。');
 }finally{await rm(root,{recursive:true,force:true});}
});

test('publication preserves an existing concept and exposes its proposed update for review',async()=>{
 const root=await mkdtemp(join(tmpdir(),'canonical-review-'));const vault=join(root,'vault'),workspace=join(root,'work');
 try{
  await mkdir(join(vault,'wiki/concepts'),{recursive:true});await writeFile(join(vault,'wiki/concepts/example.md'),'# 手写概念\n不要覆盖');
  const result=await collectCanonical({url:'https://x.com/a/status/123',vault,workspace,python:'/usr/bin/python3',
   capture:async()=>{const directory=join(workspace,'capture');await mkdir(directory,{recursive:true});await writeFile(join(directory,'article.md'),'中文原文。');return{directory,text:'中文原文。',status:'complete'};},
   flash:{extract:async()=>({slug:'example',terms:[]}),explain:async terms=>terms.map(t=>({...t,definition:'这是概念。',example:'一个例子。',uncertainty:'待核实。'}))},
   generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/example.md---\n# 来源\n摘要。\n---END FILE---\n---FILE: wiki/concepts/example.md---\n# 示例\n新观点。\n---END FILE---',
   api:{read:path=>readFile(join(vault,path),'utf8')}});
  assert.equal(result.status,'complete');assert.equal(result.reviews.length,1);assert.equal(await readFile(join(vault,'wiki/concepts/example.md'),'utf8'),'# 手写概念\n不要覆盖');
  assert.match(await readFile(join(vault,result.reviews[0].file),'utf8'),/新观点/);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('a colliding title keeps new concept references attached to the new article',async()=>{
 const root=await mkdtemp(join(tmpdir(),'canonical-collision-'));const vault=join(root,'vault'),workspace=join(root,'work');
 try{
  await mkdir(join(vault,'wiki/sources'),{recursive:true});await writeFile(join(vault,'wiki/sources/example.md'),'# 旧文章');
  const result=await collectCanonical({url:'https://x.com/a/status/123',vault,workspace,python:'/usr/bin/python3',
   capture:async()=>{const directory=join(workspace,'capture');await mkdir(directory,{recursive:true});await writeFile(join(directory,'article.md'),'新的中文原文。');return{directory,text:'新的中文原文。',status:'complete'};},
   flash:{extract:async()=>({slug:'example',terms:[]}),explain:async terms=>terms.map(t=>({...t,definition:'概念。',example:'示例。',uncertainty:'待核实。'}))},
   generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/example.md---\n# 新文章\n摘要。\n---END FILE---\n---FILE: wiki/concepts/new-concept.md---\n# 新概念\n[来源](../sources/example.md)\n---END FILE---',
   api:{read:path=>readFile(join(vault,path),'utf8')}});
  const body=await readFile(join(vault,'wiki/concepts/new-concept.md'),'utf8');
  assert.ok(body.includes('../sources/'+result.source.split('/').at(-1)));assert.equal(await readFile(join(vault,'wiki/sources/example.md'),'utf8'),'# 旧文章');
 }finally{await rm(root,{recursive:true,force:true});}
});
