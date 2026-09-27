import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';import {join} from 'node:path';import {tmpdir} from 'node:os';
import {refreshTerms} from '../src/term-refresh.js';
test('regeneration defines entities directly and preserves article evidence, handwritten content and raw bytes',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wiki-terms-'));
 try{
  for(const d of ['glossary','wiki/entities','raw'])await mkdir(join(root,d),{recursive:true});
  await writeFile(join(root,'glossary/canvas.md'),'---\ntype: glossary\ntitle: Canvas\n---\n# Canvas\n\n## 基础解释\n\nOld weak explanation\n\n## 简单例子\n\nOld example\n\n## 我的笔记\n\n保留这段手写内容\n');
  await writeFile(join(root,'wiki/entities/canvas.md'),'---\ntype: entity\ntitle: Canvas\n---\n# Canvas\n\n作者用它绘图。[来源](../sources/example.md)\n');
  await writeFile(join(root,'raw/original.md'),'untouched');
  const result=await refreshTerms({vault:root,python:'python3',explain:async terms=>terms.map(t=>({...t,definition:'Canvas 是浏览器中用于通过脚本绘图的 HTML 元素。',example:'在网页上画圆。',uncertainty:'与同名产品应按语境区分。'}))});
  assert.equal(result.updated,2);
  const entity=await readFile(join(root,'wiki/entities/canvas.md'),'utf8');assert.match(entity,/## 是什么/);assert.match(entity,/HTML 元素/);assert.match(entity,/作者用它绘图/);assert.match(entity,/sources\/example.md/);
  const glossary=await readFile(join(root,'glossary/canvas.md'),'utf8');assert.match(glossary,/保留这段手写内容/);assert.doesNotMatch(glossary,/Old weak explanation/);
  assert.equal(await readFile(join(root,'raw/original.md'),'utf8'),'untouched');assert.ok(result.backup);
 }finally{await rm(root,{recursive:true,force:true});}
});
