import {readFile} from 'node:fs/promises';
import {refreshTerms} from '../src/term-refresh.js';
import {store} from '../src/protected-compiler.js';
import {createFlash} from '../src/flash.js';
const vault=process.argv[2];if(!vault?.startsWith('/'))throw Error('Absolute Vault required');
const python=process.env.WIKI_PYTHON??'python3';
const resume=process.argv.indexOf('--resume-plan');
if(resume!==-1){
 const plan=JSON.parse(await readFile(process.argv[resume+1],'utf8'));
 if(plan.vault!==vault||plan.operation!=='refresh-terms')throw Error('Regeneration plan does not match Vault');
 console.log(JSON.stringify(await store(plan,{python})));
}else{
 const flash=createFlash({usagePath:vault+'/.personal-wiki/term-refresh-usage.jsonl'});
 console.log(JSON.stringify(await refreshTerms({vault,python,explain:flash.explain,prepareOnly:process.argv.includes('--prepare'),onProgress:p=>console.log(JSON.stringify(p))})));
}
