// Real local API/model read-only discussion; optional unique synthetic publication.
import {mkdtemp,rm,readFile,readdir,mkdir} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';import {join,resolve} from 'node:path';import {createHash} from 'node:crypto';
import {openKnowledgeQuery} from '../../src/knowledge-query.js';import {openDiscussion} from '../../src/discussion.js';
import {openReviewService,createReviewStore} from '../../src/review-service.js';
import {localNashsuAPI} from '../../src/nashsu-api.js';import {createCodex} from '../../src/codex.js';import {parseCommand} from '../../src/wk.js';
const vault=process.argv[2],python=process.argv[3],synthetic=process.argv.includes('--synthetic');if(!vault||!python)throw Error('vault python required');
const fixturePrefix='wiki/sources/acceptance-'+String(Date.now());
const stateDir=await mkdtemp(join(tmpdir(),'wiki-v06-acceptance-'));const scope={SenderId:'synthetic-acceptance',NativeChannelId:'local-only'};
const stamp=String(Date.now());const api=signal=>localNashsuAPI(vault,{signal,maxAttempts:1});
const hashes=async directory=>{const result={};async function walk(p){for(const n of await readdir(p,{withFileTypes:true})){const path=join(p,n.name);if(n.isDirectory())await walk(path);else if(n.isFile())result[path]=createHash('sha256').update(await readFile(path)).digest('hex');}}await walk(directory);return result;};
const before=await hashes(join(vault,'raw'));const created=[];let rid;
const generate=synthetic?async({purpose,prompt})=>{if(purpose==='select')return JSON.stringify({ids:JSON.parse(prompt.split('\n候选JSON：\n')[1]).filter(p=>p.title?.includes(stamp)).map(p=>p.id)});const refs=[...new Set(prompt.match(/\[K-[a-f0-9]{16} L\d+-L\d+\]/g))];return '## 原作者观点\n合成来源分别描述小团队与大团队条件。'+refs.join(' ')+'\n\n## 模型推断\n条件可能影响适用性。\n\n## 未决问题\n缺少真实对照证据。';}:createCodex({binary:'/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',model:'gpt-6-sol',textOnly:true,timeoutMs:120000});
const store=createReviewStore({vault,python});
try{
 if(synthetic){
  const client=await api();await client.assertPublisherReady();
  // Use existing protected conclusion operation for unique synthetic evidence pages.
  for(const [i,body] of ['小团队试验适用。','大型组织试验不适用。'].entries()){
   const path=fixturePrefix+'-'+i+'.md';const content=`# Synthetic ${stamp} ${i}\n2026-10-03 ${body}`;
   execFileSync(python,['-c','import sys;sys.path.insert(0,sys.argv[1]);from protected_store import Root;r=Root(sys.argv[2]);l=r.lock();r.immutable(sys.argv[3],sys.argv[4].encode())',resolve(import.meta.dirname,'..'),vault,path,content]);created.push(path);
  }
 }
 const knowledge=await openKnowledgeQuery({stateDir,api,generate});const reviews=await openReviewService({stateDir,api,store,knowledge});
 const discussion=await openDiscussion({stateDir,python,knowledge,generate,api,store,reviews});
 const text=synthetic?'小婕 wk 讨论：Synthetic '+stamp:'小婕 wk 讨论：Opus 工作流的适用条件与限制是什么？';
 const d=await discussion.execute(scope,parseCommand(text),'om_local_'+stamp);
 if(!d.text.includes('原作者观点'))throw Error('Discussion did not produce verified answer');
 const follow=await discussion.execute(scope,parseCommand(`小婕 wk 讨论：${d.id} 这些观点有哪些限制？\n用户判断：暂不直接推广`),'om_follow_'+stamp);
 if(follow.id!==d.id||!follow.text.includes('暂不直接推广'))throw Error('Follow-up did not retain discussion');
 let saved=false,approved=false;
 if(synthetic){
  const savedResult=await discussion.execute(scope,parseCommand('小婕 wk 保存结论：'+d.id),'om_save_'+stamp);saved=Boolean(savedResult.readingId);
  const key=createHash('sha256').update(createHash('sha256').update(JSON.stringify([scope.SenderId,scope.NativeChannelId])).digest('hex')+'om_save_'+stamp).digest('hex');created.push('wiki/topics/discussion-'+key.slice(0,16)+'.md');
  const proposal=await discussion.execute(scope,parseCommand('小婕 wk 综合：'+d.id+' 合成验收 '+stamp),'om_synth_'+stamp);rid=proposal.reviewId;
  const detail=await reviews.detail(scope,rid);const local=detail.item.proposalId;
  created.push('wiki/queries/review-'+local+'.md','.personal-wiki/review-proposals/'+local+'.json','.personal-wiki/review-actions/'+local,detail.item.metadata.path);
  const applied=await reviews.action(scope,rid,'应用','om_approve_'+stamp,undefined,Date.now()+1000);approved=applied.status==='applied';
  await reviews.action(scope,rid,'应用','om_approve_'+stamp,undefined,Date.now()+1000);

 }
 if(JSON.stringify(before)!==JSON.stringify(await hashes(join(vault,'raw'))))throw Error('Raw hashes changed');
 console.log(JSON.stringify({mode:synthetic?'synthetic-save':'real-read-only-model',discussion:true,followUp:true,saved,approved,rawFiles:Object.keys(before).length,rawHashesUnchanged:true,replyBytes:Buffer.byteLength(follow.text)}));
}finally{
 for(const p of created)await rm(join(vault,p),{force:true,recursive:true});
 await rm(stateDir,{recursive:true,force:true});
}
