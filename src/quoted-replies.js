import {join,resolve} from 'node:path';import {mkdir} from 'node:fs/promises';import {spawn} from 'node:child_process';import {saveJSON,optionalJSON} from './durable-files.js';import {hash,scopeKey} from './knowledge-query.js';
// Called only after original user message and the replied-to own-app message are verified.
export async function openQuotedReplies({stateDir,python,api,knowledge,store}){
 const directory=join(stateDir,'reply-saves');await mkdir(directory,{recursive:true,mode:0o700});
 async function withLock(scope,run){
  const child=spawn(python,[resolve(import.meta.dirname,'../scripts/task_lock.py'),join(directory,scopeKey(scope)+'.lock')],{stdio:['pipe','pipe','pipe']});
  try{await new Promise((yes,no)=>{child.once('error',no);child.stdout.once('data',d=>d.toString().trim()==='ready'?yes():no(Error('保存正在处理中；稍后重发保存命令')));child.once('exit',()=>no(Error('保存锁不可用或正由另一进程处理')));});return await run();}finally{await new Promise(done=>{if(child.exitCode!==null||child.signalCode!==null)return done();child.once('exit',done);child.stdin.end();});}
 }
 return {async save(scope,parent,text,messageId,signal){return withLock(scope,async()=>{
  const path=join(stateDir,'reply-saves',scopeKey(scope)+'.json');const state=await optionalJSON(path)??{};
  let request=state[messageId];if(request&&request.parentId!==parent.message_id)throw Error('保存消息的回复目标已改变');
  if(!request){request=Object.values(state).find(r=>r.parentId===parent.message_id);if(request){state[messageId]=request;await saveJSON(path,state);}}
  if(!request){request=state[messageId]={parentId:parent.message_id,key:hash(scopeKey(scope)+parent.message_id+hash(parent.body.content)),parent,text,status:'publication_pending'};await saveJSON(path,state);}
  if(request.result)return request.result;
  const client=await api(signal);await client.assertPublisherReady?.();
  const result=await store({operation:'quoted-reply',key:request.key,message:request.parent,text:request.text});
  request.status='verification_pending';await saveJSON(path,state);
  for(const page of result.pages)if(hash(await client.read(page.path))!==page.hash)throw Error('被回复内容已保留，API核验待完成；重发“小婕 wk 保存”恢复');
  const found=await client.search(result.path.split('/').at(-1).replace(/\.md$/,''));if(!found.results?.some(x=>(x.path??x.file_path??x.filePath)===result.path))throw Error('正文已保留，搜索核验待完成；重发“小婕 wk 保存”恢复');
  const id=await knowledge.register(scope,result.path,'保存的模型回复');
  request.status='complete';request.result={readingId:id,text:`【Wiki】已原样保存被回复的内容，并通过 nashsu 读搜核验。\n标注为模型回复；其中政策、数字和建议未经 Wiki 来源核验，不作为作者证据。\n小婕 wk 阅读：${id} 1`};await saveJSON(path,state);return request.result;
 });}};
}
