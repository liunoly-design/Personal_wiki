import {spawn,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {readFile,mkdir,appendFile,rename,symlink,rm,lstat} from 'node:fs/promises';
import {join,resolve,isAbsolute} from 'node:path';
import {saveJSON,optionalJSON} from './durable-files.js';
import {acquireQueueLease} from './task-queue.js';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
const exec=promisify(execFile);

export async function updateMaintenance(config,id,update){
 if(!/^[a-f0-9]{64}$/u.test(id))throw Error('Invalid maintenance ID');
 const root=join(config.stateDir,'ingestion','maintenance'),lock=join(root,'records',id);
 await mkdir(lock,{recursive:true,mode:0o700});let release;
 for(let attempt=0;attempt<40;attempt++){try{release=await acquireQueueLease(lock,config.python);break;}catch(error){if(!/already running/u.test(error.message)||attempt===39)throw error;await delay(25);}}
 try{const file=join(root,id+'.json');const value=await update(await optionalJSON(file));await saveJSON(file,value);return value;}finally{await release();}
}

export async function activateRelease(config,project,version){
 if(!/^[a-f0-9]{40}$/u.test(version)||resolve(config.runtimeRoot??'')!==join(config.stateDir,'runtime'))throw Error('Private versioned runtimeRoot required');
 const root=config.runtimeRoot;await mkdir(root,{recursive:true,mode:0o700});
 if(!(await lstat(root)).isDirectory())throw Error('Runtime root must be a regular directory');
 const release=join(root,'releases',version),receipt=join(release,'.release.json');
 if(!await optionalJSON(receipt)){
  await mkdir(join(root,'releases'),{recursive:true,mode:0o700});
  const stage=join(root,'releases',version+'-'+process.pid);await mkdir(stage,{mode:0o700});
  const archive=join(root,version+'-'+process.pid+'.tar');
  try{
   await exec('git',['archive','--format=tar','--output',archive,version],{cwd:project});
   await exec('/usr/bin/tar',['-xf',archive,'-C',stage]);
   await saveJSON(join(stage,'.release.json'),{version,createdAt:new Date().toISOString()});
   await rename(stage,release);
  }finally{await rm(archive,{force:true});await rm(stage,{recursive:true,force:true});}
 }
 const pointer=join(root,'current-'+process.pid);await symlink(release,pointer);await rename(pointer,join(root,'current'));
 if(config.configPath){const latest=JSON.parse(await readFile(config.configPath,'utf8'));if(latest.stateDir!==config.stateDir||latest.runtimeRoot!==root)throw Error('Runtime configuration changed during activation');await saveJSON(config.configPath,{...latest,processorVersion:version});}
 return release;
}

async function replayVerified(config,request){
 if(!request.activated||!config.runtimeRoot)return request;
 const cli=join(config.runtimeRoot,'releases',request.version,'scripts/wiki.mjs');
 for(let count=0;count<32;count++){
  request=await optionalJSON(join(config.stateDir,'ingestion/maintenance',request.id+'.json'));
  const task=request.tasks.find(id=>!(request.replayedTasks??[]).includes(id)&&!(request.resolvedTasks??[]).includes(id));
  if(!task)break;
  let status='failed';
  try{
   await exec(process.execPath,[cli,'retry',task,'--maintenance-replay',request.id,'--config',config.configPath],{timeout:30000});
   const result=await exec(process.execPath,[cli,'run',task,'--config',config.configPath],{timeout:3600000,maxBuffer:2*1024*1024});
   status=JSON.parse(result.stdout).status;
  }catch(error){
   const busy=/Task queue already running/iu.test(String(error.message));
   request=await updateMaintenance(config,request.id,latest=>({...latest,status:busy?'verified':'waiting_replay_result',nextAttemptAt:Date.now()+60000,replayResults:{...latest.replayResults,[task]:{status:busy?'waiting_source_lock':'waiting_result',reason:String(error.message).slice(0,1000),at:new Date().toISOString()}}}));
   break;
  }
  request=await updateMaintenance(config,request.id,latest=>({...latest,replayedTasks:[...new Set([...(latest.replayedTasks??[]),task])],replayResults:{...latest.replayResults,[task]:{status,version:request.version,at:new Date().toISOString()}}}));
 }
 return request;
}

// Runs in a separate worker, so a capture caller never has to stay alive while
// the project development session edits code and runs its regression checks.
export async function repairIngestion(config,id){
 if(!/^[a-f0-9]{64}$/u.test(id))throw Error('Invalid maintenance ID');
 const root=join(config.stateDir,'ingestion','maintenance'),file=join(root,id+'.json');
 let request=await optionalJSON(file);if(!request)throw Error('Maintenance request not found');
 const directory=join(root,id);await mkdir(directory,{recursive:true,mode:0o700});
 const release=await acquireQueueLease(directory,config.python);
 let releaseProject;
 const persist=async()=>{request=await updateMaintenance(config,id,latest=>({...latest,...request,tasks:[...new Set([...(latest?.tasks??[]),...request.tasks])],resolvedTasks:[...new Set([...(latest?.resolvedTasks??[]),...(request.resolvedTasks??[])])]}));};
 try{
  if(['verified','source_recovered'].includes(request.status)&&request.activated)return await replayVerified(config,request);
  if(['failed','running','waiting_session_result','waiting_replay_result','source_recovered'].includes(request.status))return request;
  const project=config.maintenance?.project;
  if(!isAbsolute(project??'')){request.status='waiting_bridge';await persist();return request;}
  if(resolve(project)===resolve(import.meta.dirname,'..'))throw Error('Code repair requires a development checkout separate from the running release');
  const projectLock=join(root,'projects',createHash('sha256').update(resolve(project)).digest('hex'));
  await mkdir(projectLock,{recursive:true,mode:0o700});
  try{releaseProject=await acquireQueueLease(projectLock,config.python);}catch{request.status='waiting_workspace';request.reason='Another maintenance session owns the development checkout';await persist();return request;}
  request=await optionalJSON(file);
  const before=(await exec('git',['rev-parse','HEAD'],{cwd:project})).stdout.trim();
  if((await exec('git',['status','--porcelain'],{cwd:project})).stdout.trim()){
   request.status='waiting_workspace';request.reason='Development checkout has uncommitted work; retained without concurrent edits';await persist();return request;
  }
  request.status='starting';request.workerPid=process.pid;request.baseline=before;await persist();
  const output=join(directory,'response.md'),events=join(directory,'events.jsonl');
  const args=['-a','never','exec','--sandbox','workspace-write','--json','--output-last-message',output,...(config.compilerModel?['--model',config.compilerModel]:[]),'-'];
  let pending='',writes=Promise.resolve(),sessionId;
  const code=await new Promise((accept,reject)=>{
   const child=spawn(config.codexBinary??'codex',args,{cwd:project,timeout:config.maintenance?.timeoutMs??1800000,stdio:['pipe','pipe','pipe']});
   child.on('error',reject);child.stdin.on('error',reject);
   child.stdout.on('data',chunk=>{
    pending+=chunk.toString();const lines=pending.split('\n');pending=lines.pop();
    for(const line of lines){
     writes=writes.then(()=>appendFile(events,line+'\n',{mode:0o600}));
     try{const event=JSON.parse(line);if(event.type==='thread.started'&&typeof event.thread_id==='string'&&/^[a-zA-Z0-9-]{8,100}$/u.test(event.thread_id)){
      sessionId=event.thread_id;request.sessionId=sessionId;request.status='running';writes=writes.then(persist);
     }}catch{}
    }
   });
   child.stderr.on('data',()=>{});child.on('close',accept);
   child.stdin.end(`修复本项目已接入来源的摄取故障，并运行相关回归。先读 AGENTS.md 和三层摄取规格。\n维护请求文件：${file}\n关联任务 ID：${request.tasks.join(', ')}\n任务记录在私有运行目录的 ingestion/jobs 中，可只读核对这些指定任务及其已取得材料。\n范围：修复可复用的来源处理或转换/交接代码。保持原件、幂等和人工内容保护，不操作其他私人资料，不新增收费服务，不自动接入新平台，不发消息，不推送仓库，不修改本维护请求和任务状态，不调用 maintain 或递归启动开发session。修复后运行测试并提交相关代码，最后报告变更与真实验证结果；无法修复则明确原因。\n`);
  });
  await writes;
  if(code!==0||!sessionId)throw Error('Project development session did not complete with a confirmed session ID');
  const candidate=(await exec('git',['rev-parse','HEAD'],{cwd:project})).stdout.trim();
  const commands=config.maintenance?.testCommands??[[process.execPath,'--test'],[config.python,'-m','unittest','discover','-s','tests','-v']];
  if(!Array.isArray(commands)||!commands.length)throw Error('Maintenance regression commands required');
  for(const command of commands){if(!Array.isArray(command)||!command.length||command.some(v=>typeof v!=='string'))throw Error('Invalid regression command');await exec(command[0],command.slice(1),{cwd:project,timeout:600000,maxBuffer:8*1024*1024});}
  const after=(await exec('git',['rev-parse','HEAD'],{cwd:project})).stdout.trim();
  if(after!==candidate||after===before||(await exec('git',['status','--porcelain'],{cwd:project})).stdout.trim())throw Error('Repair must produce an unchanged committed revision throughout regression');
  request.status='verified';request.version=after;request.testsPassed=true;request.finishedAt=new Date().toISOString();
  const release=config.runtimeRoot?await activateRelease(config,project,after):null;
  request.activated=Boolean(release);await persist();
  if(!release)return request;
  // Drain the durable unresolved membership, including tasks that joined late.
  return await replayVerified(config,request);
 }catch(error){request.status='failed';request.reason=error.code==='ETIMEDOUT'?'Development session timed out':String(error.message).slice(0,1000);request.finishedAt=new Date().toISOString();await persist();return request;}
 finally{await releaseProject?.();await release();}
}

export function startMaintenance(config,id){
 if(!config.maintenance?.project||!config.configPath)return false;
 const child=spawn(process.execPath,[resolve(import.meta.dirname,'../scripts/maintain-ingestion.mjs'),'--config',config.configPath,id],{detached:true,stdio:'ignore'});
 child.on('error',()=>{});child.unref();return true;
}
