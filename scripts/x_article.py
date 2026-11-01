"""Select one evidenced X post, retaining complete responsive copies."""
import copy
import re
from collections import Counter
from urllib.parse import urljoin, urlsplit


def post_url(value):
    u=urlsplit(urljoin('https://x.com',value))
    match=re.fullmatch(r'/([\w]+)/status/(\d+)/?',u.path)
    if u.scheme!='https' or u.hostname not in ('x.com','twitter.com','www.x.com','www.twitter.com') or u.username or u.password or u.port not in (None,443) or not match:
        return None
    return f'https://x.com/{match[1].lower()}/status/{match[2]}'


def article_permalink_candidates(article):
    links=[(a,post_url(a['href'])) for a in article.select('a[href]')
           if a.find_parent('article') is article and not a.has_attr('data-quote')]
    links=[(a,url) for a,url in links if url]
    # The body can link another post before its own timestamp permalink.
    # Public HTML mirrors may retain only the rendered timestamp text.
    timestamps={url for a,url in links if a.select_one('time') or re.fullmatch(
        r'\d{1,2}:\d{2}(?:\s*[AP]M)?\s*[·•]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}',
        a.get_text(' ',strip=True),re.IGNORECASE)}
    if timestamps:
        return list(timestamps) if len(timestamps)==1 else []
    # Without timestamp evidence every owned post link remains a candidate.
    # Keep conflicting responsive copies visible to the ambiguity check.
    return list(dict.fromkeys(url for _,url in links))


def article_permalink(article):
    candidates=article_permalink_candidates(article)
    return candidates[0] if candidates else None


def select_target_article(soup, url):
    target=post_url(url)
    candidates=[]
    for article in soup.select('article'):
        if target and target in article_permalink_candidates(article):
            candidates.append(article)
    # Duplicate wrapper markup may contain the same target again. Keep the
    # deepest matching target while retaining quotes inside it.
    leaves=[a for a in candidates if not any(b is not a and any(p is a for p in b.parents) for b in candidates)]
    def signature(a):
        quote_links=tuple(n['href'] for n in a.select('a[data-quote][href]'))
        return (a.get_text(' ',strip=True),tuple((n.name,n.get('href'),n.get('src')) for n in a.select('a,img,video,source')),a.get('data-reply-to'),quote_links)
    leaves=list({signature(a):a for a in leaves}.values())
    if len(leaves)>1:
        # Responsive copies can show the same post with/without an embedded
        # quote. Compare only the target's own content, then retain a variant
        # containing every quote seen in the other equivalent copies.
        def own_signature(a):
            own=copy.copy(a)
            for nested in own.select('article'):nested.decompose()
            # Only bare URL labels may differ between responsive copies.
            # Descriptive link text and every other body character must agree.
            for link in own.select('a[href]'):
                href=link['href']
                if href.startswith(('https://','http://')) and link.get_text(strip=True)==href:
                    link.decompose()
            return (own.get_text(' ',strip=True),tuple(link.get('href') for link in own.select('a[href]')))
        if len({own_signature(a) for a in leaves})==1:
            # Embedded bodies and all quote relationships are separate evidence:
            # a missing marker must not make an otherwise equal body conflict.
            quote_sets=[{signature(q)[:3] for q in a.select('article')} | {('quoted-link',href) for href in signature(a)[3]} for a in leaves]
            union=set().union(*quote_sets)
            references=[]
            reference_union=Counter()
            for article in leaves:
                own=copy.copy(article)
                for nested in own.select('article'):nested.decompose()
                refs=Counter(signature(own)[1]);references.append(refs)
                reference_union |= refs
            parents={a.get('data-reply-to') for a in leaves if a.has_attr('data-reply-to')}
            complete=[a for a,quotes,refs in zip(leaves,quote_sets,references)
                      if quotes==union and refs==reference_union
                      and len(parents)<=1 and (not parents or a.get('data-reply-to') in parents)]
            if complete and len({signature(a) for a in complete})==1:leaves=[complete[0]]
    if len(leaves)!=1:
        raise ValueError('Cannot identify the requested X post unambiguously')
    return leaves[0]
