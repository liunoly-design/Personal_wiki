"""Strict one-ASR-segment to one-Chinese-segment delivery contract."""
import re

def validate_segments(raw, translation):
    source = raw['segments']
    target = translation['segments']
    if len(source) != len(target):
        raise ValueError('Translation count must equal ASR count')
    for original, chinese in zip(source, target):
        if (chinese['id'] != original['id'] or chinese['source_segment_ids'] != [original['id']]
                or chinese['start'] != original['start'] or chinese['end'] != original['end']
                or chinese['source_text'] != original['text']):
            raise ValueError('Translation identity, source or timestamp mismatch')
        if not isinstance(chinese.get('text'), str) or not chinese['text'].strip():
            raise ValueError('Empty Chinese segment')
        if re.search(r'[A-Za-z0-9]', original['text']) and not re.search('[\u4e00-\u9fff]', chinese['text']):
            raise ValueError('Chinese delivery contains untranslated segment')
    return {'source_segments': len(source), 'translated_segments': len(target),
            'translated_groups': len(target), 'all_source_segments_present': True,
            'one_to_one': True, 'timestamp_matches': len(source), 'nonempty_segments': len(target)}

def stamp(value):
    ms = round(value * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'

def validate_markdown(text, raw):
    headings = list(re.finditer(r'^## (.+)$', text, re.M))
    sections = {}
    for i, heading in enumerate(headings):
        name = heading[1]
        for prefix in ('完整中文译文', '完整原始转写'):
            if name.startswith(prefix):
                if prefix in sections:
                    raise ValueError('Duplicate delivery section')
                sections[prefix] = text[heading.end():headings[i+1].start() if i+1<len(headings) else len(text)]
    if len(sections) != 2:
        raise ValueError('Delivery sections missing')
    rows = {key: re.findall(r'^\[([^\]\n]+) → ([^\]\n]+)\] (.+)$', value, re.M)
            for key, value in sections.items()}
    expected = [(stamp(s['start']), stamp(s['end'])) for s in raw['segments']]
    for key, values in rows.items():
        if [(a,b) for a,b,_ in values] != expected or any(not body.strip() for _,_,body in values):
            raise ValueError('Markdown delivery count, timestamp or body mismatch')
    if [body for _,_,body in rows['完整原始转写']] != [s['text'] for s in raw['segments']]:
        raise ValueError('Original ASR text changed in Markdown')
    return {'english_segments':len(expected), 'chinese_segments':len(expected),
            'timestamp_pairs_matched':len(expected), 'chinese_sections':1, 'english_sections':1,
            'all_bodies_nonempty':True, 'original_asr_text_unchanged':True}
