import {canonicalURL} from './task-queue.js';
// A source card alone is not completion evidence. New jobs require successful
// reading and attachments; older native jobs may use the desktop ingest receipt.
export function assessMigration(source,{url,jobs,nativeEntry,captureStatuses=[]}){
 const related=jobs.filter(job=>canonicalURL(job.url)===canonicalURL(url));
 const successful=related.find(job=>job.status==='done'&&!job.failure&&job.result?.status==='complete'
  &&job.result.attachmentStatus==='complete'
  &&(!job.result.sourceId||job.result.sourceId===source.sourceId)
  &&(job.result.reading?.status==='complete'||(!job.result.sourceId&&!job.result.reading)));
 if(successful)return {complete:true,mode:successful.result.reading?'verified-reading':'legacy-no-backtranslation'};
 const requestedReading=related.some(job=>job.result?.reading||job.result?.sourceId);
 if(!requestedReading&&nativeEntry?.filesWritten?.includes(source.relativeSource)&&captureStatuses.includes('complete'))return{complete:true,mode:'native-legacy-no-backtranslation'};
 return{complete:false,mode:'resume-required'};
}
