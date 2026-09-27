#!/usr/bin/env python3
"""Capture one supported public URL. No account cookies or browser bypass."""
import argparse
import copy
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify
try:
    from .media_download import extract_public, video_assets
except ImportError:
    from media_download import extract_public, video_assets


def request(url, hosts, limit, dest):
    current=url
    for redirect in range(6):
        if urlsplit(current).scheme!='https' or urlsplit(current).hostname not in hosts:
            raise ValueError('Unsupported redirect or media host')
        for attempt in range(5):
            try:
                with httpx.Client(timeout=45,follow_redirects=False) as client:
                    with client.stream('GET',current) as r:
                        if r.status_code in [301,302,303,307,308]:
                            current=str(r.url.join(r.headers['location']));break
                        r.raise_for_status()
                        length=int(r.headers.get('content-length','0'))
                        if length>limit:raise ValueError('Media exceeds download limit; waiting for confirmation')
                        size=0
                        with dest.open('wb') as f:
                            for block in r.iter_bytes():
                                size+=len(block)
                                if size>limit:raise ValueError('Media reached download limit; waiting for confirmation')
                                f.write(block)
                        return
            except (httpx.TransportError,httpx.HTTPStatusError) as error:
                if isinstance(error,httpx.HTTPStatusError) and error.response.status_code not in [408,429,500,502,503,504]:raise
                if attempt==4:raise
                time.sleep(min(2**attempt,8))
        else:raise ValueError('Fetch failed')
    raise ValueError('Too many redirects')


def select_target_article(soup, url):
    target=urlsplit(url).path.rstrip('/')
    candidates=[]
    for article in soup.select('article'):
        owned=[a for a in article.select('a[href]') if a.find_parent('article') is article]
        if any(urlsplit(a['href']).path.rstrip('/')==target for a in owned):
            candidates.append(article)
    # Duplicate wrapper markup may contain the same target again. Keep the
    # deepest matching target while retaining quotes inside it.
    leaves=[a for a in candidates if not any(b is not a and any(p is a for p in b.parents) for b in candidates)]
    def signature(a):
        return (a.get_text(' ',strip=True),tuple((n.name,n.get('href'),n.get('src')) for n in a.select('a,img,video,source')))
    leaves=list({signature(a):a for a in leaves}.values())
    if len(leaves)>1:
        # Responsive copies can show the same post with/without an embedded
        # quote. Compare only the target's own content, then retain a variant
        # containing every quote seen in the other equivalent copies.
        def own_signature(a):
            own=copy.copy(a)
            for nested in own.select('article'):nested.decompose()
            return signature(own)
        if len({own_signature(a) for a in leaves})==1:
            quote_sets=[{signature(q) for q in a.select('article')} for a in leaves]
            union=set().union(*quote_sets)
            complete=[a for a,quotes in zip(leaves,quote_sets) if quotes==union]
            if complete:leaves=[complete[0]]
    if len(leaves)!=1:
        raise ValueError('Cannot identify the requested X post unambiguously')
    return leaves[0]


def capture(url, output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    receipt=out/'capture-result.json'
    if receipt.exists():return json.loads(receipt.read_text())
    host=urlsplit(url).hostname
    if host=='mp.weixin.qq.com':
        config=out/'wechat.toml';config.write_text('[platforms.wechat]\nbrowser = "http"\n[output]\nsave_debug_html = "always"\noverwrite = false\n')
        cmd=[str(Path(sys.executable).parent/'magicmd'),'convert',url,'--config',str(config),'--output',str(out/'packages'),'--debug']
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        (out/'fetch.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise ValueError('WeChat capture failed; inspect local fetch.log, login may be required')
        articles=list((out/'packages').glob('*/article.md'))
        if len(articles)!=1:raise ValueError('Expected one WeChat article')
        directory=articles[0].parent
        metadata=json.loads((directory/'metadata.json').read_text())
        # MagicMD records failed media in its report; do not claim full capture
        # unless every declared local image exists.
        images=metadata.get('images',[])+[metadata.get('cover_image'),metadata.get('share_cover_image')]
        missing=[x for x in images if x and (not x.get('local_path') or not (directory/x['local_path']).is_file())]
        html='\n'.join(p.read_text(errors='replace') for p in directory.glob('*.html'))
        video_pending=bool(metadata.get('videos')) or any(marker in html for marker in ['<video', 'vid=', 'iframe class="video'])
        result={'directory':str(directory.resolve()),'status':'partial' if missing or video_pending else 'complete','video_status':'waiting_for_supported_download' if video_pending else 'not_detected'}
    elif host in ['x.com','twitter.com']:
        directory=out/'package';directory.mkdir(exist_ok=True)
        raw=directory/'raw.html'
        media_info=None
        try:
            request(url,{'x.com','www.x.com','twitter.com','www.twitter.com'},8*1024*1024,raw)
            soup=BeautifulSoup(raw.read_text(),'html.parser')
            article=select_target_article(soup,url)
        except (ValueError, httpx.HTTPError):
            media_info=extract_public(url)
            (directory/'extractor.json').write_text(json.dumps(media_info,ensure_ascii=False,indent=2))
            description=media_info.get('description')
            if not description:
                description=next((e.get('description') for e in media_info.get('entries',[]) if e.get('description')),None)
            if not description:raise ValueError('X text unavailable; retained metadata only')
            soup=BeautifulSoup('<article></article>','html.parser');article=soup.article
            paragraph=soup.new_tag('p');paragraph.string=description;article.append(paragraph)
        has_video=bool(article.select('video')) or media_info is not None
        if has_video and media_info is None:
            try:
                media_info=extract_public(url)
                (directory/'extractor.json').write_text(json.dumps(media_info,ensure_ascii=False,indent=2))
            except (ValueError, subprocess.TimeoutExpired):
                pass
        for n in article.select('button,nav,script,style'):n.decompose()
        assets=[]
        for n in list(article.select('img')):
            u=n.get('src','')
            if '/profile_images/' in u:n.decompose();continue
            rel='images/image-%02d%s'%(len(assets)+1,'.webp' if 'format=webp' in u else '.jpg')
            assets.append({'url':u,'path':rel,'kind':'image'});n['src']=rel
        for node in list(article.select('video')):node.decompose()
        videos=video_assets(media_info) if media_info else ([{'kind':'video','status':'waiting','error':'Public video metadata unavailable'}] if has_video else [])
        for i,item in enumerate(videos):
            item['path']='videos/video-%02d.mp4'%(i+1)
            assets.append(item)
            anchor=soup.new_tag('a',href=item.get('url',url));anchor.string='视频 %d（不转录）'%(i+1);article.append(anchor)
        for a in assets:
            if a.get('status')=='waiting':continue
            dest=directory/a['path'];dest.parent.mkdir(exist_ok=True);temp=dest.with_suffix(dest.suffix+'.part')
            try:
                request(a['url'],{'pbs.twimg.com','video.twimg.com'},1000000000 if a['kind']=='video' else 30000000,temp)
                if a['kind']=='video':
                    import imageio_ffmpeg,re
                    probe=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(temp)],capture_output=True,text=True,timeout=20)
                    duration=re.search(r'Duration: (\d+):(\d+):([\d.]+)',probe.stderr)
                    size=re.search(r'Video:.*?\b(\d{2,5})x(\d{2,5})\b',probe.stderr)
                    if not duration or not size:raise ValueError('Cannot verify video duration or resolution')
                    seconds=int(duration[1])*3600+int(duration[2])*60+float(duration[3])
                    if seconds>1800 or min(int(size[1]),int(size[2]))>1080:raise ValueError('Video exceeds duration/resolution limit; awaiting handling')
                temp.rename(dest);a['status']='downloaded'
                if a['kind']=='video':
                    for anchor in article.select('a[href]'):
                        if anchor['href']==a['url']:anchor['href']=a['path']
            except Exception:
                a['status']='failed_or_waiting';a['error']='Media unavailable or exceeds limit; retained partial file for inspection'
        # Failed attachments keep the original remote link, not a broken local link.
        body=markdownify(str(article),heading_style='ATX')
        for a in assets:
            if a['status']!='downloaded':body=body.replace(']('+a['path']+')',']('+a.get('url',url)+')')
        (directory/'article.md').write_text('---\nsource_url: '+json.dumps(url)+'\n---\n\n'+body)
        (directory/'manifest.json').write_text(json.dumps({'source_url':url,'assets':assets},ensure_ascii=False,indent=2))
        result={'directory':str(directory.resolve()),'status':'complete' if all(a['status']=='downloaded' for a in assets) else 'partial'}
    else:raise ValueError('Unsupported platform')
    receipt.write_text(json.dumps(result));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(capture(a.url,a.output),ensure_ascii=False))
