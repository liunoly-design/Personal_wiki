#!/usr/bin/env node
import {readFile,writeFile,mkdir,lstat,rename,unlink,realpath} from 'node:fs/promises';
import {join,resolve,dirname,isAbsolute} from 'node:path';import {homedir} from 'node:os';import {parseArgs} from 'node:util';import {randomUUID} from 'node:crypto';import {execFileSync} from 'node:child_process';
const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
async function regular(path){for(let p=resolve(path);;p=dirname(p)){const s=await lstat(p).catch(e=>{if(e.code!=='ENOENT')throw e;});if(s?.isSymbolicLink())throw Error('Symlink path refused');if(p===dirname(p))return;}}
async function atomic(path,bytes){await regular(path);await mkdir(dirname(path),{recursive:true,mode:0o700});const part=path+'.'+randomUUID();await writeFile(part,bytes,{flag:'wx',mode:0o600});await rename(part,path);}
try{
 const {values:v,positionals:p}=parseArgs({allowPositionals:true,options:{prefix:{type:'string'},config:{type:'string'},vault:{type:'string'},python:{type:'string'},codex:{type:'string'},'media-url':{type:'string'},'media-token-file':{type:'string'},'skills-dir':{type:'string'},help:{type:'boolean'}}});
 if(v.help||!p.length){console.log('node manage.mjs --prefix ABS_PREFIX [--config ABS_CONFIG] configure|skill-install|worker-install|worker-uninstall|uninstall\nconfigure: --vault ABS --python ABS --codex ABS --media-url ORIGIN --media-token-file ABS\nskill-install: --skills-dir ABS (default ~/.codex/skills); existing skills are retained\nUninstall retains config, releases, task state and skills.');process.exit(0);}
 if(!isAbsolute(v.prefix??''))throw Error('--prefix ABS required');const prefix=resolve(v.prefix);await regular(prefix);const owner=JSON.parse(await readFile(join(prefix,'.installation.json'),'utf8'));
 if(owner.prefix!==prefix)throw Error('Installation identity mismatch');const configPath=v.config??owner.config;if(configPath!==owner.config)throw Error('Use the installation config');await regular(configPath);const config=JSON.parse(await readFile(configPath,'utf8'));if(resolve(config.stateDir)!==join(prefix,'state'))throw Error('State identity mismatch');
 const name=owner.component==='cli'?'personal-wiki':'wiki-bridge',bin=join(prefix,'bin',name),runtime=join(prefix,'state/runtime/current');
 if(p[0]==='configure'){
  for(const [flag,key] of [['vault','vault'],['python','python'],['codex','codexBinary'],['media-token-file','mediaServiceTokenFile']])if(v[flag]){if(!isAbsolute(v[flag]))throw Error('Absolute '+flag+' required');config[key]=v[flag];}
  if(v['media-url']){const url=new URL(v['media-url']);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.pathname!=='/'||url.search||url.hash)throw Error('Media origin required');config.mediaServiceUrl=url.origin;}
  await atomic(configPath,JSON.stringify(config,null,2)+'\n');
 }else if(p[0]==='skill-install'){
  if(owner.component!=='cli')throw Error('Install the CLI skill from the CLI package');const directory=resolve(v['skills-dir']??join(homedir(),'.codex/skills'));await regular(directory);const target=join(directory,'personal-wiki');await mkdir(target,{recursive:false,mode:0o700}).catch(async e=>{if(e.code==='ENOENT'){await mkdir(directory,{recursive:true,mode:0o700});await mkdir(target,{mode:0o700});}else throw e;});
  const text=(await readFile(join(runtime,'.agents/skills/personal-wiki/SKILL.md'),'utf8')).replace('使用本项目的实际 CLI 执行摄取。',`使用已安装 CLI \`${bin}\` 执行摄取。`).replace('找不到命令时，在项目根目录使用 `node scripts/wiki.mjs`。','命令不在 PATH 时使用上述绝对路径。').replace('../../../docs/contracts/ingestion-cli.md','references/ingestion-cli.md');
  await atomic(join(target,'SKILL.md'),text);await atomic(join(target,'references/ingestion-cli.md'),await readFile(join(runtime,'docs/contracts/ingestion-cli.md')));
 }else if(['worker-install','worker-uninstall','uninstall'].includes(p[0])){
  const label='com.personal-wiki.distribution.'+owner.component,plist=join(homedir(),'Library/LaunchAgents',label+'.plist');await regular(plist);
  if(p[0]==='worker-install'){
   if(owner.component!=='cli')throw Error('The bridge runs explicit ingest jobs; install a worker with the CLI');if(process.platform!=='darwin')throw Error('launchd requires macOS');
   const xml=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');const body=`<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>${label}</string><key>ProgramArguments</key><array><string>${xml(bin)}</string><string>worker</string><string>--watch</string></array><key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ProcessType</key><string>Background</string><key>StandardOutPath</key><string>${xml(join(prefix,'state/worker.log'))}</string><key>StandardErrorPath</key><string>${xml(join(prefix,'state/worker-error.log'))}</string></dict></plist>\n`;
   const old=await readFile(plist,'utf8').catch(e=>{if(e.code!=='ENOENT')throw e;});if(old&&old!==body)throw Error('Another worker owns this launchd label; retained');await atomic(plist,body);let running=false;try{execFileSync('/bin/launchctl',['print','gui/'+process.getuid()+'/'+label],{stdio:'pipe'});running=true;}catch{}if(!running)execFileSync('/bin/launchctl',['bootstrap','gui/'+process.getuid(),plist],{stdio:'pipe'});
  }else{
   const old=await readFile(plist,'utf8').catch(e=>{if(e.code!=='ENOENT')throw e;});if(old){if(!old.includes(bin))throw Error('Another worker owns this launchd label; retained');try{execFileSync('/bin/launchctl',['bootout','gui/'+process.getuid(),plist],{stdio:'pipe'});}catch{}await unlink(plist);}
   if(p[0]==='uninstall'){
    if(owner.component==='cli'){
     const updater=join(prefix,'bin/pwiki-update'),text=await readFile(updater,'utf8').catch(e=>{if(e.code!=='ENOENT')throw e;});
     if(text){if(!text.includes(quote(join(runtime,'distribution/pwiki-setup.py')))||!text.includes(quote(prefix)))throw Error('Updater launcher edited; retained');execFileSync(config.python,[join(runtime,'distribution/pwiki-setup.py'),'schedule','--prefix',prefix,'--remove'],{stdio:'pipe'});await unlink(updater);}
    }
    const text=await readFile(bin,'utf8').catch(e=>{if(e.code!=='ENOENT')throw e;});if(text){if(!text.includes(quote(configPath))||!text.includes(quote(join(runtime,'scripts',name==='personal-wiki'?'wiki.mjs':'wiki-bridge.mjs'))))throw Error('Launcher edited; retained');await unlink(bin);}
   }
  }
 }else throw Error('Unknown lifecycle command');
 console.log(JSON.stringify({status:'ok',action:p[0],prefix,config:configPath}));
}catch(error){console.error(JSON.stringify({status:'error',message:error.message}));process.exitCode=1;}
