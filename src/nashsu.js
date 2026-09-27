import {buildChineseReading,codexTranslator} from './chinese-reading.js';
import {createCodex} from './codex.js';
import {store,compileArchive} from './protected-compiler.js';
import {readFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const exec=promisify(execFile);
const root=resolve(import.meta.dirname,'..');
export function createAdapters({vault,python,captureDirectory,flash,refresh=false,codexBinary,compilerModel,reading=false,translate=codexTranslator(codexBinary),generate=createCodex({binary:codexBinary,model:compilerModel})}){
 return {
  ...flash,
  async retryReading(sourceId,signal){
   if(!/^[a-f0-9]{20}$/u.test(sourceId))throw Error('Invalid source ID');
   const record=JSON.parse(await readFile(join(vault,'.personal-wiki',sourceId+'.json'),'utf8'));
   if(!record.source.startsWith(join(vault,'raw/inputs')+'/'))throw Error('Existing archives are not back-translated');
   return buildChineseReading({vault,record,translate,python,signal});
  },
  async lookupExisting(url,signal){
   if(refresh)return null;
   const u=new URL(url);if(['x.com','twitter.com'].includes(u.hostname)){u.hostname='x.com';u.search='';u.pathname=u.pathname.replace(/\/$/u,'');}u.hash='';
   const index=JSON.parse(await readFile(join(vault,'.personal-wiki/captures.json'),'utf8').catch(e=>{if(e.code==='ENOENT')return '{}';throw e;}));
   const found=index[u.href];if(!found)return null;
   await exec(python,[join(root,'scripts/import_capture.py'),'--vault',vault,'--snapshot',found.archive,'--message','小婕收集 '+u.href],{signal,timeout:60000,maxBuffer:1024*1024});
   if(found.source.startsWith(join(vault,'raw/inputs')+'/')){
    const directory=join(vault,'.personal-wiki/compilations',found.id);
    try{
     await readFile(join(directory,'generation.json'));
     const result=await compileArchive({vault,record:found,python,signal});
     let savedReading;
     if(reading){try{savedReading=JSON.parse(await readFile(join(vault,'.personal-wiki/readings',found.id,'result.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;savedReading={status:'pending',reason:'Only explicit translation retry resumes this stage'};}}
     return {...result,status:'existing',...(savedReading?{reading:savedReading}:{})};
    }catch(e){if(e.code!=='ENOENT')throw e;return {status:'pending',source:found.source};}
   }
   const name=found.name??found.source.split('/').at(-1).replace(/\.md$/u,'');
   const page=join(vault,'wiki/sources',name+'.md');
   try{await readFile(page);return {status:'existing',source:page};}catch(e){if(e.code!=='ENOENT')throw e;return {status:'pending',source:found.source};}
  },
  async capture(url,signal){
   const {stdout}=await exec(python,[join(root,'scripts/capture_article.py'),'--url',url,'--output',captureDirectory],{signal,timeout:900000,maxBuffer:1024*1024});
   const receipt=JSON.parse(stdout);return {...receipt,text:await readFile(join(receipt.directory,'article.md'),'utf8')};
  },
  async importAndCompile({capture,slug,context,url,signal,onStage=async()=>{}}){
   const normalized=new URL(url);if(['x.com','twitter.com'].includes(normalized.hostname)){normalized.hostname='x.com';normalized.search='';normalized.pathname=normalized.pathname.replace(/\/$/u,'');}normalized.hash='';
   const record=await store({operation:'archive',vault,snapshot:capture.directory,slug,url:normalized.href,refresh},{python,signal});
   await onStage('archived',{sourceId:record.id,archive:record.archive});
   const compiled=await compileArchive({vault,record,context,generate,python,signal,onStage});
   await onStage('compiled',{compilation:compiled});
   if(!reading)return compiled;
   await onStage('translating',{reading:{status:'processing'}});
   try{return {...compiled,reading:await buildChineseReading({vault,record,translate,python,signal})};}
   catch(error){return {...compiled,reading:{status:'pending',reason:error.message}};}

  },
 };
}
