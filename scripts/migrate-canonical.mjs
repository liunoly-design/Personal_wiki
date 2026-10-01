// Explicit local migration. All content/backups remain outside the code repository.
import {mkdir,readFile,readdir,rename,rm,lstat} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {homedir} from 'node:os';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {localNashsuAPI} from '../src/nashsu-api.js';
import {verifyPublication} from '../src/canonical-library.js';
import {saveJSON,optionalJSON} from '../src/durable-files.js';
import {assessMigration} from '../src/migration-status.js';
import {canonicalURL,acquireQueueLease} from '../src/task-queue.js';
const hash=x=>createHash('sha256').update(x).digest('hex');
const config=JSON.parse(await readFile(join(homedir(),'.openclaw/openclaw.json'),'utf8')).plugins.entries['personal-wiki'].config;
const {vault,stateDir,python}=config;
const destination=join(stateDir,'migrations','canonical-v04');await mkdir(destination,{recursive:true,mode:0o700});
async function operation(operation){
 return new Promise((accept,reject)=>{
  const child=spawn(python,[resolve(import.meta.dirname,'canonical_migration.py')],{stdio:['pipe','pipe','pipe']});let out='',err='';
  child.stdout.on('data',x=>out+=x);child.stderr.on('data',x=>err+=x);child.on('error',reject);child.stdin.on('error',reject);
  child.on('close',code=>code?reject(Error(err)):accept(JSON.parse(out)));child.stdin.end(JSON.stringify({operation,vault,destination}));
 });
}
const release=process.argv.includes('--apply')?await acquireQueueLease(stateDir,python):null;
try {
console.log(await operation('plan'));
if(!process.argv.includes('--apply'))process.exit(0);
const api=await localNashsuAPI(vault);await api.assertPublisherReady();
console.log(await operation('apply'));
const plan=await optionalJSON(join(destination,'plan.json'));
for(const [path,digest] of Object.entries(plan.hashes))if(hash(await api.read(path))!==digest)throw Error('API verification mismatch: '+path);
for(const result of Object.values(plan.sources))await verifyPublication(result,{vault,api});
await saveJSON(join(destination,'verified.json'),{planHash:hash(await readFile(join(destination,'plan.json'))),verifiedAt:new Date().toISOString()});
for(const directory of ['sources','completed','tasks','work'])await mkdir(join(stateDir,directory),{recursive:true,mode:0o700});
let oldJobsDirectory=join(stateDir,'jobs');try{await readdir(oldJobsDirectory);}catch(e){if(e.code!=='ENOENT')throw e;oldJobsDirectory=join(destination,'legacy-jobs');}
const jobs=await Promise.all((await readdir(oldJobsDirectory)).filter(name=>/^[a-f0-9]{64}\.json$/u.test(name)).map(async name=>optionalJSON(join(oldJobsDirectory,name))));
const native=await optionalJSON(join(vault,'.llm-wiki/ingest-cache.json'));
const incomplete=[],completedSourceIds=[];
for(const [url,result] of Object.entries(plan.sources)){
 result.relativeSource??=result.source.slice(vault.length+1);
 const related=jobs.filter(job=>canonicalURL(job.url)===canonicalURL(url));
 const receipts=await Promise.all(related.map(job=>optionalJSON(join(stateDir,'captures',job.id,'capture-result.json'))));
 const entry=Object.values(native?.entries??{}).find(entry=>entry.filesWritten?.includes(result.relativeSource));
 const decision=assessMigration(result,{url,jobs,nativeEntry:entry,captureStatuses:receipts.map(r=>r?.status)});
 if(decision.complete){completedSourceIds.push(result.sourceId);await saveJSON(join(stateDir,'sources',hash(canonicalURL(url))+'.json'),{url:canonicalURL(url),result:{...result,status:'complete',completionMode:decision.mode},verifiedAt:new Date().toISOString()});}
 else incomplete.push(result.sourceId);
}
await saveJSON(join(destination,'incomplete.json'),{sourceIds:incomplete});
await saveJSON(join(destination,'completed-source-ids.json'),completedSourceIds);
let completed=0,pending=0;
for(const name of await readdir(oldJobsDirectory)){
 if(!/^[a-f0-9]{64}\.json$/u.test(name))continue;
 const job=await optionalJSON(join(oldJobsDirectory,name));if(!job?.url)continue;
 await saveJSON(join(destination,'jobs',name),job);
 const known=await optionalJSON(join(stateDir,'sources',hash(canonicalURL(job.url))+'.json'));
 if(known){
  await saveJSON(join(stateDir,'completed',name),{id:job.id,url:canonicalURL(job.url),sender:job.sender,chat:job.chat,messageId:job.messageId,status:'done',stage:'verified',createdAt:job.createdAt,completedAt:new Date().toISOString(),result:known.result,receiptId:job.receiptId,silent:true});completed++;
 }else{
  const task={...job,url:canonicalURL(job.url),status:'queued',nextAttemptAt:0,silent:true};
  await saveJSON(join(stateDir,'tasks',name),task);await saveJSON(join(stateDir,'work',job.id,'task.json'),task);
  const oldCapture=join(stateDir,'captures',job.id);try{if((await lstat(oldCapture)).isSymbolicLink())throw Error('Capture symlink');const newCapture=join(stateDir,'work',job.id,'capture');await rename(oldCapture,newCapture);const receipt=await optionalJSON(join(newCapture,'capture-result.json'));if(receipt?.directory?.startsWith(oldCapture+'/')){receipt.directory=newCapture+receipt.directory.slice(oldCapture.length);await saveJSON(join(newCapture,'capture-result.json'),receipt);}}catch(e){if(e.code!=='ENOENT')throw e;}
  pending++;
 }
}
console.log(await operation('cleanup'));
// Runtime metadata is retained as a private migration backup, not a library folder.
const oldMetadata=join(vault,'.personal-wiki'),moved=join(destination,'legacy-metadata');
try{await lstat(moved);}catch(e){if(e.code!=='ENOENT')throw e;await rename(oldMetadata,moved);}
// Old task/capture folders are retired only after verified result ledgers exist.
for(const name of await readdir(oldJobsDirectory)){
 if(!/^[a-f0-9]{64}\.json$/u.test(name))continue;
 const id=name.slice(0,-5);if(await optionalJSON(join(stateDir,'completed',name))){
  const capture=join(stateDir,'captures',id);try{if((await lstat(capture)).isSymbolicLink())throw Error('Capture symlink');await rm(capture,{recursive:true});}catch(e){if(e.code!=='ENOENT')throw e;}
 }
}
await rename(join(stateDir,'jobs'),join(destination,'legacy-jobs')).catch(e=>{if(e.code!=='ENOENT')throw e;});
console.log({completed,pending,backup:destination});

} finally {await release?.();}
