import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {join,dirname,resolve} from 'node:path';
import {homedir} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {setTimeout as delay} from 'node:timers/promises';
const exec=promisify(execFile);
const root=resolve(import.meta.dirname,'..');
export function createAdapters({vault,python,captureDirectory,flash,refresh=false}){
 return {
  ...flash,
  async lookupExisting(url,signal){
   if(refresh)return null;
   const u=new URL(url);if(['x.com','twitter.com'].includes(u.hostname)){u.hostname='x.com';u.search='';u.pathname=u.pathname.replace(/\/$/u,'');}u.hash='';
   const index=JSON.parse(await readFile(join(vault,'.personal-wiki/captures.json'),'utf8').catch(e=>{if(e.code==='ENOENT')return '{}';throw e;}));
   const found=index[u.href];if(!found)return null;
   await exec(python,[join(root,'scripts/import_capture.py'),'--vault',vault,'--snapshot',found.archive,'--message','小婕收集 '+u.href],{signal,timeout:60000,maxBuffer:1024*1024});
   const name=found.name??found.source.split('/').at(-1).replace(/\.md$/u,'');
   const page=join(vault,'wiki/sources',name+'.md');
   try{await readFile(page);return {status:'existing',source:page};}catch(e){if(e.code!=='ENOENT')throw e;return {status:'pending',source:found.source};}
  },
  async capture(url,signal){
   const {stdout}=await exec(python,[join(root,'scripts/capture_article.py'),'--url',url,'--output',captureDirectory],{signal,timeout:900000,maxBuffer:1024*1024});
   const receipt=JSON.parse(stdout);return {...receipt,text:await readFile(join(receipt.directory,'article.md'),'utf8')};
  },
  async importAndCompile({capture,slug,context,url,signal}){
   const contextFile=join(captureDirectory,'analysis-context.md');await writeFile(contextFile,context);
   const {stdout}=await exec(python,[join(root,'scripts/import_capture.py'),'--vault',vault,'--snapshot',capture.directory,'--message','小婕收集 '+url,'--name',slug,'--analysis-context',contextFile,...(refresh?['--refresh']:[])],{signal,timeout:60000,maxBuffer:1024*1024});
   const imported=JSON.parse(stdout);const name=imported.name??imported.source.split('/').at(-1).replace(/\.md$/u,'');
   const page=join(vault,'wiki/sources',name+'.md');
   const app=JSON.parse(await readFile(join(homedir(),'Library/Application Support/com.llmwiki.app/app-state.json'),'utf8'));
   if(app.lastProject?.path!==vault)throw Error('nashsu must have this Vault open; original retained');
   await fetch('http://127.0.0.1:19828/api/v1/projects/'+encodeURIComponent(app.lastProject.id)+'/sources/rescan',{method:'POST',headers:{Authorization:'Bearer '+app.apiConfig.token},signal:AbortSignal.any([AbortSignal.timeout(15000),...(signal?[signal]:[])])}).then(r=>{if(!r.ok)throw Error('nashsu rescan unavailable; original retained');});
   for(let i=0;i<600;i++){
    signal?.throwIfAborted();
    const queue=JSON.parse(await readFile(join(vault,'.llm-wiki/ingest-queue.json'),'utf8').catch(e=>{if(e.code==='ENOENT')return '[]';throw e;}));
    const task=queue.find(t=>t.sourcePath==='raw/sources/'+name+'.md');
    if(task&&['error','failed','stopped'].includes(task.status))throw Error('nashsu compilation waiting or failed; inspect app queue');
    const cache=JSON.parse(await readFile(join(vault,'.llm-wiki/ingest-cache.json'),'utf8').catch(e=>{if(e.code==='ENOENT')return '{}';throw e;}));
    if(!task&&cache.entries?.[name+'.md']){
     await readFile(page,'utf8');
     if(imported.status!=='existing')await exec(python,[join(root,'scripts/finalize_capture.py'),'--vault',vault,'--source-id',name],{signal,timeout:30000});
     return {status:imported.status==='existing'?'existing':'complete',source:page};
    }
    await delay(2000,undefined,{signal});
   }
   throw Error('nashsu compilation still pending; original retained');
  },
 };
}
