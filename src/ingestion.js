import {mkdir,readFile,writeFile,lstat,readdir} from 'node:fs/promises';
import {join,resolve,dirname,isAbsolute,relative} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {saveJSON,optionalJSON} from './durable-files.js';
import {acquireQueueLease} from './task-queue.js';
import {collectCanonical,verifyPublication} from './canonical-library.js';
import {localNashsuAPI} from './nashsu-api.js';
import {validSlug} from './wk.js';
import {identifyInput,inputURLs,captureArticle} from './source-acquisition.js';
import {startMaintenance,repairIngestion} from './ingestion-maintenance.js';
import {MediaServiceClient} from './media-service-client.js';
import {hostname} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const exec=promisify(execFile);

const hash=value=>createHash('sha256').update(value).digest('hex');
const valid=id=>/^[a-f0-9]{64}$/u.test(id??'');
async function privateDirectory(path){
 await mkdir(path,{recursive:true,mode:0o700});
 for(let p=resolve(path);;p=dirname(p)){if(!(await lstat(p)).isDirectory())throw Error('State must use regular directories');if(p===dirname(p))break;}
}
async function exclusive(path,value){
 await privateDirectory(dirname(path));
 try{await writeFile(path,value,{flag:'wx',mode:0o600});}
 catch(error){if(error.code!=='EEXIST')throw error;if(!(await lstat(path)).isFile()||hash(await readFile(path))!==hash(value))throw Error('Immutable material differs; retained for review');}
}
export async function verifyBundle(bundle){
 for(const [name,expected] of Object.entries(bundle.hashes)){
  if(name.startsWith('/')||name.split('/').some(part=>!part||part==='..'))throw Error('Invalid bundle path');
  const path=join(bundle.directory,name);
  for(let p=path;p!==dirname(bundle.directory);p=dirname(p)){if((await lstat(p)).isSymbolicLink())throw Error('Bundle symlink rejected');}
  if(!(await lstat(path)).isFile()||hash(await readFile(path))!==expected)throw Error('Bundle integrity mismatch');
 }
 return bundle;
}
export async function openIngestion(config,ports={}){
 if(!isAbsolute(config.stateDir??''))throw Error('Absolute private stateDir required');
 const root=join(config.stateDir,'ingestion');await privateDirectory(root);
 const pathFor=id=>{if(!valid(id))throw Error('Invalid task ID');return join(root,'jobs',id+'.json');};
 const persist=job=>saveJSON(pathFor(job.id),job);
 async function status(id){const job=await optionalJSON(pathFor(id));if(!job)throw Error('Task not found');if(job.maintenance){const request=await optionalJSON(join(root,'maintenance',job.maintenance.id+'.json'));if(request)job.maintenance={id:request.id,status:request.status,...(request.sessionId?{sessionId:request.sessionId}:{})};}return job;}
 async function lock(name,fn){const dir=join(root,'locks',name);await privateDirectory(dir);const release=await acquireQueueLease(dir,config.python??'python3');try{return await fn();}finally{await release();}}
 async function submit({input,text,mode='record',requestId,name,background='',refresh=false}={}){
  if(!['record','convert'].includes(mode))throw Error('Invalid processing mode');
  if(requestId!==undefined&&(typeof requestId!=='string'||!requestId.trim()||requestId.length>500))throw Error('Invalid request ID');
  if(typeof background!=='string')throw Error('Background must be text');
  const source=identifyInput({input,text});
  if(name&&!validSlug(name))throw Error('Invalid English source name');
  const id=hash(requestId??mode+':'+source.url+':'+background+(refresh?':'+randomUUID():''));
  const payloadHash=hash(JSON.stringify({mode,url:source.url,name:name??source.name,background,refresh}));
  return lock('ingress',async()=>{
   const prior=await optionalJSON(pathFor(id));if(prior){if(prior.payloadHash&&prior.payloadHash!==payloadHash)throw Error('Request identity conflict');return prior;}
   const cached=!refresh?await optionalJSON(join(root,'bundles',hash(source.url)+'.json')):null;
   const job={id,mode,payloadHash,input:text!==undefined?{text}:{input},name:name??source.name,platform:source.platform,url:source.url,background,refresh,status:'queued',rounds:0,createdAt:new Date().toISOString(),...(cached?{bundle:cached}:{})};
   await persist(job);return job;
  });
 }
 async function snapshot(job){
  const directory=join(root,'work',job.id,'snapshots',String(job.generation??0));const markdown=join(directory,'article.md');
  const hashes={};
  let preparedReadingModel,canonicalUrl=job.url;
  if(job.supplementFile||job.platform==='text'){
   const text=job.supplementFile?await readFile(job.supplementFile,'utf8'):identifyInput(job.input).text;
   await exclusive(markdown,text);hashes['article.md']=hash(text);
   if(job.supplementFile){const note=JSON.stringify({kind:'user-provided',url:job.url,supplements:job.supplements},null,2);await exclusive(join(directory,'supplement.json'),note);hashes['supplement.json']=hash(note);}
   if(job.supplementImage){const bytes=await readFile(job.supplementImage.file);await exclusive(join(directory,job.supplementImage.name),bytes);hashes[job.supplementImage.name]=hash(bytes);}
  }else{
   const captured=await (ports.capture??captureArticle)({job,config:{...config,onStage:async(stage,details)=>{job.stage=stage;job.details=details;await persist(job);}},directory:join(root,'work',job.id,'capture',String(job.generation??0)+'-'+job.rounds),signal:ports.signal});
   job.pendingMaterials=captured.directory;job.lastCapture=captured;await persist(job);
   if(captured.contextStatus==='partial'||captured.status!=='complete')throw Error('Source incomplete; materials retained in pending area');
   const copy=async(dir,prefix='')=>{for(const entry of await readdir(dir,{withFileTypes:true})){
    const name=prefix+entry.name;if(entry.isSymbolicLink())throw Error('Capture symlink rejected');
    if(entry.isDirectory())await copy(join(dir,entry.name),name+'/');
    else if(entry.isFile()){const bytes=await readFile(join(dir,entry.name));await exclusive(join(directory,name),bytes);hashes[name]=hash(bytes);}
    else throw Error('Capture must contain regular files');
   }};
   await copy(captured.directory);if(!hashes['article.md'])throw Error('Captured Markdown missing');
   preparedReadingModel=captured.preparedReadingModel;
   canonicalUrl=captured.url??job.url;
  }
  return verifyBundle({directory,markdown,url:canonicalUrl,platform:job.platform,hashes,complete:true,...(preparedReadingModel?{preparedReadingModel}:{})});
 }
 function waitReason(message){
  if(/quota|capacity|额度/iu.test(message))return 'waiting_capacity';
  if(/confirmation|超过|1.?GB|30.?minutes/iu.test(message))return 'waiting_confirmation';
  if(/login|captcha|登录|验证码|HTTP 401|HTTP 403/iu.test(message))return 'waiting_login';
  if(/transcription required|not configured/iu.test(message))return 'waiting_dependency';
  return null;
 }
 async function maintenance(job){
  const fingerprint=hash(job.platform+':'+(config.processorVersion??'1')+':'+(job.maintenanceGeneration??0)+':'+job.failure.replace(/https?:\/\/\S+/gu,'[source]').slice(0,200));
  const file=join(root,'maintenance',fingerprint+'.json');
  const request=await optionalJSON(file)??{id:fingerprint,platform:job.platform,status:'waiting_bridge',tasks:[],createdAt:new Date().toISOString()};
  if(!request.tasks.includes(job.id))request.tasks.push(job.id);
  request.reason=job.failure.replace(/https?:\/\/\S+/gu,'[source]').slice(0,1200);
  await saveJSON(file,request);job.maintenance={id:request.id,status:request.status};
  if(request.status==='waiting_bridge'&&config.maintenance?.project&&config.configPath){request.status='queued';await saveJSON(file,request);if(!startMaintenance(config,request.id)){request.status='waiting_bridge';await saveJSON(file,request);}job.maintenance.status=request.status;}
 }
 async function finished(job){
  delete job.failure;await persist(job);
  if(job.maintenance){
   const file=join(root,'maintenance',job.maintenance.id+'.json'),request=await optionalJSON(file);
   if(request){request.resolvedTasks=[...new Set([...(request.resolvedTasks??[]),job.id])];if(request.tasks.every(id=>request.resolvedTasks.includes(id)))request.status='source_recovered';await saveJSON(file,request);}
  }
  return job;
 }
 async function verifyWiki(job,api){
  await verifyPublication({...job.result,files:Object.fromEntries(Object.entries(job.result.files).filter(([path])=>path.startsWith('raw/')))},{vault:config.vault,api});
  const path=relative(config.vault,job.result.source),page=await api.read(path),sections=page.split('## 完整中文正文\n');
  const body=sections.length>1?sections.at(-1).split('\n[归档原文]')[0]:'';
  const probe=body.split('\n').map(line=>line.trim().replace(/^\[[\d:.]+(?:\s*→\s*[\d:.]+)?\]\s*/u,'')).filter(line=>line.length>=8&&!/^[#>!`]|https?:\/\//u.test(line)).sort((a,b)=>b.length-a.length)[0]?.slice(0,36);
  if(!probe||!(await api.search(probe)).results?.some(r=>(r.path??r.file_path??r.filePath)===path))throw Error('Wiki full-text search verification failed');
 }
 async function run(id){const owner=await status(id);return lock('source-'+hash(owner.url),async()=>{
  const job=await status(id);
  if(job.status==='complete'||job.status==='converted'&&job.mode==='convert'){
   try{await verifyBundle(job.bundle);if(job.status==='complete')await verifyWiki(job,ports.api??await localNashsuAPI(config.vault,{maxAttempts:1}));return finished(job);}
   catch(error){job.status='waiting_verification';job.failure=String(error.message).slice(0,2000);await persist(job);return job;}
  }
  if(['pending','waiting_login','waiting_confirmation','waiting_capacity','waiting_dependency'].includes(job.status))return job;
  while(!job.bundle&&job.rounds<2){
   job.status='processing';job.rounds++;await persist(job);
   try{job.bundle=await snapshot(job);await saveJSON(join(root,'bundles',hash(job.url)+'.json'),job.bundle);job.status='converted';delete job.failure;await persist(job);}
   catch(error){
    job.failure=String(error.message).replace(/Bearer\s+\S+/giu,'Bearer [redacted]').slice(0,2000);
    job.failures=[...(job.failures??[]),{round:job.rounds,generation:job.generation??0,at:new Date().toISOString(),reason:job.failure}];
    const reason=waitReason(job.failure);
    job.status=reason??(job.rounds>=2?'pending':'queued');
    if(job.status==='pending')await maintenance(job);
    await persist(job);if(reason||job.status==='pending')return job;
   }
  }
  if(!job.bundle)return job;
  await verifyBundle(job.bundle);
  if(job.mode==='convert'){job.status='converted';return finished(job);}
  if(job.mode==='record'){
   try{
   if(!isAbsolute(config.vault??''))throw Error('Absolute target vault required');
   const api=ports.api??await localNashsuAPI(config.vault,{maxAttempts:1});
   job.status='publishing';await persist(job);
   const previous=await optionalJSON(join(root,'publications',hash(job.bundle.url)+'.json'));
   job.result=await collectCanonical({...config,api,stateDir:root,url:job.bundle.url,sourceName:job.name,background:job.background,requestId:job.id,refresh:job.refresh,previousResult:previous, isVideoPrepared:true,workspace:join(root,'work',id,'knowledge',String(job.generation??0)),preparedReadingModel:job.bundle.preparedReadingModel,
    capture:async()=>({directory:job.bundle.directory,text:await readFile(job.bundle.markdown,'utf8'),status:'complete'}),generate:ports.generate,translate:ports.translate,
    sourceContext:job.supplementFile?'正文由用户补充，原平台获取未核实；补料与原链接属于同一来源，不得声称网络抓取成功。':job.platform==='text'?'用户提供的个人文字，不得虚构外部作者。':'',
    onStage:async(stage)=>{job.stage=stage;await persist(job);}});
   await verifyPublication(job.result,{vault:config.vault,api});
   await verifyWiki(job,api);
   await saveJSON(join(root,'publications',hash(job.bundle.url)+'.json'),job.result);
   job.status='complete';await finished(job);
   }catch(error){job.failure=String(error.message).slice(0,2000);job.status=waitReason(job.failure)??'waiting_publication';await persist(job);}
  }
  return job;
 });}
 async function supplement(id,{file}){const owner=await status(id);return lock('source-'+hash(owner.url),async()=>{
  const job=await status(id);if(job.status==='complete')throw Error('Completed source requires an explicit refresh, not replacement');
  if(!isAbsolute(file??'')||!(await lstat(file)).isFile())throw Error('Regular absolute supplement file required');
  const bytes=await readFile(file);if(bytes.length>20*1024*1024)throw Error('Supplement too large for text input');
  const digest=hash(bytes),saved=join(root,'work',id,'supplements',digest+'-'+file.split('/').at(-1));await exclusive(saved,bytes);
  let readingFile=saved;
  job.supplements??=[];
  if(job.supplements.some(s=>s.sha256===digest))return job;
  job.supplements.push({kind:'user-provided',sha256:digest,file:saved,receivedAt:new Date().toISOString()});
  if(/\.(?:png|jpe?g|webp|tiff|bmp)$/iu.test(file)&&process.platform==='darwin'){
   const result=JSON.parse((await exec(config.python,[resolve(import.meta.dirname,'../scripts/image_ocr.py'),'--image',saved],{timeout:180000,maxBuffer:2*1024*1024})).stdout);
   if(!result.lines?.length){job.status='pending';job.failure='Image retained; no readable text recognized';await persist(job);return job;}
   const name='supplement-image'+file.slice(file.lastIndexOf('.')).toLowerCase();
   const text='# 用户补充截图\n\n> Apple Vision 机器识别，未经人工校订，原图为准。\n\n![补充原图]('+name+')\n\n'+result.lines.map(line=>line.text+(line.confidence<0.5?'〔识别不确定〕':'')).join('\n\n')+'\n';
   const derived=saved+'.ocr.md';await exclusive(derived,text);job.supplementImage={name,file:saved};file=derived;readingFile=derived;
  }
  if(!/\.(?:md|txt)$/iu.test(file)){job.status='waiting_dependency';job.failure='Supplement retained; conversion for this format is not configured';await persist(job);return job;}
  const supplied=await readFile(readingFile);
  new TextDecoder('utf-8',{fatal:true}).decode(supplied);
  job.supplementFile=readingFile;job.generation=(job.generation??0)+1;job.rounds=0;job.status='queued';delete job.bundle;delete job.result;await persist(job);return job;
 });}
 async function retry(id){const owner=await status(id);return lock('source-'+hash(owner.url),async()=>{const job=await status(id);if(job.status==='complete')throw Error('Task already complete');if(!job.bundle)job.generation=(job.generation??0)+1;job.maintenanceGeneration=(job.maintenanceGeneration??0)+1;job.recoveries=[...(job.recoveries??[]),{rounds:job.rounds,fromStatus:job.status,at:new Date().toISOString(),reason:'explicit-retry'}];job.rounds=0;job.status='queued';delete job.failure;await persist(job);return job;});}
 async function ingest(id){
  const owner=await status(id);await lock('source-'+hash(owner.url),async()=>{const job=await status(id);job.mode='record';if(job.status==='converted')job.status='queued';await persist(job);});
  return run(id);
 }
 async function list(){await privateDirectory(join(root,'jobs'));return Promise.all((await readdir(join(root,'jobs'))).filter(n=>/^[a-f0-9]{64}\.json$/u.test(n)).map(n=>status(n.slice(0,-5))));}
 async function submitMany(options){const urls=options.text===undefined?inputURLs(options.input??''):[];if(urls.length<=1)return [await submit(options)];const jobs=[];for(const url of urls)jobs.push(await submit({...options,input:url,requestId:options.requestId?options.requestId+':'+url:undefined}));return jobs;}
 async function doctor(){
  const checks={host:hostname(),node:process.versions.node,python:Boolean(config.python),vaultConfigured:isAbsolute(config.vault??'')};
  try{const api=ports.api??await localNashsuAPI(config.vault,{maxAttempts:1});await api.assertPublisherReady?.();await api.read('wiki/index.md');checks.wiki='ready';}catch{checks.wiki='unavailable';}
  try{const stat=await lstat(config.mediaServiceTokenFile);if(!stat.isFile()||stat.uid!==process.getuid()||(stat.mode&0o077))throw Error('Private credential file required');const token=(await readFile(config.mediaServiceTokenFile,'utf8')).trim();await new MediaServiceClient({baseUrl:config.mediaServiceUrl,token}).health();checks.media='ready';}catch{checks.media='unavailable';}
  checks.maintenance=config.maintenance?.project&&config.runtimeRoot?'configured':'not_configured';
  return {status:checks.wiki==='ready'&&checks.media==='ready'?'ready':'partial',checks};
 }
 async function workOnce(){const jobs=(await list()).filter(j=>['queued','processing','publishing'].includes(j.status)||j.status==='converted'&&j.mode==='record');const results=[];for(const job of jobs){try{results.push(await run(job.id));}catch(error){if(!/Task queue already running/u.test(error.message))throw error;}}return results;}
 async function maintain(id){const job=await status(id);if(!job.maintenance)throw Error('Task has no code maintenance request');return repairIngestion(config,job.maintenance.id);}
 return {submit,submitMany,run,status,list,supplement,retry,ingest,workOnce,maintain,doctor};
}
