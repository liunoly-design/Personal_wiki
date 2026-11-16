import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,realpath,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {openIngestion} from '../src/ingestion.js';
const exec=promisify(execFile);

test('a screenshot supplements a pending source with real local OCR and preserves the original image',{skip:process.platform!=='darwin'},async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-image-')));
 try{
  const image=join(root,'input.png');
  await exec('/usr/bin/swift',['-e',`import AppKit
let image = NSImage(size: NSSize(width:1000,height:180)); image.lockFocus()
NSColor.white.setFill(); NSRect(x:0,y:0,width:1000,height:180).fill()
NSAttributedString(string:"WIKI OCR CHECK 7391",attributes:[.font:NSFont.systemFont(ofSize:52),.foregroundColor:NSColor.black]).draw(at:NSPoint(x:30,y:60))
image.unlockFocus()
try NSBitmapImageRep(data:image.tiffRepresentation!)!.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:${JSON.stringify(image)}))`],{timeout:120000});
  const partial=join(root,'partial');await mkdir(partial);await writeFile(join(partial,'article.md'),'未取得全文');
  const service=await openIngestion({stateDir:join(root,'state'),python:'/usr/bin/python3'},{capture:async()=>({directory:partial,status:'partial'})});
  const job=await service.submit({input:'https://mp.weixin.qq.com/s/synthetic-ocr',mode:'convert'});await service.run(job.id);
  await service.supplement(job.id,{file:image});const done=await service.run(job.id);
  assert.equal(done.status,'converted');assert.match(await readFile(done.bundle.markdown,'utf8'),/WIKI OCR CHECK 7391/);
  assert.deepEqual(await readFile(join(done.bundle.directory,'supplement-image.png')),await readFile(image));
 }finally{await rm(root,{recursive:true,force:true});}
});
