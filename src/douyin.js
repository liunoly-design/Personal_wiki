import {spawn} from 'node:child_process';
import {mkdir,readFile,readdir,copyFile,writeFile,lstat} from 'node:fs/promises';
import {join,resolve,dirname,relative} from 'node:path';
import {createHash} from 'node:crypto';
import {saveJSON,optionalJSON} from './durable-files.js';
import {acquireQueueLease} from './task-queue.js';
import {localNashsuAPI} from './nashsu-api.js';
import {publishBundle,verifyPublication} from './canonical-library.js';
const hash=s=>createHash('sha256').update(s).digest('hex');
export const isDouyin=url=>{try{return ['v.douyin.com','douyin.com','www.douyin.com','www.iesdouyin.com','iesdouyin.com'].includes(new URL(url).hostname);}catch{return false;}};
export async function videoPipeline(request,{python,signal}){
 return new Promise((accept,reject)=>{
  const child=spawn(python,[resolve(import.meta.dirname,'../scripts/douyin_video.py')],{signal,stdio:['pipe','pipe','pipe']});let out='';
  child.stdout.on('data',x=>out+=x);child.stderr.on('data',()=>{});child.on('error',()=>reject(Error('Video backend unavailable')));child.stdin.on('error',()=>{});
  child.on('close',code=>{try{const value=JSON.parse(out);if(code){const error=Error(value.error??'Video stage failed; materials retained');error.pendingMetadata=value.pendingMetadata;reject(error);}else accept(value);}catch{reject(Error('Video stage interrupted; materials retained'));}});child.stdin.end(JSON.stringify(request));
 });
}
async function safeDirectory(path){await mkdir(path,{recursive:true,mode:0o700});for(let p=path;p!==dirname(p);p=dirname(p)){if((await lstat(p)).isSymbolicLink())throw Error('Symlink video state rejected');}}
async function freezeCopy(src,dest){
 if(!(await lstat(src)).isFile())throw Error('Video snapshot must contain regular files');
 try{await copyFile(src,dest,1);}catch(error){if(error.code!=='EEXIST')throw error;if(!(await lstat(dest)).isFile()||hash(await readFile(src))!==hash(await readFile(dest)))throw Error('Frozen video snapshot changed; retain human content');}
}
async function verifySearch(result,{api,vault}){
 const path=relative(vault,result.source);const body=await api.read(path);
 const probe=result.video?.searchProbe;
 if(!probe||!body.includes(probe))throw Error('Video full-text readback mismatch');
 const found=await api.search(probe);
 if(!Array.isArray(found.results)||!found.results.some(r=>(r.path??r.file_path??r.filePath)===path))throw Error('Video full-text search verification unavailable');
}
export async function collectDouyin(options,collect){
 const {vault,python,signal,onStage=async()=>{}}=options;
 const mode=options.videoMode??'compressed';if(!['compressed','original'].includes(mode))throw Error('Invalid video mode');
 const base=join(options.stateDir??dirname(options.workspace),'video-jobs');await safeDirectory(base);
 const pipeline=options.pipeline??(request=>videoPipeline(request,{python,signal}));
 const api=options.api??await localNashsuAPI(vault,{signal,maxAttempts:1,statePath:options.nashsuStatePath});
 await api.assertPublisherReady?.();
 const alias=join(base,'aliases',hash(options.url)+'.json');
 let meta=await optionalJSON(alias);
 if(!meta){await onStage('video_metadata');const budgetPath=join(base,'metadata-attempts',hash(options.url)+'.json');const budget=await optionalJSON(budgetPath)??{attempts:0};if(budget.attempts>=5)throw Error('Douyin metadata retry budget exhausted');await saveJSON(budgetPath,{attempts:budget.attempts+1});meta=await pipeline({operation:'metadata',root:base,url:options.url});if(!/^[0-9]{10,24}$/.test(meta.id??''))throw Error('Unverified Douyin stable identity');await saveJSON(alias,meta);}
 const sourceRoot=join(base,meta.id);await safeDirectory(sourceRoot);const release=await acquireQueueLease(sourceRoot,python);
 try{
  const root=join(sourceRoot,mode);await safeDirectory(root);
  const canonicalPath=join(sourceRoot,'source.json'),resultPath=join(root,'published.json');
  let result=await optionalJSON(resultPath);
  const known=await optionalJSON(canonicalPath);
  const attachBackground=async r=>{const {userRecord,...shared}=r;if(!options.background)return shared;const note=await publishBundle({vault,background:options.background,requestId:options.requestId,source:r.source},{python,signal});await verifyPublication(note,{vault,api});return {...shared,userRecord:note.source};};
  const verify=async r=>{await verifyPublication(r,{vault,api});await verifySearch(r,{api,vault});};
  if(!result){
   await onStage('video_media');
   const assetFor=m=>({id:hash(m.id+':'+mode).slice(0,16),kind:'video',status:'waiting_confirmation',fingerprint:hash(JSON.stringify({id:m.id,mode,duration:m.duration,width:m.width,height:m.height,size:m.expected_size})),error:'超过30分钟或1GB，需要精确确认'});
   const asset=assetFor(meta);
   const approval=options.mediaApprovals?.[asset.id];const approved=approval?.fingerprint===asset.fingerprint;
   const pending=(m=meta)=>({status:'partial',resumableMedia:true,video:{id:meta.id,mode,video:'waiting_confirmation',audio:'pending',transcript:'pending',knowledge:'pending'},missingAssets:[assetFor(m)]});
   if(!approved&&(meta.duration>1800||(meta.expected_size??0)>=1_000_000_000))return pending();
   let media;try{media=await pipeline({operation:'media',root,url:meta.url,mode,metadata:meta,approved});}catch(error){const fresh=error.pendingMetadata;if(fresh){if(fresh.id!==meta.id||fresh.url!==meta.url)throw Error('Refreshed video identity mismatch');meta=fresh;await saveJSON(alias,meta);}if(/confirmation required/iu.test(error.message))return pending();throw error;}
   const oldMedia=await optionalJSON(join(root,'media-publication.json'));
   const mediaPublication=oldMedia??await publishBundle({operation:'douyin-media',vault,videoId:meta.id,mode,directory:join(root,'package'),media:{...media,metadata:media.metadata??meta}},{python,signal});
   await saveJSON(join(root,'media-publication.json'),mediaPublication);await verifyPublication(mediaPublication,{vault,api});
   await onStage('video_audio_archived',{video:{mode,video:'complete',audio:'complete',transcript:'pending',knowledge:'pending',media:mediaPublication}});
   if(known){
    // New mode adds immutable media to the same canonical knowledge source.
    await verify(known);
    result={...known,assets:{...known.assets,...mediaPublication.assets},files:{...known.files,...mediaPublication.files},supplements:[...(known.supplements??[]),mediaPublication.supplement],video:{...known.video,mode,media,mediaPublication,cleanup:null}};
   }else{
    await onStage('video_transcribing');
    const transcript=await pipeline({operation:'transcribe',root,binary:options.asrBinary,recovery:options.videoRecovery??false});
    const body=await readFile(transcript.transcript,'utf8');
    const snapshot=join(root,'snapshot');await safeDirectory(snapshot);
    for(const name of await readdir(join(root,'package'))){if(['video.mp4','audio.m4a'].includes(name))continue;const src=join(root,'package',name);if((await lstat(src)).isSymbolicLink())throw Error('Video snapshot symlink rejected');if((await lstat(src)).isDirectory()){await safeDirectory(join(snapshot,name));for(const child of await readdir(src))await freezeCopy(join(src,child),join(snapshot,name,child));}else await freezeCopy(src,join(snapshot,name));}
    const assetBase='../assets/douyin-'+meta.id+'/'+mode;
    const text=`# 抖音视频资料\n\n平台标题/作者说明（不是转录）：${meta.title}\n\n平台作者：${meta.author}\n\n来源：${meta.url}\n\n保存模式：${mode}；实际尺寸：${media.video.width}×${media.video.height}\n\n[${mode==='compressed'?'压缩归档视频':'原画质下载流'}](${assetBase}/video.mp4)\n\n[独立完整音频](${assetBase}/audio.m4a)\n\n[原始机器稿](transcript.md)\n\n${body}`;
    const article=join(snapshot,'article.md');try{await writeFile(article,text,{flag:'wx'});}catch(e){if(e.code!=='EEXIST')throw e;if(await readFile(article,'utf8')!==text)throw Error('Frozen video snapshot changed');}
    await onStage('video_knowledge');
    result=await collect({...options,api,background:'',url:meta.url,workspace:join(root,'knowledge'),isVideoPrepared:true,capture:async()=>({directory:snapshot,text,status:'complete'}),sourceContext:'来源是云端原始机器转录；未经人工校订，时间锚是粗粒度分段起点。平台描述和转录分开；机器转录不是已核实事实。'});
    const searchProbe=body.split('\n').filter(l=>l.trim()&&!/^[#>［]/u.test(l))[0]?.slice(0,40);
    if(!searchProbe)throw Error('Video transcript has no voiced text; review required');
    result={...result,assets:{...result.assets,...mediaPublication.assets},files:{...result.files,...mediaPublication.files},video:{id:meta.id,mode,media,transcript,searchProbe,mediaPublication,transcriptStatus:'complete',knowledgeStatus:'complete'}};
   }
   // Save before verifying so unknown publication results are reconciled first.
   await saveJSON(resultPath,result);
  }
  await onStage('video_verifying',{video:{...result.video,video:'complete',audio:'complete',transcriptStatus:'complete',knowledgeStatus:'complete'}});await verify(result);
  if(!known)await saveJSON(canonicalPath,result);
  const requestResult=await attachBackground(result);
  await onStage('video_cleanup',{video:{...result.video,video:'complete',audio:'complete',transcriptStatus:'complete',knowledgeStatus:'complete',cleanup:'pending'}});
  const cleanup=await pipeline({operation:'cleanup',root,verified:true});result.video.cleanup=cleanup;result.retainWorkspace=true;
  await saveJSON(resultPath,result);await onStage('video_complete',{video:result.video});
  return {...requestResult,video:result.video,retainWorkspace:true};
 }finally{await release();}
}
