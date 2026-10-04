import {readFile,readdir} from 'node:fs/promises';
import {join,isAbsolute,resolve,relative} from 'node:path';
import {createHash} from 'node:crypto';
import {openTaskQueue} from '../src/task-queue.js';
import {collectCanonical} from '../src/canonical-library.js';
import {messageText} from '../src/feishu-message.js';
import {openQuotedReplies} from '../src/quoted-replies.js';
import {parseCommand} from '../src/wk.js';
import {createFlash} from '../src/flash.js';
import {openKnowledgeQuery} from '../src/knowledge-query.js';
import {openReviewService,createReviewStore} from '../src/review-service.js';
import {localNashsuAPI} from '../src/nashsu-api.js';
import {openDiscussion} from '../src/discussion.js';
import {createCodex} from '../src/codex.js';
import {createFeishuClient} from '../src/feishu-http.js';
const shellQuote=value=>"'"+value.replaceAll("'", "'\"'\"'")+"'";
function loginCommand(job,config){const profile=join(config.stateDir,'browser',createHash('sha256').update(job.sender+':'+job.chat).digest('hex').slice(0,16),new URL(job.url).hostname);return [config.python,resolve(import.meta.dirname,'../scripts/browser_session.py'),'--login','--url',job.url,'--profile',profile].map(shellQuote).join(' ');}
function waitingText(job,config){
 const assets=job.result?.missingAssets??[];
 const video=job.result?.video??job.details?.video;
 const videoText=video?`\n视频：${video.video??'已保存'}；完整音频：${video.audio??'已保存'}；全文：${video.transcriptStatus??(typeof video.transcript==='string'?video.transcript:'尚未完成')}；知识处理：${video.knowledgeStatus??video.knowledge??'尚未完成'}\n${job.status==='waiting_unknown'?'上次云请求可能已执行；显式继续可能再次消耗额度。':''}`:'';
 const lines=assets.map(a=>`${a.id} ${a.kind}: ${a.status} ${a.error??''}\n`+(a.status==='waiting_confirmation'?`小婕 wk 确认视频：${job.id} ${a.id} ${a.fingerprint}`:`小婕 wk 补附件：${job.id} ${a.id}`));
 return `【Wiki】${job.stage==='video_cleanup'?'归档完成，临时清理待恢复':job.result?.source?'部分完成，正文已核验：'+job.result.source:'本项尚未完成：'+job.url}\n任务：${job.id}\n状态：${job.status}${videoText}\n${job.status==='waiting_login'?'请在本机专用Wiki浏览器中完成该平台登录/验证码（见0.4.2验收文档），然后发送：小婕 wk 登录继续：'+job.id:lines.length?lines.join('\n'):'外部条件恢复后发送：小婕 wk 继续：'+job.id}\n${job.status==='waiting_login'?'本机终端打开专用登录窗口：\n'+loginCommand(job,config):''}\n已取得资料、成功附件和进度保留。状态：小婕 wk 状态：${job.id}`;
}
export async function openCanonicalRuntime({config,hostConfig,feishu:injectedFeishu,flash:injectedFlash,collect=collectCanonical,nashsu,queryGenerate,store}){
 for(const key of ['vault','stateDir','python'])if(!isAbsolute(config[key]??''))throw Error('Absolute paths required');
 const account={...hostConfig.channels?.feishu,...hostConfig.channels?.feishu?.accounts?.[config.accountId]};
 if(!injectedFeishu&&(account.enabled===false||(account.domain&&account.domain!=='feishu')))throw Error('Feishu account unavailable');
 const feishu=injectedFeishu??createFeishuClient({credentials:()=>({appId:account.appId,appSecret:account.appSecret})});
 const flash=injectedFlash??createFlash({proxyUrl:config.flashProxyUrl,model:config.flashModel??'gemini-flash-latest',maxAttempts:1,usagePath:join(config.stateDir,'flash-usage.jsonl')});
 const api=nashsu??(signal=>localNashsuAPI(config.vault,{signal,maxAttempts:1}));
 const notes=async scope=>{const found=[];for(const dir of ['tasks','completed'])for(const name of await readdir(join(config.stateDir,dir))){if(!/^[a-f0-9]{64}\.json$/.test(name))continue;const j=JSON.parse(await readFile(join(config.stateDir,dir,name),'utf8'));if(j.sender!==scope.SenderId||j.chat!==scope.NativeChannelId||!j.result?.userRecord)continue;const path=relative(config.vault,j.result.userRecord);const source=relative(config.vault,j.result.source);if(/^wiki\/queries\/user-note-[a-f0-9]{64}\.md$/.test(path))found.push({path,source});}return found;};
 const generate=queryGenerate??createCodex({binary:config.codexBinary,model:config.compilerModel,textOnly:true,timeoutMs:120000});
 const knowledge=await openKnowledgeQuery({stateDir:config.stateDir,api,notes,generate});
 const publicationStore=store??createReviewStore(config);
 const reviews=await openReviewService({stateDir:config.stateDir,api,notes,knowledge,store:publicationStore});
 const discussions=await openDiscussion({stateDir:config.stateDir,python:config.python,knowledge,generate,api,reviews,store:publicationStore,model:config.compilerModel??'gpt-6-sol'});
 const quoted=await openQuotedReplies({stateDir:config.stateDir,python:config.python,api,knowledge,store:publicationStore});
 const allowed=job=>config.allowedSenderIds.includes(job.sender)&&config.allowedConversationIds.includes(job.chat);
 function check(scope){if(scope.Provider!=='feishu'||scope.AccountId!==config.accountId||!allowed({sender:scope.SenderId,chat:scope.NativeChannelId}))throw Error('Wiki scope denied');}
 const queue=await openTaskQueue({stateDir:config.stateDir,python:config.python,allowed,
  run:(job,workspace,signal,onStage,previousResult)=>collect({url:job.url,text:job.text,inputError:job.inputError,background:job.background,requestId:job.id,refresh:job.refresh,vault:config.vault,workspace,python:config.python,flash,codexBinary:config.codexBinary,compilerModel:config.compilerModel,signal,onStage,previousResult,mediaAction:job.mediaAction,mediaApprovals:job.mediaApprovals,videoMode:job.videoMode,videoRecovery:job.videoRecovery,stateDir:config.stateDir,asrBinary:config.asrBinary,browserProfile:job.browserAuthorization?join(config.stateDir,'browser',createHash('sha256').update(job.sender+':'+job.chat).digest('hex').slice(0,16),new URL(job.url).hostname):undefined}),
  notifyWaiting:async(job,signal)=>{
   const reply=await feishu.reply({replyTo:job.messageId,text:waitingText(job,config),uuid:createHash('sha256').update(job.id+':waiting:'+String(job.controlMessages?.length??0)).digest('hex').slice(0,32)},{signal});
   if(!reply?.message_id||reply.chat_id!==job.chat)throw Error('Delivery result unknown');return reply.message_id;
  },
  deliver:async(job,signal)=>{
   const reviewIds=job.result.reviews?.length?await reviews.discover({SenderId:job.sender,NativeChannelId:job.chat},job.result.reviews):[];
   const result=await feishu.reply({replyTo:job.messageId,text:`【Wiki】记录完成，已通过 nashsu API 核验。\n标题：${job.result.title??"见来源卡"}\n摘要：${job.result.summary??"见来源卡"}\n正文：${job.result.source}\n${job.result.attachmentStatus==='partial'?'部分完成：正文已保存，附件缺失 '+(job.result.missingAssets?.length??0)+' 项。':'附件已核验。'}\n${job.result.contextStatus==='partial'?'上下文部分完成：'+job.result.contextGaps.join('；'):''}\n${job.result.supplements?.length?'补充附件：'+job.result.supplements.join('、'):''}\n${job.result.userRecord?'个人背景：'+job.result.userRecord:''}\n${job.result.video?`视频：${job.result.video.mode==='compressed'?'压缩归档（最高720p）':'原画质下载流（最高1080p）'}；完整音频与全文已核验。\n临时清理：${job.result.video.cleanup?.status??'待恢复'}；媒体入口：${job.result.video.mediaPublication.supplement}`:'已取得的原文与附件已归档；处理临时文件已清理。'}\n待审修改：${job.result.reviews?.length??0} 项：${reviewIds.join("、")||"无"}（查看：小婕 wk 待审：；尚未应用）。`,uuid:job.id.slice(0,32)},{signal});
   if(!result?.message_id||result.chat_id!==job.chat)throw Error('Delivery result unknown');return result.message_id;
  }});
 async function acceptMessage(scope,id,signal,expectedURL,expectedActions,implicitOnly=false){
   check(scope);if(!/^om_[\w-]+$/u.test(id??''))throw Error('Message ID required');
   let source;try{source=await feishu.getMessage(id,{signal});}catch(error){if(implicitOnly)return null;throw error;}
   if(implicitOnly&&(!source.parent_id||!['text','post',undefined].includes(source.msg_type)))return null;
   if(source.message_id!==id||source.chat_id!==scope.NativeChannelId||source.sender?.id!==scope.SenderId||source.sender.id_type!=='open_id'||source.sender.sender_type!=='user'||source.deleted)throw Error('Source mismatch');
   let userText;try{userText=messageText(source);}catch(error){if(implicitOnly)return null;throw error;}let parsed=parseCommand(userText);
   if(parsed?.action==='reply'||!parsed){
    if(!source.parent_id){if(parsed?.action==='reply')throw Error('请在飞书回复要保存的那条消息，再发送“小婕 wk 保存”');return null;}
    let parent;try{parent=await feishu.getMessage(source.parent_id,{signal});}catch(error){if(implicitOnly)return null;throw error;}
    if(parent.message_id!==source.parent_id||parent.chat_id!==scope.NativeChannelId||parent.deleted||parent.sender?.sender_type!=='app'||parent.sender?.id_type!=='app_id'||!account.appId||parent.sender?.id!==account.appId){if(parsed?.action==='reply')throw Error('只能保存当前授权会话中小婕发送的被回复消息');return null;}
    let parentText;try{parentText=messageText(parent);}catch(error){if(implicitOnly)return null;throw error;}
    if(parsed?.action==='reply'){if(expectedActions&&!expectedActions.includes('reply')&&!expectedActions.includes('discuss'))throw Error('Source command mismatch');const topicId=await discussions.resolveReply(scope,parentText);return quoted.save(scope,parent,parentText,id,signal,topicId,topicId?await discussions.legacyBinding(scope,topicId):undefined);}
    const discussionId=await discussions.resolveReply(scope,parentText);if(!discussionId)return null;
    parsed=parseCommand(`小婕 wk 讨论：${discussionId} ${userText}`);if(parsed?.action!=='discuss')throw Error('追问太长或格式不正确；请使用明确讨论命令');
   }
   if(expectedActions&&!expectedActions.includes(parsed?.action))throw Error('Source command mismatch');
   if(parsed?.action==='discuss')return discussions.execute(scope,parsed,id,signal);
   if(parsed?.action==='query')return knowledge.query(scope,parsed,signal);
   if(parsed?.action==='read')return knowledge.read(scope,parsed.id,parsed.start,signal);
   if(parsed?.action==='review'){if(parsed.mode==='list')return reviews.list(scope,parsed.start,signal);if(parsed.mode==='detail')return reviews.detail(scope,parsed.id,signal);const created=Number(source.create_time);if(!Number.isSafeInteger(created)||created<1)throw Error('Cannot verify approval timestamp; send a new command');return reviews.action(scope,parsed.id,parsed.mode,id,signal,created);}
   if(parsed?.action==='control'){
    const current=await this.status(scope,parsed.jobId);
    if(current.controlMessageIds.includes(id))return{...current,duplicate:true};
    if(parsed.mode==='状态')return current;
    const changes={controlMessageId:id,...(current.video?{videoRecovery:{messageId:id,at:new Date().toISOString(),unknownReplayRisk:current.status==='waiting_unknown'}}:{})};
    if(parsed.mode==='登录继续'){
     if(current.status!=='waiting_login'||!['x.com','mp.weixin.qq.com'].includes(new URL(current.url).hostname))throw Error('Task is not waiting for supported login');
     if(current.result?.resumableMedia){const asset=current.result.missingAssets.find(a=>a.status==='waiting_login');if(asset)changes.mediaAction={assetId:asset.id,resetAttempts:true,cycle:id};}
     changes.browserAuthorization={messageId:id,sender:scope.SenderId,chat:scope.NativeChannelId,source:current.url,at:new Date().toISOString()};
    }else if(current.status==='waiting_login')throw Error('请先完成专用浏览器登录，再发送登录继续');
    if(['补附件','确认视频'].includes(parsed.mode)){
     const asset=current.result?.missingAssets?.find(a=>a.id===parsed.assetId);if(!asset)throw Error('Attachment is not pending');
     changes.mediaAction={assetId:parsed.assetId,resetAttempts:true,cycle:id};
     if(parsed.mode==='确认视频'){
      if(asset.kind!=='video'||asset.status!=='waiting_confirmation'||asset.fingerprint!==parsed.fingerprint)throw Error('Video confirmation does not match pending attachment');
      changes.mediaApprovals={...current.mediaApprovals,[asset.id]:{fingerprint:asset.fingerprint,messageId:id,sender:scope.SenderId,chat:scope.NativeChannelId,jobId:parsed.jobId,at:new Date().toISOString()}};
     }
    }else if(parsed.mode!=='登录继续'&&current.result?.resumableMedia&&current.result.status==='partial')throw Error('请按附件ID补附件或确认视频');
    await queue.retry(parsed.jobId,changes);return{jobId:parsed.jobId,status:'queued'};
   }
   if(parsed?.action!=='record' ||(expectedURL&&parsed.url!==expectedURL))throw Error('Source command mismatch');
   const items=parsed.items??[{url:parsed.url}],jobs=[];
   for(const [index,item] of items.entries()){
    const url=item.url??'https://'+(item.inputError?'invalid':'text')+'.personal-wiki.invalid/'+createHash('sha256').update(item.text??('invalid-'+id+'-'+index)).digest('hex');
    const taskId=createHash('sha256').update(config.accountId+':'+id+(index?':'+index:'')).digest('hex');
    jobs.push(await queue.enqueue({id:taskId,messageId:id,url,itemIndex:index+1,...(item.inputError?{inputError:item.inputError}:{}),...(item.text!==undefined?{text:item.text}:{}),videoMode:parsed.videoMode,background:parsed.background??'',refresh:parsed.refresh===true,sender:scope.SenderId,chat:scope.NativeChannelId}));
   }
   return {...jobs[0],duplicate:jobs.every(j=>j.duplicate),jobs};
  }
 let controlIngress=Promise.resolve();
 return{
  async acceptReply(scope,signal){return this.acceptMessage(scope,scope.MessageSidFull??scope.MessageSid,signal,undefined,['discuss'],true);},
  async accept(scope,url,signal){return this.acceptMessage({...scope},scope.MessageSidFull??scope.MessageSid,signal,url);},
  acceptMessage(...args){const next=controlIngress.then(()=>acceptMessage.apply(this,args));controlIngress=next.catch(()=>{});return next;},
  knowledgeMessage(scope,id,kind,signal){const actions={discuss:['discuss','reply'],query:['query'],read:['read'],review:['review']}[kind];if(!actions)throw Error('Unknown knowledge tool');return this.acceptMessage(scope,id,signal,undefined,actions);},
  async status(scope,id){check(scope);const job=await queue.status(id);if(!job||job.sender!==scope.SenderId||job.chat!==scope.NativeChannelId)throw Error('Job not found');return{jobId:id,url:job.url,...(job.status==='waiting_login'?{loginCommand:loginCommand(job,config)}:{}),controlMessageIds:job.controlMessages??[],mediaApprovals:job.mediaApprovals??{},video:job.result?.video??job.details?.video??null,status:job.status,stage:job.stage,createdAt:job.createdAt,result:job.result??null,reason:job.failure??null,nextAttemptAt:job.nextAttemptAt??null,receiptConfirmed:Boolean(job.receiptId)};},
  async retryTranslation(scope,id){const job=await this.status(scope,id);if(['waiting_login','waiting_confirmation','waiting_media'].includes(job.status))throw Error('Use the explicit recovery command');await queue.retry(id);return{jobId:id,status:'queued'};},
  start:queue.start,processJobs:queue.drain,
  async close(){await queue.close();await flash.close?.();}
 };
}
