import {refreshTerms} from '../src/term-refresh.js';
import {createFlash} from '../src/flash.js';
const vault=process.argv[2];if(!vault?.startsWith('/'))throw Error('Absolute Vault required');
const flash=createFlash({usagePath:vault+'/.personal-wiki/term-refresh-usage.jsonl'});
console.log(JSON.stringify(await refreshTerms({vault,python:process.env.WIKI_PYTHON??'python3',explain:flash.explain,prepareOnly:process.argv.includes('--prepare'),onProgress:p=>console.log(JSON.stringify(p))})));
