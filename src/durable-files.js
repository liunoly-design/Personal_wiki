import {mkdir,open,rename,readFile} from 'node:fs/promises';
import {dirname} from 'node:path';
import {randomUUID} from 'node:crypto';
export async function saveJSON(path,value){
 await mkdir(dirname(path),{recursive:true,mode:0o700});
 const temporary=path+'.'+randomUUID()+'.tmp';const f=await open(temporary,'wx',0o600);
 try{await f.writeFile(JSON.stringify(value,null,2)+'\n');await f.sync();}finally{await f.close();}
 await rename(temporary,path);const d=await open(dirname(path),'r');try{await d.sync();}finally{await d.close();}
}
export async function optionalJSON(path){try{return JSON.parse(await readFile(path,'utf8'));}catch(e){if(e.code==='ENOENT')return null;throw e;}}
