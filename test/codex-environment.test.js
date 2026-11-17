import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

test('npm Codex entry can run with the minimal PATH used by launchd',async()=>{
 const directory=await mkdtemp(join(tmpdir(),'wiki-node-env-'));
 try{
  const binary=join(directory,'codex.mjs');
  await writeFile(binary,"#!/usr/bin/env node\nimport {writeFileSync} from 'node:fs';\nprocess.stdin.resume();process.stdin.on('end',()=>writeFileSync(process.argv[process.argv.indexOf('--output-last-message')+1],'synthetic response'));\n",{mode:0o700});
  const script=`import {createCodex} from ${JSON.stringify(new URL('../src/codex.js',import.meta.url).href)};const result=await createCodex({binary:${JSON.stringify(binary)}})({prompt:'synthetic'});process.stdout.write(result);`;
  const {stdout}=await promisify(execFile)(process.execPath,['--input-type=module','-e',script],{env:{...process.env,PATH:'/usr/bin:/bin'},timeout:10000});
  assert.equal(stdout,'synthetic response');
 }finally{await rm(directory,{recursive:true,force:true});}
});
