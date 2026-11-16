"""Capture an evidenced X thread and complete DraftJS article via FxEmbed v2.

Provider contract: https://github.com/FxEmbed/FxEmbed (v2 thread API).
Original JSON is retained. Missing relations, unknown blocks and tombstones fail
closed; the provider's observed chain is not proof about hidden/deleted posts.
"""
import argparse
import json
import hashlib
import re
import ipaddress
from urllib.request import Request, urlopen
from pathlib import Path
try:
    from .platform_media import download_media,acquire_video
except ImportError:from platform_media import download_media,acquire_video
from urllib.parse import urlsplit
try:
    from .blog_capture import fetch_public as pinned_fetch, public_addresses
    from .attachment_resume import atomic_json
except ImportError:
    from blog_capture import fetch_public as pinned_fetch, public_addresses
    from attachment_resume import atomic_json


def resolve_provider(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('api.fxtwitter.com','pbs.twimg.com','abs.twimg.com') or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Unsupported provider network target')
    try:return public_addresses(url)
    except (ValueError, OSError):
        # Resolve fixed provider hosts via authenticated HTTPS DNS, then pin a
        # validated public address. Never connect to the system fake-IP result.
        request = Request('https://dns.google/resolve?name='+parsed.hostname+'&type=A', headers={'Accept':'application/dns-json','User-Agent':'PersonalWiki/1.0'})
        with urlopen(request,timeout=20) as response:
            result=json.loads(response.read(65536))
        addresses=[a['data'] for a in result.get('Answer',[]) if a.get('type')==1]
        if result.get('Status')!=0 or not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast for a in addresses):
            raise ValueError('Provider public DNS resolution unavailable')
        return parsed,addresses


def fetch_public(url,limit,destination):
    return pinned_fetch(url,limit,destination,resolve_addresses=resolve_provider)


def capture(url, output):
    parsed=urlsplit(url)
    match = re.fullmatch(r'/([\w]+)/status/(\d+)/?', parsed.path)
    if not match or parsed.hostname not in ('x.com', 'twitter.com') or parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Single X post required')
    author_name, target_id = match.groups()
    directory = Path(output) / 'package'
    directory.mkdir(parents=True, exist_ok=True)
    raw = directory / 'provider.json'
    if not raw.exists():
        fetch_public('https://api.fxtwitter.com/2/thread/' + target_id, 8*1024*1024, raw)
    response = json.loads(raw.read_text())
    thread = response.get('thread')
    if response.get('code') != 200 or not isinstance(thread, list) or not thread:
        raise ValueError('X provider did not return an evidenced thread')
    if any(t.get('type') != 'status' or not isinstance(t.get('author'), dict) for t in thread):
        raise ValueError('X unavailable thread entry retained; full context missing')
    targets = [t for t in thread if str(t.get('id')) == target_id]
    if len(targets) != 1 or targets[0]['author'].get('screen_name', '').lower() != author_name.lower():
        raise ValueError('X provider source identity mismatch')
    owner = str(targets[0]['author'].get('id', ''))
    if not owner or any(str(t['author'].get('id')) != owner for t in thread):
        raise ValueError('X thread contains foreign author')
    if len({str(t.get('id')) for t in thread}) != len(thread):
        raise ValueError('X thread identities are duplicated')
    for index, post in enumerate(thread):
        if 'replying_to' not in post:
            raise ValueError('X reply relationship missing')
        parent = post['replying_to']
        if index and (not isinstance(parent, dict) or str(parent.get('status')) != str(thread[index-1]['id'])):
            raise ValueError('X same-author chain is not continuous')
        if not index and parent is not None:
            if not isinstance(parent, dict) or parent.get('screen_name', '').lower() == author_name.lower():
                raise ValueError('X same-author ancestor missing')

    assets, missing, evidence = [], [], []
    manifest_path = directory/'manifest.json'
    prior_assets = json.loads(manifest_path.read_text()).get('assets',[]) if manifest_path.exists() else []
    media_paths = {}
    block_count = 0

    def image(remote, label='图片'):
        if not isinstance(remote, str) or urlsplit(remote).hostname not in ('pbs.twimg.com', 'abs.twimg.com'):
            raise ValueError('Unsupported X image origin')
        if remote not in media_paths:
            relative = 'images/' + hashlib.sha256(remote.encode()).hexdigest()[:20] + '.jpg'
            destination = directory / relative
            destination.parent.mkdir(exist_ok=True)
            asset = dict(kind='image', url=remote, path=relative, status='downloaded')
            try:
                prior=next((a for a in prior_assets if a.get('url')==remote),{})
                if not (destination.is_file() and prior.get('sha256')==hashlib.sha256(destination.read_bytes()).hexdigest()):
                    attempts=prior.get('attempts',0)
                    if attempts>=5:raise ValueError('Image retry budget exhausted')
                    asset['attempts']=attempts+1
                    fetch_public(remote, 25*1024*1024, destination)
                else:asset['attempts']=prior.get('attempts',0)
                asset['sha256'] = hashlib.sha256(destination.read_bytes()).hexdigest()
            except (ValueError, OSError) as error:
                asset.update(status='failed', error=type(error).__name__)
                missing.append(asset)
            assets.append(asset)
            media_paths[remote] = relative if asset['status'] == 'downloaded' else remote
        return f'![{label}]({media_paths[remote]})'

    def article_body(article):
        nonlocal block_count
        content = article.get('content') or {}
        blocks = content.get('blocks')
        if not isinstance(blocks, list) or not blocks:
            raise ValueError('X long article has only a preview; full blocks missing')
        mapping = content.get('entityMap') or {}
        entities = {str(e['key']): e['value'] for e in mapping} if isinstance(mapping, list) else mapping
        media = {str(m['media_id']): m for m in article.get('media_entities', [])}
        result = ['# ' + article.get('title', 'X 长文章')]
        for block in blocks:
            block_count += 1
            kind, text = block.get('type'), block.get('text')
            if not isinstance(text, str):
                raise ValueError('X article block text missing')
            if kind == 'atomic':
                ranges = block.get('entityRanges', [])
                if not ranges:
                    raise ValueError('X article atomic media mapping missing')
                for span in ranges:
                    entity = entities.get(str(span['key']), {})
                    if entity.get('type') != 'MEDIA':
                        raise ValueError('Unsupported X article atomic entity')
                    items = entity.get('data', {}).get('mediaItems')
                    if not items:
                        raise ValueError('X article media items missing')
                    for item in items:
                        info = media.get(str(item.get('mediaId')), {}).get('media_info', {})
                        result.append(image(info.get('original_img_url')))
                continue
            # DraftJS offsets are UTF-16 units, including for emoji.
            encoded = text.encode('utf-16-le')
            def offset(value):
                try:return len(encoded[:value*2].decode('utf-16-le'))
                except UnicodeDecodeError:raise ValueError('Invalid X UTF-16 entity boundary')
            opens, closes = {}, {}
            def span_mark(start, length, before, after):
                if not isinstance(start, int) or not isinstance(length, int) or start < 0 or length < 0 or (start+length)*2 > len(encoded):
                    raise ValueError('Invalid X text range')
                opens.setdefault(offset(start), []).append(before)
                closes.setdefault(offset(start+length), []).insert(0, after)
            for style in block.get('inlineStyleRanges', []):
                marker = {'Bold':'**', 'BOLD':'**', 'Italic':'*', 'ITALIC':'*', 'Strikethrough':'~~', 'STRIKETHROUGH':'~~', 'Code':'`', 'CODE':'`'}.get(style['style'])
                if marker:span_mark(style['offset'], style['length'], marker, marker)
            for span in block.get('entityRanges', []):
                entity = entities.get(str(span['key']), {})
                if entity.get('type') in ('LINK', 'Link'):
                    href = entity.get('data', {}).get('url')
                    if not isinstance(href, str) or urlsplit(href).scheme not in ('http', 'https'):
                        raise ValueError('Unsupported X article link')
                    span_mark(span['offset'], span['length'], '[', '](' + href.replace(')', '%29') + ')')
                else:raise ValueError('Unsupported X article text entity')
            rendered = ''.join(''.join(closes.get(i, []))+''.join(opens.get(i, []))+(text[i] if i < len(text) else '') for i in range(len(text)+1))
            if kind == 'unstyled':result.append(rendered)
            elif kind in ('header-one','header-two','header-three'):result.append('#'*{'header-one':1,'header-two':2,'header-three':3}[kind]+' '+rendered)
            elif kind in ('unordered-list-item','ordered-list-item'):result.append('  '*min(int(block.get('depth',0)),10)+('- ' if kind=='unordered-list-item' else '1. ')+rendered)
            elif kind == 'blockquote':result.append('> '+rendered.replace('\n','\n> '))
            elif kind == 'code-block':
                fence='`'*max(3,max((len(m[0])+1 for m in re.finditer(r'`+',text)),default=3))
                result.append(fence+'\n'+text+'\n'+fence)
            else:raise ValueError('Unsupported X article block type: '+str(kind))
        return '\n\n'.join(result)

    seen = set()
    def post_body(post, quoted=False):
        if post.get('type') != 'status' or not post.get('id'):
            raise ValueError('Quoted X post unavailable')
        screen=post.get('author',{}).get('screen_name','')
        if not re.fullmatch(r'[A-Za-z0-9_]+',screen) or not re.fullmatch(r'\d+',str(post['id'])):
            raise ValueError('X post identity unavailable')
        canonical=f"https://x.com/{screen}/status/{post['id']}"
        if str(post['id']) in seen:
            return '[已保存来源](' + canonical + ')'
        seen.add(str(post['id']))
        evidence.append(dict(id=str(post['id']), url=canonical, author_id=post.get('author',{}).get('id'), replying_to=post.get('replying_to'), quoted=quoted))
        article = post.get('article')
        body = article_body(article) if article else (post.get('raw_text') or {}).get('text', post.get('text'))
        if not isinstance(body,str) or not body.strip() and not (post.get('media') or {}).get('videos'):raise ValueError('X full text missing')
        result = [body, '\n来源：'+canonical]
        for photo in (post.get('media') or {}).get('photos', []):result.append(image(photo['url']))
        for index,video in enumerate((post.get('media') or {}).get('videos',[])):
            media_id=video.get('id')
            if not isinstance(media_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',media_id):raise ValueError('X video media identity missing')
            asset_id=str(post['id'])+'-video-'+media_id
            asset={'kind':'video','source_id':str(post['id']),'source_url':canonical,'asset_id':asset_id,'path':'videos/'+asset_id+'.mp4'}
            formats=[f for f in video.get('formats',[]) if f.get('container')=='mp4' and f.get('url') and min(f.get('width',0),f.get('height',0))<=1080]
            formats.sort(key=lambda f:(f.get('width',0)*f.get('height',0),f.get('bitrate',0)),reverse=True)
            options=[{'url':f['url'],'duration_seconds':video.get('duration')} for f in formats]
            if not options and video.get('format')=='video/mp4' and video.get('url'):options=[{'url':video['url'],'duration_seconds':video.get('duration')}]
            acquire_video(asset,directory,options,'x',fetcher=download_media)
            assets.append(asset)
            if asset['status']!='downloaded':missing.append(asset)
            result.append('[视频转写待处理](wiki-media:'+asset_id+')')
        if post.get('quote') is not None:result.extend(['## 引用帖', post_body(post['quote'], True)])
        return '\n\n'.join(result)

    body = '\n\n'.join(post_body(post) for post in thread)
    (directory/'article.md').write_text(body+'\n')
    context = dict(provider='FxEmbed v2 thread', posts=evidence, gaps=[],
                   scope='Provider-observed continuous author chain; hidden/deleted posts are not proven absent')
    atomic_json(directory/'manifest.json', dict(source_url=url, assets=assets, context=context, article_blocks=block_count))
    return dict(directory=str(directory.resolve()), status='partial' if missing else 'complete', contextStatus='complete',
                missingAssets=missing, articleBlocks=block_count, provider='FxEmbed v2 thread')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.url, args.output), ensure_ascii=False))
