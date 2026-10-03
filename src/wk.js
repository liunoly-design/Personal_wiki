import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export function parseCommand(text) {
 if(typeof text!=='string')return null;
 if(/^小婕\s*wk\s+保存\s*[：:]?\s*$/u.test(text))return {action:'reply',mode:'save'};
 const discussion=text.match(/^小婕\s*wk\s+(讨论|新讨论|结束讨论|保存结论|综合)\s*[：:]\s*([\s\S]*)$/u);
 if(discussion){
  const [,command,body]=discussion;if(body.length>3000)return {action:'invalid'};
  if(['结束讨论','保存结论','综合'].includes(command)){
   const m=body.match(/^(D-[a-f0-9]{16})(?:[ \t]+([^\n]{1,120}))?\s*$/u);
   return m&&(command==='综合'||!m[2])?{action:'discuss',mode:{结束讨论:'end',保存结论:'save',综合:'synthesis'}[command],id:m[1],title:m[2]??''}:{action:'invalid'};
  }
  let id;let remainder=body.trim();const m=remainder.match(/^(D-[a-f0-9]{16})\s+([\s\S]+)$/u);if(m){id=m[1];remainder=m[2];}
  if(command==='新讨论'&&id)return {action:'invalid'};
  const questions=[];let judgment='',sources=[];
  for(const line of remainder.split('\n')){
   if(/^用户判断[：:]/u.test(line)){judgment+=(judgment?'\n':'')+line.replace(/^用户判断[：:]\s*/u,'');}
   else if(/^来源[：:]/u.test(line)){
    for(const v of line.replace(/^来源[：:]\s*/u,'').split(/[,，]/u)){const r=v.trim().match(/^(K-[a-f0-9]{16})(?:\s+([1-9][0-9]{0,6}))?$/u);if(!r)return {action:'invalid'};sources.push({id:r[1],start:Number(r[2]??1)});}
   }else questions.push(line);
  }
  const question=questions.join('\n').trim();return question&&question.length<=2000&&judgment.length<=1000&&sources.length<=5?{action:'discuss',mode:command==='新讨论'?'new':'turn',question,id,sources,judgment}:{action:'invalid'};
 }
 if(/^小婕\s*wk\s+(讨论|新讨论|结束讨论|保存结论|综合)/u.test(text))return {action:'invalid'};
 const knowledge=text.match(/^小婕\s*wk\s+(查询|阅读|待审|应用|跳过|稍后)\s*[：:]\s*([\s\S]*)$/u);
 if(knowledge){
  const [,mode,body]=knowledge;
  if(mode==='查询'){
   const lines=body.trim().split('\n');let topic='',aliases=[];const question=[];
   for(const line of lines){if(/^主题[：:]/u.test(line)){topic=line.replace(/^主题[：:]\s*/u,'').trim();}else if(/^别名[：:]/u.test(line)){aliases=line.replace(/^别名[：:]\s*/u,'').split(/[,，、]/u).map(x=>x.trim()).filter(Boolean);}else question.push(line);}
   if(!question.join('\n').trim()||body.length>2500||topic.length>100||aliases.length>3||aliases.some(a=>a.length>100))return{action:'invalid'};
   return {action:'query',question:question.join('\n').trim(),aliases,topic};
  }
  if(mode==='阅读'){const m=body.match(/^(K-[a-f0-9]{16})(?:\s+([1-9][0-9]{0,6}))?\s*$/u);return m?{action:'read',id:m[1],start:Number(m[2]??1)}:{action:'invalid'};}
  if(mode==='待审'){const m=body.match(/^(?:(R-[a-f0-9]{16})|([1-9][0-9]{0,6}))?\s*$/u);return m?(m[1]?{action:'review',mode:'detail',id:m[1]}:{action:'review',mode:'list',start:Number(m[2]??1)}):{action:'invalid'};}
  const m=body.match(/^(R-[a-f0-9]{16})\s*$/u);return m?{action:'review',mode,id:m[1]}:{action:'invalid'};
 }
 if(/^小婕\s*wk\s+(查询|阅读|待审|应用|跳过|稍后)/u.test(text))return{action:'invalid'};

 const control=text.match(/^小婕\s*wk\s+(状态|继续|登录继续|补附件|确认视频)\s*[：:]\s*([a-f0-9]{64})(?:\s+([a-f0-9]{16}))?(?:\s+([a-f0-9]{64}))?\s*$/u);
 if(control){const [,mode,jobId,assetId,fingerprint]=control;if((['补附件','确认视频'].includes(mode)!==Boolean(assetId))||(mode==='确认视频')!==Boolean(fingerprint))return{action:'invalid'};return{action:'control',mode,jobId,assetId,fingerprint};}
 if(/^小婕\s*wk\s+(状态|继续|登录继续|补附件|确认视频)/u.test(text))return{action:'invalid'};
 const match=text.match(/^小婕[ \t]*(?:(?:wk[ \t]+(记录|查询|讨论))|(重新收集|收集))([ \t]*[：:]|[ \t]|(?=\n|https?:\/\/|$))([\s\S]*)$/iu);
 if(!match)return /^小婕\s+wk(?:\s|[：:])/iu.test(text)?{action:'invalid'}:null;
 if(match[1]==='讨论')return {action:'reserved',mode:match[1]};
 let body=match[4],refresh=match[2]==='重新收集';
 if(/^重新收集\s*[：:]?/u.test(body)){refresh=true;body=body.replace(/^重新收集\s*[：:]?\s*/u,'');}
 const split=body.match(/(?:^|\n)\s*(?:备注|背景|个人备注|个人背景)\s*[：:]([\s\S]*)$/u);
 let background=split?.[1].trim()??'';
 if(split)body=body.slice(0,split.index);
 const urls=[...body.matchAll(/https?:\/\/[^\s<>，。；]+/gu)].map(m=>m[0]);
 if(urls.length){
  const items=urls.map(url=>{try{const u=new URL(url);if(u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443'))throw Error();return {url};}catch{return {inputError:'Unsupported source URL'};}});
  const extra=body.replace(/https?:\/\/[^\s<>，。；]+/gu,'').replace(/^[\s：:,，;；]+|[\s：:,，;；]+$/gu,'');
  background=[extra,background].filter(Boolean).join('\n');
  if(urls.length===1&&items[0].url&&!background&&!refresh)return {action:'record',url:urls[0]};
  return {action:'record',url:items[0].url,items,background,refresh};
 }
 if(!body.trim())return {action:'invalid'};
 return {action:'record',items:[{text:body}],background,refresh};
}
export const validSlug=s=>typeof s==='string'&&s.length<=100&&/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/u.test(s);
export async function recordArticle({url,vault,signal,sourceContext='',onStage=async()=>{}},deps){
 signal?.throwIfAborted();
 const existing=await deps.lookupExisting?.(url,signal);
 if(existing)return {...existing,terms:0,newDefinitions:0,attachmentStatus:"previous_archive"};
 const capture=await deps.capture(url,signal);
 await onStage('captured',{captureDirectory:capture.directory});
 const analysis=await deps.extract(capture.text,signal);
 if(!validSlug(analysis.slug)||!Array.isArray(analysis.terms)||analysis.terms.length>60)throw Error('Invalid Flash term extraction');
 const terms=[];const seen=new Set();
 for(const term of analysis.terms){
  if(!validSlug(term.slug)||typeof term.name!=='string'||!term.name.trim()||term.name.length>150)throw Error('Invalid term');
  if(term.domain!==undefined&&(typeof term.domain!=='string'||term.domain.length>150))throw Error('Invalid term domain');
  if(!seen.has(term.slug)){seen.add(term.slug);terms.push({name:term.name,slug:term.slug,...(term.domain?{domain:term.domain}:{})});}
 }
 const dir=join(vault,'glossary');await mkdir(dir,{recursive:true});
 const missing=[];
 for(const term of terms){try{await readFile(join(dir,term.slug+'.md'));}catch(e){if(e.code!=='ENOENT')throw e;missing.push(term);}}
 if(missing.length){
  // The explanation call sees only names, not the article, so foundations do
  // not silently turn the author's opinion into a general definition.
  const definitions=await deps.explain(missing,signal);
  if(!Array.isArray(definitions)||definitions.length!==missing.length)throw Error('Incomplete Flash explanations');
  for(const term of missing){
   const values=definitions.filter(d=>d.slug===term.slug);if(values.length!==1)throw Error('Missing or duplicate definition');
   const d=values[0];
   if(!['definition','example','uncertainty'].every(k=>typeof d[k]==='string'&&d[k].length<=12000)||!d.definition.trim())throw Error('Invalid definition');
   const text=`---\ntype: glossary\ntitle: ${JSON.stringify(term.name)}\ngenerated_by: Gemini Flash\nbasis: model-general-knowledge\nverified: false\n---\n# ${term.name.replaceAll('\n',' ')}\n\n## 基础解释\n\n${d.definition}\n\n## 简单例子\n\n${d.example}\n\n## 歧义与不确定性\n\n${d.uncertainty}\n\n> 基础解释由模型生成，未经独立核实；不是文章原文或作者观点。\n`;
   try{await writeFile(join(dir,term.slug+'.md'),text,{flag:'wx'});}catch(e){if(e.code!=='EEXIST')throw e;}
  }
 }
 await onStage('glossary_saved',{terms:terms.map(t=>t.slug),newDefinitions:missing.length});
 signal?.throwIfAborted();
 const foundations=await Promise.all(terms.map(async t=>`### ${t.name}\n[基础解释](../../glossary/${t.slug}.md)\n\n${await readFile(join(dir,t.slug+'.md'),'utf8')}`));
 const context=sourceContext+'\n以下基础解释已先行保存，为模型生成的通用知识，不代表作者观点。请在文章的概念/实体页引用对应基础页，另写本文用法、来源证据和关系；不要改写基础页。\n'+foundations.join('\n\n');
 const result=await deps.importAndCompile({capture,slug:analysis.slug,context,url,signal,onStage});
 await onStage(result.status,{source:result.source});
 return {...result,newDefinitions:missing.length,terms:terms.length,attachmentStatus:capture.status??'complete'};
}
