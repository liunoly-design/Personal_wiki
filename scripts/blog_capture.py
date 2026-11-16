"""Public HTTPS article capture; DNS-validated, pinned requests, no cookies."""
import http.client
import ipaddress
import json
import socket
import ssl
import time
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from bs4 import BeautifulSoup
from markdownify import markdownify
from readability import Document
import urllib.request
from urllib.parse import quote
try:
    from .image_types import image_extension
except ImportError:
    from image_types import image_extension


def public_addresses(url):
    u = urlsplit(url)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise ValueError('Only public HTTPS URLs without credentials are supported')
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)})
    if not addresses or any((not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast) for address in addresses):
        raise ValueError('Private or non-public address rejected')
    return u, addresses


def resolve_public(url, doh_endpoint='https://dns.google/resolve'):
    try:
        return public_addresses(url)
    except ValueError:
        u = urlsplit(url)
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.port not in (None, 443):
            raise
        # Some local DNS proxies return the benchmarking range as FakeIP. This
        # exception only resolves such names; never connect to those IPs or
        # accept private/mixed answers, even when HTTPS DNS knows another IP.
        try:literal=ipaddress.ip_address(u.hostname)
        except ValueError:literal=None
        if literal is not None:raise ValueError('Non-public literal rejected')
        if u.hostname.rstrip('.').lower().endswith(('.local','.localhost','.home.arpa')) or u.hostname.lower()=='localhost':raise
        addresses = {entry[4][0] for entry in socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)}
        if not addresses or any(ipaddress.ip_address(a) not in ipaddress.ip_network('198.18.0.0/15') for a in addresses):raise
        if doh_endpoint not in ('https://dns.google/resolve','https://dns.alidns.com/resolve'):raise ValueError('Unsupported DNS provider')
        endpoints=(doh_endpoint, 'https://dns.alidns.com/resolve' if doh_endpoint=='https://dns.google/resolve' else 'https://dns.google/resolve')
        for index, endpoint in enumerate(endpoints):
            request=urllib.request.Request(endpoint+'?name='+quote(u.hostname,safe='')+'&type=A',headers={'Accept':'application/dns-json'})
            try:
                with urllib.request.urlopen(request,timeout=20) as response:answer=json.loads(response.read(65536))
                break
            except OSError:
                if index==len(endpoints)-1:raise
        addresses=[a['data'] for a in answer.get('Answer',[]) if a.get('type')==1]
        if answer.get('Status')!=0 or not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast for a in addresses):raise ValueError('Public DNS resolution unavailable')
        return u,addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=45, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def fetch_public(url, limit, dest, resolve_addresses=None, response_metadata=None, user_agent=None, redirect_check=None):
    resolve_addresses = resolve_addresses or resolve_public
    current = url
    for _ in range(6):
        if redirect_check:redirect_check(current)
        u, addresses = resolve_addresses(current)
        attempts=1 if os.environ.get('WIKI_QUEUE_MANAGED')=='1' else 5
        for attempt in range(attempts):
            connection = PinnedHTTPS(u.hostname, addresses[attempt % len(addresses)])
            try:
                connection.request('GET', (u.path or '/') + ('?' + u.query if u.query else ''), headers={'User-Agent': user_agent or 'PersonalWiki/0.7.9', 'Accept-Encoding': 'identity'})
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location: raise ValueError('Redirect missing location')
                    if response_metadata is not None:response_metadata.setdefault('redirects',[]).append({'url':current,'status':response.status,'location':location})
                    current = urljoin(current, location)
                    break
                if response.status in (408, 429, 500, 502, 503, 504): raise OSError('Temporary HTTP '+str(response.status))
                if response.status != 200: raise ValueError('HTTP '+str(response.status))
                if int(response.getheader('Content-Length') or '0') > limit: raise ValueError('Response exceeds download limit')
                data = response.read(limit + 1)
                if len(data) > limit: raise ValueError('Response exceeds download limit')
                dest.write_bytes(data)
                if response_metadata is not None:response_metadata.update(content_type=response.getheader('Content-Type') or 'application/octet-stream',url=current)
                return current
            except (OSError, http.client.HTTPException):
                if attempt == attempts-1: raise
                time.sleep(min(2 ** attempt, 8))
            finally:
                connection.close()
        else:
            raise ValueError('Fetch failed')
    raise ValueError('Too many redirects')


def capture_blog(url, output, render=False):
    directory = Path(output) / 'package'
    directory.mkdir(parents=True, exist_ok=True)
    final = fetch_public(url, 20 * 1024 * 1024, directory / 'original.html')
    html=directory/'original.html'
    if render:
        try:from .public_browser import render_public
        except ImportError:from public_browser import render_public
        final=render_public(final,directory);html=directory/'rendered.html'
    soup = BeautifulSoup(html.read_text() if render else html.read_bytes(), 'html.parser')
    body = soup.select_one('article') or soup.select_one('main') or soup.select_one('[role="main"]') or soup.select_one('#content, .post-content, .entry-content, .entryPage')
    if body is None:
        candidate = BeautifulSoup(Document(str(soup)).summary(), 'html.parser')
        paragraphs = [p.get_text(' ', strip=True) for p in soup.select('p') if len(p.get_text(strip=True)) > 80]
        extracted = candidate.get_text(' ', strip=True)
        if not paragraphs or any(p not in extracted for p in paragraphs):
            raise ValueError('Article extraction incomplete; original retained, requires review')
        body = candidate
    if len(soup.select('article')) > 1:
        raise ValueError('Multiple articles; extraction requires review')
    if body.get('data-truncated')=='true' or 'paywall' in body.get('class',[]) or body.select('[data-truncated="true"], .paywall, [data-testid="paywall"], input[type="password"], #captcha'):
        raise ValueError('Article extraction incomplete; gated or truncated content retained')
    for node in body.select('script, style, nav, footer, form, noscript, .entryFooter, .recent-articles'):
        node.decompose()
    if not body.get_text(strip=True) or re.fullmatch(r'(loading[.\s…]*|正在加载[.\s…]*|加载中[.\s…]*)',body.get_text(strip=True),re.I):
        raise ValueError('Article extraction incomplete; original retained, requires review')
    assets = []
    for index, image in enumerate(body.select('img'), 1):
        src = image.get('data-src') or image.get('src')
        if not src:
            assets.append({'url': None, 'status': 'failed', 'reason': 'Missing image URL'})
            continue
        remote = urljoin(final, src)
        extension = Path(urlsplit(remote).path).suffix.lower()
        if extension not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.avif'): extension = '.img'
        relative = f'images/image-{index:03}{extension}'
        destination = directory / relative
        destination.parent.mkdir(exist_ok=True)
        try:
            fetch_public(remote, 25 * 1024 * 1024, destination)
            if extension=='.img':
                relative=f'images/image-{index:03}'+image_extension(destination.read_bytes())
                destination=destination.rename(directory/relative)
            image['src'] = relative
            assets.append({'kind':'image','url': remote, 'path': relative, 'status': 'downloaded'})
        except (ValueError, OSError, http.client.HTTPException) as error:
            image['src'] = remote
            asset={'kind':'image','url':remote,'status':'failed','reason':str(error)}
            if destination.exists():asset['retained_path']=destination.relative_to(directory).as_posix()
            assets.append(asset)
    for anchor in body.select('a[href]'):
        anchor['href'] = urljoin(final, anchor['href'])
    title = (soup.title.get_text(' ', strip=True) if soup.title else '')
    markdown = markdownify(str(body), heading_style='ATX', bullets='-', code_language='')
    if not body.select_one('h1') and title: markdown = '# '+title+'\n\n'+markdown
    (directory / 'article.md').write_text(markdown.strip()+'\n')
    (directory / 'metadata.json').write_text(json.dumps({'url': url, 'resolved_url': final, 'title': title, 'assets': assets}, ensure_ascii=False, indent=2))
    # Description, poster and embedded player are not a full transcript.
    if body.select('video, audio, iframe[src], embed[src]'):
        assets.append({'kind':'video','status':'waiting_metadata','reason':'Embedded media transcription required'})
    (directory/'manifest.json').write_text(json.dumps({'source_url':url,'assets':assets},ensure_ascii=False,indent=2))
    missing = [a for a in assets if a['status'] != 'downloaded']
    return {'directory': str(directory.resolve()), 'status': 'partial' if missing else 'complete', 'missingAssets': missing, 'publicBlog': True}
