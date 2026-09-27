#!/usr/bin/env python3
"""Read local nashsu health, compilation queue, and archive integrity.

Never prints the API token or sends content outside the local application.
"""
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    config = Path.home() / 'Library/Application Support/com.llmwiki.app/app-state.json'
    state = json.loads(config.read_text())
    project = state['lastProject']
    vault = Path(project['path'])
    request = urllib.request.Request('http://127.0.0.1:19828/health')
    health = json.loads(urllib.request.urlopen(request, timeout=10).read())
    queue_file = vault / '.llm-wiki/ingest-queue.json'
    queue = json.loads(queue_file.read_text()) if queue_file.exists() else []
    failures = []
    verified = 0
    directory = vault / '.personal-wiki'
    index_file = directory / 'captures.json'
    index = json.loads(index_file.read_text()) if index_file.exists() else {}
    if not index_file.exists():
        failures.append(str(index_file))
    for capture in index.values():
        manifest = directory / (capture['id'] + '.json')
        if not manifest.is_file():
            failures.append(str(manifest))
        if not Path(capture['source']).is_file():
            failures.append(capture['source'])
    for manifest in directory.glob('*.json'):
        if manifest.name == 'captures.json':
            continue
        capture = json.loads(manifest.read_text())
        for relative, expected in capture.get('hashes', {}).items():
            path = Path(capture['archive']) / relative
            if not path.is_file():
                failures.append(str(path))
                continue
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != expected:
                failures.append(str(path))
            else:
                verified += 1
    print(json.dumps({'health': health, 'vault': str(vault), 'queue': queue,
                     'source_pages': [str(p.relative_to(vault)) for p in (vault/'wiki/sources').glob('*.md')],
                     'verified_raw_files': verified, 'integrity_failures': failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
