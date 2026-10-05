import {readFile,mkdir,lstat} from 'node:fs/promises';
import {join,relative,isAbsolute,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {MediaServiceClient,saveMediaResult} from './media-service-client.js';
import {saveJSON,optionalJSON} from './durable-files.js';
import {acquireQueueLease} from './task-queue.js';
import {localNashsuAPI} from './nashsu-api.js';
const hash=value=>createHash('sha256').update(value).digest('hex');
async function privateDirectory(path){await mkdir(path,{recursive:true,mode:0o700});for(let p=path;;p=dirname(p)){if(!(await lstat(p)).isDirectory())throw Error('Remote media state must be a regular directory');if(p===dirname(p))break;}}
export async function collectRemoteDouyin(options,collect) {
 const {url,vault,python,signal,onStage=async()=>{}}=options;
 if(options.refresh)throw Error('Remote media refresh unsupported; request service-side reprocessing first');
 if(!isAbsolute(options.mediaServiceTokenFile??''))throw Error('Remote media credential file must be absolute');
 const tokenStat=await lstat(options.mediaServiceTokenFile);
 if(!tokenStat.isFile()||(tokenStat.mode&0o077)||tokenStat.uid!==process.getuid())throw Error('Remote media credential file must be owned and private');
 const token=(await readFile(options.mediaServiceTokenFile,'utf8')).trim();
 const client=new MediaServiceClient({baseUrl:options.mediaServiceUrl,token,signal});
 const api=options.api??await localNashsuAPI(vault,{signal,maxAttempts:1});await api.assertPublisherReady?.();
 const base=join(options.stateDir,'remote-video');await privateDirectory(base);
 const alias=join(base,'jobs',hash(url));await privateDirectory(alias);
 let release=await acquireQueueLease(alias,python);
 let remote;
 try{
  const path=join(alias,'job.json');remote=await optionalJSON(path);
  if(remote&&remote.service!==client.base.origin)throw Error('Remote media service changed; existing job retained');
  if(!remote){remote={service:client.base.origin,url,idempotencyKey:hash(JSON.stringify({url:new URL(url).href,options:{language:'zh',max_height:1080}}))};await saveJSON(path,remote);}
  if(!remote.jobId){await onStage('remote_submitting');const response=await client.submit(url,{idempotencyKey:remote.idempotencyKey});remote.jobId=response.job_id;await saveJSON(path,remote);}
 }finally{await release();}
 const report={mode:'remote',remoteJobId:remote.jobId,video:'remote',audio:'remote',transcriptStatus:'pending',knowledgeStatus:'pending'};
 await onStage('remote_waiting',{video:report});
 let result;
 try{result=await client.wait(remote.jobId,{timeoutMs:1800000});}
 catch(error){
  if(/: waiting_login$/u.test(error.message))throw Error('Remote media waiting_login; continue after Mac mini authentication is restored');
  if(/: waiting_confirmation$/u.test(error.message))throw Error('Remote media waiting_confirmation; service-side approval required');
  if(/: (?:failed|partial_failed)$/u.test(error.message))throw Error('Remote media task failed; retained job '+remote.jobId);
  throw error;
 }
 const {manifest,markdown}=result;
 if(markdown.includes(token)||JSON.stringify(manifest).includes(token)||/https?:\/\/[^\s)]+\/play\//u.test(markdown))throw Error('Remote media Markdown contains forbidden credentials or temporary capabilities');
 // A shared source/version lease prevents alias links from publishing twice.
 const directory=join(base,'sources',manifest.source.id+'-'+hash(JSON.stringify(manifest)));
 await privateDirectory(directory);release=await acquireQueueLease(directory,python);
 try{
  const snapshot=join(directory,'snapshot');await privateDirectory(snapshot);
  await saveMediaResult(join(snapshot,'transcript.md'),result);
  for(const kind of ['video','audio','cover'])await client.probe(manifest.media[kind].path.split('/')[3],kind);
  const article=`> 来源为Mac mini保存的完整机器转写${manifest.translation?'及中文机器译文':''}；未经人工校订。视频与完整音轨保存在远程服务器，媒体读取需认证。\n\n`+markdown.replace(/\]\((\/v1\/media\/[A-Za-z0-9_-]+\/(?:video|audio|cover))\)/gu,(_whole,path)=>`](${client.base.origin}${path})`);
  await saveMediaResult(join(snapshot,'article.md'),{markdown:article,manifest});
  await onStage('remote_knowledge',{video:{...report,transcriptStatus:'complete',sourceLanguage:manifest.transcription.language}});
  const publishedPath=join(directory,'published.json');const saved=await optionalJSON(publishedPath);
  const compiled=await collect({...options,url:manifest.source.url,isVideoPrepared:true,workspace:saved?options.workspace:join(directory,'knowledge'),api,previousResult:saved,refresh:false,preparedReadingModel:manifest.translation?.model??`whisper.cpp ${manifest.transcription.model}`,capture:async()=>({directory:snapshot,text:article,status:'complete'}),sourceContext:'单一视频来源；平台描述、英文原始机器稿、中文派生机器译文分别标记，机器内容未经人工核实。原视频和完整音频保存在Mac mini，manifest包含其哈希；不得声称本机保存了完整媒体。'});
  const completed={...compiled,retainWorkspace:false,video:{...report,transcriptStatus:'complete',knowledgeStatus:'complete',sourceLanguage:manifest.transcription.language,media:manifest.media,mediaBase:client.base.origin,id:manifest.source.id}};
  const {userRecord,...shared}=completed;await saveJSON(publishedPath,shared);
  const page=await api.read(relative(vault,completed.source));
  const probe=markdown.split('\n').filter(line=>/^\[[\d:.]+(?:\s*→\s*[\d:.]+)?\]/u.test(line)).map(line=>line.replace(/^\[[\d:.]+(?:\s*→\s*[\d:.]+)?\]\s*/u,'').trim()).find(line=>line.length>=8&&/[\u4e00-\u9fff]/u.test(line))?.slice(0,40);
  if(!probe||!page.includes(probe))throw Error('Remote transcript readback verification failed');
  const found=await api.search(probe);
  if(!found.results?.some(r=>(r.path??r.file_path??r.filePath)===relative(vault,completed.source)))throw Error('Remote transcript search verification failed');
  await onStage('remote_complete',{video:completed.video});return completed;
 }finally{await release();}
}
