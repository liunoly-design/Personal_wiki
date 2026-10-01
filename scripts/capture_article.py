#!/usr/bin/env python3
"""Capture one supported public URL. No account cookies or browser bypass."""
import argparse
import http.client
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
    from .media_download import extract_public, video_assets, direct_video_asset
    from .attachment_resume import atomic_json
except ImportError:
    from media_download import extract_public, video_assets, direct_video_asset
    from attachment_resume import atomic_json


def request(url, hosts, limit, dest):
    if urlsplit(url).hostname not in hosts:raise ValueError('Unsupported media host')
    try:
        from .attachment_resume import download
    except ImportError:
        from attachment_resume import download
    download(url,dest,limit=limit)


def select_target_article(soup, url):
    target=urlsplit(url).path.rstrip('/').lower()
    candidates=[]
    for article in soup.select('article'):
        owned=[a for a in article.select('a[href]') if a.find_parent('article') is article]
        if any(urlsplit(a['href']).path.rstrip('/').lower()==target for a in owned):
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


def wechat_video_pending(metadata, html):
    if metadata.get('videos'):
        return True
    soup=BeautifulSoup(html,'html.parser')
    body=soup.select_one('#js_content') or soup
    if body.select('video, iframe.video_iframe, iframe[data-vid], mp-common-videosnap'):
        return True
    return any('v.qq.com/' in (n.get('src','')+n.get('data-src','')) or 'video_player' in (n.get('src','')+n.get('data-src','')) for n in body.select('iframe'))


def capture(url, output, browser_profile=None):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    receipt=out/'capture-result.json'
    if receipt.exists():
        previous=json.loads(receipt.read_text())
        if previous.get('status')=='complete' or (previous.get('resumableMedia') and (Path(previous['directory'])/'article.md').exists()):return previous
    host=urlsplit(url).hostname
    if browser_profile:
        try:
            from .browser_session import browser_html
        except ImportError:
            from browser_session import browser_html
        def session_request(u,hosts,limit,dest):
            if urlsplit(u).hostname in ('x.com','twitter.com','mp.weixin.qq.com'):
                dest.write_text(browser_html(u,browser_profile));return
            request(u,hosts,limit,dest)
    else:session_request=request
    if host=='mp.weixin.qq.com' and browser_profile:
        directory=out/'package';directory.mkdir(exist_ok=True)
        html=browser_html(url,browser_profile);(directory/'raw.html').write_text(html)
        soup=BeautifulSoup(html,'html.parser');body=soup.select_one('#js_content')
        if body is None or not body.get_text(strip=True):raise ValueError('login/captcha required; WeChat content unavailable')
        assets=[]
        for index,n in enumerate(body.select('img'),1):
            remote=n.get('data-src') or n.get('src');relative=f'images/image-{index:02}.jpg'
            if remote:assets.append(dict(kind='image',url=remote,path=relative,status='ready'));n['src']=relative
        for index,n in enumerate(body.select('video,iframe.video_iframe,mp-common-videosnap'),1):
            assets.append(dict(kind='video',url=n.get('src') or n.get('data-src') or url,path=f'videos/video-{index:02}.mp4',status='waiting_metadata'))
        try:
            from .attachment_resume import resume_assets
        except ImportError:
            from attachment_resume import resume_assets
        atomic_json((directory/'manifest.json'),dict(source_url=url,assets=assets))
        result=resume_assets(directory,initial=True);(directory/'article.md').write_text(markdownify(str(body),heading_style='ATX'))
    elif host=='mp.weixin.qq.com':
        config=out/'wechat.toml';config.write_text('[platforms.wechat]\nbrowser = "http"\n[fetch]\nbrowser_attempts = 1\n[output]\nsave_debug_html = "always"\noverwrite = false\n')
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
        video_pending=wechat_video_pending(metadata,html)
        import shutil
        normalized=out/'package'
        if not normalized.exists():shutil.copytree(directory,normalized)
        directory=normalized
        try:
            from .attachment_resume import identify
        except ImportError:
            from attachment_resume import identify
        assets=[]
        for i,x in enumerate(v for v in images if v):
            relative=x.get('local_path') or f'images/missing-{i:02}.jpg'
            assets.append(identify(dict(kind='image',url=x.get('source_url'),path=relative,status='downloaded' if (directory/relative).is_file() else 'failed'),url))
        if video_pending:
            assets.append(identify(dict(kind='video',url=url,path='videos/pending.mp4',status='waiting_metadata',error='WeChat video metadata unavailable'),url))
        # Deduplicate cover/body references by path, keeping the image mapping.
        assets=list({a['path']:a for a in assets}.values())
        atomic_json((directory/'manifest.json'),dict(source_url=url,assets=assets))
        result={'directory':str(directory.resolve()),'status':'partial' if missing or video_pending else 'complete','resumableMedia':True,'missingAssets':[a for a in assets if a['status']!='downloaded'],'video_status':'waiting_for_supported_download' if video_pending else 'not_detected'}
    elif host in ['x.com','twitter.com']:
        directory=out/'package';directory.mkdir(exist_ok=True)
        raw=directory/'raw.html'
        media_info=None;html_available=False
        try:
            if not (directory/'raw-valid.json').exists():session_request(url,{'x.com','www.x.com','twitter.com','www.twitter.com'},8*1024*1024,raw)
            soup=BeautifulSoup(raw.read_text(),'html.parser')
            if soup.select('input[type="password"], #captcha, [data-testid="LoginForm"]'):raise ValueError('login/captcha required')
            article=select_target_article(soup,url);html_available=True
            atomic_json((directory/'raw-valid.json'),{'url':url})
        except (ValueError, OSError, http.client.HTTPException, httpx.HTTPError) as error:
            if any(word in str(error).lower() for word in ('401','403','captcha')):raise
            media_info=json.loads((directory/'extractor.json').read_text()) if (directory/'extractor.json').exists() else extract_public(url)
            atomic_json((directory/'extractor.json'),media_info)
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
                atomic_json((directory/'extractor.json'),media_info)
            except (ValueError, OSError, subprocess.TimeoutExpired):
                pass
        try:
            from .x_context import collect_context
        except ImportError:
            from x_context import collect_context
        if html_available:
            context=collect_context(url,directory,lambda u,p:session_request(u,{'x.com','www.x.com','twitter.com','www.twitter.com'},8*1024*1024,p),soup)
            soup=BeautifulSoup('<article></article>','html.parser');article=soup.article
            for post in context['posts']:
                section=soup.new_tag('section');section['data-post-url']=post['url']
                heading=soup.new_tag('h2');heading.string=('引用帖：' if post.get('role')=='quote' else '串文：')+post['url'];section.append(heading)
                link=soup.new_tag('a',href=post['url']);link.string='帖子来源';section.append(link)
                section.append(BeautifulSoup(post['html'],'html.parser'));article.append(section)
            if context['gaps']:
                note=soup.new_tag('p');note.string='上下文缺失：'+'；'.join(context['gaps']);article.append(note)
        else:
            context={'posts':[], 'gaps':['公开媒体提取仅取得目标帖，无法确认完整串文与引用'], 'pages':[]}
            paragraph=soup.new_tag('p');paragraph.string='上下文缺失：'+context['gaps'][0];article.append(paragraph)
        for n in article.select('button,nav,script,style'):n.decompose()
        assets=[]
        for n in list(article.select('img')):
            u=n.get('src','')
            if '/profile_images/' in u:n.decompose();continue
            rel='images/image-%02d%s'%(len(assets)+1,'.webp' if 'format=webp' in u else '.jpg')
            assets.append({'url':u,'path':rel,'kind':'image','post_url':(n.find_parent('section') or {}).get('data-post-url',url)});n['src']=rel
        video_nodes=list(article.select('video'))
        for index,node in enumerate(video_nodes):
            post=(node.find_parent('section') or {}).get('data-post-url',url)
            source=node.get('src') or (node.find('source') or {}).get('src','')
            try:
                info=media_info if post==url and media_info else extract_public(post)
                videos=video_assets(info)
            except (ValueError,OSError,subprocess.TimeoutExpired):
                try:videos=[direct_video_asset(source)]
                except Exception:videos=[{'kind':'video','status':'waiting_metadata','error':'Public video metadata unavailable','url':source or post}]
            for video_index,item in enumerate(videos):
                item['video_index']=video_index
                item['path']='videos/video-%02d.mp4'%(1+sum(a['kind']=='video' for a in assets));item['post_url']=post
                assets.append(item)
                anchor=soup.new_tag('a',href=item.get('url',post));anchor.string='视频（不转录）';node.insert_before(anchor)
            node.decompose()
        if not video_nodes and media_info:
            for index,item in enumerate(video_assets(media_info),1):
                item.update(path='videos/video-%02d.mp4'%index,post_url=url);assets.append(item)
                anchor=soup.new_tag('a',href=item.get('url',url));anchor.string='视频（原位置无法确认；不转录）';article.append(anchor)
        try:
            from .attachment_resume import identify
        except ImportError:
            from attachment_resume import identify
        assets=[identify(a,url) for a in assets]
        try:
            from .attachment_resume import resume_assets
        except ImportError:
            from attachment_resume import resume_assets
        manifest=directory/'manifest.json'
        prior=json.loads(manifest.read_text()).get('assets',[]) if manifest.exists() else []
        for a in assets:
            old=next((v for v in prior if v.get('id')==a['id'] and v.get('fingerprint')==a['fingerprint']),None)
            if old:a.update({k:v for k,v in old.items() if k in ('status','attempts','sha256','limitReached','error')})
        atomic_json(manifest,{'source_url':url,'assets':assets,'context':context})
        # Use the same bounded downloader for first capture and subsequent recovery.
        media=resume_assets(directory,initial=True)
        assets=media['assets']
        for a in assets:
            if a['status']=='downloaded' and a['kind']=='video':
                for anchor in article.select('a[href]'):
                    if anchor['href']==a['url']:anchor['href']=a['path']
        # Failed attachments keep the original remote link, not a broken local link.
        body=markdownify(str(article),heading_style='ATX')
        for a in assets:
            if a['status']!='downloaded':body=body.replace(']('+a['path']+')',']('+a.get('url',url)+')')
        (directory/'article.md').write_text('---\nsource_url: '+json.dumps(url)+'\n---\n\n'+body)
        atomic_json((directory/'manifest.json'),{'source_url':url,'assets':assets,'context':context})
        result={'directory':str(directory.resolve()),'status':'complete' if all(a['status']=='downloaded' for a in assets) else 'partial','resumableMedia':True,'contextStatus':'partial' if context['gaps'] else 'complete','contextGaps':context['gaps'],'missingAssets':[a for a in assets if a['status']!='downloaded']}
    else:
        try:
            from .blog_capture import capture_blog
        except ImportError:
            from blog_capture import capture_blog
        result=capture_blog(url,out)
    atomic_json(receipt,result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--output',required=True);p.add_argument('--browser-profile');a=p.parse_args()
    print(json.dumps(capture(a.url,a.output,a.browser_profile),ensure_ascii=False))
