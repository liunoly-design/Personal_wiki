import {readFile,mkdir,lstat} from 'node:fs/promises';
import {join,relative,isAbsolute,dirname} from 'node:path';
import {createHash} from 'node:crypto';
import {MediaServiceClient,saveMediaResult} from './media-service-client.js';
import {saveJSON,optionalJSON} from './durable-files.js';
import {acquireQueueLease} from './task-queue.js';
import {localNashsuAPI} from './nashsu-api.js';
const hash=value=>createHash('sha256').update(value).digest('hex');
function chineseTranscript(markdown,manifest){
 const heading=manifest.translation?/^## 完整中文译文[^\n]*\n/gmu:/^## 完整(?:中文|原始)转写[^\n]*\n/gmu;
 const sections=[...markdown.matchAll(heading)];
 if(sections.length!==1)throw Error('Remote media Chinese transcript section missing or ambiguous');
 const start=sections[0].index+sections[0][0].length;
 const rest=markdown.slice(start);const end=rest.search(/^#{1,2} /mu);
 const text=(end<0?rest:rest.slice(0,end)).trim();
 const segments=[...text.matchAll(/^\[([\d:.]+(?:\s*→\s*[\d:.]+)?)\][ \t]+([^\r\n]+)$/gmu)];
 if(!segments.length||segments.some(s=>!s[2].trim())||!/[\u4e00-\u9fff]/u.test(segments.map(s=>s[2]).join('')))throw Error('Remote media Chinese timestamped transcript missing');
 if(manifest.translation){
  const originals=[...markdown.matchAll(/^## 完整原始转写[^\n]*\n/gmu)];
  if(originals.length!==1)throw Error('Remote media original transcript section missing or ambiguous');
  const remainder=markdown.slice(originals[0].index+originals[0][0].length);const boundary=remainder.search(/^#{1,2} /mu);
  const original=boundary<0?remainder:remainder.slice(0,boundary);
  const originalSegments=[...original.matchAll(/^\[([\d:.]+(?:\s*→\s*[\d:.]+)?)\][ \t]+([^\r\n]+)$/gmu)];
  if(!originalSegments.length||originalSegments.some(s=>!s[2].trim()))throw Error('Remote media original timestamped transcript missing');
  const stamps=originalSegments.map(s=>s[1]);
  if(stamps.length!==manifest.translation.coverage.source_segments||segments.length!==stamps.length||segments.some((s,i)=>s[1]!==stamps[i]))throw Error('Remote media Chinese sentence alignment incomplete; original task retained');
 }
 return text;
}
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
 const chinese=chineseTranscript(markdown,manifest);
 const directory=join(base,'sources',manifest.source.id+'-'+hash(JSON.stringify(manifest)+':chinese-sentences-v1'));
 await privateDirectory(directory);release=await acquireQueueLease(directory,python);
 try{
  const snapshot=join(directory,'snapshot');await privateDirectory(snapshot);
  await saveMediaResult(join(snapshot,'transcript.md'),result);
  for(const kind of ['video','audio','cover'])await client.probe(manifest.media[kind].path.split('/')[3],kind);
  const title=(manifest.source.title??'抖音视频').replace(/[\r\n]/gu,' ');
  const article=`# ${title}\n\n> 完整中文逐句${manifest.translation?'机器译文':'机器转写'}；未经人工校订。保留时间戳，不以摘要替代全文。\n\n来源：${manifest.source.url}\n\n## 完整中文正文\n\n${chinese}\n\n## 媒体与来源核对\n\n${['video','audio','cover'].map(kind=>`[${{video:'视频',audio:'完整音频',cover:'封面'}[kind]}](${client.base.origin}${manifest.media[kind].path})`).join(' · ')}\n\n[完整原始转写与来源资料](transcript.md)（独立归档，仅供核对）\n`;
  await saveMediaResult(join(snapshot,'article.md'),{markdown:article,manifest});
  await onStage('remote_knowledge',{video:{...report,transcriptStatus:'complete',sourceLanguage:manifest.transcription.language}});
  const publishedPath=join(directory,'published.json');const saved=await optionalJSON(publishedPath);
  const compiled=await collect({...options,url:manifest.source.url,isVideoPrepared:true,workspace:saved?options.workspace:join(directory,'knowledge'),api,previousResult:saved,refresh:false,preparedReadingModel:manifest.translation?.model??`whisper.cpp ${manifest.transcription.model}`,capture:async()=>({directory:snapshot,text:article,status:'complete'}),sourceContext:'单一视频来源；主正文是完整中文逐句译文或中文转写，保留时间戳，不把英文原稿或摘要作为正文。英文原稿只在独立来源附件中供核对，机器内容未经人工核实。原视频和完整音频保存在Mac mini，manifest包含其哈希；不得声称本机保存了完整媒体。'});
  const completed={...compiled,retainWorkspace:false,video:{...report,transcriptStatus:'complete',knowledgeStatus:'complete',sourceLanguage:manifest.transcription.language,media:manifest.media,mediaBase:client.base.origin,id:manifest.source.id}};
  const {userRecord,...shared}=completed;await saveJSON(publishedPath,shared);
  const page=await api.read(relative(vault,completed.source));
  const probe=chinese.split('\n').filter(line=>/^\[[\d:.]+(?:\s*→\s*[\d:.]+)?\]/u.test(line)).map(line=>line.replace(/^\[[\d:.]+(?:\s*→\s*[\d:.]+)?\]\s*/u,'').trim()).find(line=>line.length>=8&&/[\u4e00-\u9fff]/u.test(line))?.slice(0,40);
  if(!probe||!page.includes(probe))throw Error('Remote transcript readback verification failed');
  const found=await api.search(probe);
  if(!found.results?.some(r=>(r.path??r.file_path??r.filePath)===relative(vault,completed.source)))throw Error('Remote transcript search verification failed');
  await onStage('remote_complete',{video:completed.video});return completed;
 }finally{await release();}
}
