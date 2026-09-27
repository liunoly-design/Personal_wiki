import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import {join,basename} from 'node:path';import {createHash} from 'node:crypto';
import {store} from './protected-compiler.js';
const hash=text=>createHash('sha256').update(text).digest('hex');
function intro(d){return `## 是什么\n\n${d.definition}\n\n## 简单例子\n\n${d.example}\n\n## 歧义与核实状态\n\n${d.uncertainty}\n\n> 基础说明由模型生成，未经独立核实；与下方文章观点分开。\n`;}
export async function refreshTerms({vault,python,explain,prepareOnly=false,onProgress=()=>{}}){
 const files=[];
 for(const folder of ['glossary','wiki/entities','wiki/concepts']){
  for(const name of (await readdir(join(vault,folder)).catch(e=>{if(e.code==='ENOENT')return [];throw e;})).filter(n=>n.endsWith('.md')).sort()){
   const path=folder+'/'+name,original=await readFile(join(vault,path),'utf8');
   const title=original.match(/^#\s+(.+)$/mu)?.[1]??basename(name,'.md');
   files.push({path,original,title,hash:hash(original),glossary:folder==='glossary'});
  }
 }
 const sources=[];
 for(const folder of ['raw/sources','raw/inputs'])for(const name of await readdir(join(vault,folder)).catch(e=>{if(e.code==='ENOENT')return [];throw e;})){if(name.endsWith('.md'))sources.push({name,text:await readFile(join(vault,folder,name),'utf8')});}
 function sourceContext(name){const re=new RegExp(name.replace(/[.*+?^${}()|[\]\\]/gu,'\\$&').replace(/\s+/gu,'\\s*'),'iu');return sources.flatMap(s=>{const m=re.exec(s.text);return m?[s.name+': '+s.text.slice(Math.max(0,m.index-220),m.index+name.length+700)]:[];}).slice(0,2).join('\n');}
 const runId=hash('source-grounded-v3:'+files.map(f=>f.path+f.hash).join('\n')).slice(0,20),directory=join(vault,'.personal-wiki/term-refresh',runId);
 await mkdir(directory,{recursive:true,mode:0o700});
 const definitions={};
 const canonical=s=>s.toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
 const entries=files.map(f=>({name:f.title,slug:'term-'+hash(f.path).slice(0,16),domain:sourceContext(f.title)?'原始资料片段仅用于辨认具体指代，不能把文章评价当作基础定义：'+sourceContext(f.title):f.glossary?'参考原解释仅用于名词消歧，不沿用错误定义：'+f.original.slice(0,900)+' 相关知识页语境：'+files.filter(p=>!p.glossary&&canonical(p.title)===canonical(f.title)).map(p=>p.original.slice(0,1800)).join('\n'):'文章中的用法仅用于辨认实体/概念，定义必须独立说明其类别、用途、必要时创作者；不把文中指标当定义：'+f.original.slice(0,1800)}));
 let next=0,completed=0;
 async function worker(){while(next<entries.length){
  const i=next;next+=4;
  const batch=entries.slice(i,i+4),file=join(directory,'batch-'+i+'.json');let values;
  try{values=JSON.parse(await readFile(file,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;values=await explain(batch);}
  if(!Array.isArray(values)||values.length!==batch.length)throw Error('Incomplete term regeneration');
  for(const term of batch){const matches=values.filter(v=>v.slug===term.slug);const d=matches[0];if(matches.length!==1||!['definition','example','uncertainty'].every(k=>typeof d[k]==='string'&&d[k].trim()&&d[k].length<15000))throw Error('Invalid regenerated definition');definitions[term.slug]=d;}
  try{await writeFile(file,JSON.stringify(values),{flag:'wx',mode:0o600});}catch(e){if(e.code!=='EEXIST')throw e;}
  completed+=batch.length;onProgress({generated:completed,total:entries.length});
 }}
 await Promise.all([worker(),worker()]);
 const changes=files.map((f,i)=>{
  const d=definitions[entries[i].slug];let content=f.original;
  if(f.glossary){
   for(const [heading,value] of [['基础解释',d.definition],['简单例子',d.example],['歧义与不确定性',d.uncertainty]]){
    const expression=new RegExp('^## '+heading+'\\s*\\n[\\s\\S]*?(?=^## |^> 基础解释|$(?![\\s\\S]))','mu');
    if(expression.test(content))content=content.replace(expression,()=>`## ${heading}\n\n${value}\n\n`);
    else content+='\n\n## '+heading+'\n\n'+value+'\n';
   }
  }else{
   content=content.replace(/\n<!-- wiki:definition:start -->[\s\S]*?<!-- wiki:definition:end -->\n/u,'\n');
   const section='\n<!-- wiki:definition:start -->\n'+intro(d)+'<!-- wiki:definition:end -->\n\n## 文章中的用法与来源\n';
   content=content.replace(/^(# .+)$/mu,(_,h)=>h+'\n'+section);
  }
  return {path:f.path,expectedHash:f.hash,content};
 });
 const plan={operation:'refresh-terms',vault,runId,changes};
 await writeFile(join(directory,'plan.json'),JSON.stringify(plan),{mode:0o600});
 if(prepareOnly)return {prepared:changes.length,runId,plan:join(directory,'plan.json')};
 return store(plan,{python});
}
