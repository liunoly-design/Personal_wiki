// Real host CLI and Python, synthetic configuration/data, no gateway start.
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const exec=promisify(execFile);
const root=resolve(import.meta.dirname,'../..'),cli=join(root,'scripts/wiki-setup.mjs');
async function binary(value,name){return value??(await exec('which',[name])).stdout.trim();}
const base=await realpath(await mkdtemp(join(tmpdir(),'wiki-real-install-')));
const python=process.env.WIKI_ACCEPTANCE_PYTHON;
if(!python)throw Error('Set WIKI_ACCEPTANCE_PYTHON to an existing Python with capture dependencies');
const hostConfigPath=join(base,'openclaw.json'),vault=join(base,'my-library'),stateDir=join(base,'private');
await mkdir(join(vault,'raw'),{recursive:true});
await writeFile(join(vault,'schema.md'),'# synthetic library\n');
await writeFile(join(vault,'raw/original.txt'),'synthetic immutable source\n');
const original=JSON.stringify({gateway:{mode:'local'},channels:{feishu:{accounts:{own:{appId:'synthetic-app',appSecret:'synthetic-secret'}}}},bindings:[{agentId:'my-entry',match:{channel:'feishu',accountId:'own'}}],plugins:{allow:['personal-wiki'],load:{paths:[]},entries:{}}})+'\n';
await writeFile(hostConfigPath,original,{mode:0o600});
const nashsuStatePath=join(base,'app-state.json');
await writeFile(nashsuStatePath,JSON.stringify({apiConfig:{enabled:true,token:'synthetic-only'},projectRegistry:{own:{path:vault}},sourceWatchConfig:{own:{autoIngest:false}},embeddingConfig:{enabled:false}}),{mode:0o600});
const settings={hostConfigPath,nashsuStatePath,vault,stateDir,python,codexBinary:await binary(process.env.WIKI_ACCEPTANCE_CODEX,'codex'),openclawBinary:await binary(process.env.WIKI_ACCEPTANCE_OPENCLAW,'openclaw'),wikiAgentId:'my-knowledge',entryAgentId:'my-entry',accountId:'own',allowedSenderIds:['ou_synthetic'],allowedConversationIds:['oc_synthetic'],flashModel:'gemini-flash-latest',compilerModel:'gpt-6-sol'};
if(process.env.WIKI_ACCEPTANCE_PACKAGE_DIR)settings.openclawPackageDir=process.env.WIKI_ACCEPTANCE_PACKAGE_DIR;
const settingsPath=join(base,'settings.json');await writeFile(settingsPath,JSON.stringify(settings),{mode:0o600});
async function run(action,args=[]){return JSON.parse((await exec(process.execPath,[cli,action,'--settings',settingsPath,...args],{timeout:60000,maxBuffer:4*1024*1024})).stdout);}
try{
 const check=await run('check');assert.equal(check.installable,true);
 const installed=await run('install');assert.equal(installed.status,'installed');assert.equal(installed.restartRequested,false);
 assert.equal((await run('install')).status,'existing');
 const host=JSON.parse(await readFile(hostConfigPath,'utf8'));
 assert.equal(host.plugins.entries['personal-gtd'],undefined);
 assert.equal(host.plugins.entries['personal-wiki'].config.vault,vault);
 assert.equal(host.plugins.entries['personal-wiki'].config.wikiAgentId,'my-knowledge');
 const restored=await run('rollback',['--receipt',installed.receipt]);assert.equal(restored.status,'rolled_back');
 assert.equal(await readFile(hostConfigPath,'utf8'),original);
 assert.equal(await readFile(join(vault,'raw/original.txt'),'utf8'),'synthetic immutable source\n');
 const invalid=JSON.parse(original);invalid.gateway.mode='synthetic-invalid-mode';
 const invalidBytes=JSON.stringify(invalid)+'\n';await writeFile(hostConfigPath,invalidBytes);
 await assert.rejects(run('install'),error=>error.stderr.includes('OpenClaw configuration validation failed'));
 assert.equal(await readFile(hostConfigPath,'utf8'),invalidBytes);
 await writeFile(hostConfigPath,original);
 console.log(JSON.stringify({realOpenClaw:true,realPython:true,isolatedCLI:true,ownLibrary:true,noPGTD:true,loaded:true,duplicateReused:true,configurationRestored:true,realValidationFailurePreserved:true,originalUnchanged:true,modelCalls:0,feishuMessages:0,gatewayRestarts:0}));
}finally{
 if(process.env.WIKI_ACCEPTANCE_KEEP==='1')console.error('Private evidence retained: '+base);
 else await rm(base,{recursive:true,force:true});
}
