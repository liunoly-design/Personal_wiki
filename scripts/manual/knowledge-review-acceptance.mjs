// Explicit local acceptance; writes only unique synthetic derived pages, removes them after verification.
import {readFile,writeFile,mkdir,unlink,mkdtemp,readdir,rm} from 'node:fs/promises';import {join,resolve} from 'node:path';import {tmpdir} from 'node:os';import {randomBytes} from 'node:crypto';
import {localNashsuAPI} from '../../src/nashsu-api.js';import {openKnowledgeQuery,hash} from '../../src/knowledge-query.js';import {openReviewService,createReviewStore} from '../../src/review-service.js';
const [vault,python]=process.argv.slice(2);if(!vault?.startsWith('/')||!python?.startsWith('/'))throw Error('Pass explicit absolute Vault and Python paths');
const api=await localNashsuAPI(vault,{maxAttempts:1});const stateDir=await mkdtemp(join(tmpdir(),'wiki-v05-acceptance-'));
const rid=randomBytes(8).toString('hex'),path=`wiki/concepts/v05-acceptance-${rid}.md`,file=`wiki/queries/review-${rid}.md`,metaFile=`.personal-wiki/review-proposals/${rid}.json`,job=`.personal-wiki/review-actions/${rid}`;
const own=[path,file,metaFile];const scope={SenderId:'synthetic-acceptance',NativeChannelId:'synthetic-acceptance'};const old='# Synthetic 0.5 acceptance\n\n手写保留：验收前原内容。\n';const candidate='合成来源：2026年测试观点，非用户真实知识。';const body='# 待审修改\n\n追加目标：'+path+'\n\n'+candidate;
async function hashes(){const found={};async function walk(dir,prefix){for(const e of await readdir(dir,{withFileTypes:true})){const p=prefix+'/'+e.name;if(e.isDirectory())await walk(join(dir,e.name),p);else if(e.isFile())found[p]=hash(await readFile(join(dir,e.name)));}}for(const dir of ['raw/sources','raw/assets'])await walk(join(vault,dir),dir);return found;}
const before=await hashes();
try{
 await writeFile(join(vault,path),old,{flag:'wx'});await writeFile(join(vault,file),body,{flag:'wx'});await mkdir(join(vault,'.personal-wiki/review-proposals'),{recursive:true});
 await writeFile(join(vault,metaFile),JSON.stringify({id:rid,path,previousHash:hash(old),candidate,sourceId:'a'.repeat(20),sourceUrl:'https://example.invalid/synthetic-acceptance',proposalHash:hash(body)}),{flag:'wx'});
 const review=await openReviewService({stateDir,api:async()=>api,store:createReviewStore({vault,python})});const ids=await review.discover(scope,[{id:rid}]);const id=ids[0];const detail=await review.detail(scope,id);if(!detail.text.includes(candidate))throw Error('Detail omitted proposed change');if(await api.read(path)!==old)throw Error('Viewing changed target');
 const applied=await review.action(scope,id,'应用','om_synthetic_apply');if(applied.status!=='applied')throw Error('Application not verified');const content=await api.read(path);if(!content.startsWith(old)||!content.includes(candidate))throw Error('Applied content lost hand-written baseline');await review.action(scope,id,'应用','om_synthetic_apply');if(await api.read(path)!==content)throw Error('Repeated approval modified content');
 const history=await readFile(join(vault,job,'before.md'),'utf8');if(history!==old)throw Error('History missing');
 const query=await openKnowledgeQuery({stateDir,api:async()=>api});const result=await query.query(scope,{question:'Opus'});if(!result.sources.length)throw Error('Live query found no evidence');const p=result.sources[0];if(!result.text.includes(p.citation))throw Error('Citation missing');await query.read(scope,p.id,p.start);const reviews=await api.reviews();const graph=await api.graph();
 if(JSON.stringify(before)!==JSON.stringify(await hashes()))throw Error('Raw bytes changed');
 console.log(JSON.stringify({ok:true,nativeReviews:reviews.reviews.length,graphNodes:graph.nodes.length,queryPages:result.sources.length,explicitApply:true,repeatIdempotent:true,history:true,rawFilesVerified:Object.keys(before).length}));
}finally{
 for(const p of own)await unlink(join(vault,p)).catch(e=>{if(e.code!=='ENOENT')throw e;});await rm(join(vault,job),{recursive:true,force:true});await rm(stateDir,{recursive:true,force:true});
}
