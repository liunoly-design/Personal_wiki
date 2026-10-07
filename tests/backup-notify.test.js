import test from 'node:test';
import assert from 'node:assert/strict';
import { backupNotification } from '../src/backup-notify.js';

const scope = {accountId:'default', senderId:'ou_user', chatId:'oc_private'};
const hostConfig = {
  plugins:{entries:{'personal-wiki':{enabled:true,config:{accountId:'default',allowedSenderIds:['ou_user'],allowedConversationIds:['oc_private']}}}},
  channels:{feishu:{enabled:true,accounts:{default:{appId:'cli_selected',appSecret:'synthetic-secret'}}}},
};
const request = {action:'send',text:'合成备份失败',uuid:'a'.repeat(32)};
const message = {message_id:'om_test',chat_id:'oc_private',msg_type:'text',deleted:false,
 sender:{id:'cli_selected',id_type:'app_id',sender_type:'app'},body:{content:JSON.stringify({text:request.text})}};

test('send uses only the selected scope and verification reads exact application/chat/text',async()=>{
 let sent;
 const client={send:async value=>{sent=value;return {message_id:'om_test',chat_id:'oc_private'};},getMessage:async()=>message};
 assert.deepEqual(await backupNotification({hostConfig,scope,request,client}),{status:'sent',messageId:'om_test'});
 assert.deepEqual(sent,{chatId:scope.chatId,text:request.text,uuid:request.uuid});
 assert.deepEqual(await backupNotification({hostConfig,scope,request:{...request,action:'verify',messageId:'om_test'},client}),{status:'verified',messageId:'om_test'});
});

test('scope changes reject before sending; readback rejects foreign sender, chat or content',async()=>{
 let calls=0;
 const client={send:async()=>{calls++;},getMessage:async()=>message};
 await assert.rejects(backupNotification({hostConfig,scope:{...scope,chatId:'oc_other'},request,client}));
 assert.equal(calls,0);
 for(const changed of [{...message,chat_id:'oc_other'},{...message,sender:{...message.sender,id:'cli_other'}},{...message,body:{content:'{"text":"different"}'}},{...message,deleted:true}]){
  await assert.rejects(backupNotification({hostConfig,scope,request:{...request,action:'verify',messageId:'om_test'},client:{getMessage:async()=>changed}}));
 }
});
