import {spawn} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {buildAnalysisPrompt,buildGenerationPrompt,parseFileBlocks} from '../vendor/nashsu/ingest.ts';

const script=resolve(import.meta.dirname,'../scripts/protected_store.py');
export function store(request,{python='python3',signal}={}){
 return new Promise((accept,reject)=>{
  const child=spawn(python,[script],{signal,stdio:['pipe','pipe','pipe']});
  let output='',error='';
  child.stdout.on('data',d=>{output+=d;});child.stderr.on('data',d=>{error+=d;});
  child.on('error',reject);child.stdin.on('error',reject);
  child.on('close',code=>{if(code!==0){reject(Error('Protected archive failed: '+error));return;}try{accept(JSON.parse(output));}catch(e){reject(e);}});
  child.stdin.end(JSON.stringify(request));
 });
}
async function optional(path){try{return await readFile(path,'utf8');}catch(e){if(e.code==='ENOENT')return '';throw e;}}
export async function compileArchive({vault,record,context='',generate,python,signal,onStage=async()=>{}}){
 const directory=join(vault,'.personal-wiki/compilations',record.id);
 const saved=await optional(join(directory,'generation.json'));
 if(saved)return store(JSON.parse(saved),{python,signal});
 const done=await optional(join(directory,'result.json'));if(done)return JSON.parse(done);
 const original=await readFile(join(record.archive,'article.md'),'utf8');
 const [schema,purpose,index]=await Promise.all(['schema.md','purpose.md','wiki/index.md'].map(p=>optional(join(vault,p))));
 if(!generate)throw Error('Protected compiler model adapter is not configured; original archived');
 await onStage('analyzing',{sourceId:record.id});
 const analysis=await generate({stage:'analysis',prompt:buildAnalysisPrompt(purpose,index,original,schema)+'\n\n## Source\n'+original+'\n\n## Processing context\n'+context,signal});
 await onStage('generating',{sourceId:record.id});
 const generation=await generate({stage:'generation',prompt:buildGenerationPrompt(schema,purpose,index,record.name+'.md',undefined,original)+'\n\n## Source\n'+original+'\n\n## Analysis\n'+analysis+'\n\n## Processing context\n'+context+'\n\n本地提交约束：文件名使用英文小写连字符。本轮只输出 wiki/sources、wiki/concepts、wiki/entities、wiki/topics、wiki/synthesis 下的 Markdown 页及 wiki/log.md。每个主张保留来源和日期，冲突观点并列，不抹去旧观点。不得修改原件。',signal});
 const parsed=parseFileBlocks(generation);
 if(parsed.warnings.length||parsed.truncatedPaths.length||!parsed.blocks.length)throw Error('Incomplete or unsafe generated candidates; original archived');
 // The desktop normally handles log updates itself; its append-only log output
 // is not a knowledge page. Our commit journal records the actual operation.
 const blocks=parsed.blocks.filter(b=>b.path!=='wiki/log.md');
 await onStage('committing',{sourceId:record.id});
 return store({operation:'commit',vault,sourceId:record.id,blocks,generation},{python,signal});
}
