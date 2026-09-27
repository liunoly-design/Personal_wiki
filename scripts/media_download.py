"""Public X metadata and bounded direct video selection; no private cookies."""
import json
import subprocess
import sys


def extract_public(url):
    result = subprocess.run([sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist', '--skip-download', '--dump-single-json', '--retries', '0', '--extractor-retries', '0', '--socket-timeout', '30', '--no-warnings', url], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError('Public media metadata unavailable; login may be required')
    return json.loads(result.stdout)


def video_assets(info):
    entries = info.get('entries') or [info]
    assets = []
    for entry in entries:
        formats = [f for f in entry.get('formats', []) if f.get('vcodec') != 'none' and f.get('ext') == 'mp4' and f.get('protocol', 'https') in ('http', 'https') and f.get('height') and f.get('width') and min(f['height'], f['width']) <= 1080]
        if not formats:
            assets.append({'kind': 'video', 'status': 'waiting', 'error': 'No supported direct MP4 format at or below 1080p'})
            continue
        chosen = max(formats, key=lambda f: (min(f['height'], f['width']), f.get('tbr') or 0))
        asset = {'kind': 'video', 'url': chosen['url'], 'duration': entry.get('duration'), 'height': chosen['height'], 'width': chosen['width'], 'expected_size': chosen.get('filesize') or chosen.get('filesize_approx')}
        if asset['duration'] is None:
            asset.update(status='waiting', error='Cannot verify duration before download')
        elif asset['duration'] > 1800 or (asset['expected_size'] or 0) > 1000000000:
            asset.update(status='waiting', error='Video exceeds 30 minutes or 1 GB; confirmation required')
        else:
            asset['status'] = 'ready'
        assets.append(asset)
    return assets


def mp4_metadata(parts):
    """Read movie duration and track dimensions from bounded MP4 moov bytes."""
    import struct
    duration = None
    dimensions = []
    def boxes(data):
        offset = 0
        while offset + 8 <= len(data):
            size, kind = struct.unpack_from('>I4s', data, offset)
            if size < 8 or offset + size > len(data):
                break
            payload = data[offset + 8:offset + size]
            if kind == b'mvhd' and payload:
                nonlocal duration
                version = payload[0]
                if version == 0 and len(payload) >= 20:
                    scale, ticks = struct.unpack_from('>II', payload, 12)
                    if scale: duration = ticks / scale
                elif version == 1 and len(payload) >= 32:
                    scale = struct.unpack_from('>I', payload, 20)[0]
                    ticks = struct.unpack_from('>Q', payload, 24)[0]
                    if scale: duration = ticks / scale
            elif kind == b'tkhd' and len(payload) >= 8:
                width, height = struct.unpack_from('>II', payload, len(payload) - 8)
                if width and height: dimensions.append((width / 65536, height / 65536))
            elif kind in (b'moov', b'trak'):
                boxes(payload)
            offset += size
    for part in parts:
        start = 0
        while True:
            index = part.find(b'moov', start)
            if index < 0: break
            start = index + 4
            if index >= 4:
                size = struct.unpack_from('>I', part, index - 4)[0]
                if 8 <= size <= len(part) - index + 4:
                    boxes(part[index - 4:index - 4 + size])
    if duration is None or not dimensions:
        raise ValueError('MP4 metadata not available within probe limit')
    width, height = max(dimensions, key=lambda d: min(d))
    return duration, width, height


def direct_video_asset(url):
    """Probe only bounded byte ranges before authorizing a full video download."""
    from urllib.parse import urlsplit
    import httpx
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'video.twimg.com' or parsed.port not in (None, 443) or parsed.username:
        raise ValueError('Unsupported direct video host')
    limit = 2 * 1024 * 1024
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        head = client.head(url)
        head.raise_for_status()
        size = int(head.headers.get('content-length', 0))
        if size <= 0 or size > 1000000000:
            raise ValueError('Video size unknown or exceeds 1 GB')
        parts = []
        for start in dict.fromkeys([0, max(0, size - limit)]):
            data = bytearray()
            with client.stream('GET', url, headers={'Range': f'bytes={start}-{min(size-1,start+limit-1)}'}) as response:
                response.raise_for_status()
                if start and response.status_code != 206:
                    raise ValueError('Video host does not support bounded tail probe')
                for chunk in response.iter_bytes(65536):
                    data.extend(chunk[:limit-len(data)])
                    if len(data) >= limit: break
            parts.append(bytes(data))
            try:
                duration, width, height = mp4_metadata(parts)
                break
            except ValueError:
                continue
        else:
            raise ValueError('Video metadata unavailable before download')
    asset = dict(kind='video', url=url, duration=duration, width=width, height=height, expected_size=size, status='ready')
    if duration > 1800 or min(width, height) > 1080:
        asset.update(status='waiting', error='Video exceeds duration/resolution limit')
    return asset
