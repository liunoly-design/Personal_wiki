// Presentation only: evidence line numbers and stored Markdown stay unchanged.
function httpURL(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&u.hostname.includes('.')&&!u.hostname.includes('..')?u.href:null;}catch{return null;}}
function advanceFence(line,current){
 const m=line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);if(!m)return current;
 if(current)return m[1][0]===current.marker[0]&&m[1].length>=current.marker.length&&!m[2].trim()?null:current;
 return {marker:m[1],opening:line};
}
export function readingContext(lines,start){
 const closing=lines[0]==='---'?lines.findIndex((l,i)=>i>0&&l==='---'):-1;
 const metadataEnd=closing>0?closing+1:0;
 const urlLine=(metadataEnd?lines.slice(1,metadataEnd-1):[]).find(l=>/^url:\s*/.test(l));
 const sourceUrl=httpURL(urlLine?.replace(/^url:\s*/,'').replace(/^(["'])(.*)\1$/,'$2'));
 let fenceBefore=null;for(const line of lines.slice(metadataEnd,start-1))fenceBefore=advanceFence(line,fenceBefore);
 const references={};let referenceFence=null;
 for(const line of lines.slice(metadataEnd)){
  const next=advanceFence(line,referenceFence);
  if(!referenceFence&&!next){const m=line.match(/^ {0,3}\[([^\]]+)\]:\s*<?([^\s>]+)>?/);if(m)references[m[1].toLowerCase().replace(/\s+/g,' ')]=m[2];}
  referenceFence=next;
 }
 return {metadataEnd,sourceUrl,fenceBefore,references};
}
function inlineLinks(text,sourceUrl,references){
 const link=(image,label,target)=>{
  label=label.replace(/\s*\n\s*/g,' ');
  const url=httpURL(target)??(sourceUrl&&target.startsWith('/')&&!target.startsWith('//')?new URL(target,sourceUrl).href:null);
  return url?`${image?'!':''}[${label}](${url})`:image?`${label||'图片'}（归档附件）`:label;
 };
 return text.replace(/(!?)\[([^\]]*)\]\(<?([^\s)>]+)>?\)/g,(_,image,label,target)=>link(image,label,target))
 .replace(/(!?)\[([^\]\n]+)\]\[([^\]\n]*)\]/g,(match,image,label,key)=>{const target=references[(key||label).toLowerCase().replace(/\s+/g,' ')];return target?link(image,label,target):match;})
 .replace(/(!?)\[\[([^\]\n]+)\]\]/g,(_,image,value)=>{const label=value.split('|').at(-1).split('/').at(-1);return image?`${label}（归档附件）`:label;});
}
export function renderReading(p,originals=[]){
 let fence=p.fenceBefore;const output=[],plain=[];
 const flush=()=>{if(plain.length){output.push(plain.join('\n').split(/(`+[^`]*`+)/g).map((part,i)=>i%2?part:inlineLinks(part,p.sourceUrl,p.references)).join(''));plain.length=0;}};
 if(fence)output.push(fence.opening);
 for(const [offset,line] of p.content.split('\n').entries()){
  if(p.start+offset<=p.metadataEnd)continue;
  const next=advanceFence(line,fence);
  if(fence||next||/^ {4}|^\t/.test(line)){flush();output.push(line);}
  else if(!/^ {0,3}\[[^\]]+\]:\s*/.test(line))plain.push(line);
  fence=next;
 }
 flush();
 if(fence)output.push(fence.marker);
 const footer=[`本次阅读第 ${p.start}–${p.end} 行，共 ${p.totalLines} 行。`];
 if(p.sourceUrl)footer.push(`来源：[原始网页](${p.sourceUrl})`);
 if(p.end<p.totalLines)footer.push(`继续：小婕 wk 阅读：${p.id} ${p.end+1}`);
 if(p.start>1)footer.push(`从头：小婕 wk 阅读：${p.id} 1`);
 for(const id of originals.slice(0,1))footer.push(`原文阅读：小婕 wk 阅读：${id} 1`);
 return `【Wiki】\n\n${output.join('\n').replace(/^\n+|\n+$/g,'')}\n\n---\n\n${footer.join('\n\n')}`;
}
