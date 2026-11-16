#!/usr/bin/env node
import {readFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {realpath} from 'node:fs/promises';
import {homedir} from 'node:os';
import {parseArgs} from 'node:util';
import {spawn} from 'node:child_process';
import {setTimeout as delay} from 'node:timers/promises';
import {openIngestion} from '../src/ingestion.js';

const help=`Personal Wiki — durable AI ingestion
  wiki submit [share text or URL] [--text TEXT | --file FILE] [--mode record|convert]
  wiki convert [share text or URL] [--text TEXT | --file FILE]
  wiki run TASK_ID | status TASK_ID | pending
  wiki ingest TASK_ID | retry TASK_ID | supplement TASK_ID --file FILE
  wiki worker [--watch] | doctor
  wiki maintain TASK_ID
  --config /absolute/private/config.json
Submission and conversion are not proof of Wiki publication. Inspect task status.
`;
try{
 const {values,positionals}=parseArgs({allowPositionals:true,options:{config:{type:'string'},text:{type:'string'},mode:{type:'string'},file:{type:'string'},name:{type:'string'},background:{type:'string'},refresh:{type:'boolean'},'request-id':{type:'string'},'maintenance-replay':{type:'string'},watch:{type:'boolean'},help:{type:'boolean'}}});
 if(values.help||!positionals.length){console.log(help);process.exit(0);}
 const configPath=resolve(values.config??process.env.WIKI_CONFIG??join(homedir(),'.config/personal-wiki/ingest.json'));
 const config={...JSON.parse(await readFile(configPath,'utf8')),configPath};
 try{config.processorVersion=JSON.parse(await readFile(resolve(import.meta.dirname,'../.release.json'),'utf8')).version;}catch(error){if(error.code!=='ENOENT')throw error;}
 const service=await openIngestion(config);const [command,id]=positionals;
 let result;
 if(command==='submit'||command==='convert'){
  const jobs=await service.submitMany({...(values.file!==undefined?{file:resolve(values.file),...(values.text!==undefined?{text:values.text}:{}),...(positionals.length>1?{input:positionals.slice(1).join(' ')}:{})}:values.text!==undefined?{text:values.text}:{input:positionals.slice(1).join(' ')}),mode:command==='convert'?'convert':values.mode??'record',name:values.name,requestId:values['request-id'],background:values.background,refresh:values.refresh});
  const results=[];
  for(const job of jobs){results.push(command==='convert'?await service.run(job.id):job);
   if(command==='submit'&&config.autoStart!==false&&job.status==='queued'){
    const child=spawn(process.execPath,[new URL(import.meta.url).pathname,'run',job.id,'--config',configPath],{detached:true,stdio:'ignore'});child.on('error',()=>{});child.unref();
   }
  }
  result=results.length===1?results[0]:results;
 }else if(command==='run')result=await service.run(id);
 else if(command==='status')result=await service.status(id);
 else if(command==='pending')result=(await service.list()).filter(j=>!['complete','converted'].includes(j.status));
 else if(command==='supplement'){if(!values.file)throw Error('--file required');result=await service.supplement(id,{file:resolve(values.file)});}
 else if(command==='retry')result=await service.retry(id,{maintenanceId:values['maintenance-replay']});
 else if(command==='ingest')result=await service.ingest(id);
 else if(command==='maintain')result=await service.maintain(id);
 else if(command==='doctor')result=await service.doctor();
 else if(command==='worker'){do{result=await service.workOnce();if(values.watch){if(config.runtimeRoot&&await realpath(join(config.runtimeRoot,'current'))!==resolve(import.meta.dirname,'..'))process.exit(0);await delay(2000);}}while(values.watch);}
 else throw Error('Unknown command; use --help');
 console.log(JSON.stringify(result));
}catch(error){console.error(JSON.stringify({status:'error',message:error.message}));process.exitCode=1;}
