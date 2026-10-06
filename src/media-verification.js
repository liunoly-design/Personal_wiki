const hosts=['v.douyin.com','douyin.com','www.douyin.com','iesdouyin.com','www.iesdouyin.com'];
function inputURL(value){
 try{const url=new URL(value);if(url.protocol!=='https:'||!hosts.includes(url.hostname)||url.username||url.password||(url.port&&url.port!=='443'))throw Error();url.hash='';return url;}catch{throw Error('Media service invalid verification input URL');}
}
export function verifyMediaEvidence(manifest,expectedSourceUrl){
 const proof=manifest.verification,source=manifest.source;
 if(!proof)throw Error('Media service verification evidence missing; upgrade server');
 const original=inputURL(proof.input_url);
 const explicit=[/^\/(?:video|share\/video)\/(\d+)\/?$/u.exec(original.pathname)?.[1],...original.searchParams.getAll('modal_id'),...original.searchParams.getAll('item_id')].filter(value=>value!==undefined&&value!==null);
 if((expectedSourceUrl&&original.href!==inputURL(expectedSourceUrl).href)||explicit.some(value=>value!==source.id)||['resolved_id','detail_id','downloaded_id'].some(key=>proof[key]!==source.id))throw Error('Media service source identity mismatch');
 for(const kind of ['video','audio']){
  const verified=proof[kind],media=manifest.media[kind];
  if(verified?.full_decode!==true||verified.sha256!==media.sha256||verified.bytes!==media.bytes||!Number.isFinite(verified.duration_seconds)||verified.duration_seconds<=0)throw Error('Media service full media verification missing or inconsistent');
 }
 const video=proof.video.duration_seconds,audio=proof.audio.duration_seconds,metadata=source.duration_seconds;
 const tolerance=Math.max(1,video*0.005);
 if(!Number.isFinite(metadata)||metadata<=0||Math.abs(video-audio)>tolerance||Math.abs(video-metadata)>tolerance)throw Error('Media service media duration mismatch');
}
