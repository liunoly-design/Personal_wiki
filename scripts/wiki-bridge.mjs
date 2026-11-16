#!/usr/bin/env node
// Wiki-only entry: accepts frozen portable sources; acquisition stays in the CLI.
import {readFile} from 'node:fs/promises';import {resolve,join} from 'node:path';import {homedir} from 'node:os';import {parseArgs} from 'node:util';import {openIngestion} from '../src/ingestion.js';
try{
 const {values:v,positionals:p}=parseArgs({allowPositionals:true,options:{config:{type:'string'},bundle:{type:'string'},name:{type:'string'},'request-id':{type:'string'},background:{type:'string'},refresh:{type:'boolean'},help:{type:'boolean'}}});
 if(v.help||!p.length){console.log('wiki-bridge doctor | ingest --bundle /absolute/bundle.json [--name english-name] | status TASK_ID | run TASK_ID\n--config /absolute/config.json');process.exit(0);}
 const configPath=resolve(v.config??process.env.WIKI_CONFIG??join(homedir(),'.config/personal-wiki/wiki-bridge.json'));const config={...JSON.parse(await readFile(configPath,'utf8')),configPath},service=await openIngestion(config);let result;
 if(p[0]==='doctor')result=await service.doctor();
 else if(p[0]==='ingest'){if(!v.bundle)throw Error('--bundle required');const job=await service.submit({bundleFile:resolve(v.bundle),name:v.name,requestId:v['request-id'],background:v.background,mode:'record',refresh:v.refresh});result=await service.run(job.id);}
 else if(p[0]==='status')result=await service.status(p[1]);
 else if(p[0]==='run')result=await service.run(p[1]);
 else throw Error('Unknown Wiki bridge command');
 console.log(JSON.stringify(result));
}catch(error){console.error(JSON.stringify({status:'error',message:error.message}));process.exitCode=1;}
