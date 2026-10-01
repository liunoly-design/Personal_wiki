import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {store} from './protected-compiler.js';
import {createCodex} from './codex.js';

function units(markdown){
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
   while(result[i+1]?.literal!==undefined&&!result[i+1].literal.trim()&&result[i+2]?.text!==undefined&&unit.text.length+result[i+1].literal.length+result[i+2].text.length<=4000){unit.text+=result[i+1].literal+result[i+2].text;i+=2;}
  }
  grouped.push(unit);
 }
 return grouped;
}
function protect(text){
 const prefix='WIKI_KEEP_'+createHash('sha256').update(text).digest('hex').slice(0,10)+'_';
 const preserved=[];
 const masked=text.replace(/`[^`\n]+`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$|(?<=\]\()<?[^\s)]+>?|https?:\/\/[^\s<>]+/gu,value=>{const token=prefix+preserved.length.toString().padStart(4,'0');preserved.push({token,value});return token;});
 return {masked,preserved};
}
function restore(source,translated,preserved){
 if(typeof translated!=='string'||!translated.trim())throw Error('Incomplete Chinese reading');
 const sourceBlocks=source.trim().split(/\n[ \t]*\n/u).length;
 if(translated.trim().split(/\n[ \t]*\n/u).length!==sourceBlocks)throw Error('Chinese reading omitted or rearranged paragraphs');
 const sourceProse=preserved.reduce((text,p)=>text.replace(p.value,''),source);
 const translatedProse=preserved.reduce((text,p)=>text.replace(p.token,''),translated);
 if(sourceProse.length>160&&translatedProse.length<sourceProse.length*0.15)throw Error('Chinese reading appears truncated; requires review');
 for(const {token,value} of preserved){if(translated.split(token).length!==2)throw Error('Chinese reading changed a protected reference');translated=translated.replace(token,value);}
 for(const pattern of [/^#{1,6} /gmu,/^\s*(?:[-*+] |\d+[.)] )/gmu,/\|/gu,/!\[/gu]){
  if([...source.matchAll(pattern)].length!==[...translated.matchAll(pattern)].length)throw Error('Chinese reading structure differs; requires review');
 }
 return translated;
}
export function codexTranslator(binary){
 const generate=createCodex({binary,model:'gpt-5.6-terra'});
 return async({text,signal})=>generate({signal,prompt:'把下面 Markdown 的所有英文正文完整翻译为中文。忠实保留每个事实、限定条件、句子顺序、标题级别、列表、表格及引文；不得摘要、扩写、删减或加解释。WIKI_KEEP_ 开头的占位符必须逐字保留且各出现一次。只输出译文 Markdown，不加外围代码围栏。\n\n'+text});
}
export async function buildChineseReading({vault,record,translate,python,signal}){
 await store({operation:'verify',vault,sourceId:record.id},{python,signal});
 const cache=join(vault,'.personal-wiki/readings',record.id);
 try{return JSON.parse(await readFile(join(cache,'result.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
 const original=await readFile(join(record.archive,'article.md'),'utf8');
 const content=[];
 // Extraction metadata stays in the immutable original, not in translated prose.
 const body=original.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/u,'');
 for(const unit of units(body)){
  signal?.throwIfAborted();
  if(unit.literal!==undefined){content.push(unit.literal);continue;}
  const latin=(unit.text.match(/[A-Za-z]/gu)??[]).length,han=(unit.text.match(/\p{Script=Han}/gu)??[]).length;
  if(latin===0||han>latin){content.push(unit.text);continue;}
  const {masked,preserved}=protect(unit.text);
  const key=createHash('sha256').update('gpt-5.6-terra:v1:'+unit.text).digest('hex');
  try{content.push(await readFile(join(cache,'units',key+'.md'),'utf8'));continue;}catch(e){if(e.code!=='ENOENT')throw e;}
  const translated=await translate({text:masked,signal});
  const restored=restore(unit.text,translated,preserved);
  await store({operation:'reading-unit',vault,sourceId:record.id,key,content:restored},{python,signal});
  content.push(restored);
 }
 return store({operation:'reading',vault,sourceId:record.id,content:content.join(''),model:'gpt-5.6-terra'},{python,signal});
}
