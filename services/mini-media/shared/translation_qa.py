"""Check untranslated prose while retaining source technical identifiers."""
import re

NAMES = {'SysStats', 'MISC', 'GRILL with DOCS', 'GRILLME', 'ADR', 'ADRs',
         'YouTube', 'JIRA', 'Linear', 'Markdown', 'Beads', 'GitLab', 'AFK',
         'Matt', 'mappococ', 'pococ', 'sandcastle'}

def stray_words(source, translation, allowed):
    # Protect whole literals only when present in the source. In particular,
    # "with" outside a skill name remains ordinary prose requiring translation.
    literals = set(NAMES)
    literals.update(x.rstrip('.') for x in re.findall(r'\b[\w.-]+\.[A-Za-z]{2,}(?:/[\w./-]+)*', source))
    literals.update(re.findall(r'\b[A-Z][a-z]+(?:[A-Z][A-Za-z]*)+\b', source))
    remaining = translation
    for literal in sorted(literals, key=len, reverse=True):
        pattern = r'(?<![A-Za-z0-9_])' + re.escape(literal) + r'(?![A-Za-z0-9_])'
        if re.search(pattern, source, re.I):
            remaining = re.sub(pattern, '', remaining, flags=re.I)
    permitted = {w.casefold() for w in allowed}
    return [w for w in re.findall(r'[A-Za-z]{3,}', remaining)
            if w.casefold() not in permitted]

def duplicate_groups(groups):
    seen = {}
    flagged = set()
    for g in groups:
        text = re.sub(r'\s+', '', g['text'])
        if len(text) > 100 and text in seen:
            other = seen[text]
            if other['source_text'] != g['source_text']:
                flagged.update((other['id'], g['id']))
        seen[text] = g
    return flagged
