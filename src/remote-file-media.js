import {readFile,lstat,mkdir,readdir} from 'node:fs/promises';
import {join,isAbsolute,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {FileMediaClient} from './file-media-client.js';
import {saveMediaResult} from './media-service-client.js';
import {saveJSON,optionalJSON} from './durable-files.js';
import {acquireQueueLease} from './task-queue.js';
const hash=x=>createHash('sha256').update(x).digest('hex');
export async function transcribeFile({file,source,config,signal,resume=false}){
 if(!isAbsolute(config.mediaServiceTokenFile??'')||!config.mediaServiceUrl)throw Error('Mini generic media not configured');
 const stat=await lstat(config.mediaServiceTokenFile);if(!stat.isFile()||stat.uid!==process.getuid()||(stat.mode&0o077))throw Error('Private media credential file required');
 const token=(await readFile(config.mediaServiceTokenFile,'utf8')).trim(),client=new FileMediaClient({baseUrl:config.mediaServiceUrl,token,signal});
 const incoming={source,file:{sha256:file.sha256,bytes:file.bytes,extension:file.extension}};
 const identity=value=>hash(JSON.stringify({platform:value.source.platform,id:value.source.id,asset:value.source.asset_id,sha256:value.file.sha256,bytes:value.file.bytes}));
 const key=identity(incoming),parent=join(config.stateDir,'remote-files'),base=join(parent,key);let input=incoming;await mkdir(base,{recursive:true,mode:0o700});
 for(let p=base;;p=dirname(p)){if(!(await lstat(p)).isDirectory())throw Error('Regular remote file state required');if(p===dirname(p))break;}
 const release=await acquireQueueLease(base,config.python);let remote;
 try{
  remote=await optionalJSON(join(base,'job.json'));
  if(!remote){
   const legacy=[];for(const entry of await readdir(parent,{withFileTypes:true})){if(!entry.isDirectory()||!/^[a-f0-9]{64}$/u.test(entry.name))continue;const candidate=await optionalJSON(join(parent,entry.name,'job.json'));if(candidate?.input){const old=candidate.input,indexAlias=source.platform==='x'&&old.source.platform==='x'&&old.source.id===source.id&&old.file.sha256===file.sha256&&old.file.bytes===file.bytes&&new RegExp('^'+source.id+'-video-[0-9]+$','u').test(old.source.asset_id);if(identity(old)===key||indexAlias)legacy.push(candidate);}}
   if(new Set(legacy.map(r=>r.service+':'+r.jobId)).size>1)throw Error('Multiple prior remote jobs; reconcile original identities');
   if(legacy.length){remote=legacy[0];await saveJSON(join(base,'job.json'),remote);}
  }
  if(remote&&remote.service!==client.base.origin)throw Error('Remote media service changed; retain original task');
  if(!remote){remote={service:client.base.origin,input,idempotencyKey:key};await saveJSON(join(base,'job.json'),remote);}
  input=remote.input;
  if(JSON.stringify(incoming)!==JSON.stringify(input)&&!(remote.acquisitions??[]).some(a=>JSON.stringify(a.source)===JSON.stringify(source))){remote.acquisitions=[...(remote.acquisitions??[]),{at:new Date().toISOString(),source}];await saveJSON(join(base,'job.json'),remote);}
  if(!remote.jobId){const receipt=await client.submitFile(input,{idempotencyKey:remote.idempotencyKey});remote.jobId=receipt.job_id;await saveJSON(join(base,'job.json'),remote);}
  const state=await client.fileStatus(remote.jobId);
  if(state.status==='waiting_upload')await client.uploadFile(remote.jobId,file.file,input.file);
  else if(resume&&['failed','partial_failed'].includes(state.status))await client.resumeFile(remote.jobId);
 }finally{await release();}
 const result=await client.waitFile(remote.jobId,input,{onStage:config.onStage});
 for(const kind of ['original','audio'])await client.probeFile(remote.jobId,kind,result.manifest.media[kind].bytes);
 const directory=join(base,'snapshot');await mkdir(directory,{recursive:true,mode:0o700});
 await saveMediaResult(join(directory,'transcript.md'),result);
 return {...result,directory,remoteJobId:remote.jobId,mediaBase:client.base.origin};
}
export async function captureLocalMedia({job,config,directory,signal}){
 const f=job.mediaFile,canonical=job.canonicalUrl??job.url;
 const source={platform:'file',id:f.sha256,url:'https://file.personal-wiki.invalid/'+f.sha256,asset_id:'original',title:f.title,...(job.mediaSupplement?{provenance:'user-provided supplement for '+canonical}:{})};
 const result=await transcribeFile({file:f,source,config,signal,resume:job.rounds>1||(job.generation??0)>0});
 await mkdir(directory,{recursive:true,mode:0o700});
 const refs=Object.entries(result.manifest.media).map(([kind,m])=>`[${kind==='audio'?'完整音频':'原始媒体'}](${result.mediaBase}${m.path})`).join(' · ');
 const chinese=result.markdown.split('## 完整中文正文\n\n')[1]?.split('\n\n## 完整原始转写')[0];if(!chinese)throw Error('Chinese transcript section missing');
 await saveMediaResult(join(directory,'transcript.md'),result);
 const article=`# ${f.title.replace(/[\r\n]/gu,' ')}\n\n> 完整中文机器转写或译文；未经人工校订。\n\n来源：${canonical}\n\n## 完整中文正文\n\n${chinese}\n\n[独立原始转写与来源资料](transcript.md)\n\n## 媒体与来源核对\n\n${refs}\n\n${job.mediaSupplement?'用户提供的音视频补料；原平台获取未核实。关联来源：'+canonical:'本地文件：'+f.title}。输入 SHA-256：${f.sha256}\n`;
 await saveMediaResult(join(directory,'article.md'),{markdown:article,manifest:result.manifest});
 return {directory,status:'complete',url:canonical,remoteJobId:result.remoteJobId,preparedReadingModel:result.manifest.translation?.model??`whisper.cpp ${result.manifest.transcription.model}`};
}
