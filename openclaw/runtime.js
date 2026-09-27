import {mkdir,readFile,writeFile,rename,readdir,link,unlink} from 'node:fs/promises';
import {join,isAbsolute} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {recordArticle,parseCommand} from '../src/wk.js';
import {createFlash} from '../src/flash.js';
import {createAdapters} from '../src/nashsu.js';
import {createFeishuClient} from '../src/feishu-http.js';
async function save(path,value){await writeFile(path+'.tmp',JSON.stringify(value,null,2),{mode:0o600});await rename(path+'.tmp',path);}
export async function openRuntime({config,hostConfig,feishu:injectedFeishu,makeAdapters=createAdapters,flash:injectedFlash}){
 for(const key of ['vault','stateDir','python'])if(!isAbsolute(config[key]??''))throw Error('Absolute paths required');
 const jobs=join(config.stateDir,'jobs');await mkdir(jobs,{recursive:true,mode:0o700});
 const account={...hostConfig.channels?.feishu,...hostConfig.channels?.feishu?.accounts?.[config.accountId]};
 if(!injectedFeishu&&(account.enabled===false||(account.domain&&account.domain!=='feishu')))throw Error('Feishu account unavailable');
 const feishu=injectedFeishu??createFeishuClient({credentials:()=>({appId:account.appId,appSecret:account.appSecret})});
 const flash=injectedFlash??createFlash({model:config.flashModel??'gemini-flash-latest',usagePath:join(config.stateDir,'flash-usage.jsonl')});
 let timer,running=false,closed=false;const controller=new AbortController();
 async function processJobs(){
  if(running||closed)return;running=true;
  try{
   for(const name of (await readdir(jobs)).filter(n=>n.endsWith('.json')).sort()){
    if(closed)break;
    const file=join(jobs,name);let job;
    try{job=JSON.parse(await readFile(file,'utf8'));if(!job||typeof job.id!=='string')throw Error('Invalid job');}catch{await rename(file,file+'.corrupt');continue;}
    if(!['queued','processing','delivery_pending'].includes(job.status))continue;
    if(!config.allowedSenderIds.includes(job.sender)||!config.allowedConversationIds.includes(job.chat)){job.status='scope_removed';await save(file,job);continue;}
    if(job.status!=='delivery_pending'){
     job.status='processing';await save(file,job);
     try{
      const deps=makeAdapters({vault:config.vault,python:config.python,captureDirectory:join(config.stateDir,'captures',job.id),flash,codexBinary:config.codexBinary,compilerModel:config.compilerModel});
      const result=await recordArticle({url:job.url,vault:config.vault,signal:controller.signal,onStage:async(stage,details)=>{job.stage=stage;job.details={...job.details,...details};await save(file,job);}},deps);
      job.result=result;job.receipt=`【Wiki】${result.status==='existing'?'已存在归档':result.status==='pending'?'已归档，分析尚未完成，请检查本机队列':'记录与分析完成'}\n基础名词：${result.terms} 个（新建 ${result.newDefinitions} 个）\n来源卡：${result.source}\n附件：${result.attachmentStatus==='complete'?'已保存':result.attachmentStatus==='previous_archive'?'沿用已有归档':'部分完成，存在失败或待处理附件'}\n基础解释由 Flash 生成，文章关联由 nashsu 加工。`;
     }catch(error){
      if(closed){job.status='queued';await save(file,job);break;}
      job.failure=error.message;
      const progress=job.stage==='glossary_saved'?'抓取和基础解释已保存，文章分析尚未完成。':job.stage==='captured'?'抓取已完成，内容已保留；基础解释和文章分析尚未完成。':'抓取尚未完成，已下载的部分文件会保留。';
      const http=error.message?.match(/^Flash HTTP (\d{3});/u)?.[1];
      const reason=http==='402'?'Flash 服务返回 HTTP 402：请检查 Google AI Studio 项目的预付额度和计费状态。恢复额度后重发原链接；更换文章链接无法解决。':http?`Flash 服务返回 HTTP ${http}，请检查模型服务状态后重试。`:job.stage==='glossary_saved'?'请检查本机 LLM Wiki 的加工队列及模型状态。':job.stage==='captured'?'Flash 名词处理失败，请检查本机任务记录及模型配置。':'请检查页面是否可访问，以及本机抓取任务记录。';
      job.receipt='【Wiki】处理未全部完成。\n'+progress+'\n'+reason;
     }
     job.status='delivery_pending';await save(file,job);
    }
    try{
     const receipt=await feishu.reply({replyTo:job.messageId,text:job.receipt,uuid:job.id.slice(0,32)},{signal:controller.signal});
     if(!receipt?.message_id||receipt.chat_id!==job.chat)throw Error('Delivery result unknown');
     job.status=job.failure?'failed':'done';job.receiptId=receipt.message_id;await save(file,job);
    }catch{job.deliveryError='Reply not confirmed; same delivery UUID will be reused';await save(file,job);}
   }
  }finally{running=false;}
 }
 return {
  async accept(c,url,signal){
   const messageId=c.MessageSidFull??c.MessageSid;if(!/^om_[\w-]+$/u.test(messageId??''))throw Error('Message ID required');
   const original=await feishu.getMessage(messageId,{signal});
   if(original.message_id!==messageId||original.chat_id!==c.NativeChannelId||original.sender?.id!==c.SenderId||original.sender.id_type!=='open_id'||original.sender.sender_type!=='user'||original.deleted)throw Error('Source mismatch');
   const parsed=parseCommand(JSON.parse(original.body.content).text);
   if(parsed?.action!=='record'||parsed.url!==url)throw Error('Source command mismatch');
   const id=createHash('sha256').update(config.accountId+':'+messageId).digest('hex');const file=join(jobs,id+'.json');
   const temporary=file+'.'+randomUUID()+'.tmp';
   try{await writeFile(temporary,JSON.stringify({id,messageId,url,sender:c.SenderId,chat:c.NativeChannelId,status:'queued',createdAt:new Date().toISOString()}),{flag:'wx',mode:0o600});await link(temporary,file);}
   catch(e){if(e.code==='EEXIST')return {duplicate:true};throw e;}
   finally{await unlink(temporary).catch(e=>{if(e.code!=='ENOENT')throw e;});}
   return {duplicate:false};
  },
  async start(){timer=setInterval(()=>{processJobs().catch(()=>{});},2000);timer.unref();processJobs().catch(()=>{});},
  processJobs,
  async close(){closed=true;clearInterval(timer);controller.abort();while(running)await new Promise(r=>setTimeout(r,50));},
 };
}
