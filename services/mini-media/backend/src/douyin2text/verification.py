"""Fail-closed provenance and media checks for new deliveries."""
import math
import re
from urllib.parse import urlsplit, parse_qs

STAGES = ('resolving', 'metadata', 'downloading', 'extracting', 'transcribing', 'translating', 'verifying')
CODES = ('SOURCE_RESOLUTION_FAILED', 'DETAIL_FETCH_FAILED', 'SOURCE_UNAVAILABLE', 'AUTH_REQUIRED', 'DOWNLOAD_FAILED', 'MEDIA_INVALID', 'EXTRACTION_FAILED', 'ASR_FAILED', 'TRANSLATION_FAILED', 'VERIFICATION_FAILED', 'SOURCE_MISMATCH', 'PROCESSING_FAILED')

class VerificationError(RuntimeError):
    def __init__(self, message, code='VERIFICATION_FAILED', retryable=False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

def explicit_ids(url):
    u = urlsplit(url)
    values = re.findall(r'/(?:video|note)/([^/]+)', u.path)
    q = parse_qs(u.query, keep_blank_values=True)
    for key in ('modal_id', 'item_id'):
        values.extend(q.get(key, []))
    return values

def binding(url, vid):
    if not re.fullmatch(r'\d{10,24}', str(vid)) or any(x != vid for x in explicit_ids(url)):
        raise VerificationError('Source ID mismatch', 'SOURCE_MISMATCH')

def durations(video, audio, source):
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in (video, audio, source)):
        raise VerificationError('Invalid media duration', 'MEDIA_INVALID')
    tolerance = max(1, video * .005)
    if abs(video - audio) > tolerance or abs(video - source) > tolerance:
        raise VerificationError('Media duration mismatch', 'MEDIA_INVALID')

def evidence(m):
    v = m.get('verification')
    if not v:
        raise VerificationError('verification evidence missing; upgrade server')
    vid = m['media_id']
    binding(v['input_url'], vid)
    u = urlsplit(m['canonical_url'])
    if u.scheme != 'https' or u.hostname not in ('www.douyin.com', 'douyin.com', 'www.iesdouyin.com', 'iesdouyin.com') or u.port not in (None, 443) or u.username or u.password or u.query or u.fragment or u.path != f'/video/{vid}':
        raise VerificationError('Canonical source mismatch', 'SOURCE_MISMATCH')
    if any(v.get(k) != vid for k in ('resolved_id', 'detail_id', 'downloaded_id')):
        raise VerificationError('Source binding mismatch', 'SOURCE_MISMATCH')
    for kind in ('video', 'audio'):
        check = v.get(kind, {})
        if check.get('full_decode') is not True or any(check.get(k) != m['files'][kind][k] for k in ('sha256', 'bytes')):
            raise VerificationError('Media evidence mismatch', 'MEDIA_INVALID')
    durations(v['video']['duration_seconds'], v['audio']['duration_seconds'], m['platform_duration_seconds'])


def identifier_fragment(source, target, index):
    """Only preserve an exact ASR suffix of a registered technical identifier."""
    if index <= 0:
        return None
    fragment=source[index]['text'].strip()
    previous=re.search(r'\b([A-Za-z]+)$',source[index-1]['text'].rstrip())
    if not re.fullmatch(r'[A-Za-z]{1,3}',fragment) or not previous:
        return None
    prefix=previous.group(1)
    identifier=prefix+fragment
    if identifier not in {'Foundry'} or target[index]['text'].strip()!=fragment or prefix not in target[index-1]['text']:
        return None
    return {'source_index':index,'source_segment_id':source[index].get('id',index),'identifier':identifier,'prefix':prefix,'fragment':fragment}
