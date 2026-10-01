import {mkdir,readFile,writeFile,readdir} from 'node:fs/promises';
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
async function captureHashes(directory){
 const hashes={};
 async function walk(path,prefix=''){for(const entry of await readdir(path,{withFileTypes:true})){const name=prefix+entry.name;if(entry.isSymbolicLink())throw Error('Snapshot symlinks are not allowed');if(entry.isDirectory())await walk(join(path,entry.name),name+'/');else hashes[name]=digest(await readFile(join(path,entry.name)));}}
 await walk(directory);return hashes;
}
export async function collectCanonical(options){
 if(options.inputError)throw Error(options.inputError);
 const {url,vault,workspace,python,signal,onStage=async()=>{}}=options;
 await mkdir(workspace,{recursive:true,mode:0o700});
 const staging=join(workspace,'staging');await mkdir(staging,{recursive:true,mode:0o700});
 const api=options.api??await localNashsuAPI(vault,{signal});
 const pendingPublication=await optionalJSON(join(workspace,'published.json'));
 const saved=pendingPublication??(!options.refresh?options.previousResult:null);
 const verifyReuse=async result=>{await verifyPublication({...result,files:Object.fromEntries(Object.entries(result.files).filter(([path])=>path.startsWith('raw/')))},{vault,api});await api.read('wiki/sources/'+result.source.split('/').at(-1));};
 const attachRequestBackground=async result=>{const {userRecord,...sourceResult}=result;if(!options.background)return sourceResult;const note=await publishBundle({vault,background:options.background,requestId:options.requestId,source:result.source},{python,signal});await verifyPublication(note,{vault,api});return {...sourceResult,userRecord:note.source};};
 if(saved){await onStage('verifying');if(pendingPublication)await verifyPublication(saved,{vault,api});else await verifyReuse(saved);return attachRequestBackground(saved);}
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
  generate:memo('generate',async input=>{const value=await (options.generate??createCodex({binary:options.codexBinary,model:options.compilerModel}))(input);if(input.stage==='generation'){const parsed=parseFileBlocks(value);if(parsed.warnings.length||parsed.truncatedPaths.length||!parsed.blocks.length||parsed.blocks.some(b=>b.path!=='wiki/log.md'&&!/^wiki\/(sources|concepts|entities|topics|synthesis)\/[a-z][a-z0-9-]*\.md$/u.test(b.path))||!parsed.blocks.some(b=>b.path==='wiki/sources/'+input.sourceName+'.md')){await saveJSON(join(workspace,'rejected-generation.json'),{sourceName:input.sourceName,paths:parsed.blocks.map(b=>b.path),warnings:parsed.warnings,value});throw Error('Incomplete or unsafe generation; rejected response retained for diagnosis');}}return value;}),
  translate:options.translate??codexTranslator(options.codexBinary)});
 const capture=options.capture??(options.text!==undefined?async()=>{const directory=join(workspace,'capture','package');await mkdir(directory,{recursive:true});await writeFile(join(directory,'article.md'),options.text);return {directory,text:options.text,status:'complete'};}:adapters.capture);
 const captured=await memo('capture',async(...args)=>{const value=await capture(...args);if(value.status!=='complete'&&!(value.publicBlog&&value.status==='partial'))throw Error('Attachments incomplete; retry required');return value;})(url,signal);
 const snapshotHashes=await captureHashes(captured.directory);
 const priorHashes=options.previousResult?.snapshotHashes??(options.previousResult?.assets?Object.fromEntries(Object.entries(options.previousResult.assets).map(([path,hash])=>[path.split('/').slice(3).join('/'),hash])):null);
 if(options.refresh&&priorHashes&&JSON.stringify(Object.entries(snapshotHashes).sort())===JSON.stringify(Object.entries(priorHashes).sort())){
  await verifyReuse(options.previousResult);return attachRequestBackground(options.previousResult);
 }
 adapters.capture=async()=>captured;
 // Existing staged archives are resumed by importAndCompile, including models
 // interrupted before a complete generation was saved.
 delete adapters.lookupExisting;
 let result=await recordArticle({url,vault:staging,signal,onStage,sourceContext:options.text!==undefined?'来源是用户粘贴的资料。text.personal-wiki.invalid 是本机内容标识，不是网页出处，不得虚构原作者或原网页。':''},adapters);
 if(result.reading?.status!=='complete')throw Error(result.reading?.reason??'Chinese reading incomplete; retry required');
 if(result.attachmentStatus!=='complete'&&!captured.publicBlog)throw Error('Attachments incomplete; retry required');
 await api.assertPublisherReady?.();
 await onStage('publishing');
 const compiled=result;
 result=await publishBundle({vault,staging,sourceId:result.sourceId},{python,signal});
 result={...result,title:compiled.title??result.title,summary:compiled.summary??null,snapshotHashes,attachmentStatus:captured.status,missingAssets:captured.missingAssets??[]};await saveJSON(join(workspace,'published.json'),result);
 await onStage('verifying');await verifyPublication(result,{vault,api});
 return attachRequestBackground(result);
}
