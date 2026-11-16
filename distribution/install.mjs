#!/usr/bin/env node
// Standalone installer: Node built-ins only; configuration and state are retained.
import {readFile,mkdir,lstat,writeFile,cp,rename,symlink,unlink,open,chmod} from 'node:fs/promises';
import {resolve,join,dirname,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {homedir} from 'node:os';
import {createHash,randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {parseArgs} from 'node:util';
const digest=b=>createHash('sha256').update(b).digest('hex');
const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
async function regularParents(path){
 for(let p=resolve(path);;p=dirname(p)){const s=await lstat(p).catch(e=>{if(e.code!=='ENOENT')throw e;});if(s&&(!s.isDirectory()||s.isSymbolicLink()))throw Error('Regular installation directories required');if(p===dirname(p))break;}
}
async function privateDirectory(path){await regularParents(path);await mkdir(path,{recursive:true,mode:0o700});}
async function immutable(path,bytes){
 await privateDirectory(dirname(path));
 try{await writeFile(path,bytes,{flag:'wx',mode:0o600});}catch(e){if(e.code!=='EEXIST')throw e;if(!(await lstat(path)).isFile()||!Buffer.from(await readFile(path)).equals(Buffer.from(bytes)))throw Error('Existing installation file differs; retained');}
}
try{
 const {values:v}=parseArgs({options:{prefix:{type:'string'},config:{type:'string'},python:{type:'string'},vault:{type:'string'},codex:{type:'string'},'media-url':{type:'string'},'media-token-file':{type:'string'},help:{type:'boolean'}}});
 if(v.help){console.log('node install.mjs [--prefix ABS_DIR] [--config ABS_FILE] [--python ABS_PYTHON] [--vault ABS_VAULT] [--codex ABS_CODEX] [--media-url ORIGIN] [--media-token-file ABS_FILE]');process.exit(0);}
 if(Number(process.versions.node.split('.')[0])<24)throw Error('Node 24+ required');
 const source=dirname(fileURLToPath(import.meta.url)),manifest=JSON.parse(await readFile(join(source,'distribution.json'),'utf8'));
 if(!/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/u.test(manifest.version)||!['cli','wiki-bridge'].includes(manifest.component)||!/^[a-f0-9]{40}$/u.test(manifest.revision))throw Error('Invalid distribution manifest');
 for(const [path,sha] of Object.entries(manifest.files)){
  if(path.startsWith('/')||path.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('Unsafe distribution path');
  for(let p=join(source,path);p!==source;p=dirname(p))if((await lstat(p)).isSymbolicLink())throw Error('Distribution symlink rejected');
  if(!(await lstat(join(source,path))).isFile()||digest(await readFile(join(source,path)))!==sha)throw Error('Distribution integrity mismatch');
 }
 const prefix=resolve(v.prefix??join(homedir(),'.local/share','personal-wiki-'+manifest.component));const configPath=resolve(v.config??join(homedir(),'.config/personal-wiki',manifest.component+'.json'));
 if(v.prefix&&!isAbsolute(v.prefix)||v.config&&!isAbsolute(v.config))throw Error('Absolute install prefix and config required');
 const python=v.python??execFileSync('/usr/bin/which',['python3'],{encoding:'utf8'}).trim();
 execFileSync(python,['-c','import sys;assert sys.version_info >= (3,9)'],{stdio:'ignore'});
 await privateDirectory(prefix);await privateDirectory(dirname(configPath));
 const stateDir=join(prefix,'state'),runtimeRoot=join(stateDir,'runtime'),version=manifest.version+'-'+digest(JSON.stringify(manifest.files)).slice(0,16),release=join(runtimeRoot,'releases',version);
 const configStat=await lstat(configPath).catch(e=>{if(e.code!=='ENOENT')throw e;});if(configStat&&(!configStat.isFile()||configStat.isSymbolicLink()))throw Error('Regular private config file required');
 const old=await readFile(configPath,'utf8').then(JSON.parse).catch(e=>{if(e.code!=='ENOENT')throw e;return null;});
 if(configStat&&(configStat.mode&0o077||configStat.uid!==process.getuid()))throw Error('Private owned config required');
 if(old&&resolve(old.stateDir)!==stateDir)throw Error('Existing config belongs to another installation');
 const config={stateDir,runtimeRoot,python,autoStart:false,...(v.vault?{vault:resolve(v.vault)}:{}),...(v.codex?{codexBinary:resolve(v.codex)}:{}),...(v['media-url']?{mediaServiceUrl:v['media-url']}:{}),...(v['media-token-file']?{mediaServiceTokenFile:resolve(v['media-token-file'])}:{})};
 await privateDirectory(join(runtimeRoot,'releases'));
 const releaseStat=await lstat(release).catch(e=>{if(e.code!=='ENOENT')throw e;});if(releaseStat&&(!releaseStat.isDirectory()||releaseStat.isSymbolicLink()))throw Error('Regular release directory required');
 const installed=await readFile(join(release,'.distribution.json'),'utf8').then(JSON.parse).catch(e=>{if(e.code!=='ENOENT')throw e;return null;});
 if(!installed){
  const stage=release+'.stage-'+randomUUID();await privateDirectory(stage);for(const path of Object.keys(manifest.files).filter(p=>p.startsWith('runtime/'))){const target=join(stage,path.slice(8));await immutable(target,await readFile(join(source,path)));}await immutable(join(stage,'.distribution.json'),JSON.stringify(manifest,null,2)+'\n');await immutable(join(stage,'.release.json'),JSON.stringify({version:manifest.revision,distribution:version})+'\n');await rename(stage,release);
 }else if(JSON.stringify(installed)!==JSON.stringify(manifest))throw Error('Release identity conflict');
 // Validate installed bytes on every replay, including files humans may have edited.
 for(const [path,sha] of Object.entries(manifest.files).filter(([p])=>p.startsWith('runtime/'))){const file=join(release,path.slice(8));for(let p=file;p!==release;p=dirname(p))if((await lstat(p)).isSymbolicLink())throw Error('Installed symlink rejected');if(digest(await readFile(file))!==sha)throw Error('Installed runtime differs; retained');}
 if(!old)await immutable(configPath,JSON.stringify(config,null,2)+'\n');
 await immutable(join(prefix,'.installation.json'),JSON.stringify({component:manifest.component,prefix,config:configPath})+'\n');
 const name=manifest.component==='wiki-bridge'?'wiki-bridge':'personal-wiki',entry=manifest.component==='wiki-bridge'?'wiki-bridge.mjs':'wiki.mjs';
 const bin=join(prefix,'bin',name);await immutable(bin,`#!/bin/sh\nexport WIKI_CONFIG=${quote(configPath)}\nexec ${quote(process.execPath)} ${quote(join(runtimeRoot,'current/scripts',entry))} "$@"\n`);await chmod(bin,0o700);
 const current=join(runtimeRoot,'current');const previous=await lstat(current).catch(e=>{if(e.code!=='ENOENT')throw e;});if(previous&&!previous.isSymbolicLink())throw Error('Runtime current must be an installer-managed symlink');
 const temporary=current+'.'+randomUUID();await symlink(release,temporary);await rename(temporary,current);
 console.log(JSON.stringify({status:'installed',component:manifest.component,prefix,config:configPath,command:bin,release,dependencies:'Install Python capture dependencies separately before URL intake; Wiki/Codex and Mini require configuration.'}));
}catch(error){console.error(JSON.stringify({status:'error',message:error.message}));process.exitCode=1;}
