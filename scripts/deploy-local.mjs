// Deploy a tested, immutable release without touching other plugins or credentials.
import {readFile,writeFile,mkdir,cp,copyFile,rename,chmod,access,readdir,lstat} from 'node:fs/promises';
import {join,resolve} from 'node:path';import {homedir} from 'node:os';import {execFileSync} from 'node:child_process';
const root=resolve(import.meta.dirname,'..'),home=homedir(),configPath=join(home,'.openclaw/openclaw.json');
const packageInfo=JSON.parse(await readFile(join(root,'package.json'),'utf8'));
const originalConfig=await readFile(configPath,'utf8');
const config=JSON.parse(originalConfig);const entry=config.plugins?.entries?.['personal-wiki'];
if(!entry?.config?.enabled)throw Error('Existing authorized Wiki installation required');
const state=entry.config.stateDir;
if(process.env.WIKI_MEDIA_SERVICE_URL||process.env.WIKI_MEDIA_SERVICE_TOKEN_FILE){
 if(!process.env.WIKI_MEDIA_SERVICE_URL||!process.env.WIKI_MEDIA_SERVICE_TOKEN_FILE)throw Error('Both media service settings required');
 const {MediaServiceClient}=await import('../src/media-service-client.js');
 const file=process.env.WIKI_MEDIA_SERVICE_TOKEN_FILE;const info=await lstat(file);
 if(!file.startsWith('/')||!info.isFile()||(info.mode&0o077)||info.uid!==process.getuid())throw Error('Media service token file must be owned and private');
 const client=new MediaServiceClient({baseUrl:process.env.WIKI_MEDIA_SERVICE_URL,token:(await readFile(file,'utf8')).trim()});
 await client.health();
 entry.config.mediaServiceUrl=client.base.origin;entry.config.mediaServiceTokenFile=file;
}

const nashsuState=JSON.parse(await readFile(join(home,'Library/Application Support/com.llmwiki.app/app-state.json'),'utf8'));
const project=Object.entries(nashsuState.projectRegistry??{}).find(([,p])=>p.path===entry.config.vault)?.[0];
if(!project||nashsuState.sourceWatchConfig?.[project]?.autoIngest!==false)throw Error('Disable duplicate automatic ingestion before deploying canonical library');
for(const name of await readdir(join(state,'tasks')).catch(e=>{if(e.code==='ENOENT')return [];throw e;})){if(!name.endsWith('.json'))continue;const j=JSON.parse(await readFile(join(state,'tasks',name),'utf8'));if(['queued','retry','processing','cleanup_pending','delivery_pending'].includes(j.status))throw Error('Wait for active Wiki jobs before deploying');}
const codex='/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex';await access(codex);
execFileSync(entry.config.python,['-c','import httpx, bs4, markdownify, readability, yt_dlp, imageio_ffmpeg, playwright'],{stdio:'ignore'});
const release=join(state,'releases',packageInfo.version);
await mkdir(release,{recursive:false});
for(const name of ['package.json','openclaw.plugin.json','openclaw','src','scripts','vendor','requirements-capture.txt'])await cp(join(root,name),join(release,name),{recursive:true});
const stamp=new Date().toISOString().replaceAll(':','-'),backup=configPath+'.before-wiki-'+packageInfo.version+'-'+stamp;
await writeFile(backup,originalConfig,{flag:'wx',mode:0o600});
const previousDeployment=await readFile(join(state,'deployment.json'),'utf8').then(JSON.parse).catch(e=>{if(e.code==='ENOENT')return {};throw e;});
const previous=previousDeployment.release??'/Users/mac/Documents/personal_OS/Personal-Wiki';
config.plugins.load.paths=config.plugins.load.paths.map(p=>p===previous?release:p);
if(!config.plugins.load.paths.includes(release))throw Error('Wiki installation path not found');
entry.config={...entry.config,canonicalLibrary:true,publishSources:false,...(process.env.WIKI_FLASH_PROXY_URL?{flashProxyUrl:process.env.WIKI_FLASH_PROXY_URL}:{}),codexBinary:codex,compilerModel:entry.config.compilerModel??'gpt-6-sol',wikiAgentId:'wiki'};
// Record deployment separately: plugin schema does not accept arbitrary fields.
const allow=config.agents?.entries?.wiki?.tools?.allow;
if(Array.isArray(allow))config.agents.entries.wiki.tools.allow=[...new Set([...allow,'wiki_record','wiki_status','wiki_retry_translation','wiki_resume','wiki_query','wiki_read','wiki_review','wiki_discuss'])];
const temporary=configPath+'.wiki.tmp';await writeFile(temporary,JSON.stringify(config,null,2)+'\n',{mode:0o600});
// Refuse to lose settings another process changed during staging.
if((await readFile(configPath,'utf8'))!==originalConfig)throw Error('Configuration changed during staging');
await rename(temporary,configPath);
await writeFile(join(state,'deployment.json'),JSON.stringify({version:packageInfo.version,release,backup,deployedAt:new Date().toISOString()},null,2),{mode:0o600});
try{execFileSync('launchctl',['print',`gui/${process.getuid()}/ai.openclaw.gateway`],{stdio:'ignore'});execFileSync('launchctl',['kickstart','-k',`gui/${process.getuid()}/ai.openclaw.gateway`],{stdio:'inherit'});}catch(error){
 execFileSync('launchctl',['bootstrap',`gui/${process.getuid()}`,join(home,'Library/LaunchAgents/ai.openclaw.gateway.plist')],{stdio:'inherit'});
}
console.log(JSON.stringify({version:packageInfo.version,release,backup,restartRequested:true}));
