import {mkdir,readdir,rm,lstat,unlink} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {saveJSON,optionalJSON} from './durable-files.js';
const valid=id=>/^[a-f0-9]{64}$/u.test(id);
const urlKey=url=>createHash('sha256').update(url).digest('hex');
export function canonicalURL(url){const u=new URL(url);if(['x.com','twitter.com'].includes(u.hostname)){u.hostname='x.com';u.search='';u.pathname=u.pathname.replace(/\/$/u,'');}u.hash='';return u.href;}
export async function acquireQueueLease(directory,python){
 const child=spawn(python,[resolve(import.meta.dirname,'../scripts/task_lock.py'),join(directory,'worker.lock')],{stdio:['pipe','pipe','pipe']});
 await new Promise((accept,reject)=>{child.once('error',reject);child.stdout.once('data',data=>data.toString().trim()==='ready'?accept():reject(Error('Task queue already running')));child.once('exit',code=>{if(code!==0)reject(Error('Task queue already running or lock unavailable'));});});
 return async()=>{await new Promise(resolve=>{child.once('exit',resolve);child.stdin.end();});};
}
function waitingReason(message,attempts){
 if(/ASR login required/iu.test(message))return 'waiting_asr_auth';
 if(/ASR unknown cloud result/iu.test(message))return 'waiting_unknown';
 if(/ASR backend unavailable|ASR backend version changed|ASR empty voiced|ASR suspected truncation|ASR retry budget exhausted|metadata retry budget exhausted|Download retry budget exhausted/iu.test(message))return 'waiting_asr';
 if(/Private or non-public|DNS resolution|Non-public DoH/iu.test(message))return 'waiting_network';
 if(/Unsupported source URL/iu.test(message))return 'waiting_input';
 if(/402|quota|capacity|额度/iu.test(message))return 'waiting_capacity';
 if(/401|403|login|captcha|验证码|登录/iu.test(message))return 'waiting_login';
 if(/Article extraction incomplete|extraction requires review/iu.test(message))return 'waiting_extraction';
 if(/Attachments incomplete|unsupported media/iu.test(message))return 'waiting_media';
 return attempts>=5?'waiting_retry':'retry';
}
export async function openTaskQueue({stateDir,python,run,deliver,notifyWaiting,now=Date.now,allowed=()=>true}){
 const active=join(stateDir,'tasks'),complete=join(stateDir,'completed'),work=join(stateDir,'work');
 for(const dir of [stateDir,active,complete,work,join(stateDir,'sources')])await mkdir(dir,{recursive:true,mode:0o700});
 const release=await acquireQueueLease(stateDir,python);let closed=false,running=false,timer,ingress=Promise.resolve();const controller=new AbortController();
 const inFlightURLs=new Set(),inFlight=new Map();let scheduling=false;
 async function status(id){if(!valid(id))throw Error('Invalid task ID');return await optionalJSON(join(active,id+'.json'))??await optionalJSON(join(complete,id+'.json'));}
 async function enqueue(task){
  if(closed)throw Error('Task queue closed');
  if(!valid(task.id))throw Error('Invalid task ID');
  if(await status(task.id))return{duplicate:true,jobId:task.id};
  const linked=await optionalJSON(join(stateDir,'sources',urlKey(canonicalURL(task.url))+'.json'));
  if(!task.refresh&&!task.background&&linked?.jobId){const owner=await status(linked.jobId);if(owner?.status?.startsWith('waiting_')&&owner.sender===task.sender&&owner.chat===task.chat)return{duplicate:true,jobId:owner.id};}
  const job={...task,url:canonicalURL(task.url),status:'queued',stage:'accepted',createdAt:task.createdAt??new Date(now()).toISOString(),attempts:0};
  await saveJSON(join(work,job.id,'task.json'),job);await saveJSON(join(active,job.id+'.json'),job);
  if(running)void schedule();
  return{duplicate:false,jobId:job.id};
 }
 async function cleanup(job){
  if(job.result?.retainWorkspace)return;
  const directory=join(work,job.id);let info;try{info=await lstat(directory);}catch(e){if(e.code!=='ENOENT')throw e;}
  if(info?.isSymbolicLink())throw Error('Refusing symlink workspace cleanup');
  if(info)await rm(directory,{recursive:true,force:true});
 }
 async function recover(startup=false){
  const warnings=[];
  for(const entry of await readdir(work,{withFileTypes:true})){
   if(!entry.isDirectory()||!valid(entry.name)){warnings.push({path:entry.name,reason:'Unrecognized workspace retained'});continue;}
   let current;try{current=await status(entry.name);}catch{warnings.push({path:entry.name,reason:'Task record damaged; reconstructing from owner'});}
   if(current)continue;
   let owner;try{owner=await optionalJSON(join(work,entry.name,'task.json'));}catch{}
   if(owner?.id===entry.name&&typeof owner.url==='string')await saveJSON(join(active,entry.name+'.json'),{...owner,status:'queued',recovered:true});
   else warnings.push({path:entry.name,reason:'No valid task owner; retained for inspection'});
  }
  if(startup){
   for(const name of (await readdir(active)).filter(n=>/^[a-f0-9]{64}\.json$/u.test(n))){
    let job;try{job=await optionalJSON(join(active,name));}catch{warnings.push({path:name,reason:'Unrecoverable task record retained'});continue;}
    // Restart never grants permission or replenishes a retry budget.
    if(job?.status==='processing')await saveJSON(join(active,name),{...job,status:(job.attempts??0)>=5?'waiting_retry':'queued',nextAttemptAt:0});
   }
  }
  await saveJSON(join(stateDir,'recovery.json'),{warnings,checkedAt:new Date(now()).toISOString()});
 }
 async function processOne(name){
  const file=join(active,name);let job;
  try{job=await optionalJSON(file);}catch{return;}
  if(!job||!valid(job.id)||name!==job.id+'.json'||closed)return;
  if(!allowed(job)){job.status='scope_removed';await saveJSON(file,job);return;}
  if(job.status?.startsWith('waiting_')||job.nextAttemptAt>now())return;
  try{
   if(job.status!=='cleanup_pending'&&job.status!=='delivery_pending'){
    const workspaceInfo=await lstat(join(work,job.id)).catch(e=>{if(e.code==='ENOENT')return null;throw e;});
    if(workspaceInfo?.isSymbolicLink())throw Error('Refusing symlink workspace');
    job.status='processing';job.attempts=(job.attempts??0)+1;await saveJSON(file,job);
    const known=await optionalJSON(join(stateDir,'sources',urlKey(job.url)+'.json'));
    job.result=await run(job,join(work,job.id),controller.signal,async(stage,details={})=>{job.stage=stage;job.details={...job.details,...details};await saveJSON(file,job);},known?.result);
    if(job.result.status==='partial'&&job.result.resumableMedia){
     const {userRecord,...sourceResult}=job.result;
     await saveJSON(join(stateDir,'sources',urlKey(job.url)+'.json'),{url:job.url,jobId:job.id,result:sourceResult});
     job.mediaActions=(job.mediaActions??[]).slice(1);job.mediaAction=job.mediaActions[0];
     job.status=job.mediaAction?'queued':job.result.missingAssets?.some(a=>a.status==='waiting_login')?'waiting_login':job.result.missingAssets?.some(a=>a.status==='waiting_confirmation')?'waiting_confirmation':'waiting_media';
     job.failure='正文已核验；附件尚未完成';await saveJSON(file,job);
     if(job.status.startsWith('waiting_')&&notifyWaiting&&!job.silent&&!job.waitingReceiptId){job.waitingReceiptId=await notifyWaiting(job,controller.signal);await saveJSON(file,job);}
     return;
    }
    if(job.result.status!=='complete')throw Error('Result incomplete; retain work');
    const {userRecord,...sourceResult}=job.result;
    await saveJSON(join(stateDir,'sources',urlKey(job.url)+'.json'),{url:job.url,result:sourceResult,verifiedAt:new Date(now()).toISOString()});
    job.status='cleanup_pending';delete job.failure;await saveJSON(file,job);
   }
   if(job.status==='cleanup_pending'){await cleanup(job);job.status='delivery_pending';await saveJSON(file,job);}
   if(deliver&&!job.silent&&!job.receiptId)job.receiptId=await deliver(job,controller.signal);
   job.status='done';job.completedAt=new Date(now()).toISOString();delete job.details;delete job.nextAttemptAt;
   await saveJSON(join(complete,name),job);await unlink(file);
  }catch(error){
   if(closed){if(!['cleanup_pending','delivery_pending'].includes(job.status))job.status=(job.attempts??0)>=5?'waiting_retry':'queued';job.nextAttemptAt=0;}
   else{
    job.failure=error.message;if(job.status!=='processing')job.attempts=(job.attempts??0)+1;
    const phase=job.status;
    job.status=waitingReason(error.message,job.attempts);
    if(['cleanup_pending','delivery_pending'].includes(phase)){job.resumePhase=phase;if(job.status==='retry')job.status=phase;}
    job.nextAttemptAt=now()+Math.min(3600000,30000*2**Math.min(job.attempts-1,7));
   }
   await saveJSON(file,job);
   if(!closed&&notifyWaiting&&!job.silent&&job.status.startsWith('waiting_')&&!job.waitingReceiptId){
    try{job.waitingReceiptId=await notifyWaiting(job,controller.signal);await saveJSON(file,job);}catch{job.waitingReceiptError=true;await saveJSON(file,job);}
   }
  }
 }
 async function scheduleNow(){
  if(scheduling||closed)return;scheduling=true;
  try{
   for(const name of (await readdir(active)).filter(n=>/^[a-f0-9]{64}\.json$/u.test(n)).sort()){
    if(inFlight.size>=2||closed)break;
    if(inFlight.has(name))continue;
    let job;try{job=await optionalJSON(join(active,name));}catch{continue;}
    if(!job||job.status?.startsWith('waiting_')||job.status==='scope_removed'||job.nextAttemptAt>now()||inFlightURLs.has(job.url))continue;
    inFlightURLs.add(job.url);
    const promise=processOne(name).catch(async error=>{await saveJSON(join(stateDir,'worker-error.json'),{reason:error.message,at:new Date(now()).toISOString()});}).finally(()=>{inFlight.delete(name);inFlightURLs.delete(job.url);});
    inFlight.set(name,promise);
   }
  }finally{scheduling=false;}
 }
 function serialize(fn){const result=ingress.then(fn);ingress=result.catch(()=>{});return result;}
 const schedule=()=>serialize(scheduleNow);
 async function drain(){
  if(closed)return;
  if(running){await schedule();return;}
  running=true;
  try{
   await recover();
   do{
    await schedule();
    if(!inFlight.size)break;
    await Promise.race([...inFlight.values()]);
   }while(inFlight.size||!closed);
  }finally{await Promise.allSettled([...inFlight.values()]);running=false;}
 }
 await recover(true);
 return{enqueue:task=>{const result=ingress.then(()=>enqueue(task));ingress=result.catch(()=>{});return result;},status,drain,recover,
  retry(id,changes={}){return serialize(async()=>{
   if(!valid(id))throw Error('Invalid task ID');if(inFlight.has(id+'.json'))throw Error('Task is still processing');
   const job=await optionalJSON(join(active,id+'.json'));if(!job)throw Error('No active task');
   if(changes.controlMessageId&&job.controlMessages?.includes(changes.controlMessageId))return;
   if(job.status==='waiting_confirmation'&&!changes.mediaAction)throw Error('Exact video confirmation or attachment selection required');
   const actions=[...(job.mediaActions??[]),...(changes.mediaAction?[changes.mediaAction]:[])];
   Object.assign(job,changes);job.mediaActions=actions;job.mediaAction=actions[0];job.controlMessages=[...(job.controlMessages??[]),...(changes.controlMessageId?[changes.controlMessageId]:[])];
   job.status=job.resumePhase??'queued';job.attempts=0;job.nextAttemptAt=0;delete job.waitingReceiptId;
   await saveJSON(join(active,id+'.json'),job);
  });},
  async start(){timer=setInterval(()=>{drain().catch(()=>{});},2000);timer.unref();void drain().catch(()=>{});},
  async close(){if(closed)return;closed=true;clearInterval(timer);controller.abort();await ingress;while(running)await new Promise(resolve=>setTimeout(resolve,25));await release();}
 };
}
