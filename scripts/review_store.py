#!/usr/bin/env python3
"""Read proposals; append explicitly approved, baseline-bound updates safely."""
import json, os, re, sys
from protected_store import Root, sha, encode


def proposal(root, rid):
    if not re.fullmatch('[a-f0-9]{16}', rid):
        raise ValueError('Review not found')
    file = f'wiki/queries/review-{rid}.md'
    body = root.read(file)
    meta = root.optional(f'.personal-wiki/review-proposals/{rid}.json')
    data = json.loads(meta) if meta else None
    safe = bool(data and data.get('id') == rid and data.get('proposalHash') == sha(body)
                and re.fullmatch(r'wiki/(concepts|entities|topics|synthesis)/[a-z][a-z0-9-]*\.md', data.get('path', ''))
                and (data.get('previousHash') is None or re.fullmatch('[a-f0-9]{64}', data.get('previousHash', '')))
                and isinstance(data.get('candidate'), str) and data['candidate'].strip()
                and body.decode().endswith(data['candidate'])
                and isinstance(data.get('sourceUrl'), str) and re.fullmatch('[a-f0-9]{20}', data.get('sourceId', '')))
    return dict(id=rid, file=file, content=body.decode(), proposalHash=sha(body), metadata=data if safe else None, metadataHash=sha(meta) if meta else None,
                risk='基线校验后追加，保留旧全文；不替换手写或保留段落' if safe else '缺少可信应用基线/元数据，仅查看、跳过或稍后')


def listing(root):
    try:
        fd, name = root.parent('wiki/queries/placeholder')
    except FileNotFoundError:
        return dict(reviews=[])
    try:
        names = sorted(os.listdir(fd))
    finally:
        os.close(fd)
    return dict(reviews=[proposal(root, n[7:-3]) for n in names if re.fullmatch(r'review-[a-f0-9]{16}\.md', n)])


def apply(root, request):
    p = proposal(root, request['id'])
    if p['proposalHash'] != request['proposalHash']:
        raise ValueError('Proposal changed; view it again')
    if p['metadataHash'] != request.get('metadataHash'):
        raise ValueError('Proposal metadata changed; view it again')
    meta = p['metadata']
    if not meta:
        raise ValueError('Missing safe baseline; legacy/native proposal cannot be applied')
    rid, target = p['id'], meta['path']
    job = f'.personal-wiki/review-actions/{rid}'
    record_path = job + '/intent.json'
    previous = root.optional(record_path)
    if previous:
        intent = json.loads(previous)
        if intent['proposalHash'] != p['proposalHash'] or intent['metadataHash'] != p['metadataHash']:
            raise ValueError('Approved proposal changed')
    else:
        current = root.optional(target)
        if (sha(current) if current is not None else None) != meta['previousHash']:
            raise ValueError('Stale baseline; no content changed')
        addition = ('\n\n## 已审来源补充 ' + rid + '\n\n' + meta['candidate'].rstrip()
                    + '\n\n来源 ID：' + meta['sourceId'] + '；出处：' + meta['sourceUrl'] + '\n').encode()
        output = (current or b'') + addition
        intent = dict(id=rid, path=target, proposalHash=p['proposalHash'], metadataHash=p['metadataHash'], previousHash=meta['previousHash'],
                      outputHash=sha(output), content=output.decode(), sourceId=meta['sourceId'], sourceUrl=meta['sourceUrl'])
        if current is not None:
            root.immutable(job + '/before.md', current)
        root.immutable(record_path, encode(intent))
    displaced = job + '/displaced.md'
    moved = root.optional(displaced)
    current = root.optional(target)
    # Recovery after publishing must never append twice or clobber an editor.
    if current is not None and sha(current) == intent['outputHash']:
        if intent['previousHash'] is not None and (moved is None or sha(moved) != intent['previousHash']):
            raise ValueError('Concurrent edit retained in displaced history; manual reconciliation required')
        return dict(status='verification_pending', path=target, hash=intent['outputHash'], history=job)
    if moved is None and intent['previousHash'] is not None:
        if current is None or sha(current) != intent['previousHash']:
            raise ValueError('Stale/concurrent baseline; no content changed')
        srcfd, src = root.parent(target)
        dstfd, dst = root.parent(displaced, create=True)
        try:
            os.rename(src, dst, src_dir_fd=srcfd, dst_dir_fd=dstfd)
            os.fsync(srcfd); os.fsync(dstfd)
        finally:
            os.close(srcfd); os.close(dstfd)
        moved = root.read(displaced)
    if moved is not None and sha(moved) != intent['previousHash']:
        restore(root, displaced, target)
        raise ValueError('Concurrent edit preserved; manual reconciliation required')
    try:
        root.put(target, intent['content'].encode())
    except FileExistsError:
        raise ValueError('Concurrent edit preserved at target; review interrupted')
    return dict(status='verification_pending', path=target, hash=intent['outputHash'], history=job)


def restore(root, source, target):
    srcfd, src = root.parent(source)
    dstfd, dst = root.parent(target)
    try:
        try:
            os.link(src, dst, src_dir_fd=srcfd, dst_dir_fd=dstfd, follow_symlinks=False)
            os.fsync(dstfd)
        except FileExistsError:
            pass
    finally:
        os.close(srcfd); os.close(dstfd)


def finalize(root, request):
    rid = request['id']
    p = proposal(root, rid)
    intent = json.loads(root.read(f'.personal-wiki/review-actions/{rid}/intent.json'))
    if p['proposalHash'] != intent['proposalHash'] or p['metadataHash'] != intent['metadataHash'] or request['hash'] != intent['outputHash'] or sha(root.read(intent['path'])) != intent['outputHash']:
        raise ValueError('Application changed before verification')
    if intent['previousHash'] is not None and sha(root.read(f'.personal-wiki/review-actions/{rid}/displaced.md')) != intent['previousHash']:
        raise ValueError('Concurrent edit retained in history; manual reconciliation required')
    return dict(status='applied', path=intent['path'], hash=intent['outputHash'])


if __name__ == '__main__':
    request = json.load(sys.stdin)
    root = Root(request['vault'])
    lock = None
    try:
        operation = request['operation']
        if operation == 'list':
            result = listing(root)
        elif operation == 'detail':
            result = proposal(root, request['id'])
        elif operation == 'outcome':
            p = proposal(root, request['id'])
            raw = root.optional(f'.personal-wiki/review-actions/{p["id"]}/intent.json')
            if raw is None:
                result = dict(safeToAbandon=True)
            else:
                intent = json.loads(raw)
                content = root.optional(intent['path'])
                result = dict(safeToAbandon=(content is not None and sha(content) != intent['outputHash']) or (content is None and intent['previousHash'] is None))
        elif operation in ('apply', 'finalize'):
            lock = root.lock()
            result = apply(root, request) if operation == 'apply' else finalize(root, request)
        else:
            raise ValueError('Unsupported review operation')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        if lock is not None:
            os.close(lock)
        os.close(root.fd)
