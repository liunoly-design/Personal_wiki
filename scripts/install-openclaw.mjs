#!/usr/bin/env node
import {readFile,copyFile,access,chmod} from 'node:fs/promises';
import {homedir} from 'node:os';import {join,resolve} from 'node:path';import {execFileSync} from 'node:child_process';
const root=resolve(import.meta.dirname,'..');const home=homedir();const configPath=join(home,'.openclaw/openclaw.json');
const host=JSON.parse(await readFile(configPath,'utf8'));
const prior=host.plugins?.entries?.['personal-wiki']?.config;
const scope=prior??host.plugins?.entries?.['personal-gtd']?.config;
if(!scope?.allowedSenderIds?.length||!scope?.allowedConversationIds?.length)throw Error('No existing approved Feishu scope; configure allowedSenderIds and allowedConversationIds first');
const vault=join(home,'Documents/Personal-Wiki-Vault');
await access(join(vault,'schema.md'));
const app=JSON.parse(await readFile(join(home,'Library/Application Support/com.llmwiki.app/app-state.json'),'utf8'));
if(app.lastProject?.path!==vault)throw Error('Open Personal-Wiki-Vault in nashsu first');
if(!host.agents?.entries?.wiki)throw Error('Existing OpenClaw wiki agent required');
const python=join(root,'.venv/bin/python');
let bootstrapPython;
for(const candidate of [process.env.WIKI_PYTHON,join(root,'.local/capture-test/venv/bin/python'),'python3.12','python3.11','python3'].filter(Boolean)){
 try{execFileSync(candidate,['-c','import sys; assert sys.version_info >= (3,11)'],{stdio:'ignore'});bootstrapPython=candidate;break;}catch{}
}
if(!bootstrapPython)throw Error('Python 3.11+ required; set WIKI_PYTHON to its executable');
if(process.argv.includes('--check')){
 console.log(JSON.stringify({ready:true,plugin:root,vault,flash:'google/gemini-flash-latest',approvedSenders:scope.allowedSenderIds.length,approvedChats:scope.allowedConversationIds.length,command:'小婕 wk 记录：链接',note:'Check is read-only; Python dependencies and plugin installation run without --check'},null,2));process.exit(0);
}
execFileSync(bootstrapPython,['-m','venv',join(root,'.venv')],{stdio:'inherit'});
execFileSync(python,['-m','pip','install','-r',join(root,'requirements-capture.txt')],{stdio:'inherit'});
const stamp=new Date().toISOString().replaceAll(':','-');await copyFile(configPath,configPath+'.before-personal-wiki-'+stamp);await chmod(configPath+'.before-personal-wiki-'+stamp,0o600);
execFileSync('openclaw',['plugins','install','--link','--force',root],{stdio:'inherit'});
const current=JSON.parse(await readFile(configPath,'utf8'));
const config={enabled:true,accountId:scope.accountId,entryAgentId:scope.entryAgentId,allowedSenderIds:scope.allowedSenderIds,allowedConversationIds:scope.allowedConversationIds,vault,stateDir:join(home,'.openclaw/personal-wiki'),python,flashModel:'gemini-flash-latest'};
// An absent allowlist is a different policy from an explicit restricted list.
// Preserve it rather than disabling all other previously available plugins.
const allow=current.plugins?.allow;
execFileSync('openclaw',['config','patch','--stdin'],{input:JSON.stringify({plugins:{...(Array.isArray(allow)?{allow:[...new Set([...allow,'personal-wiki'])]}:{}),entries:{'personal-wiki':{enabled:true,config}}}}),stdio:['pipe','inherit','inherit']});
execFileSync('openclaw',['config','validate'],{stdio:'inherit'});
execFileSync('openclaw',['gateway','restart'],{stdio:'inherit'});
console.log('Installed. Send in the already-approved Feishu private chat: 小婕 wk 记录：链接');
