export function registerWikiTools(api,config,runtime){
 api.registerTool(context=>{
  if(context.agentId!==(config.wikiAgentId??'wiki')||context.messageChannel!=='feishu'||context.agentAccountId!==config.accountId||!config.allowedSenderIds.includes(context.requesterSenderId)||!config.allowedConversationIds.includes(context.nativeChannelId))return null;
  const scope={Provider:'feishu',AccountId:context.agentAccountId,SenderId:context.requesterSenderId,NativeChannelId:context.nativeChannelId};
  const result=value=>({content:[{type:'text',text:JSON.stringify(value)}]});
  return [
   {name:'wiki_resume',label:'Wiki 续作',description:'用户明确发送状态、继续、登录继续、补附件或确认视频命令时，只传原消息ID；服务端回读鉴权并精确匹配任务附件与指纹，不能用模型自行确认。',parameters:{type:'object',properties:{messageId:{type:'string',pattern:'^om_[A-Za-z0-9_-]+$'}},required:['messageId'],additionalProperties:false},async execute(_id,args,signal){context.assertInvocationCurrent?.();return result(await (await runtime()).acceptMessage(scope,args.messageId,signal));}},
   {name:'wiki_record',label:'Wiki 记录',description:'接收当前会话中用户明确发出的 Wiki 收集指令。只提供原消息 ID；服务器验证原文并确定来源。返回持久任务编号。',parameters:{type:'object',properties:{messageId:{type:'string',pattern:'^om_[A-Za-z0-9_-]+$'}},required:['messageId'],additionalProperties:false},async execute(_id,args,signal){context.assertInvocationCurrent?.();return result(await (await runtime()).acceptMessage(scope,args.messageId,signal));}},
   {name:'wiki_status',label:'Wiki 进度',description:'读取当前发送者与会话的 Wiki 收集任务实际进度、结果和待处理状态。',parameters:{type:'object',properties:{jobId:{type:'string',pattern:'^[a-f0-9]{64}$'}},required:['jobId'],additionalProperties:false},async execute(_id,args){context.assertInvocationCurrent?.();return result(await (await runtime()).status(scope,args.jobId));}},
   {name:'wiki_retry_translation',label:'Wiki 补译',description:'用户明确要求补译时，仅恢复当前会话收集任务未完成的中文阅读，不重新采集或编译，不为旧归档补译。',parameters:{type:'object',properties:{jobId:{type:'string',pattern:'^[a-f0-9]{64}$'}},required:['jobId'],additionalProperties:false},async execute(_id,args,signal){context.assertInvocationCurrent?.();return result(await (await runtime()).retryTranslation(scope,args.jobId,signal));}},
  ];
 },{names:['wiki_resume','wiki_record','wiki_status','wiki_retry_translation']});
}
