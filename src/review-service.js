import {join,resolve} from 'node:path';
import {saveJSON,optionalJSON} from './durable-files.js';import {hash,scopeKey} from './knowledge-query.js';

import {spawn} from 'node:child_process';
export function createReviewStore({vault,python}){return input=>new Promise((accept,reject)=>{
 const child=spawn(python,[resolve(import.meta.dirname,'../scripts/review_store.py')],{stdio:['pipe','pipe','pipe'],timeout:30000});let out='',err='';
 child.stdout.on('data',x=>out+=x);child.stderr.on('data',x=>err+=x);child.on('error',reject);child.stdin.on('error',reject);
 child.on('close',code=>{if(code)return reject(Error(err.split('\n').filter(x=>/ValueError:/.test(x)).at(-1)?.replace('ValueError: ','')??'Protected review operation failed'));try{accept(JSON.parse(out));}catch(e){reject(e);}});child.stdin.end(JSON.stringify({...input,vault}));
 });}
const nativeFingerprint=item=>hash(JSON.stringify(Object.fromEntries(Object.entries(item).filter(([k])=>!['resolved','resolvedAction','resolvedAt'].includes(k)).sort(([a],[b])=>a.localeCompare(b)))));
export async function openReviewService({stateDir,api,store,notes=async()=>[]}){
 const directory=join(stateDir,'reviews');const registry=scope=>join(directory,'scopes',scopeKey(scope)+'.json');
 const actionPath=id=>join(directory,'actions',id+'.json');
 let ingress=Promise.resolve();const serial=fn=>{const next=ingress.then(fn);ingress=next.catch(()=>{});return next;};
 async function mayView(scope,item){const text=JSON.stringify(item);const owned=new Set((await notes(scope)).map(n=>n.path));const references=[...text.matchAll(/wiki\/queries\/[^"\s)<>]+/g)].map(m=>m[0]);if(references.some(p=>!/^wiki\/queries\/review-[a-f0-9]{16}\.md$/.test(p)&&!owned.has(p)))return false;const notesMentioned=[...text.matchAll(/user-note-[a-f0-9]+\.md/g)].map(m=>'wiki/queries/'+m[0]);if(notesMentioned.some(p=>!owned.has(p)))return false;return !/(?:type["\s:]+(?:personal-note|private-note)|个人备注与背景)/iu.test(text)||notesMentioned.length>0&&notesMentioned.every(p=>owned.has(p));}
 async function get(scope,id){if(!/^R-[a-f0-9]{16}$/.test(id??''))throw Error('Review not found');const item=(await optionalJSON(registry(scope)))?.[id];if(!item||!await mayView(scope,item))throw Error('Review not found');return item;}
 async function current(item,client){if(item.kind==='native'){const match=(await client.reviews()).reviews?.find(x=>x.id===item.nativeId);if(!match)throw Error('Review no longer exists');return {...item,content:match,fingerprint:nativeFingerprint(match)};}const p=await store({operation:'detail',id:item.proposalId});return {...item,...p,fingerprint:p.proposalHash+':'+(p.metadataHash??'none')};}
 async function list(scope,start=1,signal){
  if(!Number.isSafeInteger(start)||start<1)throw Error('Invalid review page');
  const client=await api(signal);const native=await client.reviews();if(!Array.isArray(native.reviews))throw Error('Invalid native reviews');const local=await store({operation:'list'});
  const candidates=[...native.reviews.map(r=>({id:'R-'+hash('native:'+r.id).slice(0,16),kind:'native',nativeId:r.id,content:r,fingerprint:nativeFingerprint(r),risk:'原生建议缺少可信写入基线，仅查看、跳过或稍后'})),...local.reviews.map(r=>({...r,proposalId:r.id,id:'R-'+hash('markdown:'+r.id).slice(0,16),kind:'markdown',fingerprint:r.proposalHash+':'+(r.metadataHash??'none')}))];
  const items=[];for(const item of candidates)if(await mayView(scope,item))items.push(item);
  const saved=await optionalJSON(registry(scope))??{};for(const item of items)saved[item.id]={...item,presentedAt:saved[item.id]?.fingerprint===item.fingerprint?saved[item.id].presentedAt??Date.now():Date.now()};await saveJSON(registry(scope),saved);
  const visible=[];for(const item of items){const a=await optionalJSON(actionPath(item.id));visible.push({...item,status:a?.status??(item.content?.resolved?'native_resolved':'pending')});}
  const page=visible.slice(start-1,start+19);return {items:page,text:'【Wiki】待审（包含已处理项，编号稳定）：\n'+page.map((i,n)=>`${start+n}. ${i.id} ${i.kind} ${i.status} ${i.content?.title??i.metadata?.path??i.file}\n${i.risk}`).join('\n')+`\n共${items.length}项${start+20<=items.length?`；下一页：小婕 wk 待审：${start+20}`:''}${native.reviews.length>=1000?'；原生结果达到1000上限，可能截断':''}\n详情：小婕 wk 待审：R-编号`};
 }
 async function detail(scope,id,signal){const item=await current(await get(scope,id),await api(signal));if(!await mayView(scope,item))throw Error('Review not found');const saved=await optionalJSON(registry(scope));saved[id]={...item,presentedAt:saved[id]?.fingerprint===item.fingerprint?saved[id].presentedAt??Date.now():Date.now()};await saveJSON(registry(scope),saved);const state=await optionalJSON(actionPath(id));return {item,text:`【Wiki】${id}；${state?.status??'pending'}\n目标/来源/建议：\n${typeof item.content==='string'?item.content:JSON.stringify(item.content,null,2)}\n${item.metadata?'目标：'+item.metadata.path+'\n出处：'+item.metadata.sourceUrl+'\n应用方式：追加建议章节，保留现有全文\n':''}风险：${item.risk}\n小婕 wk 应用：${id}\n小婕 wk 跳过：${id}\n小婕 wk 稍后：${id}`};}
 async function action(scope,id,mode,messageId,signal,messageCreatedAt=Date.now()){
  if(!['应用','跳过','稍后'].includes(mode)||!/^om_[\w-]+$/.test(messageId??''))throw Error('Explicit source command required');
  const item=await get(scope,id);let saved=await optionalJSON(actionPath(id));
  const bindingPath=join(directory,'messages',scopeKey(scope),hash(messageId)+'.json');const binding=await optionalJSON(bindingPath);
  if(binding&&(binding.id!==id||binding.mode!==mode||binding.fingerprint!==item.fingerprint))throw Error('Approval message cannot be reused for a changed proposal/action');
  if(!binding)await saveJSON(bindingPath,{id,mode,fingerprint:item.fingerprint,createdAt:messageCreatedAt});
  const approvedAt=binding?.createdAt??messageCreatedAt;if(!Number.isFinite(approvedAt)||approvedAt<(item.presentedAt??0))throw Error('Approval predates displayed proposal; send a new command');

  if(['applied','skipped'].includes(saved?.status)){if(saved.mode!==mode)throw Error('Review already finalized');return{text:`【Wiki】${id} ${saved.status}（重复命令，无额外修改）`,status:saved.status};}
  if(saved&&['verification_pending','sync_pending','applying'].includes(saved.status)&&saved.mode!==mode)throw Error('Pending action must be recovered before changing action');
  const client=await api(signal);const latest=await current(item,client);if(!await mayView(scope,latest))throw Error('Review not found');
  if(latest.fingerprint!==item.fingerprint||(saved?.fingerprint&&!['deferred','blocked'].includes(saved.status)&&saved.fingerprint!==latest.fingerprint))throw Error('Proposal changed; view it again');
  if(mode==='应用'&&(latest.kind==='native'||!latest.metadata))throw Error('Missing safe baseline; legacy/native proposal cannot be applied');
  if(latest.kind==='native'&&latest.content.resolved&&!saved)throw Error('Native review already resolved');
  saved={...(saved??{}),mode,fingerprint:item.fingerprint,authorization:{messageId,sender:scope.SenderId,chat:scope.NativeChannelId,at:new Date().toISOString()},status:mode==='稍后'?'deferred':mode==='跳过'?'sync_pending':'applying'};await saveJSON(actionPath(id),saved);
  if(mode==='应用'){
   let result;try{result=await store({operation:'apply',id:latest.proposalId,proposalHash:latest.proposalHash,metadataHash:latest.metadataHash});}catch(error){const outcome=await store({operation:'outcome',id:latest.proposalId});if(outcome.safeToAbandon){saved.status='blocked';await saveJSON(actionPath(id),saved);}throw error;}saved={...saved,...result,status:'verification_pending'};await saveJSON(actionPath(id),saved);
   if(hash(await client.read(result.path))!==result.hash)throw Error('API verification failed; repeat application to recover');
   await store({operation:'finalize',id:latest.proposalId,hash:result.hash});saved.status='applied';
  }else if(mode==='跳过'){
   if(latest.kind==='native'){await client.patchReview(latest.nativeId,{resolved:true,action:'Skip'});const check=(await client.reviews()).reviews?.find(r=>r.id===latest.nativeId);if(!check?.resolved||check.resolvedAction!=='Skip')throw Error('Review sync not verified; repeat skip to recover');}
   saved.status='skipped';
  }
  await saveJSON(actionPath(id),saved);return {status:saved.status,text:`【Wiki】${id} ${saved.status}${saved.path?'\n正文：'+saved.path+'\n修改前历史：'+saved.history:''}`};
 }
 async function discover(scope,records){const saved=await optionalJSON(registry(scope))??{};const ids=[];for(const r of records){if(!/^[a-f0-9]{16}$/.test(r.id))throw Error('Invalid proposal ID');const p=await store({operation:'detail',id:r.id});if(!await mayView(scope,p))continue;const id='R-'+hash('markdown:'+r.id).slice(0,16);saved[id]={...p,id,proposalId:r.id,kind:'markdown',fingerprint:p.proposalHash+':'+(p.metadataHash??'none'),presentedAt:saved[id]?.fingerprint===p.proposalHash+':'+(p.metadataHash??'none')?saved[id].presentedAt??Date.now():Date.now()};ids.push(id);}await saveJSON(registry(scope),saved);return ids;}
 return {discover:(...args)=>serial(()=>discover(...args)),list:(...args)=>serial(()=>list(...args)),detail:(...args)=>serial(()=>detail(...args)),action:(...args)=>serial(()=>action(...args))};
}
