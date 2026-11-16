import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const exec=promisify(execFile);
const cli=new URL('../scripts/wiki.mjs',import.meta.url).pathname;
import {openIngestion} from '../src/ingestion.js';
import {updateMaintenance} from '../src/ingestion-maintenance.js';

test('AI can convert text, inspect its durable task and reuse it without touching a Wiki',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-cli-')));
 try{
  const config=join(root,'config.json');await writeFile(config,JSON.stringify({stateDir:join(root,'state'),python:'/usr/bin/python3',autoStart:false}));
  const call=async args=>JSON.parse((await exec(process.execPath,[cli,...args,'--config',config])).stdout);
  const original='# 我的想法\n\n这是完整原话，不应被摘要替代。\n';
  const done=await call(['convert','--text',original]);
  assert.equal(done.status,'converted');
  assert.equal(await readFile(done.bundle.markdown,'utf8'),original);
  assert.equal((await call(['status',done.id])).status,'converted');
  assert.equal((await call(['convert','--text',original])).id,done.id);
  await assert.rejects(readFile(join(root,'vault/wiki/index.md')),{code:'ENOENT'});
  await call(['submit','--text','第一份资料','--request-id','stable-call']);
  await assert.rejects(call(['submit','--text','另一份资料','--request-id','stable-call']),/conflict/);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('worker reschedules checkout-waiting maintenance and late members of verified repairs with backoff',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-maint-queue-')));
 try{
  const config={stateDir:join(root,'state'),python:'/usr/bin/python3',configPath:join(root,'config.json'),maintenance:{project:join(root,'development')}};
  const started=[],service=await openIngestion(config,{dispatchMaintenance:async id=>{started.push(id);return true;}}),id='d'.repeat(64);
  await updateMaintenance(config,id,()=>({id,status:'waiting_workspace',tasks:['1'.repeat(64)],nextAttemptAt:0}));
  await service.workOnce();assert.deepEqual(started,[id]);await service.workOnce();assert.equal(started.length,1);
  await updateMaintenance(config,id,r=>({...r,status:'verified',activated:true,tasks:['late-task'],replayedTasks:[],nextAttemptAt:0}));
  await service.workOnce();assert.deepEqual(started,[id,id]);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('parallel same-platform failures remain attached to one maintenance request',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-aggregate-')));
 try{
  let arrivals=0,release;const barrier=new Promise(r=>release=r);
  const service=await openIngestion({stateDir:join(root,'state'),python:'/usr/bin/python3'},{capture:async({job})=>{
   if(job.rounds===2){if(++arrivals===2)release();await barrier;}throw Error('Synthetic source parser failure');
  }});
  const a=await service.submit({input:'https://x.com/example/status/101',mode:'convert'}),b=await service.submit({input:'https://x.com/example/status/102',mode:'convert'});
  const jobs=await Promise.all([service.run(a.id),service.run(b.id)]);
  assert.equal(jobs[0].maintenance.id,jobs[1].maintenance.id);
  const request=await service.maintain(a.id);
  assert.deepEqual(request.tasks.sort(),[a.id,b.id].sort());
 }finally{await rm(root,{recursive:true,force:true});}
});

test('unsupported platforms stay pending without automatic development, and speculative login errors still recover twice',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-route-fail-')));
 try{
  const service=await openIngestion({stateDir:join(root,'state'),python:'/usr/bin/python3'},{capture:async()=>{throw Error('WeChat capture failed; inspect local fetch.log, login may be required');}});
  const other=await service.submit({input:'https://www.kuaishou.com/short-video/synthetic',mode:'convert'});
  const pending=await service.run(other.id);assert.equal(pending.status,'pending');assert.equal(pending.nextAction,'source_support_planned');assert.equal(pending.maintenance,undefined);
  const known=await service.submit({input:'https://mp.weixin.qq.com/s/synthetic',mode:'convert'});
  const repaired=await service.run(known.id);assert.equal(repaired.status,'pending');assert.equal(repaired.rounds,2);assert.ok(repaired.maintenance);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('a process interruption in the second round recovers into pending rather than permanent processing',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-crash-')));
 try{
  const config={stateDir:join(root,'state'),python:'/usr/bin/python3'};
  const service=await openIngestion(config),job=await service.submit({input:'https://x.com/example/status/555',mode:'convert'});
  const moduleURL=new URL('../src/ingestion.js',import.meta.url).href;
  const script=`import {openIngestion} from ${JSON.stringify(moduleURL)};const s=await openIngestion(${JSON.stringify(config)},{capture:async({job})=>{if(job.rounds===2)process.exit(9);throw Error('synthetic first round failure')}});await s.run(${JSON.stringify(job.id)});`;
  await assert.rejects(exec(process.execPath,['--input-type=module','-e',script]));
  await new Promise(r=>setTimeout(r,100));
  const recovered=await service.run(job.id);assert.equal(recovered.status,'pending');assert.equal(recovered.rounds,2);assert.ok(recovered.maintenance);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('incomplete WeChat is pending after two rounds and supplied full text resumes the same task',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-pending-')));
 try{
  const partial=join(root,'partial');await mkdir(partial);await writeFile(join(partial,'article.md'),'只有开头');
  const config={stateDir:join(root,'state'),python:'/usr/bin/python3'};
  const source={capture:async()=>({directory:partial,status:'partial'})};
  const service=await openIngestion(config,source);
  const job=await service.submit({input:'https://mp.weixin.qq.com/s/synthetic-article?needed=value',mode:'convert'});
  const pending=await service.run(job.id);
  assert.equal(pending.status,'pending');assert.equal(pending.rounds,2);
  assert.equal((await (await openIngestion(config,source)).run(job.id)).rounds,2);
  const full=join(root,'full.md');await writeFile(full,'# 用户补充的正文\n\n这是补齐的完整正文及结尾。');
  await service.supplement(job.id,{file:full});
  const done=await service.run(job.id);
  assert.equal(done.id,job.id);assert.equal(done.status,'converted');
  assert.match(await readFile(done.bundle.markdown,'utf8'),/完整正文及结尾/);
  assert.equal(done.supplements[0].kind,'user-provided');
 }finally{await rm(root,{recursive:true,force:true});}
});

test('X share links route to one source and preserve captured original files in convert mode',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-x-')));
 try{
  const external=join(root,'captured');await mkdir(external);await writeFile(join(external,'article.md'),'# 帖子\n\n目标帖与引用帖的完整文字。');await writeFile(join(external,'raw.html'),'<article>原始页面</article>');
  const service=await openIngestion({stateDir:join(root,'state'),python:'/usr/bin/python3'},{capture:async()=>({directory:external,status:'complete',contextStatus:'complete'})});
  const a=await service.submit({input:'记录 https://x.com/example/status/123?s=46',mode:'convert'});
  const b=await service.submit({input:'https://twitter.com/example/status/123?a=tracking',mode:'convert'});
  assert.equal(a.id,b.id);assert.equal(a.platform,'x');
  const done=await service.run(a.id);assert.equal(done.status,'converted');
  assert.match(await readFile(join(done.bundle.directory,'raw.html'),'utf8'),/原始页面/);
  const another=await service.submit({input:'https://x.com/example/status/123',mode:'convert',requestId:'new-ai-invocation'});
  const reused=await (await openIngestion({stateDir:join(root,'state'),python:'/usr/bin/python3'},{capture:async()=>{throw Error('Network must not be repeated');}})).run(another.id);
  assert.equal(reused.status,'converted');assert.equal(reused.bundle.markdown,done.bundle.markdown);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('recording text uses Wiki compilation without Flash and verifies the published full text',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-record-'))),vault=join(root,'vault');
 try{
  await mkdir(vault);
  const service=await openIngestion({stateDir:join(root,'state'),vault,python:'/usr/bin/python3'},{
   api:{read:path=>readFile(join(vault,path),'utf8'),search:async()=>({results:[{path:'wiki/sources/user-note.md'}]})},
   generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/user-note.md---\n# 用户想法\n摘要。\n---END FILE---'
  });
  const job=await service.submit({text:'# 用户想法\n\n[00:00] 这里保留未经缩写的完整原话与末节。',name:'user-note',mode:'convert'});
  assert.equal((await service.run(job.id)).status,'converted');
  const done=await service.ingest(job.id);
  assert.equal(done.status,'complete');
  assert.match(await readFile(done.result.source,'utf8'),/完整原话与末节/);
  assert.equal((await service.run(job.id)).result.source,done.result.source);
  await writeFile(join(vault,'raw/assets',done.result.sourceId,'article.md'),'篡改后的字节');
  assert.equal((await service.run(job.id)).status,'waiting_verification');
 }finally{await rm(root,{recursive:true,force:true});}
});
