import test from 'node:test';
import assert from 'node:assert/strict';
import {assertMigrationState} from '../src/nashsu-api.js';

test('source relocation refuses active monitoring or pending native file changes',()=>{
 const stopped={autoIngest:false,enabled:false};
 assert.throws(()=>assertMigrationState({...stopped,enabled:true},{tasks:[]}),/monitor/i);
 assert.throws(()=>assertMigrationState(stopped,{tasks:[{kind:'deleted'}]}),/pending/i);
 assert.throws(()=>assertMigrationState(stopped,null),/queue/i);
 assert.doesNotThrow(()=>assertMigrationState(stopped,{tasks:[]}));
});
