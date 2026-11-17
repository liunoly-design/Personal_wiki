// Shared command leases and exclusive installation leases use the same OS flock.
import {mkdir,lstat,realpath,readFile} from 'node:fs/promises';
import {resolve,join,dirname} from 'node:path';
import {spawn} from 'node:child_process';

export async function runtimeLease(config,{exclusive=false}={}){
 if(!config.runtimeRoot)return async()=>{};
 const root=resolve(config.runtimeRoot);
 if(root!==join(resolve(config.stateDir),'runtime'))throw Error('Runtime installation identity mismatch');
 await mkdir(root,{recursive:true,mode:0o700});
 for(let path=root;;path=dirname(path)){if((await lstat(path)).isSymbolicLink())throw Error('Runtime symlink refused');if(path===dirname(path))break;}
 const child=spawn(config.python??'python3',[resolve(import.meta.dirname,'../scripts/runtime_lock.py'),join(root,'use.lock'),exclusive?'exclusive':'shared'],{stdio:['pipe','pipe','pipe']});
 try{await new Promise((accept,reject)=>{
  child.once('error',reject);
  child.stdout.once('data',data=>{if(data.toString().trim()==='ready')accept();else reject(Object.assign(Error('Runtime busy; update deferred'),{code:'RUNTIME_BUSY'}));});
  child.once('exit',code=>{if(code!==0)reject(Error('Runtime lease unavailable'));});
 });}catch(error){child.stdin.destroy();throw error;}
 const release=async()=>{if(child.exitCode!==null)return;await new Promise(accept=>{child.once('exit',accept);child.stdin.end();});};
 if(!exclusive){try{const transaction=JSON.parse(await readFile(join(root,'activation.json'),'utf8'));if(transaction.phase==='activating')throw Object.assign(Error('Interrupted runtime activation; run pwiki-update'),{code:'RUNTIME_BUSY'});}catch(error){if(error.code!=='ENOENT'){await release();throw error;}}}
 if(!exclusive&&await realpath(join(root,'current'))!==resolve(import.meta.dirname,'..')){await release();throw Object.assign(Error('Runtime changed; retry command'),{code:'RUNTIME_CHANGED'});}
 return release;
}
