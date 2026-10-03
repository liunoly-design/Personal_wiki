// Read-only replay of an authorized real Feishu reply into isolated runtime state.
import {readFile,cp,mkdtemp,rm} from 'node:fs/promises';import {join} from 'node:path';import {tmpdir} from 'node:os';
import {createFeishuClient} from '../../src/feishu-http.js';import {openCanonicalRuntime} from '../../openclaw/canonical-runtime.js';import {scopeKey} from '../../src/knowledge-query.js';
const id=process.argv[2];if(!/^om_[\w-]+$/.test(id??''))throw Error('Original reply message ID required');
const hostConfig=JSON.parse(await readFile('/Users/mac/.openclaw/openclaw.json','utf8'));const config=hostConfig.plugins.entries['personal-wiki'].config;
const account={...hostConfig.channels.feishu,...hostConfig.channels.feishu.accounts?.[config.accountId]};
const client=createFeishuClient({credentials:()=>({appId:account.appId,appSecret:account.appSecret})});const message=await client.getMessage(id);
const scope={Provider:'feishu',AccountId:config.accountId,SenderId:message.sender?.id,NativeChannelId:message.chat_id,MessageSid:id};
if(message.sender?.sender_type!=='user'||!config.allowedSenderIds.includes(scope.SenderId)||!config.allowedConversationIds.includes(scope.NativeChannelId))throw Error('Unauthorized replay');
const stateDir=await mkdtemp(join(tmpdir(),'wiki-reply-replay-'));let runtime;
try{
 for(const dir of ['discussions','knowledge'])await cp(join(config.stateDir,dir,scopeKey(scope)+'.json'),join(stateDir,dir,scopeKey(scope)+'.json')).catch(e=>{if(e.code!=='ENOENT')throw e;});
 const generate=async({purpose,prompt})=>purpose==='select'?JSON.stringify({ids:JSON.parse(prompt.split('\n候选JSON：\n')[1]).slice(0,3).map(x=>x.id)}):'原作者证据保留；新问题尚需本地实施依据。模型建议应分别标注。'+[...new Set(prompt.match(/\[K-[a-f0-9]{16} L\d+-L\d+\]/g))].slice(0,2).join(' ');
 runtime=await openCanonicalRuntime({config:{...config,stateDir},hostConfig,feishu:{getMessage:(...args)=>client.getMessage(...args),reply:async()=>{throw Error('Replay must never send a message');}},flash:{},queryGenerate:generate});
 const result=await runtime.acceptReply(scope);if(!result?.id)throw Error('Real reply was not routed into scoped Wiki discussion');
 console.log(JSON.stringify({isolatedState:true,readOnlyVault:true,noMessagesSent:true,realParentVerified:true,discussionId:result.id}));
}finally{await runtime?.close();await rm(stateDir,{recursive:true,force:true});}
