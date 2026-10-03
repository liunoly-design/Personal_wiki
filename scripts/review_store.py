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
    return publish_intent(root, job, intent)


def publish_intent(root, job, intent):
    target = intent["path"]
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



def publish_quoted_reply(root, request):
    key, message, text = request.get('key', ''), request.get('message'), request.get('text')
    if not re.fullmatch('[a-f0-9]{64}', key) or not isinstance(message, dict) or not isinstance(text, str) or not text.strip() or len(text.encode()) > 100000:
        raise ValueError('Invalid quoted reply')
    message_id = message.get('message_id', '')
    if not re.fullmatch(r'om_[\w-]+', message_id):
        raise ValueError('Invalid quoted message ID')
    raw_json = f'raw/assets/{key[:20]}/feishu-message.json'
    raw_text = f'raw/sources/model-reply-{key[:16]}.md'
    path = f'wiki/topics/saved-reply-{key[:16]}.md'
    record = encode(message)
    # Explicit archival of a model response; never label it as author evidence.
    body = f'---\ntype: saved-model-reply\nverified: false\n---\n# 保存的模型回复\n\n> 这是小婕模型回复的原样保存。政策、数字和建议未经 Wiki 来源核验，不属于原作者证据。\n\n## 原回复正文\n\n{text}\n'
    body += f'\n\n## 保存来源\n\n飞书消息：{message_id}；发送时间戳：{message.get("create_time", "unknown")}\n\n[原回复正文](../../{raw_text}) · [原始消息记录](../../{raw_json})\n'
    root.immutable(raw_json, record)
    root.immutable(raw_text, text.encode())
    if request.get('discussionId'):
        if not isinstance(request.get('savedAt'), str):
            raise ValueError('Missing saved reply timestamp')
        body = '记录时间：' + request['savedAt'] + '\n\n' + body
        binding = topic_info(root, request)
        previous = root.optional(f'.personal-wiki/topic-actions/{key}/intent.json')
        cursor = json.loads(previous)['cursor'] if previous else (binding.get('cursor', 0) if binding.get('path') else request.get('legacyCursor', 0))
        result = append_topic(root, {**request, 'content': body, 'cursor': cursor})
        return {**result, 'pages': [dict(path=result['path'], hash=result['hash']), dict(path=raw_text, hash=sha(text.encode()))]}
    root.immutable(path, body.encode())
    return dict(path=path, pages=[dict(path=path, hash=sha(body.encode())), dict(path=raw_text, hash=sha(text.encode()))])


def topic_identity(request):
    scope, discussion = request.get('scope', ''), request.get('discussionId', '')
    if not re.fullmatch('[a-f0-9]{64}', scope) or not re.fullmatch('D-[a-f0-9]{16}', discussion):
        raise ValueError('Invalid topic identity')
    return f'.personal-wiki/topics/{scope}/{discussion}.json'


def topic_info(root, request):
    binding = root.optional(topic_identity(request))
    return json.loads(binding) if binding else dict(cursor=0)


def append_topic(root, request):
    binding_path = topic_identity(request)
    key, content = request.get('key', ''), request.get('content')
    if not re.fullmatch('[a-f0-9]{64}', key) or not isinstance(content, str) or not content.strip() or len(content.encode()) > 100000:
        raise ValueError('Invalid topic entry')
    cursor = request.get('cursor', 0)
    if not isinstance(cursor, int) or cursor < 0 or not isinstance(request.get('newRecord', False), bool):
        raise ValueError('Invalid topic cursor')
    binding = topic_info(root, request)
    if binding.get('pending') and binding['pending'] != key:
        raise ValueError('同议题保存尚未核验；请先重发原保存命令恢复')
    job = f'.personal-wiki/topic-actions/{key}'
    previous = root.optional(job + '/intent.json')
    if previous:
        intent = json.loads(previous)
        if intent['entry'] != content or intent['binding'] != binding_path or intent['cursor'] != cursor or intent['newRecord'] != request.get('newRecord', False):
            raise ValueError('Topic save request changed')
    else:
        if root.optional(job + '/complete.json'):
            raise ValueError('Missing topic intent')
        path = binding.get('path')
        legacy = request.get('legacyPath')
        if not path and legacy:
            if not re.fullmatch(r'wiki/topics/discussion-[a-f0-9]{16}\.md', legacy):
                raise ValueError('Invalid legacy discussion path')
            root.read(legacy)  # Never silently replace a missing historical binding.
            path = legacy
        if request.get('newRecord') or not path:
            identity = key if request.get('newRecord') else sha(binding_path.encode())
            path = f'wiki/topics/discussion-{identity[:16]}.md'
        current = root.optional(path)
        # A previously bound document disappearing must not be recreated silently.
        if path == binding.get('path') and current is None:
            raise ValueError('Bound topic document missing; reconcile before saving')
        addition = f'\n\n## 持续记录 {key[:16]}\n\n' + content
        output = (current or b'') + addition.encode()
        intent = dict(path=path, binding=binding_path, previousHash=sha(current) if current is not None else None,
                      outputHash=sha(output), content=output.decode(), entry=content, cursor=cursor,
                      newRecord=request.get('newRecord', False))
        if current is not None:
            root.immutable(job + '/before.md', current)
        root.immutable(job + '/intent.json', encode(intent))
    if root.optional(job + '/complete.json'):
        # Reconcile an acknowledged write after the caller lost its response.
        current = root.read(intent['path'])
        if not current.startswith(intent['content'].encode()):
            raise ValueError('Completed topic entry edited; manual reconciliation required')
        return dict(path=intent['path'], hash=sha(current), entryId=key[:16], history=job)
    root.put(binding_path, encode({**binding, 'pending': key}), replace=True)
    return {**publish_intent(root, job, intent), 'entryId': key[:16]}


def finalize_topic(root, request):
    key = request.get('key', '')
    if not re.fullmatch('[a-f0-9]{64}', key):
        raise ValueError('Invalid topic save key')
    job = f'.personal-wiki/topic-actions/{key}'
    intent = json.loads(root.read(job + '/intent.json'))
    if intent['binding'] != topic_identity(request) or sha(root.read(intent['path'])) != request['hash']:
        raise ValueError('Topic changed before verification')
    if intent['previousHash'] is not None and sha(root.read(job + '/displaced.md')) != intent['previousHash']:
        raise ValueError('Concurrent edit retained in history; manual reconciliation required')
    binding = topic_info(root, request)
    if binding.get('pending') not in (None, key):
        raise ValueError('Another topic save is pending')
    if not root.optional(job + '/complete.json'):
        root.immutable(job + '/complete.json', encode(dict(path=intent['path'], hash=request['hash'])))
    if binding.get('pending') == key:
        root.put(intent['binding'], encode(dict(path=intent['path'], cursor=max(binding.get('cursor', 0), intent['cursor']))), replace=True)
    return dict(path=intent['path'], hash=request['hash'])


def publish_discussion(root, request):
    key = request.get('key', '')
    if not re.fullmatch('[a-f0-9]{64}', key):
        raise ValueError('Invalid discussion publication key')
    content = request.get('content')
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 100000:
        raise ValueError('Invalid discussion content')
    if request['operation'] == 'conclusion':
        path = f'wiki/topics/discussion-{key[:16]}.md'
        root.immutable(path, content.encode())
        return dict(path=path, hash=sha(content.encode()))
    scope = request.get('scope')
    if not isinstance(scope, str) or not re.fullmatch('[a-f0-9]{64}', scope):
        raise ValueError('Invalid discussion scope')
    path = f'wiki/synthesis/synthesis-{key[:16]}.md'
    rid = key[:16]
    metadata_path = f'.personal-wiki/review-proposals/{rid}.json'
    previous = root.optional(metadata_path)
    if previous:
        data = json.loads(previous)
        if data['candidate'] != content or data.get('ownerScope') != scope:
            raise ValueError('Existing synthesis differs')
    else:
        current = root.optional(path)
        body = f'# 综合草稿 {rid}（待审，尚未发布）\n\n目标：{path}\n\n' + content
        data = dict(id=rid, path=path, candidate=content, sourceId=key[:20],
                    sourceUrl='讨论依据见文章引用清单', ownerScope=scope,
                    previousHash=sha(current) if current is not None else None,
                    proposalHash=sha(body.encode()))
        # Persist intent before visible proposal; same request repairs interrupted publication.
        root.immutable(metadata_path, encode(data))
    body = f'# 综合草稿 {rid}（待审，尚未发布）\n\n目标：{path}\n\n' + content
    root.immutable(f'wiki/queries/review-{rid}.md', body.encode())
    return dict(id=rid, path=path)


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
        elif operation in ('topic-info', 'topic-append', 'topic-finalize'):
            lock = root.lock()
            result = {'topic-info': topic_info, 'topic-append': append_topic, 'topic-finalize': finalize_topic}[operation](root, request)
        elif operation == 'quoted-reply':
            lock = root.lock()
            result = publish_quoted_reply(root, request)
        elif operation in ('conclusion', 'synthesis'):
            lock = root.lock()
            result = publish_discussion(root, request)
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
