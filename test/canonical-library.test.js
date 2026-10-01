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

test('pasted text preserves bytes and background stays separate; duplicate and unchanged refresh skip models',async()=>{
 const root=await mkdtemp(join(tmpdir(),'canonical-text-')),vault=join(root,'vault');let calls=0;
 const base={url:'https://text.personal-wiki.invalid/abc',text:'这是一份粘贴文本。\n\n```js\nconst path = "../raw/assets/literal";\nconst ref = "[example](../raw/assets/literal)";\n```\n\n原始末节。\n',background:'个人秘密背景',requestId:'a'.repeat(64),vault,python:'/usr/bin/python3',flash:{extract:async text=>{calls++;assert.ok(!text.includes('秘密'));return{slug:'pasted-text',terms:[]};},explain:async()=>[]},generate:async({stage})=>{calls++;return stage==='analysis'?'分析':'---FILE: wiki/sources/pasted-text.md---\n# 粘贴\n摘要。\n---END FILE---';},api:{read:p=>readFile(join(vault,p),'utf8')}};
 try{await mkdir(vault);const result=await collectCanonical({...base,workspace:join(root,'w1')});assert.equal(await readFile(join(vault,'raw/assets',result.sourceId,'article.md'),'utf8'),base.text);assert.ok(! (await readFile(result.source,'utf8')).includes('秘密'));assert.ok((await readFile(result.source,'utf8')).includes('const ref = "[example](../raw/assets/literal)";'));assert.match(await readFile(result.userRecord,'utf8'),/个人秘密背景/);const count=calls;await collectCanonical({...base,workspace:join(root,'w2'),previousResult:result});await collectCanonical({...base,workspace:join(root,'w3'),previousResult:result,refresh:true});assert.equal(calls,count);}finally{await rm(root,{recursive:true,force:true});}
});

test('changed refresh keeps the old original and manual card, and creates a new version',async()=>{
 const root=await mkdtemp(join(tmpdir(),'changed-')),vault=join(root,'v');let body='第一版原文。';let calls=0;
 const base={url:'https://example.org/article',vault,python:'/usr/bin/python3',capture:async url=>{calls++;const dir=join(root,'captures',String(calls));await mkdir(dir,{recursive:true});await writeFile(join(dir,'article.md'),body);return {directory:dir,text:body,status:'complete'};},flash:{extract:async()=>({slug:'versioned-article',terms:[]}),explain:async()=>[]},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/versioned-article.md---\n# 资料\n摘要。\n---END FILE---',api:{read:p=>readFile(join(vault,p),'utf8')}};
 try{await mkdir(vault);const first=await collectCanonical({...base,workspace:join(root,'w1')});const bytes=await readFile(join(vault,'raw/assets',first.sourceId,'article.md'));await writeFile(first.source,'# 手写资料卡');body='第二版原文，新增末节。';const second=await collectCanonical({...base,workspace:join(root,'w2'),previousResult:first,refresh:true});assert.notEqual(second.sourceId,first.sourceId);assert.notEqual(second.source,first.source);assert.deepEqual(await readFile(join(vault,'raw/assets',first.sourceId,'article.md')),bytes);assert.equal(await readFile(first.source,'utf8'),'# 手写资料卡');assert.match(await readFile(second.source,'utf8'),/新增末节/);}finally{await rm(root,{recursive:true,force:true});}
});
test('partial platform capture is retried after recovery instead of memoized forever',async()=>{
 const root=await mkdtemp(join(tmpdir(),'capture-recovery-')),vault=join(root,'v'),workspace=join(root,'w');let captures=0;
 const input={url:'https://x.com/a/status/123',vault,workspace,python:'/usr/bin/python3',capture:async()=>{captures++;const directory=join(workspace,'capture');await mkdir(directory,{recursive:true});await writeFile(join(directory,'article.md'),'中文完整内容。');return{directory,text:'中文完整内容。',status:captures===1?'partial':'complete'};},flash:{extract:async()=>({slug:'recovered-source',terms:[]}),explain:async()=>[]},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/recovered-source.md---\n# 资料\n摘要。\n---END FILE---',api:{read:p=>readFile(join(vault,p),'utf8')}};
 try{await mkdir(vault);await assert.rejects(collectCanonical(input),/Attachments incomplete/);assert.equal((await collectCanonical(input)).status,'complete');assert.equal(captures,2);}finally{await rm(root,{recursive:true,force:true});}
});
test('translation quota failures keep their waiting reason and resume without repeating successful models',async()=>{
 const root=await mkdtemp(join(tmpdir(),'quota-reading-')),vault=join(root,'v'),workspace=join(root,'w');let quota=true,calls=0;
 const input={url:'https://example.org/quota',vault,workspace,python:'/usr/bin/python3',capture:async()=>{calls++;const directory=join(workspace,'capture');await mkdir(directory,{recursive:true});await writeFile(join(directory,'article.md'),'# Example\n\nFirst paragraph.');return{directory,text:'# Example\n\nFirst paragraph.',status:'complete'};},flash:{extract:async()=>{calls++;return{slug:'quota-example',terms:[]};},explain:async()=>[]},generate:async({stage})=>{calls++;return stage==='analysis'?'分析':'---FILE: wiki/sources/quota-example.md---\n# 来源\n摘要。\n---END FILE---';},translate:async()=>{if(quota)throw Error('Codex quota unavailable; waiting for quota');return '# 示例\n\n第一段。';},api:{read:p=>readFile(join(vault,p),'utf8')}};
 try{await mkdir(vault);await assert.rejects(collectCanonical(input),/quota/);const successfulCalls=calls;quota=false;assert.equal((await collectCanonical(input)).status,'complete');assert.equal(calls,successfulCalls);}finally{await rm(root,{recursive:true,force:true});}
});
