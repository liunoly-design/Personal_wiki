import {readFile} from 'node:fs/promises';
import {join,resolve,dirname} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import {preparePlatformMedia} from './platform-media.js';
import {captureLocalMedia} from './remote-file-media.js';
import {collectRemoteDouyin} from './remote-douyin.js';
const exec=promisify(execFile);
const hash=value=>createHash('sha256').update(value).digest('hex');
export const supportedSource=platform=>['x','wechat','douyin','text','web','xiaohongshu','file'].includes(platform);
export const inputURLs=input=>[...new Set((input.match(/https?:\/\/[^\s<>\[\]()，。；]+/gu)??[]).map(s=>s.replace(/\\&/gu,'&').replace(/[)）】」』！!？?]+$/u,'')))];

export function identifyInput({input,text}){
 if(text!==undefined){if(typeof text!=='string'||!text.trim())throw Error('Nonempty text required');return {platform:'text',text,url:'https://text.personal-wiki.invalid/'+hash(text),name:'user-note-'+hash(text).slice(0,12)};}
 if(typeof input!=='string'||!input.trim())throw Error('Input required');
 const urls=inputURLs(input);
 if(!urls.length)return identifyInput({text:input});
 if(urls.length!==1)throw Error('Submit one distinct source at a time');
 const u=new URL(urls[0]);
 if(u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443'))throw Error('Unsupported source URL');
 u.hash='';let platform='web',name,fetchUrl;
 if(['x.com','www.x.com','twitter.com','www.twitter.com'].includes(u.hostname)){
  const post=u.pathname.match(/^\/([a-zA-Z0-9_]+)\/status\/(\d+)\/?$/u);if(!post)throw Error('Single X post required');
  u.hostname='x.com';u.search='';u.pathname=u.pathname.replace(/\/$/u,'');platform='x';name=('x-'+post[1].replaceAll('_','-')+'-'+post[2]).toLowerCase();
 }else if(u.hostname==='mp.weixin.qq.com')platform='wechat';
 else if(['v.douyin.com','www.douyin.com','douyin.com','iesdouyin.com','www.iesdouyin.com'].includes(u.hostname))platform='douyin';
 else if(['www.xiaohongshu.com','xiaohongshu.com'].includes(u.hostname)){
  const note=u.pathname.match(/^\/(?:explore|discovery\/item)\/([a-f0-9]{24})\/?$/u);if(!note)throw Error('Single Xiaohongshu note required');
  platform='xiaohongshu';fetchUrl=u.href;u.hostname='www.xiaohongshu.com';u.pathname='/explore/'+note[1];u.search='';name='xiaohongshu-'+note[1];
 }else if(['xhslink.com','www.xhslink.com','xhslink.cn','www.xhslink.cn'].includes(u.hostname)){platform='xiaohongshu';fetchUrl=u.href;}
 else if(/(^|\.)(kuaishou\.com|bilibili\.com|b23\.tv|youtube\.com|youtu\.be|instagram\.com|tiktok\.com|weibo\.com|weibo\.cn|zhihu\.com)$/u.test(u.hostname))platform='unsupported';
 return {platform,url:u.href,...(fetchUrl?{fetchUrl}:{}),name:name??platform+'-article-'+hash(u.href).slice(0,12)};
}

export async function captureArticle({job,config,directory,signal}){
 if(job.mediaFile)return captureLocalMedia({job,config,directory,signal});
 if(job.platform==='douyin')return collectRemoteDouyin({...config,url:job.url,convertOnly:true,resumeRemote:job.rounds>1||job.recoveries?.length>0,explicitRemoteRecovery:job.recoveries?.length>0,stateDir:config.stateDir,python:config.python,signal,onStage:config.onStage});
 const fx=job.platform==='x'&&(job.rounds===1||job.lastCapture?.provider==='FxEmbed v2 thread'&&job.lastCapture?.contextStatus==='complete');
 const script=fx?'x_provider.py':job.platform==='xiaohongshu'?'xiaohongshu_capture.py':'capture_article.py';
 if(fx)directory=join(dirname(directory),String(job.generation??0)+'-fx');
 await config.onStage?.('fetching',{directory:join(directory,'package')});
 const {stdout}=await exec(config.python,[resolve(import.meta.dirname,'../scripts/'+script),'--url',job.fetchUrl??job.url,'--output',directory,...(job.platform==='web'&&job.rounds>1?['--render']:[]),...(job.platform==='xiaohongshu'&&job.rounds>1?['--desktop']:[]),...(job.rounds>1&&config.browserProfile&&['x','wechat'].includes(job.platform)?['--browser-profile',config.browserProfile]:[])],{signal,env:{...process.env,WIKI_QUEUE_MANAGED:'1'},timeout:900000,maxBuffer:2*1024*1024});
 let capture=JSON.parse(stdout);const manifest=await readFile(join(capture.directory,'manifest.json'),'utf8').then(JSON.parse).catch(e=>{if(e.code==='ENOENT')return null;throw e;});
 if(manifest?.assets?.some(a=>a.kind==='video')){job.lastCapture=capture;await config.onStage?.('media_preparing',{directory:capture.directory});capture=await preparePlatformMedia({capture,manifest,job,config,directory,signal});}
 if(job.platform==='xiaohongshu'&&manifest?.assets?.some(a=>a.kind==='image')&&(config.ocr===false||process.platform!=='darwin'))return {...capture,status:'partial',failure:'Xiaohongshu image OCR not configured; acquired materials retained'};
 if(capture.status==='complete'&&capture.contextStatus!=='partial'&&config.ocr!==false&&process.platform==='darwin'){
  const result=await exec(config.python,[resolve(import.meta.dirname,'../scripts/image_ocr.py'),'--package',capture.directory,'--output',join(directory,'ocr-package')],{signal,timeout:900000,maxBuffer:2*1024*1024});
  return {...capture,...JSON.parse(result.stdout)};
 }
 return capture;
}
