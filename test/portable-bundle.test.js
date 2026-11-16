import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,mkdir,readFile,readdir,writeFile,rm,realpath} from 'node:fs/promises';import {join} from 'node:path';import {tmpdir} from 'node:os';import {openIngestion} from '../src/ingestion.js';
test('conversion can move into an independent Wiki installation without reacquisition',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-portable-')));
 try{
  const a=await openIngestion({stateDir:join(root,'convert-state'),python:'/usr/bin/python3'});const task=await a.submit({text:'独立来源包需要完整保留最后一句。',mode:'convert'});await a.run(task.id);
  const exported=await a.exportBundle(task.id,{directory:join(root,'package')});
  const vault=join(root,'vault');await mkdir(vault);const b=await openIngestion({stateDir:join(root,'wiki-state'),vault,python:'/usr/bin/python3'},{capture:()=>{throw Error('Must not reacquire exported source');},api:{read:path=>readFile(join(vault,path),'utf8'),search:async()=>({results:(await readdir(join(vault,'wiki/sources'))).map(n=>({path:'wiki/sources/'+n}))})},generate:async({stage,sourceName})=>stage==='analysis'?'分析':`---FILE: wiki/sources/${sourceName}.md---\n# 来源\n完整来源。\n---END FILE---`});
  const imported=await b.submit({bundleFile:exported.manifest,name:'portable-source'});const done=await b.run(imported.id);assert.equal(done.status,'complete',done.failure);assert.match(await readFile(done.result.source,'utf8'),/完整保留最后一句/);
  assert.equal((await b.submit({bundleFile:exported.manifest,name:'portable-source'})).id,imported.id);
  await writeFile(join(root,'package/payload/article.md'),'tampered');await assert.rejects(b.submit({bundleFile:exported.manifest,name:'tampered-source'}),/integrity/);
 }finally{await rm(root,{recursive:true,force:true});}
});
test('portable imports reject replacement without refresh and unsafe paths before writing',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-portable-')));
 try{
  const s=await openIngestion({stateDir:join(root,'state'),python:'/usr/bin/python3'});const j=await s.submit({text:'相同来源的原始正文必须保护。',mode:'convert'});await s.run(j.id);const exported=await s.exportBundle(j.id,{directory:join(root,'export')});
  const {createHash}=await import('node:crypto');const manifest=JSON.parse(await readFile(exported.manifest,'utf8'));const replacement='这是更改后的来源正文，必须明确刷新。';await writeFile(join(root,'export/payload/article.md'),replacement);manifest.hashes['article.md']=createHash('sha256').update(replacement).digest('hex');await writeFile(exported.manifest,JSON.stringify(manifest));
  await assert.rejects(s.submit({bundleFile:exported.manifest,mode:'convert',requestId:'new-import'}),/refresh/);
  const {writePortable}=await import('../src/portable-bundle.js');await assert.rejects(writePortable({directory:root,hashes:{'../outside':'a'.repeat(64)}},join(root,'bad')),/Unsafe/);assert.deepEqual((await readdir(root)).filter(n=>n==='outside'),[]);
 }finally{await rm(root,{recursive:true,force:true});}
});
