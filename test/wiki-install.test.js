import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,realpath,symlink} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import * as filesystem from 'node:fs/promises';
import {syncBuiltinESMExports} from 'node:module';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {installWiki,checkWikiInstallation,rollbackWiki} from '../src/wiki-install.js';

async function fixture(t){
 const base=await realpath(await mkdtemp(join(tmpdir(),'wiki-install-')));
 t.after(()=>rm(base,{recursive:true,force:true}));
 const vault=join(base,'my-vault'),stateDir=join(base,'private');
 await mkdir(join(vault,'raw'),{recursive:true});
 await writeFile(join(vault,'schema.md'),'# synthetic schema\n');
 await writeFile(join(vault,'raw/evidence.txt'),'immutable evidence\n');
 const hostConfigPath=join(base,'openclaw.json');
 const original=JSON.stringify({gateway:{mode:'local'},channels:{feishu:{accounts:{mine:{appId:'synthetic',appSecret:'synthetic'}}}},plugins:{allow:['unrelated'],load:{paths:['/unrelated']},entries:{unrelated:{enabled:false}}},bindings:[{agentId:'entry',match:{channel:'feishu',accountId:'mine'}}]})+'\n';
 await writeFile(hostConfigPath,original,{mode:0o600});
 const nashsuStatePath=join(base,'nashsu.json');
 await writeFile(nashsuStatePath,JSON.stringify({projectRegistry:{new:{path:vault}},sourceWatchConfig:{new:{autoIngest:false}},embeddingConfig:{enabled:false},apiConfig:{enabled:true,token:'synthetic-api-token'}}));
 const binary=join(base,'dependency');
 await writeFile(binary,'#!/usr/bin/env node\nconsole.log("dependency available");\n',{mode:0o700});
 const openclawBinary=join(base,'openclaw');
 await writeFile(openclawBinary,'#!/usr/bin/env node\nif(process.argv.includes("inspect"))console.log(JSON.stringify({plugin:{status:"loaded"},typedHooks:[{name:"reply_dispatch"}]}));\n',{mode:0o700});
 const settings={hostConfigPath,nashsuStatePath,vault,stateDir,python:binary,codexBinary:binary,openclawBinary,accountId:'mine',entryAgentId:'entry',wikiAgentId:'knowledge',allowedSenderIds:['ou_owner'],allowedConversationIds:['oc_private'],flashModel:'gemini-test',compilerModel:'test-model'};
 return {base,settings,original};
}

test('independent install binds own library and scope, preserves other configuration and original data',async t=>{
 const {settings,original}=await fixture(t);
 const check=await checkWikiInstallation(settings);
 assert.equal(check.installable,true);
 const result=await installWiki(settings);
 const host=JSON.parse(await readFile(settings.hostConfigPath,'utf8'));
 assert.equal(host.plugins.entries['personal-wiki'].config.vault,settings.vault);
 assert.equal(host.plugins.entries['personal-wiki'].config.wikiAgentId,'knowledge');
 assert.deepEqual(host.plugins.entries['personal-wiki'].config.allowedSenderIds,['ou_owner']);
 assert.deepEqual(host.plugins.entries.unrelated,JSON.parse(original).plugins.entries.unrelated);
 assert.deepEqual(host.bindings,JSON.parse(original).bindings);
 assert.equal(host.plugins.entries['personal-gtd'],undefined);
 assert.equal(await readFile(join(settings.vault,'raw/evidence.txt'),'utf8'),'immutable evidence\n');
 assert.equal(result.status,'installed');
 assert.equal((await installWiki(settings)).status,'existing');
 const restored=await rollbackWiki(settings,result.receipt);
 assert.equal(restored.status,'rolled_back');
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),original);
 assert.equal(await readFile(join(settings.vault,'raw/evidence.txt'),'utf8'),'immutable evidence\n');
});

test('missing dependency blocks installation without changing the host or creating private state',async t=>{
 const {settings,original}=await fixture(t);
 settings.python=join(dirnameFor(settings.hostConfigPath),'missing-python');
 const report=await checkWikiInstallation(settings);
 assert.equal(report.installable,false);
 assert.deepEqual(report.checks.find(c=>c.name==='python_dependencies'),{name:'python_dependencies',status:'blocked'});
 await assert.rejects(installWiki(settings),/Preflight blocked/);
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),original);
 await assert.rejects(readFile(join(settings.stateDir,'installation.json')),e=>e.code==='ENOENT');
});
function dirnameFor(path){return path.slice(0,path.lastIndexOf('/'));}

test('host validation failure preserves original bytes and post-commit failure restores them',async t=>{
 const {settings,original}=await fixture(t);
 await writeFile(settings.openclawBinary,'#!/usr/bin/env node\nif(process.argv.includes("validate"))process.exit(2);\n',{mode:0o700});
 await assert.rejects(installWiki(settings));
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),original);
 await writeFile(settings.openclawBinary,'#!/usr/bin/env node\nif(process.argv.includes("inspect")){if(!process.env.OPENCLAW_CONFIG_PATH.endsWith(".candidate.json"))process.exit(3);console.log(JSON.stringify({plugin:{status:"loaded"},typedHooks:[{name:"reply_dispatch"}]}));}\n',{mode:0o700});
 await assert.rejects(installWiki(settings),/original configuration restored/);
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),original);
});

test('rollback refuses later edits and concurrent installers without deleting data',async t=>{
 const {settings}=await fixture(t);
 const result=await installWiki(settings);
 const edited=(await readFile(settings.hostConfigPath,'utf8'))+' ';
 await writeFile(settings.hostConfigPath,edited);
 await assert.rejects(rollbackWiki(settings,result.receipt),/rollback refused/);
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),edited);
 await writeFile(settings.hostConfigPath+'.wiki-setup.lock','other installer',{flag:'wx'});
 await assert.rejects(installWiki(settings),e=>e.code==='EEXIST');
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),edited);
});

test('installation metadata symlinks cannot redirect private backup and release writes',async t=>{
 const {settings,base,original}=await fixture(t);
 await mkdir(settings.stateDir);
 const outside=join(base,'outside');await mkdir(outside);
 await symlink(outside,join(settings.stateDir,'installations'));
 await assert.rejects(installWiki(settings),/Symbolic link rejected/);
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),original);
});

test('an external host edit during installation marker commit is retained',async t=>{
 const {settings,original}=await fixture(t),edited=original+' ';
 const prior=filesystem.default.rename;
 filesystem.default.rename=async(from,to)=>{
  if(to===join(settings.stateDir,'installation.json'))await writeFile(settings.hostConfigPath,edited);
  return prior(from,to);
 };
 syncBuiltinESMExports();
 try{
  await assert.rejects(installWiki(settings),/configuration changed/);
  assert.equal(await readFile(settings.hostConfigPath,'utf8'),edited);
 }finally{filesystem.default.rename=prior;syncBuiltinESMExports();}
});

test('CLI failure receipt never repeats malformed inspection output',async t=>{
 const {settings,base,original}=await fixture(t),secret='synthetic-secret-do-not-log';
 await writeFile(settings.openclawBinary,'#!/usr/bin/env node\nif(process.argv.includes("inspect"))console.log("'+secret+'");\n',{mode:0o700});
 const settingsPath=join(base,'settings.json');await writeFile(settingsPath,JSON.stringify(settings),{mode:0o600});
 let failure;
 try{await promisify(execFile)(process.execPath,[new URL('../scripts/wiki-setup.mjs',import.meta.url).pathname,'install','--settings',settingsPath]);}
 catch(error){failure=error;}
 assert.ok(failure);
 assert.doesNotMatch(failure.stderr,new RegExp(secret+'|synthetic-'));
 assert.match(failure.stderr,/invalid JSON/);
 assert.equal(await readFile(settings.hostConfigPath,'utf8'),original);
});
