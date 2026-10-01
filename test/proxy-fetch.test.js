import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer,request} from 'node:http';
import {connect} from 'node:net';
import {once} from 'node:events';
import {createProxyFetch} from '../src/proxy-fetch.js';

test('configured fetch uses its own proxy without changing global fetch',async()=>{
 const target=createServer((req,res)=>res.end('through proxy'));
 let tunnels=0;
 const proxy=createServer((req,res)=>{tunnels++;const upstream=request(req.url,{method:req.method,headers:req.headers},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);});req.pipe(upstream);upstream.on('error',()=>res.destroy());});
 proxy.on('connect',(req,client,head)=>{
  tunnels++;const [host,port]=req.url.split(':');const upstream=connect(Number(port),host,()=>{client.write('HTTP/1.1 200 Connection Established\r\n\r\n');upstream.write(head);client.pipe(upstream);upstream.pipe(client);});
  client.on('error',()=>upstream.destroy());upstream.on('error',()=>client.destroy());client.on('close',()=>upstream.destroy());
 });
 target.listen(0,'127.0.0.1');proxy.listen(0,'127.0.0.1');await Promise.all([once(target,'listening'),once(proxy,'listening')]);
 const original=globalThis.fetch,fetchViaProxy=createProxyFetch(`http://127.0.0.1:${proxy.address().port}`);
 try{const r=await fetchViaProxy(`http://127.0.0.1:${target.address().port}`,{signal:AbortSignal.timeout(5000)});assert.equal(await r.text(),'through proxy');assert.equal(tunnels,1);assert.equal(globalThis.fetch,original);}
 finally{await fetchViaProxy.close();target.close();proxy.close();}
});
