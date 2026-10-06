import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm,realpath} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {openClawGoogleKey} from '../src/openclaw-auth.js';
import {localNashsuAPI} from '../src/nashsu-api.js';
import {collectCanonical} from '../src/canonical-library.js';
import {collectDouyin} from '../src/douyin.js';
import {collectRemoteDouyin} from '../src/remote-douyin.js';
import {resolveWikiFeishuAccount} from '../src/feishu-http.js';

test('credential resolver uses selected host agent and SDK without reading the fixed wiki account',async t=>{
 const base=await mkdtemp(join(tmpdir(),'wiki-auth-'));t.after(()=>rm(base,{recursive:true,force:true}));
 await mkdir(join(base,'dist/plugin-sdk'),{recursive:true});
 await writeFile(join(base,'dist/plugin-sdk/agent-runtime.js'),`export function ensureAuthProfileStore(dir){if(!dir.endsWith('/own-agent'))throw Error('Wrong agent');return {profiles:{mine:{provider:'google'}}};}
 export async function resolveApiKeyForProfile({cfg,profileId}){if(!cfg.agents.entries.knowledge||profileId!=='mine')throw Error('Wrong scope');return {apiKey:'synthetic-only'};}`);
 const resolver=openClawGoogleKey({agentId:'knowledge',packageDir:base,hostConfig:{agents:{entries:{knowledge:{agentDir:join(base,'own-agent')}}}}});
 assert.equal(await resolver(),'synthetic-only');
});

test('selected named account cannot fall back to a different default account',()=>{
 const host={channels:{feishu:{appId:'default-app',appSecret:'default-secret',accounts:{own:{appId:'own-app',appSecret:'own-secret'}}}}};
 assert.deepEqual(resolveWikiFeishuAccount(host,'own',{explicit:true}),{appId:'own-app',appSecret:'own-secret'});
 assert.throws(()=>resolveWikiFeishuAccount(host,'missing',{explicit:true}),/Selected Feishu account unavailable/);
 host.channels.feishu.enabled=false;
 assert.equal(resolveWikiFeishuAccount(host,'own',{explicit:true}).enabled,false);
 delete host.channels.feishu.enabled;host.channels.feishu.domain='lark';
 assert.equal(resolveWikiFeishuAccount(host,'own',{explicit:true}).domain,'lark');
 delete host.channels.feishu.accounts.own.appSecret;
 assert.equal(resolveWikiFeishuAccount(host,'own',{explicit:true}).appSecret,undefined);
});

for(const kind of ['text','local-video','remote-video'])test('selected library guard applies to '+kind+' collection before publication',async t=>{
 const base=await realpath(await mkdtemp(join(tmpdir(),'wiki-collection-config-')));t.after(()=>rm(base,{recursive:true,force:true}));
 const vault=join(base,'vault'),nashsuStatePath=join(base,'app.json');
 await mkdir(vault);
 await writeFile(nashsuStatePath,JSON.stringify({apiConfig:{enabled:true,token:'synthetic'},projectRegistry:{own:{path:vault}},sourceWatchConfig:{own:{autoIngest:true}}}));
 const input={vault,nashsuStatePath,workspace:join(base,'work'),stateDir:join(base,'state'),python:'/usr/bin/python3',url:'https://v.douyin.com/synthetic/',
 text:'合成中文原文。',flash:{extract:async()=>({slug:'synthetic-source',terms:[]}),explain:async()=>[]},
 generate:async({stage})=>stage==='analysis'?'合成分析':'---FILE: wiki/sources/synthetic-source.md---\n# 合成资料\n合成摘要。\n---END FILE---'};
 if(kind==='text')input.url='https://example.org/synthetic';
 if(kind==='remote-video'){
  input.mediaServiceTokenFile=join(base,'token');await writeFile(input.mediaServiceTokenFile,'synthetic',{mode:0o600});
  input.mediaServiceUrl='http://127.0.0.1:8765';
 }
 const collect=kind==='text'?collectCanonical:kind==='local-video'?collectDouyin:collectRemoteDouyin;
 await assert.rejects(collect(input),/Disable duplicate automatic ingestion/);
});

test('fixed library API checks use selected app state rather than another registered library',async t=>{
 const base=await mkdtemp(join(tmpdir(),'wiki-api-'));t.after(()=>rm(base,{recursive:true,force:true}));
 const statePath=join(base,'app.json'),vault=join(base,'vault');
 await writeFile(statePath,JSON.stringify({apiConfig:{enabled:true,token:'synthetic'},projectRegistry:{mine:{path:vault}},sourceWatchConfig:{mine:{autoIngest:false}}}));
 const api=await localNashsuAPI(vault,{statePath});
 await api.assertPublisherReady();
 await writeFile(statePath,JSON.stringify({apiConfig:{enabled:true,token:'synthetic'},projectRegistry:{mine:{path:vault}},sourceWatchConfig:{mine:{autoIngest:true}}}));
 await assert.rejects(api.assertPublisherReady(),/duplicate automatic ingestion/);
});
