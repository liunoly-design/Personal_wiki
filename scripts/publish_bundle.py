#!/usr/bin/env python3
"""Publish staged results without replacing any existing user content."""
import json, os, re, sys, posixpath
from pathlib import Path
from protected_store import Root, encode, sha, verify, rewrite_attachments


def rewrite_links(body, path, mapping):
    def target(value):
        bare, separator, fragment = value.partition('#')
        normalized = posixpath.normpath(posixpath.join(posixpath.dirname(path), bare))
        return posixpath.relpath(mapping[normalized], posixpath.dirname(path)) + (separator + fragment if separator else '') if normalized in mapping else value
    body = re.sub(r'(\]\(<?)([^\s)>]+)', lambda m: m[1] + target(m[2]), body)
    body = re.sub(r'(?m)^(\s*\[[^\]]+\]:\s*<?)([^\s>]+)', lambda m: m[1] + target(m[2]), body)
    return body


def publish(request):
    target = Root(request['vault'])
    staging = Root(request['staging'])
    lock = target.lock()
    try:
        sid = request['sourceId']
        if not re.fullmatch('[a-f0-9]{20}', sid):
            raise ValueError('Invalid source ID')
        record = json.loads(staging.read(f'.personal-wiki/{sid}.json'))
        verify(staging, record)
        previous = staging.optional('.personal-wiki/publication.json')
        if previous:
            plan = json.loads(previous)
        else:
            slug = record['name']
            if not re.fullmatch('[a-z][a-z0-9-]*', slug):
                raise ValueError('Invalid name')
            name = slug
            # Reserve a collision-free name once; replay uses the durable plan.
            if target.optional(f'wiki/sources/{name}.md') or target.optional(f'raw/sources/{name}.md'):
                name = slug + '-' + sid[:8]
            raw = rewrite_attachments(staging.read(f'raw/assets/{sid}/article.md').decode(), record, '../..')
            raw = raw.rstrip() + f'\n\n[原始网页]({record["url"]})\n'
            reading = staging.read(f'reading/{slug}.zh.md').decode()
            reading = re.sub(r'^---\n.*?\n---\n', '', reading, count=1, flags=re.S)
            reading = reading.replace('../raw/assets/', '../../raw/assets/')
            card = staging.read(f'wiki/sources/{slug}.md').decode()
            body = f'{card.rstrip()}\n\n## 完整中文正文\n\n{reading.strip()}\n\n[归档原文](../../raw/sources/{name}.md)\n'
            mapping = {f'wiki/sources/{slug}.md': f'wiki/sources/{name}.md', f'raw/sources/{slug}.md': f'raw/sources/{name}.md', f'raw/inputs/{slug}.md': f'raw/sources/{name}.md', f'reading/{slug}.zh.md': f'wiki/sources/{name}.md'}
            body = rewrite_links(body, f'wiki/sources/{name}.md', mapping)
            files = {f'raw/sources/{name}.md': raw, f'wiki/sources/{name}.md': body}
            reviews = []
            candidates = json.loads(staging.read(f'.personal-wiki/compilations/{sid}/generation.json'))['blocks']
            for block in candidates:
                path = block['path']
                if path == f'wiki/sources/{slug}.md':
                    continue
                if not re.fullmatch(r'wiki/(concepts|entities|topics|synthesis)/[a-z][a-z0-9-]*\.md', path):
                    raise ValueError('Unsafe candidate')
                content = rewrite_links(staging.read(f'.personal-wiki/compilations/{sid}/candidates/{path}').decode(), path, mapping)
                old = target.optional(path)
                if (old is not None and old != content.encode()) or path.startswith('wiki/synthesis/'):
                    rid = sha((sid + path).encode())[:16]
                    review = f'wiki/queries/review-{rid}.md'
                    files[review] = f'# 待审修改\n\n目标：[现有页面](../../{path})\n\n已有内容未被覆盖。请比较后决定是否采用下方内容。\n\n{content}'
                    reviews.append({'id': rid, 'path': path, 'file': review})
                else:
                    files[path] = content
            plan = dict(sourceId=sid, name=name, url=record['url'], files=files, reviews=reviews, assets=record['hashes'])
            staging.immutable('.personal-wiki/publication.json', encode(plan))
        for path, digest in plan['assets'].items():
            data = staging.read(f'raw/assets/{sid}/{path}')
            if sha(data) != digest:
                raise ValueError('Archive integrity mismatch')
            target.immutable(f'raw/assets/{sid}/{path}', data)
        for path, content in plan['files'].items():
            target.immutable(path, content.encode())
        return dict(status='complete', sourceId=sid,
                    source=str(target.path / f'wiki/sources/{plan["name"]}.md'), title=record['name'],
                    files={p: sha(v.encode()) for p, v in plan['files'].items()},
                    assets={f'raw/assets/{sid}/{p}': h for p, h in plan['assets'].items()}, reviews=plan['reviews'])
    finally:
        os.close(lock)
        os.close(target.fd)
        os.close(staging.fd)

if __name__ == '__main__':
    print(json.dumps(publish(json.load(sys.stdin)), ensure_ascii=False))
