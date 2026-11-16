import {open,mkdir,link,unlink,lstat} from 'node:fs/promises';
import {constants} from 'node:fs';
import {isAbsolute,dirname,join,extname,basename,resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
export const mediaExtension=file=>/\.(mp4|mov|mkv|webm|m4v|mp3|m4a|wav|aac|flac|ogg|opus|aiff|aif|caf)$/iu.test(file);
export async function freezeMedia(file,root){
 if(!isAbsolute(file??'')||!mediaExtension(file))throw Error('Absolute audio/video file required');
 await mkdir(root,{recursive:true,mode:0o700});
 for(let p=resolve(root);;p=dirname(p)){if(!(await lstat(p)).isDirectory())throw Error('Media state must use regular directories');if(p===dirname(p))break;}
 const input=await open(file,constants.O_RDONLY|constants.O_NOFOLLOW);let out;const temporary=join(root,'.upload-'+randomUUID());
 try{
  const before=await input.stat();if(!before.isFile()||!before.size)throw Error('Regular nonempty media file required');if(before.size>1_000_000_000)throw Error('Media exceeds 1GB; confirmation required');
  out=await open(temporary,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW,0o600);
  const sha=createHash('sha256');let bytes=0;const buffer=Buffer.alloc(1024*1024);
  while(true){const {bytesRead}=await input.read(buffer);if(!bytesRead)break;bytes+=bytesRead;if(bytes>before.size)throw Error('Media changed during snapshot');const chunk=buffer.subarray(0,bytesRead);sha.update(chunk);await out.writeFile(chunk);}
  const after=await input.stat();if(bytes!==before.size||after.mtimeMs!==before.mtimeMs||after.ctimeMs!==before.ctimeMs)throw Error('Media changed during snapshot');
  await out.sync();await out.close();out=undefined;const sha256=sha.digest('hex'),extension=extname(file).toLowerCase(),destination=join(root,sha256+extension);
  try{await link(temporary,destination);}catch(error){if(error.code!=='EEXIST')throw error;const prior=await open(destination,constants.O_RDONLY|constants.O_NOFOLLOW);try{const h=createHash('sha256');for await(const chunk of prior.createReadStream({autoClose:false}))h.update(chunk);if(h.digest('hex')!==sha256)throw Error('Stored media integrity mismatch');}finally{await prior.close();}}
  const dir=await open(root,constants.O_RDONLY);try{await dir.sync();}finally{await dir.close();}
  return {file:destination,sha256,bytes,extension,title:basename(file),originalPath:file};
 }finally{await input.close();await out?.close();await unlink(temporary).catch(e=>{if(e.code!=='ENOENT')throw e;});}
}
