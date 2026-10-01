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
  run:(job,workspace,signal,onStage,previousResult)=>collect({url:job.url,vault:config.vault,workspace,python:config.python,flash,codexBinary:config.codexBinary,compilerModel:config.compilerModel,signal,onStage,previousResult}),
  deliver:async(job,signal)=>{
   const result=await feishu.reply({replyTo:job.messageId,text:`【Wiki】记录完成，已通过 nashsu API 核验。\n正文：${job.result.source}\n原文、图片与附件已归档；处理临时文件已清理。\n待审修改：${job.result.reviews?.length??0} 项（已保存在 nashsu，未覆盖已有页面）。`,uuid:job.id.slice(0,32)},{signal});
   if(!result?.message_id||result.chat_id!==job.chat)throw Error('Delivery result unknown');return result.message_id;
  }});
 return{
  async accept(scope,url,signal){
   check(scope);const id=scope.MessageSidFull??scope.MessageSid;if(!/^om_[\w-]+$/u.test(id??''))throw Error('Message ID required');
   const source=await feishu.getMessage(id,{signal});
   if(source.message_id!==id||source.chat_id!==scope.NativeChannelId||source.sender?.id!==scope.SenderId||source.sender.id_type!=='open_id'||source.sender.sender_type!=='user'||source.deleted)throw Error('Source mismatch');
   const parsed=parseCommand(JSON.parse(source.body.content).text);if(parsed?.action!=='record'||parsed.url!==url)throw Error('Source command mismatch');
   return queue.enqueue({id:createHash('sha256').update(config.accountId+':'+id).digest('hex'),messageId:id,url,sender:scope.SenderId,chat:scope.NativeChannelId});
  },
  async acceptMessage(scope,id,signal){check(scope);const source=await feishu.getMessage(id,{signal});const parsed=parseCommand(JSON.parse(source.body.content).text);if(parsed?.action!=='record')throw Error('Source command mismatch');return this.accept({...scope,MessageSid:id},parsed.url,signal);},
  async status(scope,id){check(scope);const job=await queue.status(id);if(!job||job.sender!==scope.SenderId||job.chat!==scope.NativeChannelId)throw Error('Job not found');return{jobId:id,status:job.status,stage:job.stage,createdAt:job.createdAt,result:job.result??null,reason:job.failure??null,nextAttemptAt:job.nextAttemptAt??null,receiptConfirmed:Boolean(job.receiptId)};},
  async retryTranslation(scope,id){await this.status(scope,id);await queue.retry(id);return{jobId:id,status:'queued'};},
  start:queue.start,processJobs:queue.drain,
  async close(){await queue.close();await flash.close?.();}
 };
}
