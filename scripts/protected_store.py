#!/usr/bin/env python3
"""Archive and commit derived candidates without replacing existing knowledge.

All Vault traversal uses directory descriptors and O_NOFOLLOW. New files become
visible via an atomic hard link; existing pages are only read, never replaced.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from datetime import datetime, timezone
from uuid import uuid4


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


class Root:
    def __init__(self, path):
        self.path = Path(path).absolute()
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def parent(self, path, create=False):
        parts = path.split('/')
        if any(p in ('', '.', '..') or '\\' in p for p in parts) or path.startswith('/'):
            raise ValueError('Unsafe relative path')
        fd = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, dir_fd=fd)
                    except FileExistsError:
                        pass
                new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = new
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise

    def read(self, path):
        fd, name = self.parent(path)
        try:
            stream = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(stream, 'rb') as f:
                if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                    raise ValueError('Expected regular file')
                return f.read()
        finally:
            os.close(fd)

    def optional(self, path):
        try:
            return self.read(path)
        except FileNotFoundError:
            return None

    def put(self, path, data, replace=False):
        fd, name = self.parent(path, create=True)
        temp = '.pending-' + uuid4().hex
        try:
            stream = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(stream, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if replace:
                if not path.startswith('.personal-wiki/'):
                    raise ValueError('Only runtime state may be replaced')
                os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            else:
                os.link(temp, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)

    def immutable(self, path, data):
        try:
            self.put(path, data)
        except FileExistsError:
            if self.read(path) != data:
                raise ValueError('Existing immutable file differs: ' + path)

    def lock(self):
        fd, name = self.parent('.personal-wiki/protected.lock', create=True)
        try:
            lock = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        finally:
            os.close(fd)
        fcntl.flock(lock, fcntl.LOCK_EX)
        return lock


def verify(root, record):
    for path, expected in record['hashes'].items():
        if sha(root.read(f"raw/assets/{record['id']}/{path}")) != expected:
            raise ValueError('Archive integrity mismatch')


def archive(root, request):
    url = request['url']
    index = json.loads(root.optional('.personal-wiki/captures.json') or '{}')
    if url in index and not request.get('refresh'):
        record = index[url]
        verify(root, record)
        return {**record, 'status': 'existing'}
    snapshot = Root(request['snapshot'])
    if snapshot.path == root.path or root.path in snapshot.path.parents or snapshot.path in root.path.parents:
        os.close(snapshot.fd)
        raise ValueError('Snapshot and Vault must be separate directories')
    files = {}
    try:
        for directory, dirs, names in os.walk(snapshot.path, followlinks=False):
            if any((Path(directory) / p).is_symlink() for p in dirs + names):
                raise ValueError('Snapshot symlinks are not allowed')
            for name in names:
                relative = str((Path(directory) / name).relative_to(snapshot.path))
                files[relative] = snapshot.read(relative)
    finally:
        os.close(snapshot.fd)
    if 'article.md' not in files:
        raise ValueError('Missing article.md')
    hashes = {p: sha(data) for p, data in sorted(files.items())}
    identity = sha((url + json.dumps(hashes, sort_keys=True)).encode())[:20]
    manifest = f'.personal-wiki/{identity}.json'
    old = root.optional(manifest)
    if old:
        record = json.loads(old)
        verify(root, record)
        index[url] = record
        root.put('.personal-wiki/captures.json', encode(index), replace=True)
        return {**record, 'status': 'existing'}
    intent_path = f'.personal-wiki/imports/{identity}.json'
    intent = root.optional(intent_path)
    if intent:
        record = json.loads(intent)
        source = str(Path(record['source']).relative_to(root.path))
    else:
        slug = request['slug']
        if len(slug) > 100 or not re.fullmatch('[a-z][a-z0-9]*(?:-[a-z0-9]+)*', slug):
            raise ValueError('Invalid English slug')
        name = slug
        number = 2
        while root.optional(f'raw/inputs/{name}.md') is not None or root.optional(f'wiki/sources/{name}.md') is not None:
            name = f'{slug}--{number}'
            number += 1
        source = f'raw/inputs/{name}.md'
        record = dict(id=identity, name=name, url=url, archive=str(root.path / 'raw/assets' / identity),
                      source=str(root.path / source), hashes=hashes, imported_at=datetime.now(timezone.utc).isoformat(),
                      status='archived', compilation='not_verified')
        root.immutable(intent_path, encode(record))
    for path, data in files.items():
        root.immutable(f'raw/assets/{identity}/{path}', data)
    # Source adapter is immutable; processing context is stored separately.
    root.immutable(source, files['article.md'])
    root.immutable(manifest, encode(record))
    index[url] = record
    root.put('.personal-wiki/captures.json', encode(index), replace=True)
    return record


def commit(root, request):
    record = json.loads(root.read(f".personal-wiki/{request['sourceId']}.json"))
    verify(root, record)
    job = f".personal-wiki/compilations/{record['id']}"
    result_path = job + '/result.json'
    previous_result = root.optional(result_path)
    if previous_result:
        return json.loads(previous_result)
    blocks = request['blocks']
    expected = f"wiki/sources/{record['name']}.md"
    paths = [b['path'] for b in blocks]
    if expected not in paths or len(set(paths)) != len(paths):
        raise ValueError('Missing source card or duplicate candidate paths')
    for b in blocks:
        if not re.fullmatch(r'wiki/(?:sources|concepts|entities|topics|synthesis)/[a-z][a-z0-9-]*\.md', b['path']):
            raise ValueError('Unsupported candidate path: ' + b['path'])
        if not b['content'].strip():
            raise ValueError('Empty candidate')
        # Validate ancestors and any existing leaf before any knowledge writes.
        root.optional(b['path'])
    root.immutable(job + '/generation.json', encode(request))
    reviews = []
    created = []
    for b in blocks:
        path = b['path']
        reference = f"../../raw/assets/{record['id']}/article.md"
        body = b['content'].rstrip() + f"\n\n## 加工来源\n\n[原始提取稿]({reference}) · {record['url']}\n\n来源 ID：{record['id']}；采集时间：{record['imported_at']}\n"
        destinations = {p: f"../../raw/assets/{record['id']}/{p}" for p in record['hashes']}
        def rewrite_link(match):
            target = match.group(2)
            angled = target.startswith('<')
            bare = target[1:-1] if angled else target
            normalized = bare.removeprefix('./')
            replacement = destinations.get(normalized)
            if replacement is None and bare.startswith('../assets/'):
                replacement = '../../raw/assets/' + bare[len('../assets/'):]
            if replacement is None:
                return match.group(0)
            return match.group(1) + ('<' + replacement + '>' if angled else replacement)
        # Replace only destinations, preserving optional titles and reference IDs.
        body = re.sub(r'(\]\([ \t]*)(<[^>\n]+>|[^\s)]+)', rewrite_link, body)
        body = re.sub(r'(^[ \t]{0,3}\[[^]\n]+\]:[ \t]*)(<[^>\n]+>|[^\s]+)', rewrite_link, body, flags=re.M)
        candidate = body.encode()
        history = job + '/candidates/' + path
        root.immutable(history, candidate)
        existing = root.optional(path)
        if existing is None and not path.startswith('wiki/synthesis/'):
            try:
                root.put(path, candidate)
                created.append(path)
                continue
            except FileExistsError:
                existing = root.read(path)
        # Restart after successful create is harmless; identical pages aren't proposals.
        if existing == candidate:
            created.append(path)
            continue
        review_id = sha((record['id'] + path).encode())[:16]
        review_path = f'.personal-wiki/reviews/{review_id}.json'
        proposal = dict(id=review_id, sourceId=record['id'], path=path, status='pending',
                        createdAt=record['imported_at'], previous=existing.decode() if existing is not None else None,
                        previousHash=sha(existing) if existing is not None else None,
                        candidate=body, sourceUrl=record['url'], reason='existing-page' if existing is not None else 'synthesis')
        if root.optional(review_path) is None:
            root.immutable(review_path, encode(proposal))
        reviews.append(dict(id=review_id, file=str(root.path / review_path)))
    source_text = next(b['content'] for b in blocks if b['path'] == expected)
    heading = re.search(r'^#\s+(.+)$', source_text, re.M)
    prose = re.sub(r'\A---\n.*?\n---\n', '', source_text, flags=re.S)
    summary = next((p.strip() for p in prose.split('\n\n') if p.strip() and not p.lstrip().startswith(('#', '|', '```', '---'))), '')[:240]
    result = dict(status='complete', title=heading.group(1) if heading else record['name'], summary=summary,
                  source=str(root.path / expected), sourceId=record['id'],
                  archive=record['archive'], reviews=reviews, created=created)
    root.immutable(result_path, encode(result))
    return result


if __name__ == '__main__':
    request = json.load(sys.stdin)
    root = Root(request['vault'])
    lock = root.lock()
    try:
        operation = request['operation']
        if operation == 'archive':
            result = archive(root, request)
        elif operation == 'commit':
            result = commit(root, request)
        else:
            raise ValueError('Unknown operation')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        os.close(lock)
        os.close(root.fd)
