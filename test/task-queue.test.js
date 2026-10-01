import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,access} from 'node:fs/promises';import {tmpdir} from 'node:os';import {join} from 'node:path';
import {openTaskQueue} from '../src/task-queue.js';
const task={id:'a'.repeat(64),url:'https://x.com/a/status/123',sender:'ou_test',chat:'oc_test'};
test('startup resumes an interrupted task, preserves failed work, then removes workspace only after verification',async()=>{
 const stateDir=await mkdtemp(join(tmpdir(),'wiki-queue-'));let fail=true,runs=0,clock=0;
 const options={stateDir,python:'/usr/bin/python3',now:()=>clock,run:async(job,workspace)=>{runs++;await mkdir(workspace,{recursive:true});await writeFile(join(workspace,'kept'),'recover me');if(fail)throw Error('API unavailable');return{status:'complete',sourceId:'b'.repeat(20),files:{'wiki/sources/example.md':'hash'}};}};
 let queue=await openTaskQueue(options);
 try{
  await queue.enqueue(task);await queue.drain();assert.equal((await queue.status(task.id)).status,'retry');await access(join(stateDir,'work',task.id,'kept'));
  await queue.close();fail=false;clock=1000000;queue=await openTaskQueue(options);await queue.drain();
  assert.equal((await queue.status(task.id)).status,'done');await assert.rejects(access(join(stateDir,'work',task.id)));
  assert.equal((await queue.enqueue(task)).duplicate,true);await queue.drain();assert.equal(runs,2);
 }finally{await queue.close();await rm(stateDir,{recursive:true,force:true});}
});
test('two processes cannot own the same queue and successful jobs do not run again after a cleanup interruption',async()=>{
 const stateDir=await mkdtemp(join(tmpdir(),'wiki-lock-'));let count=0;
 const options={stateDir,python:'/usr/bin/python3',run:async()=>{count++;return{status:'complete'};}};
 const queue=await openTaskQueue(options);
 try{
  await assert.rejects(openTaskQueue(options),/already running/);
  await queue.enqueue(task);await queue.drain();await queue.drain();assert.equal(count,1);
  assert.equal((await queue.status(task.id)).status,'done');
 }finally{await queue.close();await rm(stateDir,{recursive:true,force:true});}
});

test('delivery failure resumes delivery after cleanup without rerunning the article',async()=>{
 const stateDir=await mkdtemp(join(tmpdir(),'wiki-delivery-'));let count=0,clock=0,offline=true;
 const options={stateDir,python:'/usr/bin/python3',now:()=>clock,run:async()=>{count++;return{status:'complete'};},deliver:async()=>{if(offline)throw Error('delivery unavailable');return'om_reply';}};
 let queue=await openTaskQueue(options);
 try{
  await queue.enqueue(task);await queue.drain();assert.equal((await queue.status(task.id)).status,'delivery_pending');
  await queue.close();offline=false;clock=1000000;queue=await openTaskQueue(options);await queue.drain();
  assert.equal(count,1);assert.equal((await queue.status(task.id)).status,'done');
 }finally{await queue.close();await rm(stateDir,{recursive:true,force:true});}
});

test('a slow task does not block a different article and repeated failures wait after five attempts',async()=>{
 const stateDir=await mkdtemp(join(tmpdir(),'wiki-parallel-'));let unblock,second=false,clock=0;
 const first=new Promise(resolve=>unblock=resolve);
 const queue=await openTaskQueue({stateDir,python:'/usr/bin/python3',now:()=>clock,run:async job=>{
  if(job.id===task.id){await first;return{status:'complete'};}second=true;throw Error('network unavailable');
 }});
 try{
  await queue.enqueue(task);await queue.enqueue({...task,id:'b'.repeat(64),url:'https://x.com/a/status/456'});
  const draining=queue.drain();await new Promise(resolve=>setTimeout(resolve,100));assert.equal(second,true);unblock();await draining;
  for(let i=0;i<5;i++){clock+=4000000;await queue.drain();}
  const status=await queue.status('b'.repeat(64));assert.equal(status.status,'waiting_retry');assert.equal(status.attempts,5);
 }finally{unblock();await queue.close();await rm(stateDir,{recursive:true,force:true});}
});
