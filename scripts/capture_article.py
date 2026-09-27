#!/usr/bin/env python3
"""Capture one supported public URL. No account cookies or browser bypass."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify


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
        result={'directory':str(directory.resolve()),'status':'partial' if missing else 'complete'}
    elif host in ['x.com','twitter.com']:
        directory=out/'package';directory.mkdir(exist_ok=True)
        raw=directory/'raw.html';request(url,{'x.com','www.x.com','twitter.com','www.twitter.com'},8*1024*1024,raw)
        soup=BeautifulSoup(raw.read_text(),'html.parser');articles=soup.select('article')
        if not articles:raise ValueError('X article unavailable; login or another parser is required')
        article=select_target_article(soup,url)
        for n in article.select('button,nav,script,style'):n.decompose()
        assets=[]
        for n in list(article.select('img')):
            u=n.get('src','')
            if '/profile_images/' in u:n.decompose();continue
            rel='images/image-%02d%s'%(len(assets)+1,'.webp' if 'format=webp' in u else '.jpg')
            assets.append({'url':u,'path':rel,'kind':'image'});n['src']=rel
        for i,n in enumerate(list(article.select('video'))):
            u=n.get('src') or (n.find('source') or {}).get('src')
            if not u:continue
            rel='videos/video-%02d.mp4'%(i+1);assets.append({'url':u,'path':rel,'kind':'video'})
            a=soup.new_tag('a',href=rel);a.string='视频 %d（不转录）'%(i+1);n.replace_with(a)
        for a in assets:
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
            except Exception:
                a['status']='failed_or_waiting';a['error']='Media unavailable or exceeds limit; retained partial file for inspection'
        # Failed attachments keep the original remote link, not a broken local link.
        body=markdownify(str(article),heading_style='ATX')
        for a in assets:
            if a['status']!='downloaded':body=body.replace(']('+a['path']+')',']('+a['url']+')')
        (directory/'article.md').write_text('---\nsource_url: '+json.dumps(url)+'\n---\n\n'+body)
        (directory/'manifest.json').write_text(json.dumps({'source_url':url,'assets':assets},ensure_ascii=False,indent=2))
        result={'directory':str(directory.resolve()),'status':'complete' if all(a['status']=='downloaded' for a in assets) else 'partial'}
    else:raise ValueError('Unsupported platform')
    receipt.write_text(json.dumps(result));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(capture(a.url,a.output),ensure_ascii=False))
