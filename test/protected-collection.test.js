import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,readFile,writeFile,rm,symlink,readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,dirname,resolve} from 'node:path';
import {createAdapters} from '../src/nashsu.js';
import {recordArticle} from '../src/wk.js';

test('collection preserves original and concurrent manual changes; candidates retain dated provenance',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-protect-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');
  await mkdir(snapshot);await mkdir(join(vault,'wiki/concepts'),{recursive:true});
  await writeFile(join(snapshot,'article.md'),'# Evidence\nNew claim.');
  const human=join(vault,'wiki/concepts/claim.md');await writeFile(human,'Old claim, source A (2025).\n<!-- preserve -->');
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},generate:async({stage})=>{
   if(stage==='analysis')return '新证据与旧观点存在冲突。';
   await writeFile(human,'Old claim, source A (2025).\n<!-- preserve -->\nConcurrent human note.');
   return '---FILE: wiki/sources/evidence.md---\n# 新证据\n新观点。\n---END FILE---\n---FILE: wiki/concepts/claim.md---\n# 主张\nNew claim.\n---END FILE---';
  }});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'evidence',context:'',url:'https://x.com/a/status/123'});
  assert.equal(result.status,'complete');
  assert.match(await readFile(human,'utf8'),/Concurrent human note/);
  assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),'# Evidence\nNew claim.');
  const source=await readFile(result.source,'utf8');assert.match(source,/raw\/assets\//);assert.match(source,/https:\/\/x.com\/a\/status\/123/);
  assert.equal(result.reviews.length,1);
  const proposal=JSON.parse(await readFile(result.reviews[0].file,'utf8'));
  assert.match(proposal.previous,/Concurrent human note/);assert.match(proposal.candidate,/New claim/);assert.match(proposal.createdAt,/^20\d\d-/);
  assert.equal(proposal.sourceId,result.sourceId);
  await assert.rejects(readFile(join(vault,'raw/sources/evidence.md')), {code:'ENOENT'});
 }finally{await rm(root,{recursive:true,force:true});}
});

test('local media references resolve to immutable archived bytes from the generated source card',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-media-links-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(join(snapshot,'images'),{recursive:true});
  const original='# Evidence\n![image](images/image-01.jpg)';await writeFile(join(snapshot,'article.md'),original);await writeFile(join(snapshot,'images/image-01.jpg'),'immutable image');
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/evidence.md---\n# 证据\n![image](images/image-01.jpg)\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'evidence',context:'',url:'https://x.com/a/status/123'});
  const body=await readFile(result.source,'utf8');const target=body.match(/!\[image\]\(([^)]+)\)/u)[1];
  assert.equal(await readFile(resolve(dirname(result.source),target),'utf8'),'immutable image');
  assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('resubmitting after a source-card-only commit finishes saved candidates without any model call',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-partial-commit-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'# Evidence');
  const options={vault,python:'python3',captureDirectory:root,flash:{},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/evidence.md---\n# 证据\n---END FILE---\n---FILE: wiki/concepts/evidence.md---\n# 概念\n---END FILE---'};
  const input={capture:{directory:snapshot},slug:'evidence',context:'',url:'https://x.com/a/status/123'};
  const first=await createAdapters(options).importAndCompile(input);
  await rm(join(vault,'.personal-wiki/compilations',first.sourceId,'result.json'));
  await rm(join(vault,'wiki/concepts/evidence.md'));
  const adapters=createAdapters({...options,generate:async()=>assert.fail('saved commit must not call model')});
  const result=await recordArticle({url:input.url,vault},adapters);
  assert.ok(['complete','existing'].includes(result.status));
  assert.match(await readFile(join(vault,'wiki/concepts/evidence.md'),'utf8'),/概念/);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('an interrupted model response archives the source but writes no pages; retry reuses the archive',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-interrupted-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);
  await writeFile(join(snapshot,'article.md'),'# Saved evidence');
  let truncated=true,calls=0;
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},generate:async({stage})=>{
   calls++;if(stage==='analysis')return '分析';
   return '---FILE: wiki/sources/evidence.md---\n# 证据\n'+(truncated?'':'---END FILE---');
  }});
  const input={capture:{directory:snapshot},slug:'evidence',context:'',url:'https://x.com/a/status/123'};
  await assert.rejects(adapters.importAndCompile(input),/Incomplete/);
  assert.equal((await readdir(join(vault,'raw/assets'))).length,1);
  await assert.rejects(readFile(join(vault,'wiki/sources/evidence.md')),{code:'ENOENT'});
  truncated=false;const result=await adapters.importAndCompile(input);assert.equal(result.status,'complete');
  const count=calls;await adapters.importAndCompile(input);assert.equal(calls,count);
  assert.equal((await readdir(join(vault,'raw/assets'))).length,1);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('unsafe candidates and symlink destinations cannot change files outside the Vault',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-symlink-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot'),outside=join(root,'outside');
  await mkdir(join(vault,'wiki'),{recursive:true});await mkdir(snapshot);await mkdir(outside);
  await writeFile(join(snapshot,'article.md'),'# Safe evidence');
  await writeFile(join(outside,'evidence.md'),'Human file');
  await symlink(outside,join(vault,'wiki/sources'));
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/evidence.md---\nOverwrite\n---END FILE---'});
  await assert.rejects(adapters.importAndCompile({capture:{directory:snapshot},slug:'evidence',url:'https://x.com/a/status/123'}),/Protected archive failed/);
  assert.equal(await readFile(join(outside,'evidence.md'),'utf8'),'Human file');
 }finally{await rm(root,{recursive:true,force:true});}
});

test('unchanged refresh repairs interrupted archive indexing without creating another source version',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-index-recovery-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'# Evidence');
  const options={vault,python:'python3',captureDirectory:root,flash:{},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/evidence.md---\n# 证据\n---END FILE---'};
  const input={capture:{directory:snapshot},slug:'evidence',context:'',url:'https://x.com/a/status/123'};
  const first=await createAdapters(options).importAndCompile(input);
  await writeFile(join(vault,'.personal-wiki/captures.json'),'{}');
  const second=await createAdapters({...options,refresh:true}).importAndCompile(input);
  assert.equal(first.sourceId,second.sourceId);
  const index=JSON.parse(await readFile(join(vault,'.personal-wiki/captures.json'),'utf8'));
  assert.equal(index[input.url].id,first.sourceId);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('archive interrupted between source creation and manifest resumes using the reserved name',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-archive-recovery-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'# Evidence');
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/evidence.md---\n# 证据\n---END FILE---'});
  const input={capture:{directory:snapshot},slug:'evidence',context:'',url:'https://x.com/a/status/123'};
  const first=await adapters.importAndCompile(input);
  await rm(join(vault,'.personal-wiki',first.sourceId+'.json'));
  await writeFile(join(vault,'.personal-wiki/captures.json'),'{}');
  await adapters.importAndCompile(input);
  assert.deepEqual(await readdir(join(vault,'raw/inputs')),['evidence.md']);
 }finally{await rm(root,{recursive:true,force:true});}
});
