import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {openIngestion} from '../src/ingestion.js';
test('local media is frozen at submission and changed paths cannot replace a queued original',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-file-')));
 try{
  const file=join(root,'voice.wav');await writeFile(file,'synthetic audio input');
  const service=await openIngestion({stateDir:join(root,'state'),python:'/usr/bin/python3'});
  const job=await service.submit({file,mode:'convert'});
  assert.equal(job.platform,'file');assert.match(job.url,/^https:\/\/file.personal-wiki.invalid\/[a-f0-9]{64}$/);
  await writeFile(file,'changed input');
  assert.equal(await readFile(job.mediaFile.file,'utf8'),'synthetic audio input');
  assert.notEqual((await service.submit({file,mode:'convert'})).id,job.id);
  await assert.rejects(service.submit({file,text:'ambiguous'}),/one input/i);
 }finally{await rm(root,{recursive:true,force:true});}
});
