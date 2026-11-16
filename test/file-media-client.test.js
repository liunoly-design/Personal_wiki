import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {mkdtemp,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {FileMediaClient} from '../src/file-media-client.js';
import {openIngestion} from '../src/ingestion.js';
const hash=x=>createHash('sha256').update(x).digest('hex');
async function fixture(){
 let input,manifest,submits=0,state='waiting_upload',uploads=0;const jobId='a'.repeat(32),markdown='# 音频\n\n## 完整中文正文\n\n[00:00:00.000 → 00:00:12.000] 完整中文正文和最后一句都需要保留。\n\n## 完整原始转写\n\n[00:00:00.000 → 00:00:12.000] 完整中文正文和最后一句都需要保留。\n';
 const server=createServer(async(req,res)=>{
  assert.equal(req.headers.authorization,'Bearer synthetic-secret');let chunks=[];for await(const b of req)chunks.push(b);const bytes=Buffer.concat(chunks);
  const json=data=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({api_version:'1',...data}));};
  if(req.url==='/v1/file-jobs'){submits++;input=JSON.parse(bytes);manifest={api_version:'1',kind:'file',job_id:jobId,input,duration_seconds:12,transcription:{engine:'whisper.cpp',model:'synthetic-medium',model_sha256:'b'.repeat(64),language:'zh'},verification:{input_sha256:input.file.sha256,original:{full_decode:true,duration_seconds:12},audio:{full_decode:true,duration_seconds:12},source_binding:'client_acquisition_claim'},coverage:{head_tail_verified:true,first_start:0,last_end:12,segments:1},segments:[{start:0,end:12,text:'完整中文正文和最后一句都需要保留。'}],markdown:{sha256:hash(markdown)},media:Object.fromEntries(['original','audio'].map(k=>[k,{path:`/v1/file-media/${jobId}/${k}`,sha256:input.file.sha256,bytes:input.file.bytes,mime:'audio/wav'}]))};json({job_id:jobId,status:state,reused:submits>1});}
  else if(req.method==='PUT'){uploads++;assert.equal(hash(bytes),input.file.sha256);assert.equal(bytes.length,input.file.bytes);state='succeeded';json({job_id:jobId,status:state});}
  else if(req.url===`/v1/jobs/${jobId}`)json({job_id:jobId,status:state});
  else if(req.url.endsWith('/manifest'))json(manifest);
  else if(req.url.endsWith('/markdown')){res.setHeader('Content-Type','text/markdown');res.end(markdown);}
  else if(req.url.startsWith('/v1/file-media/')){const [,start,end]=req.headers.range.match(/bytes=(\d+)-(\d+)/);res.statusCode=206;res.setHeader('Content-Range',`bytes ${start}-${end}/${input.file.bytes}`);res.end(Buffer.alloc(Number(end)-Number(start)+1));}
  else{res.statusCode=404;res.end();}
 });await new Promise(r=>server.listen(0,'127.0.0.1',r));
 return {url:`http://127.0.0.1:${server.address().port}`,jobId,get input(){return input;},get manifest(){return manifest;},get submits(){return submits;},get uploads(){return uploads;},close:()=>new Promise(r=>server.close(r))};
}
test('real upload and durable CLI workflow reuse the original job, freeze transcript and protect the file',async()=>{
 const root=await realpath(await mkdtemp(join(tmpdir(),'wiki-media-http-'))),f=await fixture();
 try{
  const file=join(root,'voice.wav'),token=join(root,'token');await writeFile(file,'synthetic audio bytes');await writeFile(token,'synthetic-secret',{mode:0o600});
  const config={stateDir:join(root,'state'),python:'/usr/bin/python3',mediaServiceUrl:f.url,mediaServiceTokenFile:token};let service=await openIngestion(config);
  const job=await service.submit({file,mode:'convert'}),done=await service.run(job.id);assert.equal(done.status,'converted',done.failure);assert.match(await readFile(done.bundle.markdown,'utf8'),/最后一句/);
  service=await openIngestion(config);assert.equal((await service.run(job.id)).status,'converted');assert.equal(f.submits,1);assert.equal(f.uploads,1);assert.equal(await readFile(file,'utf8'),'synthetic audio bytes');
  const client=new FileMediaClient({baseUrl:f.url,token:'synthetic-secret'});
  f.manifest.input={...f.input,source:{...f.input.source,id:'wrong'}};await assert.rejects(client.fileResult(f.jobId,f.input),/binding/);f.manifest.input=f.input;
  f.manifest.segments[0].end=1;await assert.rejects(client.fileResult(f.jobId,f.input),/head\/tail/);f.manifest.segments[0].end=12;
  f.manifest.media.audio.path='/v1/file-media/'+'c'.repeat(32)+'/audio';await assert.rejects(client.fileResult(f.jobId,f.input),/metadata/);
 }finally{await f.close();await rm(root,{recursive:true,force:true});}
});
