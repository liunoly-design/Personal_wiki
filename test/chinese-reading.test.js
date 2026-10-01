import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
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
