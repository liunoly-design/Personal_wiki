#!/usr/bin/env node
import {readFile} from 'node:fs/promises';
import {parseArgs} from 'node:util';
import {resolve} from 'node:path';
import {repairIngestion} from '../src/ingestion-maintenance.js';
const {values,positionals}=parseArgs({allowPositionals:true,options:{config:{type:'string'}}});
try{
 const configPath=resolve(values.config);const config={...JSON.parse(await readFile(configPath,'utf8')),configPath};
 console.log(JSON.stringify(await repairIngestion(config,positionals[0])));
}catch(error){console.error(JSON.stringify({status:'failed',reason:error.message}));process.exitCode=1;}
