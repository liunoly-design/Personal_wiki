import {resolveWikiFeishuAccount} from './feishu-http.js';
import {readFileSync,lstatSync,renameSync} from 'node:fs';
import {readFile,writeFile,mkdir,lstat,readdir,cp,rename,unlink} from 'node:fs/promises';
import {join,resolve,dirname,isAbsolute,relative} from 'node:path';
import {homedir} from 'node:os';
import {createHash,randomUUID} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {localNashsuAPI} from './nashsu-api.js';

const exec=promisify(execFile);
const root=resolve(import.meta.dirname,'..');
const payload=['package.json','openclaw.plugin.json','openclaw','src','scripts','vendor','requirements-capture.txt'];
const tools=['wiki_record','wiki_status','wiki_retry_translation','wiki_resume','wiki_query','wiki_read','wiki_review','wiki_discuss'];
const hash=value=>createHash('sha256').update(value).digest('hex');
const defaultAppState=join(homedir(),'Library/Application Support/com.llmwiki.app/app-state.json');
const id=value=>typeof value==='string'&&/^[a-zA-Z0-9_-]+$/.test(value)&&!['__proto__','constructor','prototype'].includes(value);
function normalized(input){
 const s={nashsuStatePath:defaultAppState,...input};
 const keys=['hostConfigPath','nashsuStatePath','vault','stateDir','python','codexBinary','openclawBinary'];
 for(const key of keys)if(typeof s[key]!=='string'||!isAbsolute(s[key]))throw Error('Absolute path required: '+key);
 for(const key of ['accountId','entryAgentId','wikiAgentId'])if(!id(s[key]))throw Error('Invalid identifier: '+key);
 for(const [key,prefix] of [['allowedSenderIds','ou_'],['allowedConversationIds','oc_']]){
  if(!Array.isArray(s[key])||!s[key].length||s[key].some(v=>typeof v!=='string'||!new RegExp('^'+prefix+'[A-Za-z0-9_-]+$').test(v)))throw Error('Explicit scope required: '+key);
 }
 for(const key of ['flashModel','compilerModel'])if(typeof s[key]!=='string'||!s[key].trim())throw Error('Model required: '+key);
 for(const key of ['openclawPackageDir','flashProxyUrl'])if(s[key]!==undefined&&typeof s[key]!=='string')throw Error('Invalid setting: '+key);
 if(s.openclawPackageDir&&!isAbsolute(s.openclawPackageDir))throw Error('Absolute package path required');
 for(const key of keys)s[key]=resolve(s[key]);
 const inside=(a,b)=>a===b||relative(b,a).split('/')[0]!=='..';
 if(inside(s.stateDir,s.vault)||inside(s.vault,s.stateDir))throw Error('Vault and private state must be separate');
 if(inside(s.hostConfigPath,s.stateDir)||inside(s.hostConfigPath,s.vault))throw Error('Host configuration must be outside Wiki data');
 if(inside(s.stateDir,root))throw Error('Private state must be outside the source checkout');
 return s;
}
async function noLinks(path){
 let current=resolve(path);
 while(true){
  const st=await lstat(current).catch(e=>{if(e.code==='ENOENT')return null;throw e;});
  if(st?.isSymbolicLink())throw Error('Symbolic link rejected');
  if(current===dirname(current))break;
  current=dirname(current);
 }
}
async function safeSettings(input){
 const s=normalized(input);
 for(const path of [s.hostConfigPath,s.stateDir,s.vault,join(s.stateDir,'installations'),join(s.stateDir,'installation.json')])await noLinks(path);
 return s;
}
async function command(binary,args,env={}){
 return exec(binary,args,{env:{...process.env,...env},timeout:30000,maxBuffer:1024*1024});
}
async function sourceHash(directory){
 const parts=[];
 async function walk(path){
  const st=await lstat(join(directory,path));
  if(st.isSymbolicLink())throw Error('Release symlink rejected');
  if(st.isDirectory())for(const name of (await readdir(join(directory,path))).sort())await walk(join(path,name));
  else if(st.isFile())parts.push(path+'\0'+hash(await readFile(join(directory,path))));
 }
 for(const name of payload)await walk(name);
 return hash(parts.join('\n'));
}
export async function checkWikiInstallation(input,{apiCheck=false}={}){
 const s=await safeSettings(input),checks=[];
 const check=async(name,run)=>{try{await run();checks.push({name,status:'ok'});}catch{checks.push({name,status:'blocked'});}};
 let host,app,project;
 await check('node',async()=>{if(Number(process.versions.node.split('.')[0])<24)throw Error();});
 await check('vault',async()=>{if(!(await lstat(s.vault)).isDirectory())throw Error();await readFile(join(s.vault,'schema.md'));});
 await check('host_config',async()=>{host=JSON.parse(await readFile(s.hostConfigPath,'utf8'));});
 await check('feishu_account',async()=>{
  const account=resolveWikiFeishuAccount(host??{},s.accountId,{explicit:true});
  if(account.enabled===false||account.domain&&account.domain!=='feishu'||!account.appId||!account.appSecret)throw Error();
 });
 await check('entry_routing',async()=>{
  if(!host?.bindings?.some(b=>b.agentId===s.entryAgentId&&b.match?.channel==='feishu'&&b.match?.accountId===s.accountId))throw Error();
 });
 await check('python_dependencies',()=>command(s.python,['-c','import sys; assert sys.version_info >= (3,11); import httpx, bs4, markdownify, readability, yt_dlp, imageio_ffmpeg, playwright']));
 await check('codex_cli',()=>command(s.codexBinary,['--version']));
 await check('openclaw_cli',()=>command(s.openclawBinary,['--version']));
 await check('nashsu_fixed_library',async()=>{
  app=JSON.parse(await readFile(s.nashsuStatePath,'utf8'));
  const matches=Object.entries(app.projectRegistry??{}).filter(([,p])=>resolve(p.path??'')===s.vault);
  if(matches.length!==1)throw Error();
  project=matches[0][0];
  if(app.sourceWatchConfig?.[project]?.autoIngest!==false||app.embeddingConfig?.enabled||app.apiConfig?.enabled!==true||!app.apiConfig.token)throw Error();
 });
 if(apiCheck)await check('nashsu_api_read',async()=>{
  const api=await localNashsuAPI(s.vault,{statePath:s.nashsuStatePath,maxAttempts:1});
  await api.assertPublisherReady();
  if(typeof await api.read('wiki/index.md')!=='string')throw Error();
 });
 return {installable:checks.every(c=>c.status==='ok'),checks,models:{flash:s.flashModel,compiler:s.compilerModel,authentication:'not_verified',quota:'not_verified'},feishuAcceptance:'not_verified',apiChecked:apiCheck};
}
async function atomic(path,bytes,expectedHash){
 const temporary=path+'.'+randomUUID()+'.tmp';
 try{
  await writeFile(temporary,bytes,{flag:'wx',mode:0o600});
  if(expectedHash!==undefined){
   if(lstatSync(path).isSymbolicLink()||hash(readFileSync(path))!==expectedHash)throw Error('Host configuration changed; replacement refused');
   // No async boundary between final baseline check and replacement. Other
   // writers must honor the same lock for full interprocess exclusion.
   renameSync(temporary,path);
  }else await rename(temporary,path);
 }
 finally{await unlink(temporary).catch(e=>{if(e.code!=='ENOENT')throw e;});}
}
async function locked(s,run){
 const lock=s.hostConfigPath+'.wiki-setup.lock';
 await writeFile(lock,String(process.pid),{flag:'wx',mode:0o600});
 try{return await run();}
 finally{await unlink(lock);}
}
function candidateHost(host,s,release){
 const config={enabled:true,accountId:s.accountId,entryAgentId:s.entryAgentId,wikiAgentId:s.wikiAgentId,allowedSenderIds:s.allowedSenderIds,allowedConversationIds:s.allowedConversationIds,vault:s.vault,stateDir:s.stateDir,python:s.python,codexBinary:s.codexBinary,flashModel:s.flashModel,compilerModel:s.compilerModel,canonicalLibrary:true,publishSources:false,nashsuStatePath:s.nashsuStatePath,strictFeishuAccount:true,...(s.openclawPackageDir?{openclawPackageDir:s.openclawPackageDir}:{}),...(s.flashProxyUrl?{flashProxyUrl:s.flashProxyUrl}:{})};
 const plugins=host.plugins??={};plugins.entries??={};plugins.load??={};plugins.load.paths??=[];
 const old=plugins.entries['personal-wiki'];
 if(old?.enabled||old?.config?.enabled)throw Error('Existing active Wiki must be migrated explicitly');
 plugins.load.paths=[...new Set([...plugins.load.paths,release])];
 if(Array.isArray(plugins.allow))plugins.allow=[...new Set([...plugins.allow,'personal-wiki'])];
 plugins.entries['personal-wiki']={enabled:true,config};
 host.agents??={};host.agents.entries??={};host.agents.ownership??='explicit';
 for(const agentId of new Set([s.entryAgentId,s.wikiAgentId])){
  host.agents.entries[agentId]??={workspace:join(s.stateDir,'agents',agentId,'workspace'),agentDir:join(s.stateDir,'agents',agentId,'agent')};
 }
 const agent=host.agents.entries[s.wikiAgentId];
 if(Array.isArray(agent.tools?.allow))agent.tools.allow=[...new Set([...agent.tools.allow,...tools])];
 return host;
}
async function verifyHost(s,configPath){
 const env={OPENCLAW_CONFIG_PATH:configPath,OPENCLAW_STATE_DIR:dirname(s.hostConfigPath)};
 try{await command(s.openclawBinary,['config','validate'],env);}
 catch{throw Error('OpenClaw configuration validation failed');}
 let stdout;
 try{({stdout}=await command(s.openclawBinary,['plugins','inspect','personal-wiki','--runtime','--json'],env));}
 catch{throw Error('OpenClaw plugin inspection failed');}
 let loaded;
 try{loaded=JSON.parse(stdout);}catch{throw Error('OpenClaw plugin inspection returned invalid JSON');}
 if(loaded?.plugin?.status!=='loaded'||!Array.isArray(loaded.typedHooks)||!loaded.typedHooks.some(h=>h.name==='reply_dispatch'))throw Error('Plugin load not confirmed');
}
async function receiptAt(s,path){
 await noLinks(path);
 if(dirname(path)!==join(s.stateDir,'installations')||!/^install-[a-f0-9-]+\.json$/.test(path.slice(dirname(path).length+1)))throw Error('Invalid installation receipt');
 const r=JSON.parse(await readFile(path,'utf8'));
 if(r.hostConfigPath!==s.hostConfigPath||r.stateDir!==s.stateDir)throw Error('Installation receipt scope mismatch');
 if(r.release!==path.slice(0,-5))throw Error('Invalid release location');
 await noLinks(r.release);
 return r;
}
export async function installWiki(input){
 const s=await safeSettings(input);
 return locked(s,async()=>{
  const report=await checkWikiInstallation(s);
  if(!report.installable)throw Error('Preflight blocked: '+report.checks.filter(c=>c.status==='blocked').map(c=>c.name).join(', '));
  const digest=await sourceHash(root),settingsHash=hash(JSON.stringify(s));
  const marker=join(s.stateDir,'installation.json');
  const latest=await readFile(marker,'utf8').then(JSON.parse).catch(e=>{if(e.code==='ENOENT')return null;throw e;});
  if(latest){
   const r=await receiptAt(s,latest.receipt);
   if(r.sourceHash===digest&&r.settingsHash===settingsHash&&hash(await readFile(s.hostConfigPath))===r.installedHash){
    if(await sourceHash(r.release)!==digest)throw Error('Installed release integrity mismatch');
    await verifyHost(s,s.hostConfigPath);
    return {status:'existing',receipt:latest.receipt,release:r.release,report};
   }
  }
  const original=await readFile(s.hostConfigPath),host=JSON.parse(original);
  const installation=join(s.stateDir,'installations'),tag='install-'+randomUUID();
  await mkdir(installation,{recursive:true,mode:0o700});
  const release=join(installation,tag),receipt=join(installation,tag+'.json'),backup=join(installation,tag+'.before.json');
  await mkdir(release,{mode:0o700});
  for(const name of payload)await cp(join(root,name),join(release,name),{recursive:true,dereference:false});
  if(await sourceHash(release)!==digest)throw Error('Staged release integrity mismatch');
  const installed=JSON.stringify(candidateHost(host,s,release),null,2)+'\n';
  await writeFile(backup,original,{flag:'wx',mode:0o600});
  const r={hostConfigPath:s.hostConfigPath,stateDir:s.stateDir,release,backup,sourceHash:digest,settingsHash,originalHash:hash(original),installedHash:hash(installed),phase:'staged'};
  await writeFile(receipt,JSON.stringify(r,null,2),{flag:'wx',mode:0o600});
  const staged=join(installation,tag+'.candidate.json');
  await writeFile(staged,installed,{flag:'wx',mode:0o600});
  try{await verifyHost(s,staged);}
  catch(error){
   r.phase='validation_failed';await atomic(receipt,JSON.stringify(r));
   throw Error(error.message+'; original configuration preserved; receipt: '+receipt);
  }
  if(hash(await readFile(s.hostConfigPath))!==r.originalHash)throw Error('Host configuration changed during staging');
  await atomic(marker,JSON.stringify({receipt}));
  await atomic(s.hostConfigPath,installed,r.originalHash);
  try{await verifyHost(s,s.hostConfigPath);}
  catch{
   if(hash(await readFile(s.hostConfigPath))!==r.installedHash)throw Error('Install verification failed; concurrent configuration preserved; receipt: '+receipt);
   await atomic(s.hostConfigPath,original,r.installedHash);
   r.phase='rolled_back';await atomic(receipt,JSON.stringify(r));
   throw Error('Install verification failed; original configuration restored; receipt: '+receipt);
  }
  r.phase='installed';await atomic(receipt,JSON.stringify(r));
  return {status:'installed',receipt,release,report,restartRequested:false};
 });
}
export async function rollbackWiki(input,receiptPath){
 const s=await safeSettings(input);
 return locked(s,async()=>{
  const r=await receiptAt(s,resolve(receiptPath));
  const backup=join(dirname(receiptPath),receiptPath.slice(dirname(receiptPath).length+1).replace(/\.json$/,'.before.json'));
  if(r.backup!==backup)throw Error('Invalid configuration backup');
  await noLinks(backup);
  const original=await readFile(backup);
  if(hash(original)!==r.originalHash)throw Error('Configuration backup integrity mismatch');
  const current=hash(await readFile(s.hostConfigPath));
  if(current===r.originalHash)return {status:'already_rolled_back'};
  if(current!==r.installedHash)throw Error('Host configuration changed; rollback refused');
  await atomic(s.hostConfigPath,original,r.installedHash);
  r.phase='rolled_back';await atomic(resolve(receiptPath),JSON.stringify(r));
  return {status:'rolled_back',dataPreserved:true,restartRequested:false};
 });
}
