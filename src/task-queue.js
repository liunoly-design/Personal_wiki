import {mkdir,readdir,readFile,rm,lstat,unlink} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {saveJSON,optionalJSON} from './durable-files.js';
const valid=id=>/^[a-f0-9]{64}$/u.test(id);
const urlKey=url=>createHash('sha256').update(url).digest('hex');
export function canonicalURL(url){const u=new URL(url);if(['x.com','twitter.com'].includes(u.hostname)){u.hostname='x.com';u.search='';u.pathname=u.pathname.replace(/\/$/u,'');}u.hash='';return u.href;}
async function acquire(directory,python){
 const child=spawn(python,[resolve(import.meta.dirname,'../scripts/task_lock.py'),join(directory,'worker.lock')],{stdio:['pipe','pipe','pipe']});
 await new Promise((accept,reject)=>{child.once('error',reject);child.stdout.once('data',data=>data.toString().trim()==='ready'?accept():reject(Error('Task queue already running')));child.once('exit',code=>{if(code!==0)reject(Error('Task queue already running or lock unavailable'));});});
 return async()=>{await new Promise(resolve=>{child.once('exit',resolve);child.stdin.end();});};
}
export async function openTaskQueue({stateDir,python,run,deliver,now=Date.now,allowed=()=>true}){
 const active=join(stateDir,'tasks'),complete=join(stateDir,'completed'),work=join(stateDir,'work');
 for(const dir of [stateDir,active,complete,work,join(stateDir,'sources')])await mkdir(dir,{recursive:true,mode:0o700});
 const release=await acquire(stateDir,python);let closed=false,running=false,timer,ingress=Promise.resolve();const controller=new AbortController();
 async function status(id){if(!valid(id))throw Error('Invalid task ID');return await optionalJSON(join(active,id+'.json'))??await optionalJSON(join(complete,id+'.json'));}
 async function enqueue(task){
  if(!valid(task.id))throw Error('Invalid task ID');
  if(await status(task.id))return{duplicate:true,jobId:task.id};
  const job={...task,url:canonicalURL(task.url),status:'queued',stage:'accepted',createdAt:task.createdAt??new Date(now()).toISOString(),attempts:0};
  // A workspace owner record allows reconstruction if the active file is lost.
  await saveJSON(join(work,job.id,'task.json'),job);await saveJSON(join(active,job.id+'.json'),job);
  return{duplicate:false,jobId:job.id};
 }
 async function cleanup(job){
  const directory=join(work,job.id);let info;try{info=await lstat(directory);}catch(e){if(e.code!=='ENOENT')throw e;}
  if(info?.isSymbolicLink())throw Error('Refusing symlink workspace cleanup');
  if(info)await rm(directory,{recursive:true,force:true});
 }
 async function recover(){
  for(const entry of await readdir(work,{withFileTypes:true})){
   if(!entry.isDirectory()||!valid(entry.name))continue;
   if(await status(entry.name))continue;
   const owner=await optionalJSON(join(work,entry.name,'task.json'));
   if(owner?.id===entry.name&&typeof owner.url==='string')await saveJSON(join(active,entry.name+'.json'),{...owner,status:'queued',recovered:true});
  }
 }
 async function drain(){
  if(closed||running)return;running=true;
  try{
   await recover();
   for(const name of (await readdir(active)).filter(n=>/^[a-f0-9]{64}\.json$/u.test(n)).sort()){
    if(closed)break;
    const file=join(active,name);let job;
    try{job=await optionalJSON(file);}catch{continue;}
    if(!job||!valid(job.id)||name!==job.id+'.json')continue;
    if(!allowed(job)){job.status='scope_removed';await saveJSON(file,job);continue;}
    if(job.nextAttemptAt>now())continue;
    try{
     if(job.status!=='cleanup_pending'&&job.status!=='delivery_pending'){
      job.status='processing';await saveJSON(file,job);
      const known=await optionalJSON(join(stateDir,'sources',urlKey(job.url)+'.json'));
      job.result=await run(job,join(work,job.id),controller.signal,async(stage,details={})=>{job.stage=stage;job.details={...job.details,...details};await saveJSON(file,job);},known?.result);
      if(job.result.status!=='complete'){
       job.status=job.result.status==='awaiting_review'?'waiting_review':'retry';job.nextAttemptAt=now()+60000;await saveJSON(file,job);continue;
      }
      // The result returned by run is already verified through the native API.
      await saveJSON(join(stateDir,'sources',urlKey(job.url)+'.json'),{url:job.url,result:job.result,verifiedAt:new Date(now()).toISOString()});
      job.status='cleanup_pending';delete job.failure;await saveJSON(file,job);
     }
     if(job.status==='cleanup_pending'){await cleanup(job);job.status='delivery_pending';await saveJSON(file,job);}
     if(deliver&&!job.silent&&!job.receiptId)job.receiptId=await deliver(job,controller.signal);
     job.status='done';job.completedAt=new Date(now()).toISOString();delete job.details;delete job.nextAttemptAt;
     await saveJSON(join(complete,name),job);await unlink(file);
    }catch(error){
     if(closed){if(!['cleanup_pending','delivery_pending'].includes(job.status))job.status='queued';}
     else{
      job.failure=error.message;job.attempts=(job.attempts??0)+1;
      if(!['cleanup_pending','delivery_pending'].includes(job.status))job.status='retry';
      job.nextAttemptAt=now()+Math.min(3600000,30000*2**Math.min(job.attempts-1,7));
     }
     await saveJSON(file,job);
    }
   }
  }finally{running=false;}
 }
 return{enqueue:task=>{const result=ingress.then(()=>enqueue(task));ingress=result.catch(()=>{});return result;},status,drain,recover,
  async retry(id){if(running)throw Error('Worker busy; task will resume automatically');const job=await optionalJSON(join(active,id+'.json'));if(!job)throw Error('No active task');job.nextAttemptAt=0;await saveJSON(join(active,id+'.json'),job);},
  async start(){await recover();timer=setInterval(()=>{drain().catch(()=>{});},2000);timer.unref();void drain().catch(()=>{});},
  async close(){if(closed)return;closed=true;clearInterval(timer);controller.abort();while(running)await new Promise(resolve=>setTimeout(resolve,25));await release();}
 };
}
