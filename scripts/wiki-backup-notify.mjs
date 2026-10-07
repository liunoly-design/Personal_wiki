#!/usr/bin/env node
import {backupNotification} from '../src/backup-notify.js';

// The Python runner reads both configs with anchored, no-follow directory handles.
// Only the selected account crosses this private stdin boundary; never log inputs.
try {
 if(process.argv.length!==2)throw Error('Notification input required');
 let input='';
 for await(const chunk of process.stdin){input+=chunk;if(Buffer.byteLength(input)>65536)throw Error('Request too large');}
 const request=JSON.parse(input);
 const result=await backupNotification({hostConfig:request.hostConfig,scope:request.scope,request});
 console.log(JSON.stringify(result));
} catch {
 console.log(JSON.stringify({status:'failed',cause:'Notification unavailable or result unknown; receipt retained'}));
 process.exitCode=1;
}
