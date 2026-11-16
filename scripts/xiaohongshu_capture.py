"""Single public Xiaohongshu note: never execute state or read account cookies.

Field contract and parser reference pinned in docs/research/xiaohongshu-ingestion-options-2026-11-16.md.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.parse import parse_qs
from bs4 import BeautifulSoup
try:
    from .blog_capture import fetch_public,resolve_public
    from .image_types import image_extension
except ImportError:
    from blog_capture import fetch_public,resolve_public
    from image_types import image_extension

LONG_HOSTS=('www.xiaohongshu.com','xiaohongshu.com')
SHORT_HOSTS=('xhslink.com','www.xhslink.com','xhslink.cn','www.xhslink.cn')
MOBILE_UA='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
DESKTOP_UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36'

def resolve_xhs(url):
    # Preserve mainland CDN geography when the local proxy returns FakeIP.
    return resolve_public(url,doh_endpoint='https://dns.alidns.com/resolve')


def note_identity(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.hostname not in LONG_HOSTS:raise ValueError('Single Xiaohongshu note URL required')
    match=re.fullmatch(r'/(?:explore|discovery/item)/([a-f0-9]{24})/?',u.path)
    if not match:raise ValueError('Single Xiaohongshu note URL required')
    return match[1]


def check_page_url(url):
    u=urlsplit(url)
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.hostname not in LONG_HOSTS+SHORT_HOSTS:raise ValueError('Unexpected Xiaohongshu redirect rejected')
    if u.hostname in LONG_HOSTS and u.path.startswith(('/login','/404','/website-login')):
        code=parse_qs(u.query).get('error_code',[''])[0]
        detail='; share token missing or rejected (300031), note visibility unconfirmed' if code=='300031' else '; complete share URL or authorized session needed'
        raise ValueError('Xiaohongshu public access gated'+detail)


def initial_state(html):
    soup=BeautifulSoup(html,'html.parser')
    for script in soup.select('script'):
        text=script.string or script.get_text()
        assignment=re.search(r'(?:window\.)?__INITIAL_STATE__\s*=\s*',text)
        if not assignment:continue
        start=assignment.end()
        if text[start:start+1]!='{':raise ValueError('Xiaohongshu state is not an object')
        depth=0;quoted=False;escaped=False
        for index in range(start,len(text)):
            char=text[index]
            if quoted:
                if escaped:escaped=False
                elif char=='\\':escaped=True
                elif char=='"':quoted=False
                continue
            if char=='"':quoted=True
            elif char in '{[':depth+=1
            elif char in '}]':depth-=1
            if depth==0:
                raw=text[start:index+1]
                # Match JSON strings first: sentinel words inside them are data.
                clean=re.sub(r'"(?:\\.|[^"\\])*"|\b(?:undefined|NaN|Infinity)\b',lambda m:m[0] if m[0].startswith('"') else 'null',raw)
                return json.loads(clean)
        raise ValueError('Xiaohongshu initial state truncated; original retained')
    raise ValueError('Xiaohongshu full note state unavailable; preview is insufficient')


def capture(url, output, desktop=False):
    check_page_url(url)
    directory=Path(output)/'package';directory.mkdir(parents=True,exist_ok=True)
    requested_id=note_identity(url) if urlsplit(url).hostname in LONG_HOSTS else None
    evidence={'requested_url':url}
    try:
        final=fetch_public(url,20*1024*1024,directory/'original.html',user_agent=DESKTOP_UA if desktop else MOBILE_UA,redirect_check=check_page_url,resolve_addresses=resolve_xhs,response_metadata=evidence)
    finally:
        (directory/'fetch-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    check_page_url(final);target=note_identity(final)
    if requested_id and target!=requested_id:raise ValueError('Xiaohongshu redirected note identity mismatch')
    state=initial_state((directory/'original.html').read_text())
    (directory/'initial-state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
    details=state.get('note',{}).get('noteDetailMap',{})
    note=details.get(target,{}).get('note',{})
    if not note and 'noteData' in state:
        mobile=state['noteData']
        if mobile.get('hasError'):raise ValueError('Xiaohongshu public access gated; full mobile note unavailable')
        note=mobile.get('data',{}).get('noteData',{})
    if note.get('noteId')!=target:raise ValueError('Xiaohongshu target note identity missing or mismatched')
    if note.get('type') not in ('normal','video'):raise ValueError('Xiaohongshu unsupported note type; original retained')
    if not isinstance(note.get('desc'),str) or not isinstance(note.get('imageList'),list):raise ValueError('Xiaohongshu full note fields missing')
    canonical='https://www.xiaohongshu.com/explore/'+target
    title=note.get('title') or '小红书笔记'
    user=note.get('user') or {};author=user.get('nickname') or user.get('nickName') or '未提供'
    # These fields are text, not author-supplied Markdown/HTML.
    def literal(text):return re.sub(r'([\\`*_[\]<>#])',r'\\\1',str(text))
    parts=['# '+literal(title),'来源：'+canonical,'作者：'+literal(author),literal(note['desc'])]
    assets=[]
    for index,image in enumerate(note['imageList'],1):
        remote=image.get('urlDefault') or image.get('url')
        if not remote:
            options=image.get('infoList') or []
            remote=next((x.get('url') for x in options if x.get('url')),None)
        asset={'kind':'image','url':remote,'index':index,'status':'failed'};assets.append(asset)
        if remote:
            # Some server-provided CDN URLs use HTTP. Upgrade, never downgrade.
            if remote.startswith('http://'):remote='https://'+remote[7:];asset['url']=remote
            raw=directory/f'image-response-{index:03}'
            try:
                fetch_public(remote,25*1024*1024,raw,resolve_addresses=resolve_xhs)
                relative=f'images/image-{index:03}'+image_extension(raw.read_bytes())
                destination=directory/relative;destination.parent.mkdir(exist_ok=True);raw.rename(destination)
                asset.update(status='downloaded',path=relative);parts.append(f'![图片 {index}]({relative})')
            except (ValueError,OSError) as error:asset['error']=type(error).__name__
        if asset['status']!='downloaded':parts.append(f'图片 {index}：待补（未获得完整图片）')
        if image.get('livePhoto') or image.get('stream'):
            assets.append({'kind':'video','index':index,'status':'waiting_metadata','error':'Live photo transcription required'})
    if note['type']=='video':assets.append({'kind':'video','status':'waiting_metadata','error':'Video transcription required; Mini generic media interface not configured'})
    if not note['desc'].strip() and not assets:raise ValueError('Xiaohongshu note body empty; retained for review')
    metadata={'url':canonical,'noteId':target,'type':note['type'],'title':title,'author':user,'time':note.get('time'),'lastUpdateTime':note.get('lastUpdateTime'),'assets':assets,'imageSource':'server-provided default image; not a lossless-original guarantee'}
    (directory/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    (directory/'manifest.json').write_text(json.dumps({'source_url':canonical,'assets':assets},ensure_ascii=False,indent=2))
    (directory/'article.md').write_text('\n\n'.join(parts)+'\n')
    missing=[a for a in assets if a['status']!='downloaded']
    return {'directory':str(directory.resolve()),'url':canonical,'status':'partial' if missing else 'complete','missingAssets':missing,'provider':'Xiaohongshu public initial state'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--output',required=True);parser.add_argument('--desktop',action='store_true');args=parser.parse_args()
    print(json.dumps(capture(args.url,args.output,desktop=args.desktop),ensure_ascii=False))
