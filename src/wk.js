import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export function parseCommand(text) {
 if(typeof text!=='string'||!/^小婕\s+wk(?:\s|[：:])/iu.test(text))return null;
 const match=text.match(/^小婕\s+wk\s+(记录|查询|讨论)\s*[：:]\s*([\s\S]*)$/iu);
 if(!match)return {action:'invalid'};
 if(match[1]!=='记录')return {action:'reserved',mode:match[1]};
 const url=match[2].trim();
 try{const u=new URL(url);if(/\s/u.test(url)||u.protocol!=='https:'||u.username||u.password||u.port)throw Error();
 if(!((u.hostname==='x.com'||u.hostname==='twitter.com')&&/^\/[^/]+\/status\/\d+\/?$/u.test(u.pathname))&&!(u.hostname==='mp.weixin.qq.com'&&u.pathname.startsWith('/s')))throw Error();
 return {action:'record',url};}catch{return {action:'invalid'};}
}
export const validSlug=s=>typeof s==='string'&&s.length<=100&&/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/u.test(s);
export async function recordArticle({url,vault,signal,onStage=async()=>{}},deps){
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
 const context='以下基础解释已先行保存，为模型生成的通用知识，不代表作者观点。请在文章的概念/实体页引用对应基础页，另写本文用法、来源证据和关系；不要改写基础页。\n'+foundations.join('\n\n');
 const result=await deps.importAndCompile({capture,slug:analysis.slug,context,url,signal});
 await onStage(result.status,{source:result.source});
 return {...result,newDefinitions:missing.length,terms:terms.length,attachmentStatus:capture.status??'complete'};
}
