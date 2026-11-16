"""Bounded, pinned public media acquisition. No cookies, arbitrary hosts or playlists."""
import hashlib,http.client,os,time
from pathlib import Path
from urllib.parse import urljoin,urlsplit
try:from .blog_capture import resolve_public,PinnedHTTPS
except ImportError:from blog_capture import resolve_public,PinnedHTTPS

def check(url,platform):
 u=urlsplit(url)
 allowed=u.hostname=='video.twimg.com' if platform=='x' else u.hostname=='xhscdn.com' or (u.hostname or '').endswith('.xhscdn.com')
 if u.scheme!='https' or not allowed or u.username or u.password or u.port not in (None,443):raise ValueError('Unsupported public video origin')
 return u

def download_media(url,destination,*,platform,expected_bytes=None):
 if url.startswith('http://'):url='https://'+url[7:]
 destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True);part=destination.with_suffix('.download-part');current=url;deadline=time.monotonic()+300
 if expected_bytes and expected_bytes>1_000_000_000:raise ValueError('Video exceeds 1GB; confirmation required')
 for _ in range(6):
  check(current,platform);u,addresses=resolve_public(current,doh_endpoint='https://dns.alidns.com/resolve' if platform=='xiaohongshu' else 'https://dns.google/resolve')
  connection=PinnedHTTPS(u.hostname,addresses[0])
  try:
   connection.request('GET',(u.path or '/')+('?' +u.query if u.query else ''),headers={'User-Agent':'Mozilla/5.0 PersonalWiki/0.8.0','Accept-Encoding':'identity'})
   response=connection.getresponse()
   if response.status in (301,302,303,307,308):
    location=response.getheader('Location')
    if not location:raise ValueError('Media redirect missing location')
    current=urljoin(current,location);continue
   if response.status!=200:raise ValueError('Public video HTTP '+str(response.status))
   length=int(response.getheader('Content-Length') or 0)
   if length>1_000_000_000:raise ValueError('Video exceeds 1GB; confirmation required')
   sha=hashlib.sha256();size=0
   with part.open('wb') as f:
    os.chmod(part,0o600)
    while True:
     if time.monotonic()>deadline:raise ValueError('Public media download timed out')
     b=response.read(1024*1024)
     if not b:break
     size+=len(b)
     if size>1_000_000_000:raise ValueError('Video exceeds 1GB; confirmation required')
     f.write(b);sha.update(b)
    f.flush();os.fsync(f.fileno())
   if not size or length and size!=length or expected_bytes and size!=expected_bytes:raise ValueError('Media size mismatch; original response retained')
   if destination.exists():
    if destination.is_symlink() or hashlib.sha256(destination.read_bytes()).hexdigest()!=sha.hexdigest():raise ValueError('Existing acquired media differs')
    part.unlink()
   else:os.link(part,destination);part.unlink()
   return {'sha256':sha.hexdigest(),'bytes':size,'url':current}
  finally:connection.close()
 raise ValueError('Too many media redirects')

def candidates_xhs(video):
 media=video.get('media') or {}
 if not media:
  try:media=json.loads(video.get('mediaV2','{}'))
  except (ValueError,TypeError):media={}
 streams=media.get('stream') or {};options=[]
 for group in streams.values():
  if not isinstance(group,list):continue
  for item in group:
   if not isinstance(item,dict):continue
   url=item.get('masterUrl') or item.get('master_url')
   if not url:continue
   w,h=item.get('width',0),item.get('height',0)
   if min(w,h)>1080:continue
   duration=item.get('videoDuration') or item.get('video_duration') or item.get('duration')
   options.append({'url':url,'width':w,'height':h,'duration_seconds':duration/1000 if duration else None,'bytes':item.get('size'),'backups':item.get('backupUrls') or item.get('backup_urls') or []})
 return sorted(options,key=lambda x:(x['width']*x['height'],-(x['bytes'] or 0)),reverse=True)

import json

def acquire_video(asset,directory,options,platform,fetcher=None):
 fetcher=fetcher or download_media
 asset.update(status='failed')
 last='No usable progressive MP4 candidate'
 for option in options:
  if option.get('duration_seconds',0) and option['duration_seconds']>1800:
   asset.update(status='waiting_confirmation',error='Video exceeds 30 minutes; confirmation required');return asset
  for remote in [option['url'],*option.get('backups',[])]:
   try:
    result=fetcher(remote,Path(directory)/asset['path'],platform=platform,expected_bytes=option.get('bytes'))
    asset.update(result,status='downloaded',duration_seconds=option.get('duration_seconds'));return asset
   except (ValueError,OSError,http.client.HTTPException) as error:
    last=str(error) if 'confirmation required' in str(error) else type(error).__name__
 if 'confirmation required' in last:asset.update(status='waiting_confirmation')
 asset['error']=last;return asset
