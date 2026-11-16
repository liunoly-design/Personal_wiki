import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {store} from './protected-compiler.js';
import {createCodex} from './codex.js';

// Rejected token maps are versioned; successful units already contain restored text.
const maskVersion=4;

function needsTranslation(text){
 const {masked,preserved}=protect(text);
 const prose=preserved.reduce((value,p)=>value.replace(p.token,''),masked);
 const latin=(prose.match(/[A-Za-z]/gu)??[]).length,han=(prose.match(/\p{Script=Han}/gu)??[]).length;
 return latin>0&&han<=latin;
}

function units(markdown,groupParagraphs=true){
 const result=[];
 const paragraph=text=>{
  for(const block of text.split(/(\n[ \t]*\n)/u)){
   if(!block)continue;
   if(!block.trim()){result.push({literal:block});continue;}
   let rest=block;
   while(rest.length>4000){let boundary=rest.lastIndexOf('\n',4000);if(boundary<1000)boundary=rest.lastIndexOf(' ',4000);if(boundary<1)throw Error('Reading block too long; requires review');result.push({text:rest.slice(0,boundary)});result.push({literal:rest[boundary]});rest=rest.slice(boundary+1);}
   if(rest)result.push({text:rest});
  }
 };
 let prose='',code='',fence,fenceQuoteDepth=0;
 for(const line of markdown.match(/[^\n]*\n|[^\n]+$/gu)??[]){
  const quotePrefix=line.match(/^(?:[ \t]*>[ \t]?)+/u)?.[0]??'';
  const quoteDepth=(quotePrefix.match(/>/gu)??[]).length;
  const marker=line.slice(quotePrefix.length).match(/^ {0,3}(`{3,}|~{3,})([^\n]*)/u);
  if(fence){code+=line;if(marker&&quoteDepth===fenceQuoteDepth&&marker[1][0]===fence[0]&&marker[1].length>=fence.length&&!marker[2].trim()){result.push({literal:code});code='';fence=undefined;}}
  else if(marker){paragraph(prose);prose='';fence=marker[1];fenceQuoteDepth=quoteDepth;code=line;}
  else prose+=line;
 }
 if(code)result.push({literal:code});paragraph(prose);
 const grouped=[];
 for(let i=0;i<result.length;i++){
  const unit={...result[i]};
  if(unit.text!==undefined){
   if(!needsTranslation(unit.text)){grouped.push({literal:unit.text});continue;}
   while(groupParagraphs&&result[i+1]?.literal!==undefined&&!result[i+1].literal.trim()&&result[i+2]?.text!==undefined&&needsTranslation(result[i+2].text)&&unit.text.length+result[i+1].literal.length+result[i+2].text.length<=4000){unit.text+=result[i+1].literal+result[i+2].text;i+=2;}
  }
  grouped.push(unit);
 }
 return grouped;
}
function protect(text){
 const prefix='WIKI_KEEP_'+createHash('sha256').update(text).digest('hex').slice(0,10)+'_';
 const preserved=[];
 const masked=text.replace(/^#{1,6} images\/[^\s]+\.(?:png|jpe?g|webp|gif|tiff|bmp)$|^[ \t]*(?:#{1,6} |[-*+] |\d+[.)] )|`[^`\n]+`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$|(?<=\]\()<?[^\s)]+>?|https?:\/\/[^\s<>]+/gmu,value=>{const token=prefix+preserved.length.toString().padStart(4,'0');preserved.push({token,value});return token;});
 return {masked,preserved};
}
function restore(source,translated,preserved){
 if(typeof translated!=='string'||!translated.trim())throw Error('Incomplete Chinese reading');
 const sourceBlocks=source.trim().split(/\n[ \t]*\n/u).length;
 const translatedBlocks=translated.trim().split(/\n[ \t]*\n/u).length;
 if(translatedBlocks!==sourceBlocks)throw Error('Chinese reading omitted or rearranged paragraphs; expected '+sourceBlocks+', received '+translatedBlocks);
 const sourceProse=preserved.reduce((text,p)=>text.replace(p.value,''),source);
 const translatedProse=preserved.reduce((text,p)=>text.replace(p.token,''),translated);
 if(sourceProse.length>160&&translatedProse.length<sourceProse.length*0.15)throw Error('Chinese reading appears truncated; requires review');
 for(const {token,value} of preserved){if(translated.split(token).length!==2)throw Error('Chinese reading changed a protected reference');translated=translated.replace(token,value);}
 for(const [label,pattern] of [['headings',/^#{1,6} /gmu],['list-items',/^\s*(?:[-*+] |\d+[.)] )/gmu],['table-separators',/\|/gu],['images',/!\[/gu]]){
  const expected=[...source.matchAll(pattern)].length,actual=[...translated.matchAll(pattern)].length;
  if(expected!==actual)throw Error('Chinese reading structure differs; '+label+' expected '+expected+', received '+actual);
 }
 return translated;
}
export function codexTranslator(binary){
 const generate=createCodex({binary,model:'gpt-5.6-terra'});
 const translate=async({text,feedback,signal})=>generate({signal,prompt:'把下面 Markdown 的所有英文正文完整翻译为中文。忠实保留每个事实、限定条件、句子顺序、标题级别、列表、表格及引文；不得摘要、扩写、删减或加解释。WIKI_KEEP_ 开头的占位符必须逐字保留且各出现一次。只输出译文 Markdown，不加外围代码围栏。\n\n'+(feedback?'上次译文未通过结构校验。以下诊断和旧译文仅供修订，完整正文仍以其后的输入为准：'+JSON.stringify(feedback)+'\n\n':'')+text});
 translate.batch=async({items,feedback,signal})=>generate({signal,prompt:'将输入数组中每项text的英文完整忠实翻译为中文。只返回JSON数组，每项恰含原样id与译文text，覆盖全部id且各一次。每项是独立段落，保留段内空行、顺序、Markdown和所有WIKI_KEEP_占位符，不合并项目，不摘要、不增删事实。feedback是上次被拒译文及诊断，仅供修订。\n\n'+JSON.stringify({items,...(feedback?{feedback}:{})})});
 return translate;
}
export async function buildChineseReading({vault,record,translate,python,signal,preparedModel}){
 await store({operation:'verify',vault,sourceId:record.id},{python,signal});
 const cache=join(vault,'.personal-wiki/readings',record.id);
 try{return JSON.parse(await readFile(join(cache,'result.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
 const original=await readFile(join(record.archive,'article.md'),'utf8');
 const content=[],pending=[],pendingByKey=new Map();
 // Extraction metadata stays in the immutable original, not in translated prose.
 const body=original.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/u,'');
 if(preparedModel)return store({operation:'reading',vault,sourceId:record.id,content:body,model:preparedModel},{python,signal});
 const planned=[];
 for(const group of units(body)){
  if(group.text!==undefined&&typeof translate.batch==='function'){
   const key=createHash('sha256').update('gpt-5.6-terra:v1:'+group.text).digest('hex');
   try{planned.push({literal:await readFile(join(cache,'units',key+'.md'),'utf8')});continue;}catch(error){if(error.code!=='ENOENT')throw error;}
   planned.push(...units(group.text,false));
  }else planned.push(group);
 }
 for(const unit of planned){
  signal?.throwIfAborted();
  if(unit.literal!==undefined){content.push(unit.literal);continue;}
  if(!needsTranslation(unit.text)){content.push(unit.text);continue;}
  const {masked,preserved}=protect(unit.text);
  const key=createHash('sha256').update('gpt-5.6-terra:v1:'+unit.text).digest('hex');
  try{content.push(await readFile(join(cache,'units',key+'.md'),'utf8'));continue;}catch(e){if(e.code!=='ENOENT')throw e;}
  const duplicate=pendingByKey.get(key);
  if(duplicate)duplicate.positions.push(content.length);
  else{const next={index:content.length,positions:[content.length],key,text:unit.text,masked,preserved};pending.push(next);pendingByKey.set(key,next);}
  content.push(null);
 }
 const rejection=key=>({operation:'reading-rejection',vault,sourceId:record.id,key});
 const feedbackFor=async key=>{const {feedback}=await store(rejection(key),{python,signal});return feedback?.maskVersion===maskVersion?feedback:undefined;};
 const reject=async(key,reason,previousOutput)=>store({...rejection(key),feedback:{maskVersion,reason,previousOutput}},{python,signal});
 const complete=async(unit,translated)=>{
  let restored;
  try{restored=restore(unit.text,translated,unit.preserved);}
  catch(error){await reject(unit.key,error.message,translated);throw error;}
  await store({operation:'reading-unit',vault,sourceId:record.id,key:unit.key,content:restored},{python,signal});for(const index of unit.positions)content[index]=restored;
 };
 if(typeof translate.batch==='function'){
  const batches=[];let batch=[],size=0;
  for(const unit of pending){if(batch.length&&size+unit.masked.length>4000){batches.push(batch);batch=[];size=0;}batch.push(unit);size+=unit.masked.length;}if(batch.length)batches.push(batch);
  for(const batch of batches){
   signal?.throwIfAborted();
   const key=createHash('sha256').update('batch:'+maskVersion+':'+batch.map(u=>u.key).join(',')).digest('hex');
   const items=[];for(const unit of batch)items.push({id:'part-'+unit.index,text:unit.masked,feedback:await feedbackFor(unit.key)});
   const raw=await translate.batch({items,feedback:await feedbackFor(key),signal});
   let results;
   try{
    results=typeof raw==='string'?JSON.parse(raw):raw;
    if(!Array.isArray(results)||results.length!==items.length||new Set(results.map(r=>r?.id)).size!==items.length||results.some(r=>!items.some(i=>i.id===r?.id)||typeof r?.text!=='string'))throw Error('Translation batch identities missing or duplicated');
   }catch(error){await reject(key,error.message,typeof raw==='string'?raw:JSON.stringify(raw));throw error;}
   let failure;
   for(const unit of batch){try{await complete(unit,results.find(r=>r.id==='part-'+unit.index).text);}catch(error){failure??=error;}}
   if(failure)throw failure;
  }
 }else{
  for(const unit of pending){signal?.throwIfAborted();await complete(unit,await translate({text:unit.masked,feedback:await feedbackFor(unit.key),signal}));}
 }
 return store({operation:'reading',vault,sourceId:record.id,content:content.join(''),model:'gpt-5.6-terra'},{python,signal});
}
