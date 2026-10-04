// Authorized single-source acceptance only. No production deployment or messages.
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {homedir} from 'node:os';
import {collectCanonical} from '../../src/canonical-library.js';
import {createFlash} from '../../src/flash.js';
const args=process.argv.slice(2);const source=args[0]??'https://v.douyin.com/Tg6ANQWIT7w/';
if(source!=='https://v.douyin.com/Tg6ANQWIT7w/')throw Error('This acceptance runner is restricted to the authorized source');
const base=resolve('.local/v070/acceptance');await mkdir(base,{recursive:true,mode:0o700});
const {config}=JSON.parse(await readFile(join(homedir(),'.openclaw/openclaw.json'),'utf8')).plugins.entries['personal-wiki'];
if(config.vault!=='/Users/mac/Documents/Personal-Wiki-Vault')throw Error('Acceptance Vault identity mismatch');
const flash=createFlash({proxyUrl:config.flashProxyUrl,model:config.flashModel??'gemini-flash-latest',maxAttempts:1,usagePath:join(base,'flash-usage.jsonl')});
try{
 const result=await collectCanonical({url:source,vault:config.vault,stateDir:base,workspace:join(base,'work'),python:config.python,flash,codexBinary:config.codexBinary,compilerModel:config.compilerModel,asrBinary:resolve('.local/v070/codex-asr-aarch64-apple-darwin/codex-asr'),videoMode:'compressed',onStage:async stage=>{await writeFile(join(base,'stage.json'),JSON.stringify({stage,at:new Date().toISOString()}),{mode:0o600});console.log(stage);}});
 await writeFile(join(base,'result.json'),JSON.stringify(result,null,2),{mode:0o600});console.log(JSON.stringify({status:result.status,source:result.source,video:result.video?.mediaPublication?.supplement,cleanup:result.video?.cleanup}));
}catch(error){const report={status:'blocked',reason:error.message,source,productionDeployed:false,realMessageReceipt:false};await writeFile(join(base,'result.json'),JSON.stringify(report,null,2),{mode:0o600});console.log(JSON.stringify(report));process.exitCode=2;}finally{await flash.close?.();}
