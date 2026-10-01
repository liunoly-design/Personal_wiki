#!/usr/bin/env python3
"""Journaled migration of legacy display copies; archive bytes never change."""
import json, os, posixpath, re, sys
from pathlib import Path
from protected_store import Root, encode, sha, rewrite_attachments, verify


def plan(vault, destination):
    root, backup = Root(vault), Root(destination)
    lock = root.lock()
    try:
        old_plan = backup.optional('plan.json')
        if old_plan:
            return json.loads(old_plan)
        index = json.loads(root.optional('.personal-wiki/captures.json') or '{}')
        changes, mapping, deletes, sources = {}, {}, {}, {}
        records = {r['id']: r for r in index.values()}
        for sid, record in records.items():
            verify(root, record)
            slug = record['name']
            rawpath, page = f'raw/sources/{slug}.md', f'wiki/sources/{slug}.md'
            if not root.optional(page):
                continue
            original = root.read(f'raw/assets/{sid}/article.md').decode()
            if root.optional(rawpath) is None:
                changes[rawpath] = rewrite_attachments(original, record, '../..').rstrip() + f'\n\n[原始网页]({record["url"]})\n'
            for old in [f'raw/inputs/{slug}.md', f'raw/sources/collected/{slug}.md']:
                if root.optional(old) is not None:
                    mapping[old] = rawpath
                    deletes[old] = sha(root.read(old))
            reading_path = f'reading/{slug}.zh.md'
            translated = root.optional(reading_path)
            if translated is not None:
                mapping[reading_path] = page
                deletes[reading_path] = sha(translated)
                body = re.sub(r'^---\n.*?\n---\n', '', translated.decode(), count=1, flags=re.S)
                body = body.replace('../raw/assets/', '../../raw/assets/')
            else:
                # Previously completed legacy articles are not retranslated.
                body = rewrite_attachments(original, record, '../..')
            current = root.read(page).decode()
            marker = f'<!-- personal-wiki:fulltext:{sid} -->'
            if marker not in current:
                heading = '完整中文正文' if translated is not None else '归档全文'
                changes[page] = current.rstrip() + f'\n\n{marker}\n\n## {heading}\n\n{body.strip()}\n\n[归档原文](../../{rawpath})\n'
            sources[record['url']] = dict(status='published_unverified', sourceId=sid, source=str(root.path / page), relativeSource=page,
                files=[page, rawpath], assets={f'raw/assets/{sid}/{p}': h for p, h in record['hashes'].items()}, reviews=[])
        for p in sorted((root.path / 'glossary').glob('*.md')):
            old = str(p.relative_to(root.path))
            slug = p.stem
            if not re.fullmatch('[a-z][a-z0-9-]*', slug):
                raise ValueError('Unrecognized glossary filename')
            target = next((f'wiki/{kind}/{slug}.md' for kind in ['concepts', 'entities'] if root.optional(f'wiki/{kind}/{slug}.md') is not None), f'wiki/concepts/{slug}.md')
            original = root.read(old).decode()
            existing = changes.get(target, (root.optional(target) or b'').decode())
            if not existing:
                changes[target] = original
            elif original.strip() not in existing:
                changes[target] = existing.rstrip() + '\n\n## 原独立名词页的基础说明\n\n' + original.strip() + '\n'
            mapping[old] = target
            deletes[old] = sha(root.read(old))
        # Pending proposals become durable, visible nashsu pages before caches go.
        for p in sorted((root.path / '.personal-wiki/reviews').glob('*.json')):
            proposal = json.loads(root.read(str(p.relative_to(root.path))))
            if proposal.get('status') != 'pending':
                continue
            rid = proposal['id']
            if not re.fullmatch('[a-f0-9]+', rid):
                raise ValueError('Invalid review ID')
            reviewpath = f'wiki/queries/review-{rid}.md'
            if root.optional(reviewpath) is None:
                changes[reviewpath] = '# 待审修改\n\n目标：' + proposal['path'] + '\n\n已有页面未覆盖，以下为待审候选。\n\n' + proposal['candidate']
        def rewrite(content, path):
            def link(match):
                target = match[1]
                normalized = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                if normalized in mapping:
                    return '](' + posixpath.relpath(mapping[normalized], posixpath.dirname(path))
                return match[0]
            return re.sub(r'\]\(([^\s)#]+)', link, content)
        for p in (root.path / 'wiki').rglob('*.md'):
            relative = str(p.relative_to(root.path))
            content = changes.get(relative, root.read(relative).decode())
            fixed = rewrite(content, relative)
            if fixed != content:
                changes[relative] = fixed
        for p in list(changes):
            changes[p] = rewrite(changes[p], p)
        before = {}
        for path in set(changes) | set(deletes):
            old = root.optional(path)
            before[path] = sha(old) if old is not None else None
            if old is not None:
                backup.immutable('before/' + path, old)
        # Preserve runtime metadata outside the library for recovery and audit.
        for p in (root.path / '.personal-wiki').rglob('*'):
            if p.is_file() and p.name != 'protected.lock':
                rel = str(p.relative_to(root.path))
                backup.immutable('before/' + rel, root.read(rel))
        result = dict(vault=str(root.path), changes=changes, before=before, deletes=deletes, sources=sources,
                      hashes={p: sha(v.encode()) for p, v in changes.items()})
        for source in sources.values():
            source['files'] = {p: result['hashes'].get(p) or sha(root.read(p)) for p in source['files']}
        backup.immutable('plan.json', encode(result))
        return result
    finally:
        os.close(lock)
        os.close(root.fd)
        os.close(backup.fd)


def apply(vault, destination, cleanup=False):
    root, journal = Root(vault), Root(destination)
    lock = root.lock()
    try:
        p = json.loads(journal.read('plan.json'))
        if p['vault'] != str(root.path):
            raise ValueError('Migration Vault mismatch')
        if cleanup:
            if json.loads(journal.read('verified.json')).get('planHash') != sha(journal.read('plan.json')):
                raise ValueError('API verification required before cleanup')
            for path, digest in p['hashes'].items():
                if sha(root.read(path)) != digest:
                    raise ValueError('Published file changed; retain old copies')
            complete_ids = set(json.loads(journal.optional('completed-source-ids.json') or '[]'))
            protected_copies = set()
            for source in p['sources'].values():
                if source['sourceId'] not in complete_ids:
                    slug = Path(source['source']).stem
                    protected_copies.update([f'reading/{slug}.zh.md', f'raw/inputs/{slug}.md', f'raw/sources/collected/{slug}.md'])
            cleaned = 0
            for path, digest in p['deletes'].items():
                if path in protected_copies:
                    continue
                current = root.optional(path)
                if current is None:
                    continue
                if sha(current) != digest:
                    raise ValueError('Old file changed; retain it')
                fd, name = root.parent(path)
                try:
                    backup_fd, backup_name = journal.parent('removed/' + path, create=True)
                    try:
                        if journal.optional('removed/' + path) is not None:
                            raise ValueError('Cleanup recovery exists; inspect before retry')
                        os.rename(name, backup_name, src_dir_fd=fd, dst_dir_fd=backup_fd)
                        os.fsync(fd); os.fsync(backup_fd)
                        if sha(journal.read('removed/' + path)) != digest:
                            try:
                                os.link(backup_name, name, src_dir_fd=backup_fd, dst_dir_fd=fd, follow_symlinks=False)
                            except FileExistsError:
                                pass
                            raise ValueError('Concurrent edit retained during cleanup')
                    finally:
                        os.close(backup_fd)
                finally:
                    os.close(fd)
                cleaned += 1
            for directory in ['reading', 'raw/inputs', 'raw/sources/collected', 'glossary']:
                try:
                    (root.path / directory).rmdir()
                except (FileNotFoundError, OSError):
                    pass
            return {'cleaned': cleaned, 'retained': len(set(p['deletes']) & protected_copies)}
        # Check all existing files before any replacements.
        for path, content in p['changes'].items():
            current = root.optional(path)
            if current == content.encode():
                continue
            displaced = journal.optional('displaced/' + path)
            actual = current if current is not None else displaced
            if (sha(actual) if actual is not None else None) != p['before'][path]:
                raise ValueError('Concurrent edit; migration stopped: ' + path)
        for path, content in p['changes'].items():
            current = root.optional(path)
            if current == content.encode():
                continue
            if current is None:
                displaced = journal.optional('displaced/' + path)
                if displaced is not None and sha(displaced) != p['before'][path]:
                    raise ValueError('Displaced page changed; retain for recovery')
                root.immutable(path, content.encode())
            else:
                displaced = 'displaced/' + path
                srcfd, srcname = root.parent(path)
                dstfd, dstname = journal.parent(displaced, create=True)
                try:
                    if journal.optional(displaced) is None:
                        os.rename(srcname, dstname, src_dir_fd=srcfd, dst_dir_fd=dstfd)
                        os.fsync(srcfd); os.fsync(dstfd)
                    actual = journal.read(displaced)
                    if sha(actual) != p['before'][path]:
                        try:
                            os.link(dstname, srcname, src_dir_fd=dstfd, dst_dir_fd=srcfd, follow_symlinks=False)
                        except FileExistsError:
                            pass
                        raise ValueError('Concurrent edit retained in migration recovery: ' + path)
                    root.immutable(path, content.encode())
                finally:
                    os.close(srcfd); os.close(dstfd)
        return {'published': len(p['changes'])}
    finally:
        os.close(lock); os.close(root.fd); os.close(journal.fd)

if __name__ == '__main__':
    request = json.load(sys.stdin)
    if request['operation'] == 'plan':
        result = plan(request['vault'], request['destination'])
        print(json.dumps({'changes': len(result['changes']), 'deletes': len(result['deletes']), 'sources': len(result['sources'])}))
    else:
        print(json.dumps(apply(request['vault'], request['destination'], request['operation'] == 'cleanup')))
