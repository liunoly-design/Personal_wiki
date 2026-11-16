import transcriptPolicy from '../services/mini-media/transcript-identifiers.json' with {type:'json'};
import {isDeepStrictEqual} from 'node:util';
import {MediaServiceClient} from './media-service-client.js';
import {open} from 'node:fs/promises';
import {constants} from 'node:fs';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
const identifiers=transcriptPolicy.identifiers;
const hash=value=>createHash('sha256').update(value).digest('hex');
const id=value=>{if(!/^[a-f0-9]{32}$/u.test(value??''))throw Error('Invalid file job ID');return value;};
const finite=x=>Number.isFinite(x)&&x>0;
function preservedToken(kept,segment,index){
 if(kept.index!==index||typeof kept.source_text!=='string'||kept.target_text!==segment.text||kept.start!==segment.start||kept.end!==segment.end)return false;
 return identifiers.includes(kept.token)||kept.kind==='pronunciation'&&[...kept.source_text.matchAll(new RegExp(transcriptPolicy.pronunciation,'gu'))].some(m=>m[1]===kept.token);
}
export class FileMediaClient extends MediaServiceClient{
 async submitFile(input,{idempotencyKey}={}){
  let data;try{data=await this.json('/v1/file-jobs',{method:'POST',body:input,headers:{'Idempotency-Key':idempotencyKey??hash(JSON.stringify(input))}});}catch(error){if(error.message==='Media service HTTP 404')throw Error('Mini generic media interface not configured');throw error;}id(data.job_id);
  if(!['waiting_upload','queued','downloading','extracting','transcribing','succeeded','failed','partial_failed','waiting_confirmation'].includes(data.status))throw Error('Invalid file submission state');return data;
 }
 async uploadFile(jobId,file,expected){
  const handle=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW),abort=new AbortController(),timer=setTimeout(()=>abort.abort(),300000);
  try{
   const stat=await handle.stat();if(!stat.isFile()||stat.size!==expected.bytes)throw Error('Local media size mismatch');
   const check=createHash('sha256');for await(const b of handle.createReadStream({autoClose:false}))check.update(b);if(check.digest('hex')!==expected.sha256)throw Error('Local media hash mismatch');
   const response=await fetch(new URL(`/v1/file-jobs/${id(jobId)}/content`,this.base),{method:'PUT',redirect:'error',duplex:'half',signal:this.signal?AbortSignal.any([abort.signal,this.signal]):abort.signal,headers:{Authorization:`Bearer ${this.token}`,'Content-Type':'application/octet-stream','Content-Length':String(expected.bytes)},body:handle.createReadStream({start:0,autoClose:false})});
   if(!response.ok)throw Error('Media service upload HTTP '+response.status);
   const chunks=[];let total=0;for await(const b of response.body){total+=b.length;if(total>16384){abort.abort();throw Error('Upload response too large');}chunks.push(b);}
   const data=JSON.parse(Buffer.concat(chunks));if(data.api_version!=='1'||data.job_id!==jobId)throw Error('Invalid upload receipt');return data;
  }finally{clearTimeout(timer);await handle.close();}
 }
 async fileStatus(jobId){const data=await this.json(`/v1/jobs/${id(jobId)}`);if(data.job_id!==jobId||!['waiting_upload','queued','downloading','extracting','transcribing','succeeded','failed','partial_failed','waiting_confirmation'].includes(data.status))throw Error('Invalid file task state');return data;}
 async resumeFile(jobId){const data=await this.json(`/v1/file-jobs/${id(jobId)}/resume`,{method:'POST'});if(data.job_id!==jobId||data.status!=='queued'||data.reused!==true)throw Error('File recovery not confirmed');return data;}
 async fileResult(jobId,expectedInput){
  const m=await this.json(`/v1/file-jobs/${id(jobId)}/manifest`),asr=m.transcription;
  if(m.kind!=='file'||m.job_id!==jobId||!isDeepStrictEqual(m.input,expectedInput))throw Error('File source/input binding mismatch');
  if(asr?.engine!=='whisper.cpp'||!asr.model||!/^[a-f0-9]{64}$/u.test(asr.model_sha256??'')||!asr.language||!finite(m.duration_seconds))throw Error('Invalid file transcription metadata');
  if(m.verification?.input_sha256!==expectedInput.file.sha256||m.verification.source_binding!=='client_acquisition_claim'||m.verification.original?.full_decode!==true||m.verification.audio?.full_decode!==true)throw Error('File verification missing');
  for(const d of [m.verification.original.duration_seconds,m.verification.audio.duration_seconds,expectedInput.source.duration_seconds??m.duration_seconds])if(!finite(d)||Math.abs(d-m.duration_seconds)>Math.max(1,m.duration_seconds*.005))throw Error('File duration mismatch');
  for(const kind of ['original','audio']){
   const f=m.media?.[kind];if(f?.path!==`/v1/file-media/${jobId}/${kind}`||!/^[a-f0-9]{64}$/u.test(f.sha256??'')||!Number.isSafeInteger(f.bytes)||f.bytes<=0)throw Error('File media metadata invalid');
  }
  if(m.media.original.sha256!==expectedInput.file.sha256||m.media.original.bytes!==expectedInput.file.bytes)throw Error('Uploaded original mismatch');
  const segments=m.segments;let end=0;
  if(!Array.isArray(segments)||!segments.length||m.coverage?.head_tail_verified!==true||m.coverage.segments!==segments.length)throw Error('File transcript coverage missing');
  for(const s of segments){if(!Number.isFinite(s.start)||!Number.isFinite(s.end)||s.start<0||s.end<=s.start||s.start<end-.25||s.end>m.duration_seconds+1||typeof s.text!=='string'||!s.text.trim())throw Error('File transcript segment invalid');end=s.end;}
  for(const [index,s] of segments.entries()){
   let text=s.text.replace(/https?:\/\/\S+/gu,'');
   for(const kept of m.coverage.preserved_identifiers??[]){
    if(!preservedToken(kept,s,index))continue;
    const pattern=new RegExp('(?<![A-Za-z0-9_])'+kept.token+'(?![A-Za-z0-9_])','gu');if(pattern.test(kept.source_text)){pattern.lastIndex=0;text=text.replace(pattern,'');}
   }
   if((text.match(/[A-Za-z]/gu)??[]).length>3&&(text.match(/[A-Za-z]/gu)??[]).length>(text.match(/[\u3400-\u9fff]/gu)??[]).length)throw Error('File Chinese prose translation incomplete');
  }
  if(segments[0].start>10||m.duration_seconds-end>10||m.coverage.first_start!==segments[0].start||m.coverage.last_end!==end)throw Error('File transcript head/tail incomplete');
  if(asr.language!=='zh'&&asr.language!=='chinese'){
   const t=m.translation;if(t?.source_language!==({'english':'en'}[asr.language]??asr.language)||t?.target_language!=='zh'||!/^[a-f0-9]{64}$/u.test(t.model_sha256??'')||t.coverage?.all_source_segments_present!==true||t.coverage.source_segments!==segments.length)throw Error('File Chinese translation incomplete');
  }
  const {bytes,response}=await this.request(`/v1/file-jobs/${jobId}/markdown`);
  if(!response.headers.get('content-type')?.startsWith('text/markdown')||hash(bytes)!==m.markdown?.sha256)throw Error('File Markdown integrity mismatch');
  const markdown=new TextDecoder('utf-8',{fatal:true}).decode(bytes);if(markdown.includes(this.token)||/\/play\//u.test(markdown))throw Error('File Markdown contains credentials');
  return {manifest:m,markdown};
 }
 async waitFile(jobId,expectedInput,{timeoutMs=1800000,pollMs=2000,onStage=async()=>{}}={}){
  const deadline=Date.now()+timeoutMs;
  while(Date.now()<deadline){const j=await this.fileStatus(jobId);await onStage(j.stage??j.status,{remoteJobId:jobId,status:j.status});if(j.status==='succeeded')return this.fileResult(jobId,expectedInput);if(['failed','partial_failed','waiting_confirmation'].includes(j.status)){const e=Error('Remote media '+j.status+'; stage='+String(j.stage??'unknown')+'; retain job '+jobId);e.remoteFailure=j;throw e;}await delay(pollMs,undefined,{signal:this.signal});}
  throw Error('Remote media wait timed out; retain job '+jobId);
 }
 async probeFile(jobId,kind,expectedBytes){
  for(const start of new Set([0,Math.floor(expectedBytes/2),Math.max(0,expectedBytes-16)])){
   const end=Math.min(start+15,expectedBytes-1);const {response,bytes}=await this.request(`/v1/file-media/${id(jobId)}/${kind}`,{headers:{Range:`bytes=${start}-${end}`},maxBytes:16});
   if(response.status!==206||response.headers.get('content-range')!==`bytes ${start}-${end}/${expectedBytes}`||bytes.length!==end-start+1)throw Error('File media Range mismatch');
  }
 }
}
