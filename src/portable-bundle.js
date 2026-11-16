import {readFile,writeFile,mkdir,lstat,rename,rm} from 'node:fs/promises';import {resolve,join,dirname,isAbsolute} from 'node:path';import {createHash,randomUUID} from 'node:crypto';
const hash=x=>createHash('sha256').update(x).digest('hex');
async function parents(path){for(let p=resolve(path);;p=dirname(p)){const s=await lstat(p).catch(e=>{if(e.code!=='ENOENT')throw e;});if(s?.isSymbolicLink())throw Error('Portable bundle symlink rejected');if(p===dirname(p))break;}}
function safeHashes(hashes){
 if(!hashes||typeof hashes!=='object'||Array.isArray(hashes)||Object.keys(hashes).length>2048)throw Error('Invalid portable file list');
 for(const [name,sha] of Object.entries(hashes))if(name.startsWith('/')||name.includes('\\')||name.split('/').some(p=>!p||p==='.'||p==='..')||typeof sha!=='string'||!/^[a-f0-9]{64}$/u.test(sha))throw Error('Unsafe portable path or hash');
}
export async function readPortable(file){
 if(!isAbsolute(file))throw Error('Absolute portable manifest required');await parents(file);const stat=await lstat(file);if(!stat.isFile()||stat.size>8*1024*1024)throw Error('Invalid portable manifest');const bytes=await readFile(file);const m=JSON.parse(bytes);
 if(m.format!=='personal-wiki-source-v1'||m.complete!==true||!['text','file','web','x','wechat','douyin','xiaohongshu'].includes(m.source?.platform)||!m.hashes?.['article.md'])throw Error('Complete source bundle required');
 const url=new URL(m.source.url);if(url.protocol!=='https:'||url.username||url.password||url.hash||url.port&&url.port!=='443')throw Error('Invalid portable source URL');
 safeHashes(m.hashes);const directory=join(dirname(file),'payload');let total=0;
 for(const [name,sha] of Object.entries(m.hashes)){
  if(name.startsWith('/')||name.includes('\\')||name.split('/').some(p=>!p||p==='.'||p==='..')||!/^[a-f0-9]{64}$/u.test(sha))throw Error('Unsafe portable path or hash');
  const path=join(directory,name);await parents(path);const s=await lstat(path);total+=s.size;if(!s.isFile()||total>250*1024*1024||hash(await readFile(path))!==sha)throw Error('Portable bundle integrity mismatch');
 }
 return {manifest:m,digest:hash(bytes),bundle:{directory,markdown:join(directory,'article.md'),url:m.source.url,platform:m.source.platform,hashes:m.hashes,complete:true}};
}
export async function writePortable(bundle,directory){
 safeHashes(bundle.hashes);if(!isAbsolute(directory))throw Error('Absolute portable destination required');await parents(dirname(directory));
 if(await lstat(directory).catch(e=>{if(e.code!=='ENOENT')throw e;}))throw Error('Portable destination already exists; retained');
 await mkdir(dirname(directory),{recursive:true,mode:0o700});const stage=directory+'.stage-'+randomUUID();await mkdir(stage,{mode:0o700});
 try{
  for(const [name,sha] of Object.entries(bundle.hashes)){const bytes=await readFile(join(bundle.directory,name));if(hash(bytes)!==sha)throw Error('Source integrity mismatch');const path=join(stage,'payload',name);await mkdir(dirname(path),{recursive:true,mode:0o700});await writeFile(path,bytes,{flag:'wx',mode:0o600});}
  const m={format:'personal-wiki-source-v1',complete:true,source:{url:bundle.url,platform:bundle.platform},hashes:bundle.hashes};await writeFile(join(stage,'bundle.json'),JSON.stringify(m,null,2)+'\n',{flag:'wx',mode:0o600});await readPortable(join(stage,'bundle.json'));await rename(stage,directory);return {directory,manifest:join(directory,'bundle.json')};
 }finally{await rm(stage,{recursive:true,force:true});}
}
export async function freezePortable(file,root){
 const read=await readPortable(file);const directory=join(root,read.digest);await parents(root);
 if(!await lstat(directory).catch(e=>{if(e.code!=='ENOENT')throw e;})){try{await writePortable(read.bundle,directory);}catch(e){if(!['EEXIST','ENOTEMPTY'].includes(e.code)&&!e.message.includes('destination already exists'))throw e;}}
 const frozen=await readPortable(join(directory,'bundle.json'));if(JSON.stringify(frozen.manifest)!==JSON.stringify(read.manifest))throw Error('Imported bundle conflict');return frozen;
}
