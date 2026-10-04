"""Per-attachment bounded download and immutable publication inputs."""
import argparse
import hashlib
import http.client
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin
try:
    from .blog_capture import public_addresses, PinnedHTTPS
except ImportError:
    from blog_capture import public_addresses, PinnedHTTPS
LIMIT=1000000000

class ConfirmationRequired(ValueError):pass


def atomic_json(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    temporary.replace(path)
    directory=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)


def identify(asset,source):
    asset=dict(asset)
    fields={k:asset.get(k) for k in ('url','path','kind','post_url','duration','expected_size','width','height')}
    identity=json.dumps([source,fields],sort_keys=True,ensure_ascii=False)
    asset['id']=hashlib.sha256((source+'\n'+str(asset.get('path'))).encode()).hexdigest()[:16]
    asset['fingerprint']=hashlib.sha256(identity.encode()).hexdigest()
    return asset


def safe_destination(directory,relative):
    if not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:raise ValueError('Unsafe attachment path')
    dest=directory/relative
    if directory.resolve() not in dest.resolve().parents:raise ValueError('Unsafe attachment path')
    for p in [dest,*dest.parents]:
        if p==directory.parent:break
        if p.is_symlink():raise ValueError('Attachment symlink rejected')
    dest.parent.mkdir(parents=True,exist_ok=True)
    return dest


def download(url,dest,limit=LIMIT,approved=False,validate_url=None,resolve_addresses=public_addresses):
    """Single network attempt. Range resumes only with an exact strong validator."""
    partial=dest.with_suffix(dest.suffix+'.part');progress=partial.with_suffix(partial.suffix+'.json')
    current=url
    for _ in range(6):
        if validate_url:validate_url(current)
        u,addresses=resolve_addresses(current);connection=PinnedHTTPS(u.hostname,addresses[0])
        old=json.loads(progress.read_text()) if progress.exists() else {}
        offset=partial.stat().st_size if partial.exists() and old.get('url')==current and old.get('validator') else 0
        if not approved and offset>=limit:raise ConfirmationRequired('Download reached 1 GB; confirmation required')
        headers={'User-Agent':'PersonalWiki/0.4.2','Accept-Encoding':'identity'}
        if offset:headers.update(Range=f'bytes={offset}-',**{'If-Range':old['validator']})
        try:
            connection.request('GET',u.path+('?' + u.query if u.query else ''),headers=headers);response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                current=urljoin(current,response.getheader('Location') or '');continue
            if response.status in (401,403):raise ValueError(f'HTTP {response.status}; login required')
            if response.status not in (200,206):raise OSError('HTTP '+str(response.status))
            validator=response.getheader('ETag')
            if validator and validator.startswith('W/'):validator=None
            if offset and response.status==206:
                match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)',response.getheader('Content-Range') or '')
                if not match or int(match[1])!=offset or validator!=old['validator']:
                    progress.unlink(missing_ok=True)
                    raise ValueError('Unsafe partial response; validator/range changed; next attempt restarts this attachment')
            elif response.status==206:raise ValueError('Unexpected partial response')
            else:offset=0
            length=int(response.getheader('Content-Length') or 0)
            if length and length+offset>limit and not approved:raise ConfirmationRequired('Estimated download exceeds 1 GB; confirmation required')
            atomic_json(progress,dict(url=current,validator=validator))
            with partial.open('ab' if offset else 'wb') as f:
                size=offset
                while True:
                    remaining=65536 if approved else min(65536,limit-size)
                    if remaining<=0:raise ConfirmationRequired('Download reached 1 GB; confirmation required')
                    block=response.read(remaining)
                    if not block:break
                    f.write(block);size+=len(block);f.flush()
                    if not approved and size>=limit:raise ConfirmationRequired('Download reached 1 GB; confirmation required')
                os.fsync(f.fileno())
            if length and size-offset!=length:raise OSError('Incomplete attachment response')
            partial.replace(dest);progress.unlink(missing_ok=True);return
        finally:connection.close()
    raise ValueError('Too many redirects')


def verify_video(dest,approved):
    import imageio_ffmpeg
    probe=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(dest)],capture_output=True,text=True,timeout=30)
    duration=re.search(r'Duration: (\d+):(\d+):([\d.]+)',probe.stderr);size=re.search(r'Video:.*?\b(\d{2,5})x(\d{2,5})\b',probe.stderr)
    if not duration or not size:raise ValueError('Cannot verify video metadata')
    seconds=int(duration[1])*3600+int(duration[2])*60+float(duration[3])
    if min(int(size[1]),int(size[2]))>1080:raise ValueError('Video exceeds 1080p; confirmation cannot override')
    if seconds>1800 and not approved:raise ConfirmationRequired('Video exceeds 30 minutes; confirmation required')


def resume_assets(directory,selected=None,approvals=None,initial=False,browser_profile=None):
    directory=Path(directory);path=directory/'manifest.json';manifest=json.loads(path.read_text());assets=[];approvals=approvals or {}
    for original in manifest['assets']:
        a=identify(original,manifest['source_url']);assets.append(a)
        if a.get('status')=='downloaded':
            dest=safe_destination(directory,a['path'])
            if not dest.is_file() or (a.get('sha256') and hashlib.sha256(dest.read_bytes()).hexdigest()!=a['sha256']):raise ValueError('Successful attachment integrity mismatch')
            a['sha256']=hashlib.sha256(dest.read_bytes()).hexdigest();continue
        if selected and selected!=a['id']:continue
        if a.get('attempts',0)>=5 and not initial:
            a['status']='waiting_retry';continue
        if a['kind']=='video' and (not a.get('duration') or not a.get('width') or not a.get('height')) and not initial:
            try:
                try:
                    from .media_download import extract_public, video_assets, direct_video_asset
                except ImportError:
                    from media_download import extract_public, video_assets, direct_video_asset
                a['metadataAttempts']=a.get('metadataAttempts',0)+1
                atomic_json(path,{**manifest,'assets':assets+manifest['assets'][len(assets):]})
                origin=a.get('post_url') or manifest['source_url']
                if browser_profile and '/status/' in origin:
                    try:
                        from .browser_session import browser_html
                        from .x_context import parse_posts, post_url
                    except ImportError:
                        from browser_session import browser_html
                        from x_context import parse_posts, post_url
                    from bs4 import BeautifulSoup
                    posts=parse_posts(BeautifulSoup(browser_html(origin,browser_profile),'html.parser'))
                    html=posts.get(post_url(origin),{}).get('html','');nodes=BeautifulSoup(html,'html.parser').select('video')
                    node=nodes[a.get('video_index',0)]
                    metadata=dict(kind='video',url=node.get('src'),duration=float(node.get('data-duration',0)),width=int(node.get('data-width',0)),height=int(node.get('data-height',0)))
                else:metadata=video_assets(extract_public(origin))[a.get('video_index',0)] if '/status/' in origin else direct_video_asset(a['url'])
                a.update(metadata);a.update(identify(a,manifest['source_url']))
            except Exception as error:
                a.update(status='waiting_login' if 'login' in str(error) or 'captcha' in str(error) else 'waiting_metadata',error=str(error));continue
        approval=approvals.get(a['id'],{});approved=approval.get('fingerprint')==a['fingerprint']
        if a['kind']=='video':
            if not a.get('duration') or not a.get('width') or not a.get('height') or min(a['width'],a['height'])>1080:
                a.update(status='waiting_metadata',error='视频时长/分辨率未验证或超过1080p');continue
            if (a['duration']>1800 or (a.get('expected_size') or 0)>LIMIT or a.get('limitReached')) and not approved:
                a.update(status='waiting_confirmation',error='超过30分钟或1GB，需要精确确认');continue
        try:
            dest=safe_destination(directory,a['path'])
            # A selected explicit recovery starts a new bounded cycle, via reset_attempts.
            a['attempts']=a.get('attempts',0)+1
            atomic_json(path,{**manifest,'assets':assets+manifest['assets'][len(assets):]})
            download(a['url'],dest,limit=LIMIT if a['kind']=='video' else 30000000,approved=approved if a['kind']=='video' else False)
            if a['kind']=='video':verify_video(dest,approved)
            a.update(status='downloaded',sha256=hashlib.sha256(dest.read_bytes()).hexdigest());a.pop('error',None)
        except ConfirmationRequired as error:
            a.update(status='waiting_confirmation',limitReached=True,error=str(error))
            # A post-download probe can discover duration; retain bytes privately.
            if 'dest' in locals() and dest.exists():dest.replace(dest.with_suffix(dest.suffix+'.part'))
        except Exception as error:
            a.update(status='waiting_login' if 'login' in str(error) or 'captcha' in str(error) else 'failed',error=str(error))
        atomic_json(path,{**manifest,'assets':assets+manifest['assets'][len(assets):]})
    manifest['assets']=assets;atomic_json(path,manifest)
    missing=[a for a in assets if a.get('status')!='downloaded']
    return dict(directory=str(directory.resolve()),status='partial' if missing else 'complete',resumableMedia=True,missingAssets=missing,assets=assets)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);parser.add_argument('--asset');parser.add_argument('--approvals');parser.add_argument('--cycle');parser.add_argument('--browser-profile');args=parser.parse_args()
    if args.cycle:
        path=Path(args.directory)/'manifest.json';m=json.loads(path.read_text())
        for a in m['assets']:
            if identify(a,m['source_url'])['id']==args.asset and a.get('cycle')!=args.cycle:a['attempts']=0;a['cycle']=args.cycle
        atomic_json(path,m)
    print(json.dumps(resume_assets(args.directory,args.asset,json.loads(Path(args.approvals).read_text()) if args.approvals else {},browser_profile=args.browser_profile),ensure_ascii=False))
