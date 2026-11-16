import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,chmod,rm,realpath} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {repairIngestion} from '../src/ingestion-maintenance.js';
const exec=promisify(execFile);

test('a busy source lease leaves verified replay pending and a later attempt can execute it',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-replay-busy-')));
 try{
  const stateDir=join(root,'state'),runtimeRoot=join(stateDir,'runtime'),version='e'.repeat(40),id='f'.repeat(64),task='2'.repeat(64),counter=join(root,'calls');
  const release=join(runtimeRoot,'releases',version,'scripts');await mkdir(release,{recursive:true});
  await writeFile(join(release,'wiki.mjs'),`import fs from 'node:fs';const p=${JSON.stringify(counter)};const n=fs.existsSync(p)?Number(fs.readFileSync(p,'utf8'))+1:1;fs.writeFileSync(p,String(n));if(n===1){console.error('Task queue already running');process.exit(1)}console.log(JSON.stringify({status:process.argv[2]==='retry'?'queued':'converted'}));`);
  const directory=join(stateDir,'ingestion/maintenance');await mkdir(directory,{recursive:true});await writeFile(join(directory,id+'.json'),JSON.stringify({id,tasks:[task],status:'verified',activated:true,testsPassed:true,version}));
  const config={stateDir,runtimeRoot,python:'/usr/bin/python3',configPath:join(root,'config.json'),codexBinary:'/must-not-create-another-session'};
  const busy=await repairIngestion(config,id);assert.ok(!(busy.replayedTasks??[]).includes(task));
  const done=await repairIngestion(config,id);assert.equal(done.replayResults[task].status,'converted');assert.equal(await readFile(counter,'utf8'),'3');
 }finally{await rm(root,{recursive:true,force:true});}
});

test('maintenance requires an acknowledged Codex session and independently passing regression before enabling repair',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-maintenance-')));
 try{
  const project=join(root,'project');await mkdir(project);await exec('git',['init'],{cwd:project});
  const git=['-c','user.name=WikiTest','-c','user.email=wiki@example.invalid'];
  await writeFile(join(project,'processor.txt'),'broken');await exec('git',['add','processor.txt'],{cwd:project});await exec('git',[...git,'commit','-m','fixture'],{cwd:project});
  const binary=join(root,'fake-codex');
  await writeFile(binary,`#!${process.execPath}\nconst fs=require('node:fs');Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,500);fs.writeFileSync('processor.txt','repaired');console.log(JSON.stringify({type:'thread.started',thread_id:'fixture-session-1'}));console.log(JSON.stringify({type:'turn.completed'}));\n`);await chmod(binary,0o700);
  const stateDir=join(root,'state'),id='a'.repeat(64),directory=join(stateDir,'ingestion/maintenance');await mkdir(directory,{recursive:true});
  await writeFile(join(directory,id+'.json'),JSON.stringify({id,status:'queued',tasks:[],reason:'synthetic processor failure'}));
  const config={stateDir,runtimeRoot:join(stateDir,'runtime'),python:'/usr/bin/python3',codexBinary:binary,maintenance:{project,testCommands:[[process.execPath,'-e',"require('node:assert/strict').equal(require('node:fs').readFileSync('processor.txt','utf8'),'repaired')"]]}};
  const concurrent='c'.repeat(64);await writeFile(join(directory,concurrent+'.json'),JSON.stringify({id:concurrent,status:'queued',tasks:[],reason:'parallel fault'}));
  const outcomes=await Promise.all([repairIngestion(config,id),repairIngestion(config,concurrent)]);
  const result=outcomes.find(r=>r.status==='verified'),waiting=outcomes.find(r=>r.status==='waiting_workspace');
  assert.ok(result);assert.ok(waiting);
  assert.equal(waiting.status,'waiting_workspace');
  assert.equal(result.status,'verified');assert.equal(result.testsPassed,true);assert.equal(result.sessionId,'fixture-session-1');
  assert.equal(JSON.parse(await readFile(join(directory,result.id+'.json'),'utf8')).version,result.version);
  assert.equal(await readFile(join(config.runtimeRoot,'current/processor.txt'),'utf8'),'repaired');
  await writeFile(binary,(await readFile(binary,'utf8')).replace("'repaired'","'changed-but-broken'"));
  const second='b'.repeat(64);await writeFile(join(directory,second+'.json'),JSON.stringify({id:second,status:'queued',tasks:[],reason:'another synthetic failure'}));
  const rejected=await repairIngestion({...config,maintenance:{...config.maintenance,testCommands:[[process.execPath,'-e','process.exit(3)']]}},second);
  assert.equal(rejected.status,'failed');
  assert.equal(await readFile(join(config.runtimeRoot,'current/processor.txt'),'utf8'),'repaired');
  await writeFile(join(project,'processor.txt'),'repaired');
  await writeFile(binary,`#!${process.execPath}\nconst fs=require('node:fs'),cp=require('node:child_process');fs.mkdirSync('raw');fs.writeFileSync('raw/evidence.txt','synthetic private evidence');cp.execFileSync('git',['add','raw']);cp.execFileSync('git',${JSON.stringify([...git,'commit','-m','unexpected child commit'])});console.log(JSON.stringify({type:'thread.started',thread_id:'fixture-session-2'}));\n`);
  const third='d'.repeat(64);await writeFile(join(directory,third+'.json'),JSON.stringify({id:third,status:'queued',tasks:[],reason:'unexpected committed content'}));
  const unsafe=await repairIngestion(config,third);assert.equal(unsafe.status,'failed');
  await assert.rejects(readFile(join(config.runtimeRoot,'current/raw/evidence.txt')),{code:'ENOENT'});
 }finally{await rm(root,{recursive:true,force:true});}
});
