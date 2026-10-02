#!/usr/bin/env python3
"""Publish staged results without replacing any existing user content."""
import json, os, re, sys, posixpath
from pathlib import Path
from protected_store import Root, encode, sha, verify, rewrite_attachments, rewrite_prose


def rewrite_links(body, path, mapping):
    def target(value):
        bare, separator, fragment = value.partition('#')
        normalized = posixpath.normpath(posixpath.join(posixpath.dirname(path), bare))
        return posixpath.relpath(mapping[normalized], posixpath.dirname(path)) + (separator + fragment if separator else '') if normalized in mapping else value
    def prose(text):
        text = re.sub(r'(\]\(<?)([^\s)>]+)', lambda m: m[1] + target(m[2]), text)
        return re.sub(r'(?m)^(\s*\[[^\]]+\]:\s*<?)([^\s>]+)', lambda m: m[1] + target(m[2]), text)
    return rewrite_prose(body, prose)


def publish(request):
    target = Root(request['vault'])
    if request.get('operation')=='supplement':
        lock=target.lock()
        try:
            sid=request['sourceId'];asset=request['asset'];aid=asset['id']
            if not re.fullmatch('[a-f0-9]{20}',sid) or not re.fullmatch('[a-f0-9]{16}',aid):raise ValueError('Invalid supplement ID')
            source=str(Path(request['source']).relative_to(target.path))
            if not re.fullmatch(r'wiki/sources/[a-z][a-z0-9-]*\.md',source):raise ValueError('Invalid supplement source')
            relative=asset['path']
            if Path(relative).is_absolute() or '..' in Path(relative).parts:raise ValueError('Unsafe attachment')
            root=Root(request['directory'])
            try:data=root.read(relative)
            finally:os.close(root.fd)
            digest=sha(data)
            if asset.get('sha256') and asset['sha256']!=digest:raise ValueError('Attachment hash mismatch')
            path=f'raw/assets/{sid}/supplements/{aid}/'+Path(relative).name
            target.immutable(path,data)
            page=f'wiki/queries/media-{sid}-{aid}.md'
            body=f'# 附件补充记录\n\n[原来源卡](../../{source})\n\n附件 {aid}：[下载附件](../../{path})\n\n帖子来源：{asset.get("post_url") or asset.get("url")}\n\nSHA256：{digest}\n\n原文与原来源卡保持不变；此附件由独立续作取得。\n'
            target.immutable(page,body.encode())
            return dict(files={page:sha(body.encode())},assets={path:digest},supplement=page)
        finally:
            os.close(lock);os.close(target.fd)
    if 'background' in request:
        lock = target.lock()
        try:
            rid = request['requestId']
            if not re.fullmatch('[a-f0-9]{64}', rid):
                raise ValueError('Invalid request ID')
            source = str(Path(request['source']).relative_to(target.path))
            if not re.fullmatch(r'wiki/sources/[a-z][a-z0-9-]*\.md', source):
                raise ValueError('Invalid note source')
            path = f'wiki/queries/user-note-{rid}.md'
            body = f'# 个人备注与背景\n\n来源：[资料卡](../../{source})\n\n以下为用户提供的背景，不属于原作者内容或来源证据。\n\n{request["background"]}\n'
            target.immutable(path, body.encode())
            return dict(source=str(target.path / path), files={path: sha(body.encode())}, assets={})
        finally:
            os.close(lock)
            os.close(target.fd)
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
                number = 2
                while target.optional(f'wiki/sources/{slug}--{number}.md') or target.optional(f'raw/sources/{slug}--{number}.md'):
                    number += 1
                name = f'{slug}--{number}'
            raw = rewrite_attachments(staging.read(f'raw/assets/{sid}/article.md').decode(), record, '../..')
            origin = '用户粘贴文本（本机内容标识，不是网页出处）' if record['url'].startswith('https://text.personal-wiki.invalid/') else f'[原始网页]({record["url"]})'
            raw = raw.rstrip() + f'\n\n{origin}\n'
            reading = staging.read(f'reading/{slug}.zh.md').decode()
            reading = re.sub(r'^---\n.*?\n---\n', '', reading, count=1, flags=re.S)
            reading = rewrite_prose(reading, lambda text: re.sub(r'(\]\([ \t]*<?|^[ \t]{0,3}\[[^]\n]+\]:[ \t]*<?)\.\./raw/assets/', r'\1../../raw/assets/', text, flags=re.M))
            card = staging.read(f'wiki/sources/{slug}.md').decode()
            body = f'{card.rstrip()}\n\n## 完整中文正文\n\n{reading.strip()}\n\n[归档原文](../../raw/sources/{name}.md)\n'
            if request.get('missingAssets'):
                body+='\n## 附件尚未完成\n\n'+ '\n'.join(f'- {a.get("id", "未编号")}：{a.get("kind", "附件")}；{a.get("status", "failed")}；{a.get("post_url") or a.get("url", "")}' for a in request['missingAssets'])+'\n\n后续补下载记录单独保存，原文和本页不被覆盖。以任务状态及附件补充记录为准。\n'
            if request.get('contextGaps'):body+='\n## 上下文缺失\n\n'+'\n'.join('- '+v for v in request['contextGaps'])+'\n'
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
                    metadata = dict(id=rid, path=path, previousHash=sha(old) if old is not None else None, candidate=content, sourceId=sid, sourceUrl=record['url'], proposalHash=sha(files[review].encode()))
                    files[f'.personal-wiki/review-proposals/{rid}.json'] = encode(metadata).decode()
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
                    files={p: sha(v.encode()) for p, v in plan['files'].items() if not p.startswith('.personal-wiki/')},
                    metadata={p: sha(v.encode()) for p, v in plan['files'].items() if p.startswith('.personal-wiki/')},
                    assets={f'raw/assets/{sid}/{p}': h for p, h in plan['assets'].items()}, reviews=plan['reviews'])
    finally:
        os.close(lock)
        os.close(target.fd)
        os.close(staging.fd)

if __name__ == '__main__':
    print(json.dumps(publish(json.load(sys.stdin)), ensure_ascii=False))
