#!/usr/bin/env node
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {installWiki,checkWikiInstallation,rollbackWiki} from '../src/wiki-install.js';

const [action,...args]=process.argv.slice(2);
function argument(name){const i=args.indexOf(name);return i<0?undefined:args[i+1];}
try{
 const settingsPath=argument('--settings');
 if(!settingsPath||!['check','install','rollback'].includes(action))throw Error('Usage: wiki-setup.mjs check|install|rollback --settings /private/settings.json [--api] [--receipt /private/install-receipt.json]');
 const settings=JSON.parse(await readFile(resolve(settingsPath),'utf8'));
 const result=action==='check'?await checkWikiInstallation(settings,{apiCheck:args.includes('--api')}):action==='install'?await installWiki(settings):await rollbackWiki(settings,argument('--receipt')??'');
 console.log(JSON.stringify(result,null,2));
 if(result.installable===false)process.exitCode=1;
}catch(error){
 // Dependency output and host validation logs can contain credentials. Emit only
 // our fixed diagnostics, never a child process's command, stdout or stderr.
 const safe=error.cmd?'Host validation or dependency command failed; original configuration preserved':error instanceof SyntaxError?'Invalid JSON configuration':error.message;
 console.error(JSON.stringify({status:'failed',reason:safe,next:'Correct the reported setting or inspect the private installation receipt; do not replay unknown configuration changes'}));
 process.exitCode=1;
}
