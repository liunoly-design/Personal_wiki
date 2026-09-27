import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';import {join} from 'node:path';import {tmpdir} from 'node:os';
import {refreshTerms} from '../src/term-refresh.js';
test('regeneration defines entities directly and preserves article evidence, handwritten content and raw bytes',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-terms-'));
 try{
  for(const d of ['glossary','wiki/entities','raw'])await mkdir(join(root,d),{recursive:true});
  await writeFile(join(root,'glossary/canvas.md'),'---\ntype: glossary\ntitle: Canvas\n---\n# Canvas\n\n## 基础解释\n\nOld weak explanation\n<!-- preserve --> 手写保留块 <!-- /preserve -->\n\n## 简单例子\n\nOld example\n\n## 我的笔记\n\n保留这段手写内容\n');
  await writeFile(join(root,'wiki/entities/canvas.md'),'---\ntype: entity\ntitle: Canvas\n---\n# Canvas\n\n作者用它绘图。[来源](../sources/example.md)\n');
  await writeFile(join(root,'raw/original.md'),'untouched');
  const result=await refreshTerms({vault:root,python:'python3',explain:async terms=>terms.map(t=>({...t,definition:'Canvas 是浏览器中用于通过脚本绘图的 HTML 元素。',example:'在网页上画圆。',uncertainty:'与同名产品应按语境区分。'}))});
  assert.equal(result.updated,2);
  const entity=await readFile(join(root,'wiki/entities/canvas.md'),'utf8');assert.match(entity,/## 是什么/);assert.match(entity,/HTML 元素/);assert.match(entity,/作者用它绘图/);assert.match(entity,/sources\/example.md/);
  const glossary=await readFile(join(root,'glossary/canvas.md'),'utf8');assert.match(glossary,/保留这段手写内容/);assert.match(glossary,/手写保留块/);assert.ok(glossary.indexOf("HTML 元素")<glossary.indexOf("Old weak explanation"));
  assert.equal(await readFile(join(root,'raw/original.md'),'utf8'),'untouched');assert.ok(result.backup);
 }finally{await rm(root,{recursive:true,force:true});}
});

test('public resume command restores a page after interruption between move and publication',async()=>{
 const {rename}=await import('node:fs/promises');const {execFileSync}=await import('node:child_process');
 const vault=await mkdtemp(join(tmpdir(),'wiki-refresh-resume-'));
 try{
  await mkdir(join(vault,'glossary'));await writeFile(join(vault,'glossary/a.md'),'# A\n\nOriginal handwritten note.');
  const plan=await refreshTerms({vault,python:'python3',prepareOnly:true,explain:async ts=>ts.map(t=>({...t,definition:'基础定义',example:'例子',uncertainty:'待核实'}))});
  const displaced=join(vault,'.personal-wiki/term-refresh',plan.runId,'displaced/glossary');await mkdir(displaced,{recursive:true});
  await rename(join(vault,'glossary/a.md'),join(displaced,'a.md'));
  const args=['scripts/refresh-terms.js',vault,'--resume-plan',plan.plan];
  const result=JSON.parse(execFileSync(process.execPath,args,{encoding:'utf8'}));assert.equal(result.updated,1);assert.deepEqual(result.conflicts,[]);
  const body=await readFile(join(vault,'glossary/a.md'),'utf8');assert.match(body,/基础定义/);assert.match(body,/Original handwritten note/);
  execFileSync(process.execPath,args);assert.equal(await readFile(join(vault,'glossary/a.md'),'utf8'),body);
 }finally{await rm(vault,{recursive:true,force:true});}
});
