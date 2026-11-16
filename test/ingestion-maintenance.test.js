import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,chmod,rm,realpath} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {repairIngestion} from '../src/ingestion-maintenance.js';
const exec=promisify(execFile);

test('maintenance requires an acknowledged Codex session and independently passing regression before enabling repair',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-maintenance-')));
 try{
  const project=join(root,'project');await mkdir(project);await exec('git',['init'],{cwd:project});
  const git=['-c','user.name=WikiTest','-c','user.email=wiki@example.invalid'];
  await writeFile(join(project,'processor.txt'),'broken');await exec('git',['add','processor.txt'],{cwd:project});await exec('git',[...git,'commit','-m','fixture'],{cwd:project});
  const binary=join(root,'fake-codex');
  await writeFile(binary,`#!${process.execPath}\nconst fs=require('node:fs'),cp=require('node:child_process');fs.writeFileSync('processor.txt','repaired');cp.execFileSync('git',${JSON.stringify([...git,'commit','-am','repair'])});console.log(JSON.stringify({type:'thread.started',thread_id:'fixture-session-1'}));console.log(JSON.stringify({type:'turn.completed'}));\n`);await chmod(binary,0o700);
  const stateDir=join(root,'state'),id='a'.repeat(64),directory=join(stateDir,'ingestion/maintenance');await mkdir(directory,{recursive:true});
  await writeFile(join(directory,id+'.json'),JSON.stringify({id,status:'queued',tasks:[],reason:'synthetic processor failure'}));
  const config={stateDir,runtimeRoot:join(stateDir,'runtime'),python:'/usr/bin/python3',codexBinary:binary,maintenance:{project,testCommands:[[process.execPath,'-e',"require('node:assert/strict').equal(require('node:fs').readFileSync('processor.txt','utf8'),'repaired')"]]}};
  const result=await repairIngestion(config,id);
  assert.equal(result.status,'verified');assert.equal(result.testsPassed,true);assert.equal(result.sessionId,'fixture-session-1');
  assert.equal(JSON.parse(await readFile(join(directory,id+'.json'),'utf8')).version,result.version);
  assert.equal(await readFile(join(config.runtimeRoot,'current/processor.txt'),'utf8'),'repaired');
  await writeFile(binary,(await readFile(binary,'utf8')).replace("'repaired'","'changed-but-broken'"));
  const second='b'.repeat(64);await writeFile(join(directory,second+'.json'),JSON.stringify({id:second,status:'queued',tasks:[],reason:'another synthetic failure'}));
  const rejected=await repairIngestion({...config,maintenance:{...config.maintenance,testCommands:[[process.execPath,'-e','process.exit(3)']]}},second);
  assert.equal(rejected.status,'failed');
  assert.equal(await readFile(join(config.runtimeRoot,'current/processor.txt'),'utf8'),'repaired');
 }finally{await rm(root,{recursive:true,force:true});}
});
