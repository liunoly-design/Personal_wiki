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
