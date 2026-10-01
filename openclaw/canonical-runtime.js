import {join,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
import {openTaskQueue} from '../src/task-queue.js';
import {collectCanonical} from '../src/canonical-library.js';
import {parseCommand} from '../src/wk.js';
import {createFlash} from '../src/flash.js';
import {createFeishuClient} from '../src/feishu-http.js';
export async function openCanonicalRuntime({config,hostConfig,feishu:injectedFeishu,flash:injectedFlash,collect=collectCanonical}){
 for(const key of ['vault','stateDir','python'])if(!isAbsolute(config[key]??''))throw Error('Absolute paths required');
 const account={...hostConfig.channels?.feishu,...hostConfig.channels?.feishu?.accounts?.[config.accountId]};
 if(!injectedFeishu&&(account.enabled===false||(account.domain&&account.domain!=='feishu')))throw Error('Feishu account unavailable');
 const feishu=injectedFeishu??createFeishuClient({credentials:()=>({appId:account.appId,appSecret:account.appSecret})});
 const flash=injectedFlash??createFlash({proxyUrl:config.flashProxyUrl,model:config.flashModel??'gemini-flash-latest',usagePath:join(config.stateDir,'flash-usage.jsonl')});
 const allowed=job=>config.allowedSenderIds.includes(job.sender)&&config.allowedConversationIds.includes(job.chat);
 function check(scope){if(scope.Provider!=='feishu'||scope.AccountId!==config.accountId||!allowed({sender:scope.SenderId,chat:scope.NativeChannelId}))throw Error('Wiki scope denied');}
 const queue=await openTaskQueue({stateDir:config.stateDir,python:config.python,allowed,
  run:(job,workspace,signal,onStage,previousResult)=>collect({url:job.url,text:job.text,background:job.background,requestId:job.id,refresh:job.refresh,vault:config.vault,workspace,python:config.python,flash,codexBinary:config.codexBinary,compilerModel:config.compilerModel,signal,onStage,previousResult}),
  notifyWaiting:async(job,signal)=>{
   const reply=await feishu.reply({replyTo:job.messageId,text:`【Wiki】本项尚未完成：${job.url}\n状态：${job.status}。已取得的资料及任务保留，可在外部条件恢复后重试。其他项独立处理。`,uuid:createHash('sha256').update(job.id+':waiting').digest('hex').slice(0,32)},{signal});
   if(!reply?.message_id||reply.chat_id!==job.chat)throw Error('Delivery result unknown');return reply.message_id;
  },
  deliver:async(job,signal)=>{
   const result=await feishu.reply({replyTo:job.messageId,text:`【Wiki】记录完成，已通过 nashsu API 核验。\n标题：${job.result.title??"见来源卡"}\n摘要：${job.result.summary??"见来源卡"}\n正文：${job.result.source}\n${job.result.attachmentStatus==='partial'?'部分完成：正文已保存，图片缺失 '+(job.result.missingAssets?.length??0)+' 项。':'附件已核验。'}\n${job.result.userRecord?'个人背景：'+job.result.userRecord:''}\n已取得的原文与附件已归档；处理临时文件已清理。\n待审修改：${job.result.reviews?.length??0} 项：${job.result.reviews?.map(r=>r.id).join("、")||"无"}（已保存在 nashsu，未覆盖已有页面）。`,uuid:job.id.slice(0,32)},{signal});
   if(!result?.message_id||result.chat_id!==job.chat)throw Error('Delivery result unknown');return result.message_id;
  }});
 return{
  async accept(scope,url,signal){return this.acceptMessage({...scope},scope.MessageSidFull??scope.MessageSid,signal,url);},
  async acceptMessage(scope,id,signal,expectedURL){
   check(scope);if(!/^om_[\w-]+$/u.test(id??''))throw Error('Message ID required');
   const source=await feishu.getMessage(id,{signal});
   if(source.message_id!==id||source.chat_id!==scope.NativeChannelId||source.sender?.id!==scope.SenderId||source.sender.id_type!=='open_id'||source.sender.sender_type!=='user'||source.deleted)throw Error('Source mismatch');
   const parsed=parseCommand(JSON.parse(source.body.content).text);
   if(parsed?.action!=='record'||(expectedURL&&parsed.url!==expectedURL))throw Error('Source command mismatch');
   const items=parsed.items??[{url:parsed.url}],jobs=[];
   for(const [index,item] of items.entries()){
    const url=item.url??'https://text.personal-wiki.invalid/'+createHash('sha256').update(item.text).digest('hex');
    const taskId=createHash('sha256').update(config.accountId+':'+id+(index?':'+index:'')).digest('hex');
    jobs.push(await queue.enqueue({id:taskId,messageId:id,url,...(item.text!==undefined?{text:item.text}:{}),background:parsed.background??'',refresh:parsed.refresh===true,sender:scope.SenderId,chat:scope.NativeChannelId}));
   }
   return {...jobs[0],duplicate:jobs.every(j=>j.duplicate),jobs};
  },
  async status(scope,id){check(scope);const job=await queue.status(id);if(!job||job.sender!==scope.SenderId||job.chat!==scope.NativeChannelId)throw Error('Job not found');return{jobId:id,status:job.status,stage:job.stage,createdAt:job.createdAt,result:job.result??null,reason:job.failure??null,nextAttemptAt:job.nextAttemptAt??null,receiptConfirmed:Boolean(job.receiptId)};},
  async retryTranslation(scope,id){await this.status(scope,id);await queue.retry(id);return{jobId:id,status:'queued'};},
  start:queue.start,processJobs:queue.drain,
  async close(){await queue.close();await flash.close?.();}
 };
}
