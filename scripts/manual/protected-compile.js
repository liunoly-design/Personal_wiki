// Explicit live-model smoke test. Uses synthetic text and an isolated Vault.
import {mkdtemp,mkdir,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';
import {createAdapters} from '../../src/nashsu.js';
const root=await mkdtemp(join(tmpdir(),'wiki-live-synthetic-'));
try {
 const vault=join(root,'vault'),snapshot=join(root,'snapshot');await mkdir(vault);await mkdir(snapshot);
 await writeFile(join(snapshot,'article.md'),'# Evidence Notebook\nA synthetic experiment compares two pens. Pen A lasts two days. Pen B lasts three days. The sample contains only one pen of each kind; the result does not establish a general rule.');
 const adapters=createAdapters({vault,python:process.env.WIKI_PYTHON??'python3',captureDirectory:root,flash:{},codexBinary:process.env.WIKI_CODEX_BINARY??'codex'});
 const result=await adapters.importAndCompile({capture:{directory:snapshot},slug:'evidence-notebook',context:'',url:'https://x.com/example/status/123'});
 console.log(JSON.stringify({status:result.status,pages:result.created,reviews:result.reviews.length,source:await readFile(result.source,'utf8')},null,2));
}finally{await rm(root,{recursive:true,force:true});}
