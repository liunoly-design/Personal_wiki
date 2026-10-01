import test from 'node:test';import assert from 'node:assert/strict';import {assessMigration} from '../src/migration-status.js';
const source={sourceId:'abc',relativeSource:'wiki/sources/sample.md'},url='https://x.com/a/status/1';
const full={url,status:'done',result:{status:'complete',sourceId:'abc',attachmentStatus:'complete',reading:{status:'complete'}}};
test('migration refuses incomplete history even if a source card and native entry exist',()=>{
 for(const result of [{...full.result,status:'pending'},{...full.result,reading:{status:'pending'}},{...full.result,attachmentStatus:'partial'}]){
  assert.equal(assessMigration(source,{url,jobs:[{...full,result}],nativeEntry:{filesWritten:[source.relativeSource]},captureStatuses:['complete']}).complete,false);
 }
 assert.equal(assessMigration(source,{url,jobs:[full]}).complete,true);
 assert.equal(assessMigration(source,{url,jobs:[{url,status:'failed'}]}).complete,false);
});
test('a successful later task can settle an earlier failure for the same immutable source',()=>{
 assert.equal(assessMigration(source,{url,jobs:[{url,status:'failed'},full]}).complete,true);
 assert.equal(assessMigration(source,{url,jobs:[{url,status:'done',result:{status:'complete',attachmentStatus:'complete'}}]}).mode,'legacy-no-backtranslation');
});
