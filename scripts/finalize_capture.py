#!/usr/bin/env python3
"""Repair known raw-asset links in newly generated source cards after first import.

Run only for initial generated cards, before manual editing. Backups are retained.
This is an installation-test adapter, not an automatic editor of existing notes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def finalize(vault, source_ids):
    vault = Path(vault).resolve()
    repaired = []
    for page in (vault / 'wiki/sources').glob('*.md'):
        if page.stem not in source_ids:
            continue
        old = page.read_text()

        def replace(match):
            relative = match.group(1)
            target = (vault / 'raw/assets' / relative).resolve()
            if not target.is_relative_to(vault / 'raw/assets') or not target.is_file():
                return match.group(0)
            return '](' + os.path.relpath(target, page.parent) + ')'

        new = re.sub(r'\]\(\.\./assets/([^\s)]+)\)', replace, old)
        if old == new:
            continue
        history = vault / '.personal-wiki/generated-history' / hashlib.sha256(old.encode()).hexdigest()
        history.mkdir(parents=True, exist_ok=True)
        backup = history / page.name
        if not backup.exists():
            backup.write_text(old)
        temp = history / (page.name + '.tmp')
        temp.write_text(new)
        os.replace(temp, page)
        repaired.append(str(page.relative_to(vault)))
    return {'repaired_source_cards': repaired}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', required=True)
    parser.add_argument('--source-id', required=True, action='append', help='Explicit newly generated source card ID; repeat for multiple cards')
    args = parser.parse_args()
    print(json.dumps(finalize(args.vault, args.source_id), ensure_ascii=False))
