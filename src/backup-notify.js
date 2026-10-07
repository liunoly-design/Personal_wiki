import {createFeishuClient,resolveWikiFeishuAccount} from './feishu-http.js';

/** Narrow notification boundary: only the configured Wiki account and private chat. */
export async function backupNotification({hostConfig,scope,request,client}) {
 const wiki=hostConfig.plugins?.entries?.['personal-wiki'];
 const config=wiki?.config;
 if(wiki?.enabled!==true || !config || config.accountId!==scope.accountId ||
    config.allowedSenderIds?.length!==1 || config.allowedSenderIds[0]!==scope.senderId ||
    config.allowedConversationIds?.length!==1 || config.allowedConversationIds[0]!==scope.chatId ||
    !/^ou_[\w-]+$/u.test(scope.senderId) || !/^oc_[\w-]+$/u.test(scope.chatId)) throw Error('Backup notification scope unavailable');
 const account=resolveWikiFeishuAccount(hostConfig,scope.accountId,{explicit:true});
 if(account.enabled===false || hostConfig.channels?.feishu?.enabled!==true ||
    (account.domain && account.domain!=='feishu') || !account.appId || !account.appSecret) throw Error('Backup notification account unavailable');
 if(!['send','verify'].includes(request.action) || typeof request.text!=='string' || !request.text || request.text.length>4000 ||
    !/^[a-f0-9]{32}$/u.test(request.uuid)) throw Error('Invalid notification request');
 const api=client??createFeishuClient({credentials:()=>account});
 if(request.action==='send') {
  const sent=await api.send({chatId:scope.chatId,text:request.text,uuid:request.uuid});
  if(!/^om_[\w-]+$/u.test(sent?.message_id) || sent.chat_id!==scope.chatId) throw Error('Notification send result unknown');
  return {status:'sent',messageId:sent.message_id};
 }
 if(!/^om_[\w-]+$/u.test(request.messageId)) throw Error('Invalid notification message ID');
 const message=await api.getMessage(request.messageId);
 if(message.message_id!==request.messageId || message.chat_id!==scope.chatId || message.deleted===true ||
    message.msg_type!=='text' || message.sender?.id_type!=='app_id' || message.sender?.sender_type!=='app' ||
    message.sender?.id!==account.appId || JSON.parse(message.body?.content??'null')?.text!==request.text) throw Error('Notification readback differs');
 return {status:'verified',messageId:request.messageId};
}
