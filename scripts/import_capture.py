#!/usr/bin/env python3
"""Import an already captured article package into nashsu; never fetch or compile.

The snapshot must contain article.md and its local attachments. Original bytes
live under raw/assets; raw/sources contains the Markdown adapter for nashsu.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temp, path)


def collect(vault, snapshot, message, refresh=False):
    if not message.startswith('小婕收集 '):
        raise ValueError('Message must start with 小婕收集 followed by a space')
    urls = re.findall(r'https?://[^\s]+', message)
    if len(urls) != 1:
        raise ValueError('This package importer accepts exactly one URL per package')
    u = urlsplit(urls[0])
    if u.hostname not in ('x.com', 'twitter.com', 'mp.weixin.qq.com'):
        raise ValueError('Only X and WeChat are supported in this importer')
    if u.hostname in ('x.com', 'twitter.com'):
        if not re.fullmatch(r'/[^/]+/status/\d+/?', u.path):
            raise ValueError('Expected a single X post URL')
        url = urlunsplit(('https', 'x.com', u.path.rstrip('/'), '', ''))
    else:
        url = urlunsplit(('https', u.hostname, u.path, u.query, ''))
    vault, snapshot = Path(vault).resolve(), Path(snapshot).resolve()
    state = vault / '.personal-wiki'
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'import.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index_path = state / 'captures.json'
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
        if url in index and not refresh:
            result = index[url]
            if not Path(result['source']).is_file() or not Path(result['archive']).is_dir():
                raise ValueError('Existing archive is incomplete; restore it before importing')
            if any(not (Path(result['archive']) / p).is_file() or
                   digest(Path(result['archive']) / p) != expected
                   for p, expected in result['hashes'].items()):
                raise ValueError('Existing archive integrity mismatch; restore it before importing')
            return {**result, 'status': 'existing'}
        if not (snapshot / 'article.md').is_file():
            raise ValueError('Missing article.md')
        if snapshot == vault or vault in snapshot.parents or snapshot in vault.parents:
            raise ValueError('Snapshot and Vault must be separate directories')
        files = sorted(p for p in snapshot.rglob('*') if p.is_file())
        if any(p.is_symlink() for p in snapshot.rglob('*')):
            raise ValueError('Snapshot symlinks are not allowed')
        hashes = {str(p.relative_to(snapshot)): digest(p) for p in files}
        identity = hashlib.sha256((url + json.dumps(hashes, sort_keys=True)).encode()).hexdigest()[:20]
        archive = vault / 'raw/assets' / identity
        source = vault / 'raw/sources' / (identity + '.md')
        archive.parent.mkdir(parents=True, exist_ok=True)
        source.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            stage = Path(tempfile.mkdtemp(prefix='capture-', dir=state))
            try:
                for relative, expected in hashes.items():
                    dest = stage / relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(snapshot / relative, dest)
                    if digest(dest) != expected:
                        raise ValueError('Snapshot changed while being copied')
                os.rename(stage, archive)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        if any(not (archive / p).is_file() or digest(archive / p) != h for p, h in hashes.items()):
            raise ValueError('Archive integrity mismatch; refusing to overwrite')
        content = (archive / 'article.md').read_text()
        for relative in sorted(hashes, key=len, reverse=True):
            if relative != 'article.md':
                content = content.replace('](' + relative + ')', '](' + '../assets/' + identity + '/' + relative + ')')
        content += '\n\n## 归档出处\n\n原始 URL：' + url + '\n\n[原始提取文件](../assets/' + identity + '/article.md)\n'
        if not source.exists():
            temporary = state / (identity + '.md.tmp')
            temporary.write_text(content)
            os.rename(temporary, source)
        elif source.read_text() != content:
            raise ValueError('Existing source differs; refusing to overwrite')
        result = {'id': identity, 'url': url, 'archive': str(archive), 'source': str(source),
                  'status': 'archived', 'imported_at': datetime.now(timezone.utc).isoformat(),
                  'hashes': hashes, 'compilation': 'not_verified'}
        atomic_json(state / (identity + '.json'), result)
        index[url] = result
        atomic_json(index_path, index)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--message', required=True)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    print(json.dumps(collect(args.vault, args.snapshot, args.message, args.refresh), ensure_ascii=False))
