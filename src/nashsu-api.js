import {setTimeout as delay} from 'node:timers/promises';
import {readFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {homedir} from 'node:os';
export function assertMigrationState(watch,queue){
 if(watch?.autoIngest!==false||watch?.enabled!==false)throw Error('Disable nashsu file monitoring and automatic ingestion before source migration');
 if(!Array.isArray(queue?.tasks))throw Error('Native file change queue cannot be verified');
 if(queue.tasks.length)throw Error('Wait for pending native file changes before source migration');
}
export async function localNashsuAPI(vault,{signal,maxAttempts=5}={}){
 const state=JSON.parse(await readFile(join(homedir(),'Library/Application Support/com.llmwiki.app/app-state.json'),'utf8'));
 const project=Object.entries(state.projectRegistry??{}).find(([,p])=>resolve(p.path)===resolve(vault))?.[0];
 if(!project||!state.apiConfig?.enabled)throw Error('Nashsu local API is unavailable');
 const prefix='http://127.0.0.1:19828/api/v1/projects/'+encodeURIComponent(project);
 async function request(path,body){
  for(let attempt=0;attempt<maxAttempts;attempt++){
  const response=await fetch(prefix+path,{method:body?'POST':'GET',redirect:'error',headers:{Authorization:'Bearer '+state.apiConfig.token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000)});
  if([429,502,503,504].includes(response.status)&&attempt<maxAttempts-1){await response.body?.cancel();await delay(1100*(attempt+1),undefined,{signal});continue;}
  if(!response.ok)throw Error('Nashsu API HTTP '+response.status);
  const value=await response.json();if(value.ok!==true)throw Error('Nashsu API result not confirmed');return value;
  }
 }
 return {assertMigrationReady:async()=>{
  const latest=JSON.parse(await readFile(join(homedir(),'Library/Application Support/com.llmwiki.app/app-state.json'),'utf8'));
  const queue=JSON.parse(await readFile(join(vault,'.llm-wiki/file-change-queue.json'),'utf8'));
  assertMigrationState(latest.sourceWatchConfig?.[project],queue);
 },assertPublisherReady:async()=>{const latest=JSON.parse(await readFile(join(homedir(),'Library/Application Support/com.llmwiki.app/app-state.json'),'utf8'));if(latest.sourceWatchConfig?.[project]?.autoIngest!==false)throw Error('Disable duplicate automatic ingestion for this integrated nashsu project');},read:async path=>(await request('/files/content?path='+encodeURIComponent(path))).content,search:async query=>request('/search',{query}),rescan:async()=>request('/sources/rescan',{})};
}
