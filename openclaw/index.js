import {parseCommand} from '../src/wk.js';
import {openRuntime as defaultOpenRuntime} from './runtime.js';
import {registerWikiTools} from './tools.js';
export function createPlugin({openRuntime=defaultOpenRuntime}={}){
 return {id:'personal-wiki',name:'Personal Wiki',register(api){
  const config=api.pluginConfig??{};if(config.enabled!==true)return;
  if(!config.allowedSenderIds?.length||!config.allowedConversationIds?.length||!config.accountId||!config.entryAgentId)throw Error('Wiki requires explicit Feishu scope');
  let pending;
  const runtime=()=>pending??=openRuntime({config,hostConfig:api.config});
  registerWikiTools(api,config,runtime);
  api.registerService({id:'personal-wiki',async start(){await (await runtime()).start();},async stop(){if(pending)await (await pending).close();}});
  api.on('reply_dispatch',async(event,ctx)=>{
   const c=event.ctx;
   if(c.Provider!=='feishu'||c.AccountId!==config.accountId||c.AgentId!==config.entryAgentId||c.SenderIsBot||!config.allowedSenderIds.includes(c.SenderId)||!config.allowedConversationIds.includes(c.NativeChannelId))return;
   const command=parseCommand(c.rawText??c.RawBody);if(!command)return;
   const finish=(text)=>{const queuedFinal=text?ctx.dispatcher.sendFinalReply({text}):false;ctx.recordProcessed('completed',{reason:'personal_wiki'});ctx.markIdle('message_completed');return {handled:true,queuedFinal,counts:ctx.dispatcher.getQueuedCounts()};};
   if(event.sendPolicy!=='allow'||event.suppressUserDelivery||event.suppressReplyLifecycle||event.shouldRouteToOriginating||event.isTailDispatch||ctx.abortSignal?.aborted)return finish();
   if(command.action==='reserved')return finish(`【Wiki】“${command.mode}”已预留，暂未开放。目前请使用：小婕 wk 记录：链接`);
   if(command.action==='invalid')return finish('【Wiki】请使用“小婕收集：内容”或“小婕 wk 记录：链接”，支持公开博客、X、微信、多链接及粘贴文本；个人说明请用“备注：”。');
   try{
    const result=await (await runtime()).accept(c,command.url,ctx.abortSignal);
    if(['query','read','review'].includes(command.action))return finish(result.text);
    if(command.action==='control')return finish(`【Wiki】任务：${result.jobId}\n状态：${result.status}\n${result.result?.source?'正文：'+result.result.source:''}\n${result.reason??''}\n${result.loginCommand?'本机打开登录窗口：\n'+result.loginCommand:''}\n${(result.result?.missingAssets??[]).map(a=>`${a.id} ${a.kind} ${a.status}`+(a.status==='waiting_confirmation'?`\n小婕 wk 确认视频：${result.jobId} ${a.id} ${a.fingerprint}`:`\n小婕 wk 补附件：${result.jobId} ${a.id}`)).join('\n')}`);
    return finish(result.duplicate?'【Wiki】这条消息已接收，请勿重复提交；结果以完成回执为准。':'【Wiki】收到，开始采集。任务：'+(result.jobs??[result]).map(j=>j.jobId).join('、')+'。写入资料库并核验后回复结果。');
   }catch(error){const known=['Source mismatch','Source command mismatch','Message ID required','Resolved Feishu credentials required','Feishu request failed or result unknown'];if(['query','read','review'].includes(command.action))return finish('【Wiki】本次未完成：'+(error?.message??'本机API或模型不可用')+'；未自动批准或切换付费服务。');if(command.action==='control')return finish('【Wiki】续作未受理：'+(error?.message??'未知错误'));const reason=known.includes(error?.message)?error.message:'Local runtime unavailable';api.logger.warn('personal-wiki: could not accept request: '+reason);return finish('【Wiki】本次未确认接收，请检查插件配置及处理记录。');}
  },{priority:110,eligibleDispatchKinds:['agent']});
 }};
}
export default createPlugin();
