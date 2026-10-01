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
export async function compileArchive({vault,record,context='',generate,explain,python,signal,onStage=async()=>{}}){
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
 const generation=await generate({stage:'generation',sourceName:record.name,prompt:buildGenerationPrompt(schema,purpose,index,record.name+'.md',undefined,original)+'\n\n## Source\n'+original+'\n\n## Analysis\n'+analysis+'\n\n## Processing context\n'+context+'\n\n本地提交约束（必须遵守，否则全部提交拒绝）：所有文件路径只能使用 ASCII 英文小写字母、数字、连字符，不能使用中文或下划线。正文与标题仍用中文。来源卡路径必须恰为 wiki/sources/'+record.name+'.md。不要使用来源卡标题或概念的中文名作为路径。本轮只输出 wiki/sources、wiki/concepts、wiki/entities、wiki/topics、wiki/synthesis 下的 Markdown 页及 wiki/log.md。每个主张保留来源和日期，冲突观点并列，不抹去旧观点。不得修改原件。',signal});
 const parsed=parseFileBlocks(generation);
 if(parsed.warnings.length||parsed.truncatedPaths.length||!parsed.blocks.length)throw Error('Incomplete or unsafe generated candidates; original archived');
 // The desktop normally handles log updates itself; its append-only log output
 // is not a knowledge page. Our commit journal records the actual operation.
 const blocks=parsed.blocks.filter(b=>b.path!=='wiki/log.md');
 const knowledge=blocks.filter(b=>/^wiki\/(entities|concepts)\//u.test(b.path));
 if(explain&&knowledge.length){
  for(let start=0;start<knowledge.length;start+=6){
   const batch=knowledge.slice(start,start+6);
   const terms=batch.map((b,i)=>({slug:'definition-'+(start+i),name:b.content.match(/^#\s+(.+)$/mu)?.[1]??b.path.split('/').at(-1).replace(/\.md$/u,''),domain:'文章语境仅用于消歧：'+b.content.slice(0,1200)}));
   const values=await explain(terms,signal);
   for(let i=0;i<batch.length;i++){
    const matching=Array.isArray(values)?values.filter(d=>d.slug===terms[i].slug):[];
    if(matching.length!==1||!['definition','example','uncertainty'].every(k=>typeof matching[0][k]==='string'&&matching[0][k].trim()))throw Error('Incomplete knowledge definitions; original archived');
    const d=matching[0],section=`\n\n## 是什么\n\n${d.definition}\n\n## 简单例子\n\n${d.example}\n\n## 歧义与核实状态\n\n${d.uncertainty}\n\n> 基础说明由模型生成，未经独立核实；下文是文章观点及证据。\n\n## 文章中的用法与来源\n`;
    if(!/^# /mu.test(batch[i].content))throw Error('Knowledge page is missing title');
    batch[i].content=batch[i].content.replace(/^(# .+)$/mu,(_,heading)=>heading+section);
   }
  }
 }

 await onStage('committing',{sourceId:record.id});
 return store({operation:'commit',vault,sourceId:record.id,blocks,generation},{python,signal});
}
