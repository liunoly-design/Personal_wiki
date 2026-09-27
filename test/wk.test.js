import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {parseCommand,recordArticle} from '../src/wk.js';

test('only record executes; query/discuss remain reserved',()=>{
 assert.equal(parseCommand('hello'),null);
 assert.deepEqual(parseCommand('小婕 wk 记录：https://x.com/a/status/123'),{action:'record',url:'https://x.com/a/status/123'});
 assert.equal(parseCommand('小婕 wk 查询：Canvas').action,'reserved');
 assert.equal(parseCommand('小婕 wk 讨论：视频制作').action,'reserved');
 assert.equal(parseCommand('小婕 wk 记录：https://x.com/a/status/1 https://x.com/a/status/2').action,'invalid');
});
test('basic Flash explanations are saved before article compilation; basics do not receive article body',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wk-test-'));const events=[];
 try{
 const result=await recordArticle({url:'https://x.com/a/status/123',vault:root}, {
 capture:async()=>({directory:'/fixture',text:'Article-only detail',status:'complete'}),
 extract:async text=>{assert.match(text,/Article-only/);return {slug:'canvas-animation',terms:[{name:'Canvas',slug:'canvas'}]};},
 explain:async terms=>{events.push('explain');assert.deepEqual(terms,[{name:'Canvas',slug:'canvas'}]);return [{name:'Canvas',slug:'canvas',definition:'浏览器绘图接口。',example:'绘制一个圆。',uncertainty:'无'}];},
 importAndCompile:async ({context})=>{events.push('compile');assert.match(await readFile(join(root,'glossary/canvas.md'),'utf8'),/浏览器绘图接口/);assert.match(context,/glossary\/canvas.md/);return {source:'wiki/sources/canvas-animation.md',status:'complete'};},
 });
 assert.equal(result.status,'complete');assert.deepEqual(events,['explain','compile']);
 }finally{await rm(root,{recursive:true,force:true});}
});
test('Flash failure retains capture and never starts article compilation',async()=>{
 const root=await mkdtemp(join(tmpdir(),'wk-test-'));let compiled=false;
 try{await assert.rejects(recordArticle({url:'https://x.com/a/status/123',vault:root},{capture:async()=>({directory:'/retained-capture',text:'text'}),extract:async()=>({slug:'sample',terms:[{name:'Term',slug:'term'}]}),explain:async()=>{throw Error('Flash unavailable');},importAndCompile:async()=>{compiled=true;}}),/Flash unavailable/);assert.equal(compiled,false);}finally{await rm(root,{recursive:true,force:true});}
});

test('existing URL returns before capture or paid Flash calls',async()=>{
 const result=await recordArticle({url:'https://x.com/a/status/1',vault:'/unused'},{lookupExisting:async()=>({status:'existing',source:'saved.md'}),capture:async()=>assert.fail('must not recapture'),extract:async()=>assert.fail('must not call Flash')});
 assert.equal(result.status,'existing');assert.equal(result.newDefinitions,0);
});
