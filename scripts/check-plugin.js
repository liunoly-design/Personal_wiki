import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';import {tmpdir} from 'node:os';import {join,resolve} from 'node:path';import {execFileSync} from 'node:child_process';
const root=resolve(import.meta.dirname,'..');const state=mkdtempSync(join(tmpdir(),'wiki-plugin-check-'));
try{
 const config=join(state,'openclaw.json');writeFileSync(config,JSON.stringify({gateway:{mode:'local'},plugins:{allow:['personal-wiki'],load:{paths:[root]},entries:{'personal-wiki':{enabled:true,config:{enabled:true,accountId:'default',entryAgentId:'xiaojie',allowedSenderIds:['ou_test'],allowedConversationIds:['oc_test'],vault:join(state,'vault'),stateDir:join(state,'jobs'),python:'/usr/bin/python3'}}}}}));
 const env={...process.env,OPENCLAW_STATE_DIR:state,OPENCLAW_CONFIG_PATH:config};
 const doctor=JSON.parse(execFileSync('openclaw',['plugins','doctor','--json'],{env,encoding:'utf8',maxBuffer:4*1024*1024}));if(!doctor.ok)throw Error('Plugin doctor failed');
 const runtime=JSON.parse(execFileSync('openclaw',['plugins','inspect','personal-wiki','--runtime','--json'],{env,encoding:'utf8',maxBuffer:4*1024*1024}));
 if(runtime.plugin?.status!=='loaded'||!runtime.typedHooks?.some(h=>h.name==='reply_dispatch'))throw Error('Wiki hook not loaded');
 console.log(JSON.stringify({isolated:true,loaded:true,hook:'reply_dispatch'}));
}finally{rmSync(state,{recursive:true,force:true});}
