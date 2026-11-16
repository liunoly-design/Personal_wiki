import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,symlink} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createAdapters} from '../src/nashsu.js';

test('new English source gets a separate full Chinese reading with original code and links',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);
  const original='# Small experiment\n\nThe result applies only to this sample.\n\n```js\nconst n = 2;\nconst example = "[x](images/a.jpg)";\n```\n\n[Source](https://example.org/source)\n\n![图](<images/a.jpg> "图片")';
  await mkdir(join(snapshot,'images'));await writeFile(join(snapshot,'images/a.jpg'),'image');
  await writeFile(join(snapshot,'article.md'),original);
  const stages=[];
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>{assert.equal(stages.at(-1).stage,'translating');assert.equal(stages.find(s=>s.stage==='compiled').details.compilation.status,'complete');return text.replace('Small experiment','小型实验').replace('The result applies only to this sample.','结果仅适用于此次样本。').replace('Source','来源');},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/experiment.md---\n# 实验\n简短摘要。\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'experiment',context:'',url:'https://x.com/a/status/123',onStage:async(stage,details)=>{stages.push({stage,details});}});
  assert.equal(result.reading.status,'complete');
  const body=await readFile(result.reading.path,'utf8');assert.match(body,/# 小型实验/);assert.match(body,/结果仅适用于此次样本/);assert.match(body,/const n = 2;/);assert.match(body,/https:\/\/example.org\/source/);assert.match(body,/原文/);
  assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),original);
  assert.notEqual(result.reading.path,result.source);
  assert.ok(body.includes(`../raw/assets/${result.sourceId}/images/a.jpg`));
  assert.ok(body.includes('const example = "[x](images/a.jpg)";'));
 }finally{await rm(root,{recursive:true,force:true});}
});

test('indented code fences and longer closing fences preserve code bytes without translation',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-fence-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);
  const code='  ```js\n  console.log("Hello");\n  ````';await writeFile(join(snapshot,'article.md'),'# 代码示例\n\n'+code);
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async()=>assert.fail('code must not enter translation'),generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/example.md---\n# 来源\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'example',context:'',url:'https://x.com/a/status/123'});
  assert.equal(result.reading.status,'complete');assert.ok((await readFile(result.reading.path,'utf8')).includes(code));
 }finally{await rm(root,{recursive:true,force:true});}
});

test('dropped paragraphs or modified protected links leave reading pending, never replacing the original',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-invalid-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);const original='First paragraph.\n\nSecond paragraph with [evidence](https://example.org).';await writeFile(join(snapshot,'article.md'),original);
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async()=> '简短摘要。',generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/example.md---\n# 来源\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'example',context:'',url:'https://x.com/a/status/123'});
  assert.equal(result.status,'complete');assert.equal(result.reading.status,'pending');
  await assert.rejects(readFile(join(vault,'reading/example.zh.md')),{code:'ENOENT'});
  assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('translation failure keeps compiled knowledge; retry only translates unfinished units',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-retry-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'# First section\n\n```js\nconst n = 2;\n```\n\nSecond section.');
  let modelCalls=0,translations=0,fail=true;
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>{translations++;if(text.includes('Second')&&fail)throw Error('Codex quota unavailable; waiting for quota');return text.replace('First section','第一节').replace('Second section.','第二节。');},generate:async({stage})=>{modelCalls++;return stage==='analysis'?'分析':'---FILE: wiki/sources/example.md---\n# 来源\n---END FILE---';}});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'example',context:'',url:'https://x.com/a/status/123'});
  assert.equal(result.status,'complete');assert.equal(result.reading.status,'pending');assert.match(await readFile(result.source,'utf8'),/来源/);
  fail=false;const retry=await adapters.retryReading(result.sourceId);assert.equal(retry.status,'complete');assert.equal(modelCalls,2);assert.equal(translations,3);
  await adapters.retryReading(result.sourceId);assert.equal(translations,3);
  assert.match(await readFile(retry.path,'utf8'),/第二节/);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('rejected reading structure is explained on retry while original bytes remain protected',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-feedback-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);
  const original='# Checklist\n\n- Keep every item.';await writeFile(join(snapshot,'article.md'),original);let calls=0;
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,
   translate:async({text,feedback})=>{calls++;const translated=text.replace('Checklist','核对清单').replace('Keep every item.','保留每一项。');return feedback?translated:translated+'\n- extra';},
   generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/checklist.md---\n# 清单\n摘要。\n---END FILE---'
  });
  const first=await adapters.importAndCompile({capture:{directory:snapshot},slug:'checklist',url:'https://example.org/checklist'});assert.equal(first.reading.status,'pending');
  const recovered=await adapters.retryReading(first.sourceId);assert.equal(recovered.status,'complete');assert.match(await readFile(recovered.path,'utf8'),/- 保留每一项/);assert.equal(await readFile(join(first.archive,'article.md'),'utf8'),original);assert.equal(calls,2);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('reading rejection state cannot follow a directory symlink into an original attachment',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-symlink-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);
  const original='# Checklist\n\n- Keep every item.',attachment='{"original":"ATTACHMENT"}';
  const key=createHash('sha256').update('gpt-5.6-terra:v1:'+original).digest('hex');
  await writeFile(join(snapshot,'article.md'),original);await writeFile(join(snapshot,key+'.json'),attachment);
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=> text+'\n- extra',generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/checklist.md---\n# 清单\n摘要。\n---END FILE---'});
  const first=await adapters.importAndCompile({capture:{directory:snapshot},slug:'checklist',url:'https://example.org/checklist'});assert.equal(first.reading.status,'pending');
  const rejected=join(vault,'.personal-wiki/readings',first.sourceId,'rejected');await rm(rejected,{recursive:true,force:true});await symlink(first.archive,rejected,'dir');
  await assert.rejects(adapters.retryReading(first.sourceId));assert.equal(await readFile(join(first.archive,key+'.json'),'utf8'),attachment);assert.equal(await readFile(join(first.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('numeric Markdown prefixes in OCR prose survive natural-language translation verbatim',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-number-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);const original='2024. Large language models improved.';await writeFile(join(snapshot,'article.md'),original);
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>text.replace('2024.','2024年').replace('Large language models improved.','大语言模型取得了进步。'),generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/ocr-year.md---\n# 年份\n摘要。\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'ocr-year',url:'https://example.org/year'});assert.equal(result.reading.status,'complete');assert.match(await readFile(result.reading.path,'utf8'),/2024\. 大语言模型取得了进步/);assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('Chinese prose and signed links stay verbatim while a separate English OCR paragraph is translated',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-language-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);
  const chinese='中文正文应逐字保留，链接不是英文正文。[出处](https://example.org/'+('tracking-'.repeat(100))+')';const original=chinese+'\n\n### images/image-001.png\n\n2024. Large language models improved.';await writeFile(join(snapshot,'article.md'),original);
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>{assert.ok(!text.includes('中文正文'),'native prose must remain outside the translation request');assert.ok(!text.includes('images/image-001.png'),'asset identifiers are not prose');return text.replace('Large language models improved.','大语言模型取得了进步。');},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/mixed-language.md---\n# 混合资料\n摘要。\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'mixed-language',url:'https://example.org/mixed'});assert.equal(result.reading.status,'complete');const reading=await readFile(result.reading.path,'utf8');assert.ok(reading.includes('中文正文应逐字保留，链接不是英文正文。'));assert.match(reading,/2024\. 大语言模型取得了进步/);assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('an English heading about an images directory remains prose that needs translation',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-image-heading-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);const title='images/ stores all screenshots needed to reproduce the experiment';await writeFile(join(snapshot,'article.md'),'### '+title);let calls=0;
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>{calls++;return text.replace(title,'images/ 目录存放重现实验所需的全部截图');},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/image-heading.md---\n# 图片目录\n摘要。\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'image-heading',url:'https://example.org/image-heading'});assert.equal(result.reading.status,'complete');assert.equal(calls,1);assert.match(await readFile(result.reading.path,'utf8'),/### images\/ 目录存放重现实验所需的全部截图/);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('separated English fragments translate in one batch while retaining their own positions',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-batch-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);const original='中文开头保持原样。\n\nFirst fragment.\n\n中文中段保持原样。\n\nSecond fragment.';await writeFile(join(snapshot,'article.md'),original);let batches=0;
  const translate=async()=>assert.fail('batch-capable model must not receive one call per fragment');
  translate.batch=async({items})=>{batches++;assert.equal(items.length,2);return JSON.stringify(items.map(({id,text})=>({id,text:text.replace('First fragment.','第一段英文。').replace('Second fragment.','第二段英文。')})));};
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate,generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/batch-reading.md---\n# 批量阅读\n摘要。\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'batch-reading',url:'https://example.org/batch'});assert.equal(result.reading.status,'complete');assert.equal(batches,1);const reading=await readFile(result.reading.path,'utf8');assert.ok(reading.indexOf('第一段英文')<reading.indexOf('中文中段'));assert.ok(reading.indexOf('中文中段')<reading.indexOf('第二段英文'));assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('a batch rejects foreign identities and resumes only unfinished validated fragments',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-batch-retry-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);const original='First fragment.\n\n中文中段保持原样。\n\n# Second heading';await writeFile(join(snapshot,'article.md'),original);let attempt=0;const sizes=[];
  const translate=async()=>assert.fail('batch interface expected');
  translate.batch=async({items,feedback})=>{
   sizes.push(items.length);attempt++;
   if(attempt===1)return JSON.stringify(items.map((x,i)=>({id:i===0?'foreign-id':x.id,text:x.text})));
   if(attempt===2){assert.ok(feedback);return JSON.stringify(items.map((x,i)=>({id:x.id,text:x.text.replace('First fragment.','第一段。').replace('Second heading','第二节')+(i===1?'\n- extra':'')})));}
   assert.equal(items.length,1);assert.ok(items[0].feedback);return JSON.stringify(items.map(x=>({id:x.id,text:x.text.replace('Second heading','第二节')})));
  };
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate,generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/batch-retry.md---\n# 批量恢复\n摘要。\n---END FILE---'});
  const first=await adapters.importAndCompile({capture:{directory:snapshot},slug:'batch-retry',url:'https://example.org/batch-retry'});assert.equal(first.reading.status,'pending');
  await assert.rejects(adapters.retryReading(first.sourceId),/structure/);
  const done=await adapters.retryReading(first.sourceId);assert.equal(done.status,'complete');assert.deepEqual(sizes,[2,2,1]);const reading=await readFile(done.path,'utf8');assert.match(reading,/第一段/);assert.match(reading,/# 第二节/);assert.equal(await readFile(join(first.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('duplicate English fragments reuse one validated translation in both model interfaces',async()=>{
 for(const mode of ['single','batch']){
  const root=await mkdtemp(join(tmpdir(),'wiki-reading-dedup-'));
  try{
   const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'Repeated phrase.\n\n中文中段保持原样。\n\nRepeated phrase.');let calls=0;
   const translate=async()=>{calls++;return calls===1?'第一种完整译文。':'另一种完整译文。';};
   if(mode==='batch')translate.batch=async({items})=>{calls++;return JSON.stringify(items.map((x,i)=>({id:x.id,text:i===0?'第一种完整译文。':'另一种完整译文。'})));};
   const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate,generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/repeated-reading.md---\n# 重复片段\n摘要。\n---END FILE---'});
   const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'repeated-reading',url:'https://example.org/repeated'});assert.equal(result.reading.status,'complete',mode);assert.equal(calls,1);assert.equal((await readFile(result.reading.path,'utf8')).split('第一种完整译文。').length-1,2);
  }finally{await rm(root,{recursive:true,force:true});}
 }
});

test('batch translation gives consecutive source paragraphs separate identities',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-boundaries-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'First fragment.\n\nSecond fragment.');let received=0;
  const translate=async()=>assert.fail('batch interface expected');translate.batch=async({items})=>{received=items.length;return JSON.stringify(items.map(x=>({id:x.id,text:x.text.replace('First fragment.','第一段。').replace('Second fragment.','第二段。').replaceAll('\n\n',' ')})));};
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate,generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/paragraph-identities.md---\n# 段落\n摘要。\n---END FILE---'});
  const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'paragraph-identities',url:'https://example.org/paragraphs'});assert.equal(result.reading.status,'complete');assert.equal(received,2);assert.match(await readFile(result.reading.path,'utf8'),/第一段。\n\n第二段。/);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('enabling batch translation reuses successful legacy groups and translates only the failed tail',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-reading-upgrade-'));
 try{
  const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);const original='First fragment.\n\nSecond fragment.\n\n```js\nconst n = 2;\n```\n\nLast fragment.';await writeFile(join(snapshot,'article.md'),original);let calls=0;
  const translate=async({text})=>{calls++;if(text.includes('Last fragment.'))throw Error('Codex quota unavailable');return text.replace('First fragment.','第一段。').replace('Second fragment.','第二段。');};
  const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate,generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/upgraded-reading.md---\n# 升级恢复\n摘要。\n---END FILE---'});
  const first=await adapters.importAndCompile({capture:{directory:snapshot},slug:'upgraded-reading',url:'https://example.org/upgrade'});assert.equal(first.reading.status,'pending');assert.equal(calls,2);
  translate.batch=async({items})=>{calls++;assert.equal(items.length,1);assert.ok(items[0].text.includes('Last fragment.'));return JSON.stringify(items.map(x=>({id:x.id,text:x.text.replace('Last fragment.','最后一段。')})));};
  const done=await adapters.retryReading(first.sourceId);assert.equal(done.status,'complete');assert.equal(calls,3);assert.match(await readFile(done.path,'utf8'),/第一段。\n\n第二段。/);assert.match(await readFile(done.path,'utf8'),/最后一段/);assert.equal(await readFile(join(first.archive,'article.md'),'utf8'),original);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('long English article retains every section, table, image, link and code through Chinese reading',async()=>{
 const root=await mkdtemp(join(tmpdir(),'long-reading-'));
 try{const vault=join(root,'v'),snapshot=join(root,'s');await mkdir(vault);await mkdir(snapshot);await mkdir(join(snapshot,'images'));await writeFile(join(snapshot,'images/a.png'),'image');const paragraphs=Array.from({length:45},(_,i)=>`## Section ${i+1}\n\nThis paragraph preserves all evidence and limitations for sample ${i+1}. `+('The source describes an experiment with a bounded result. '.repeat(8)));const original=paragraphs.join('\n\n')+'\n\n| Label | Value |\n| --- | --- |\n| Sample | 45 |\n\n![Image](images/a.png)\n\n[Evidence](https://example.org/evidence)\n\n```python\nprint("unchanged")\n```\n\n## Final section\n\nFinal evidence remains.';await writeFile(join(snapshot,'article.md'),original);let translations=0;const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>{translations++;return text.replaceAll('Section','章节').replaceAll('This paragraph preserves all evidence and limitations for sample','本段保留该样本的所有证据和限制').replaceAll('The source describes an experiment with a bounded result.','来源描述的是具有适用范围限制的实验结果。').replace('Final section','最后一节').replace('Final evidence remains.','最后证据保留。');},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/long-article.md---\n# 长文\n摘要。\n---END FILE---'});const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'long-article',url:'https://example.org/long'});assert.equal(result.reading.status,'complete');const body=await readFile(result.reading.path,'utf8');for(let i=1;i<=45;i++)assert.ok(body.includes('## 章节 '+i));assert.match(body,/最后证据保留/);assert.match(body,/https:\/\/example.org\/evidence/);assert.match(body,/print\("unchanged"\)/);assert.match(body,/\| Sample \| 45 \|/);assert.ok(translations>5);assert.equal(await readFile(join(result.archive,'article.md'),'utf8'),original);}finally{await rm(root,{recursive:true,force:true});}
});
test('quoted code fences from public blogs remain byte-identical and never enter translation',async()=>{
 const root=await mkdtemp(join(tmpdir(),'quoted-code-'));const code='> ```python\n> # English comment\n> print("hello")\n> ```';
 try{const vault=join(root,'v'),snapshot=join(root,'s');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'# Example\n\n'+code+'\n\nFinal paragraph.');const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>{assert.ok(!text.includes('English comment'));return text.replace('Example','示例').replace('Final paragraph.','最后一段。');},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/quoted-code.md---\n# 来源\n摘要。\n---END FILE---'});const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'quoted-code',url:'https://example.org/code'});assert.equal(result.reading.status,'complete');assert.ok((await readFile(result.reading.path,'utf8')).includes(code));}finally{await rm(root,{recursive:true,force:true});}
});
test('quoted fence syntax inside a normal code block cannot close the outer fence',async()=>{
 const root=await mkdtemp(join(tmpdir(),'nested-quote-code-'));const code='```markdown\n> ```\n> English literal code\n> ```\n```';
 try{const vault=join(root,'v'),snapshot=join(root,'s');await mkdir(vault);await mkdir(snapshot);await writeFile(join(snapshot,'article.md'),'# Example\n\n'+code);const adapters=createAdapters({vault,python:'python3',captureDirectory:root,flash:{},reading:true,translate:async({text})=>{assert.ok(!text.includes('English literal code'));return text.replace('Example','示例');},generate:async({stage})=>stage==='analysis'?'分析':'---FILE: wiki/sources/nested-code.md---\n# 来源\n摘要。\n---END FILE---'});const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'nested-code',url:'https://example.org/code'});assert.equal(result.reading.status,'complete');assert.ok((await readFile(result.reading.path,'utf8')).includes(code));}finally{await rm(root,{recursive:true,force:true});}
});
