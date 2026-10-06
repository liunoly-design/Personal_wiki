import {createRequire} from 'node:module';
import {realpathSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';

// Reuse the host's HTTP client, as with the existing credential resolver.
// A dispatcher belongs to this client only; never change the global dispatcher.
export function createProxyFetch(proxyUrl,{packageDir}={}){
 if(!proxyUrl)return Object.assign((...args)=>fetch(...args),{close:async()=>{}});
 const url=new URL(proxyUrl);
 if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw Error('Invalid Flash proxy URL');
 const require=createRequire(packageDir?join(packageDir,'package.json'):join(realpathSync(join(homedir(),'.openclaw/tools/node')),'lib/node_modules/openclaw/package.json'));
 const {ProxyAgent,fetch:proxyFetch}=require('undici');
 const dispatcher=new ProxyAgent(url.href);
 return Object.assign((url,options={})=>proxyFetch(url,{...options,dispatcher}),{close:()=>dispatcher.close()});
}
