import {readFile,mkdir,cp,lstat,rename,rm,writeFile,readdir} from 'node:fs/promises';
import {join,resolve,relative} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {freezeMedia} from './media-files.js';
import {transcribeFile} from './remote-file-media.js';
import {saveMediaResult} from './media-service-client.js';
export function transcriptBody(manifest){
 const stamp=x=>{const ms=Math.round(x*1000);return `${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;};
 return manifest.segments.map(s=>`[${stamp(s.start)} → ${stamp(s.end)}] ${s.text.trim()}`).join('\n\n');
}
export async function preparePlatformMedia({capture,manifest,job,config,directory,signal}){
 const videos=manifest.assets.filter(a=>a.kind==='video');
 if(capture.status!=='complete'||capture.contextStatus==='partial'||videos.some(v=>v.status!=='downloaded')){
  if(videos.some(v=>v.status==='waiting_metadata'))return {...capture,status:'partial',failure:'Video transcription required; live photo metadata not configured'};
  const confirmation=videos.some(v=>v.status==='waiting_confirmation');
  return {...capture,status:'partial',failure:confirmation?'Video exceeds limits; confirmation required':'Platform media acquisition incomplete; acquired materials retained'};
 }
 const target=join(directory,'media-package'),binding=createHash('sha256').update(JSON.stringify(manifest)+capture.directory).digest('hex');
 if(await lstat(target).catch(e=>{if(e.code!=='ENOENT')throw e;})){
  const sealed=JSON.parse(await readFile(join(target,'package-seal.json'),'utf8'));if(sealed.binding!==binding)throw Error('Existing derived media binding differs');
  for(const [name,sha] of Object.entries(sealed.hashes)){if(name.startsWith('/')||name.split('/').includes('..')||(await lstat(join(target,name))).isSymbolicLink()||createHash('sha256').update(await readFile(join(target,name))).digest('hex')!==sha)throw Error('Derived media package integrity mismatch');}
  return {...capture,directory:target,status:'complete'};
 }
 let article=await readFile(join(capture.directory,'article.md'),'utf8');const sources=[];
 for(const v of videos){
  if(!/^[A-Za-z0-9_-]{1,128}$/u.test(v.asset_id??'')||!v.path||v.path.startsWith('/')||v.path.split('/').some(p=>!p||p==='..'))throw Error('Invalid platform media binding');
  const path=resolve(capture.directory,v.path);if(relative(capture.directory,path).startsWith('..'))throw Error('Unsafe platform media path');
  const file=await freezeMedia(path,join(config.stateDir,'ingestion/media-inputs'));
  if(file.sha256!==v.sha256||file.bytes!==v.bytes)throw Error('Acquired platform media integrity mismatch');
  const source={platform:job.platform,id:v.source_id,url:v.source_url,asset_id:v.asset_id,title:job.platform+' '+v.source_id,...(v.duration_seconds?{duration_seconds:v.duration_seconds}:{}),acquisition_sha256:createHash('sha256').update(await readFile(join(capture.directory,'manifest.json'))).digest('hex')};
  const result=await transcribeFile({file,source,config,signal,resume:job.rounds>1||(job.generation??0)>0});
  sources.push({assetId:v.asset_id,result,original:{sha256:file.sha256,bytes:file.bytes}});
  const marker='[视频转写待处理](wiki-media:'+v.asset_id+')';
  if(article.split(marker).length!==2)throw Error('Video placement marker missing or ambiguous');
  article=article.replace(marker,`\n\n### 视频完整中文${result.manifest.translation?'机器译文':'机器转写'}\n\n> 未经人工校订；保留全部时间段。\n\n${transcriptBody(result.manifest)}\n\n[原始媒体](${result.mediaBase}${result.manifest.media.original.path}) · [完整音频](${result.mediaBase}${result.manifest.media.audio.path}) · [独立原始转写](media/${v.asset_id}.md)\n\n`);
 }
 // Keep heavy originals in the client input area and Mini; preserve source JSON and covers.
 const excluded=new Set(videos.map(v=>resolve(capture.directory,v.path)));
 const stage=target+'.stage-'+randomUUID();
 try{
 await cp(capture.directory,stage,{recursive:true,filter:async src=>{if((await lstat(src)).isSymbolicLink())throw Error('Capture symlink rejected');return !excluded.has(resolve(src));}});
 await mkdir(join(stage,'media'),{recursive:true,mode:0o700});
 for(const s of sources)await saveMediaResult(join(stage,'media',s.assetId+'.md'),s.result);
 await writeFile(join(stage,'article.acquired.md'),await readFile(join(capture.directory,'article.md')),{flag:'wx',mode:0o600});
 // This is a new derived package, never an overwrite of the acquired original.
 await writeFile(join(stage,'article.md'),article,{mode:0o600});
 await writeFile(join(stage,'media-sources.json'),JSON.stringify(sources.map(s=>({assetId:s.assetId,jobId:s.result.remoteJobId,service:s.result.mediaBase,input:s.original,media:s.result.manifest.media,source:s.result.manifest.input.source})),null,2)+'\n',{flag:'wx',mode:0o600});
 const hashes={};const seal=async(dir,prefix='')=>{for(const entry of await readdir(dir,{withFileTypes:true})){const name=prefix+entry.name;if(entry.isDirectory())await seal(join(dir,entry.name),name+'/');else if(entry.isFile())hashes[name]=createHash('sha256').update(await readFile(join(dir,entry.name))).digest('hex');else throw Error('Regular derived files required');}};await seal(stage);await writeFile(join(stage,'package-seal.json'),JSON.stringify({binding,hashes}),{flag:'wx',mode:0o600});
 await rename(stage,target);
 }finally{await rm(stage,{recursive:true,force:true});}
 return {...capture,directory:target,status:'complete'};
}
