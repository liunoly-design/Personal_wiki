// Canonical readable representation; original API body remains separately archived.
export function messageText(message){
 const body=JSON.parse(message.body?.content??'{}');
 if(message.msg_type==='text'||typeof body.text==='string')return body.text??'';
 if(message.msg_type!=='post')throw Error('仅支持保存文本或富文本回复，附件不能当成已读正文');
 const post=body.zh_cn??body.en_us??body;
 if(Array.isArray(post.content_v2)&&post.content_v2.flat().every(x=>x.tag==='md'))return post.content_v2.flat().map(x=>x.text??'').join('\n');
 if(!Array.isArray(post.content))throw Error('回复正文格式不受支持');
 return [post.title,...post.content.map(row=>row.map(x=>{
  if(x.tag==='text'||x.tag==='md')return x.text??'';
  if(x.tag==='a')return `[${x.text??x.href}](${x.href})`;
  if(x.tag==='code_block')return `\n\n\`\`\`${x.language??''}\n${x.text??''}\n\`\`\`\n\n`;
  if(x.tag==='hr')return '\n\n---\n\n';
  if(x.tag==='img')return '（原回复附图片，本文未读取图片内容）';
  throw Error('回复包含暂不支持的富文本元素；未保存不完整正文');
 }).join(''))].filter(Boolean).join('\n\n');
}
export const comparableText=text=>text.replace(/[\s#*_`]/gu,'');
