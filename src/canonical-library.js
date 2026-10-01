import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {createAdapters} from './nashsu.js';
import {createCodex} from './codex.js';
import {codexTranslator} from './chinese-reading.js';
import {recordArticle,validSlug} from './wk.js';
import {parseFileBlocks} from '../vendor/nashsu/ingest.ts';
import {localNashsuAPI} from './nashsu-api.js';
import {saveJSON,optionalJSON} from './durable-files.js';
const digest=x=>createHash('sha256').update(x).digest('hex');
export async function publishBundle(input,{python,signal}){
 return new Promise((accept,reject)=>{
  const child=spawn(python,[resolve(import.meta.dirname,'../scripts/publish_bundle.py')],{signal,stdio:['pipe','pipe','pipe']});let out='',err='';
  child.stdout.on('data',x=>out+=x);child.stderr.on('data',x=>err+=x);child.on('error',reject);child.stdin.on('error',reject);
  child.on('close',code=>{if(code)return reject(Error('Publication failed: '+err));try{accept(JSON.parse(out));}catch(e){reject(e);}});child.stdin.end(JSON.stringify(input));
 });
}
export async function verifyPublication(result,{vault,api}){
 for(const [path,hash] of Object.entries(result.files)){
  if(digest(await api.read(path))!==hash)throw Error('Nashsu API content mismatch: '+path);
 }
 for(const [path,hash] of Object.entries(result.assets)){
  if(digest(await readFile(join(vault,path)))!==hash)throw Error('Archive integrity mismatch: '+path);
 }
}
export async function collectCanonical(options){
 const {url,vault,workspace,python,signal,onStage=async()=>{}}=options;
 await mkdir(workspace,{recursive:true,mode:0o700});
 const staging=join(workspace,'staging');await mkdir(staging,{recursive:true,mode:0o700});
 const api=options.api??await localNashsuAPI(vault,{signal});
 const saved=options.previousResult??await optionalJSON(join(workspace,'published.json'));
 if(saved){await onStage('verifying');await verifyPublication(saved,{vault,api});return saved;}
 // Memoize successful expensive calls before continuing to the next stage.
 const memo=(name,fn)=>async(input,...rest)=>{
  const serial=typeof input==='object'&&input!==null?Object.fromEntries(Object.entries(input).filter(([k])=>k!=='signal')):input;
  const path=join(workspace,'calls',name+'-'+digest(JSON.stringify(serial))+'.json');
  const old=await optionalJSON(path);if(old)return old.value;
  const value=await fn(input,...rest);await saveJSON(path,{value});return value;
 };
 for(const path of ['schema.md','purpose.md','wiki/index.md']){
  try{const data=await readFile(join(vault,path));await mkdir(join(staging,path,'..'),{recursive:true});await writeFile(join(staging,path),data,{flag:'wx'});}catch(e){if(!['ENOENT','EEXIST'].includes(e.code))throw e;}
 }
 const flash={extract:memo('extract',async(...args)=>{const value=await options.flash.extract(...args);if(!validSlug(value.slug))throw Error('Invalid source name');return {...value,terms:[]};}),explain:memo('explain',options.flash.explain)};
 const adapters=createAdapters({vault:staging,python,captureDirectory:join(workspace,'capture'),flash,reading:true,
  generate:memo('generate',async input=>{const value=await (options.generate??createCodex({binary:options.codexBinary,model:options.compilerModel}))(input);if(input.stage==='generation'){const parsed=parseFileBlocks(value);if(parsed.warnings.length||parsed.truncatedPaths.length||!parsed.blocks.length)throw Error('Incomplete generation');}return value;}),
  translate:options.translate??codexTranslator(options.codexBinary)});
 const capture=options.capture??adapters.capture;
 adapters.capture=memo('capture',async(...args)=>{const value=await capture(...args);if(value.status!=='complete')throw Error('Attachments incomplete; retry required');return value;});
 // Existing staged archives are resumed by importAndCompile, including models
 // interrupted before a complete generation was saved.
 delete adapters.lookupExisting;
 let result=await recordArticle({url,vault:staging,signal,onStage},adapters);
 if(result.reading?.status!=='complete')throw Error('Chinese reading incomplete; retry required');
 if(result.attachmentStatus!=='complete')throw Error('Attachments incomplete; retry required');
 await api.assertPublisherReady?.();
 await onStage('publishing');
 result=await publishBundle({vault,staging,sourceId:result.sourceId},{python,signal});
 await saveJSON(join(workspace,'published.json'),result);
 await onStage('verifying');await verifyPublication(result,{vault,api});
 return result;
}
