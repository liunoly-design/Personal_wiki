"""Select one evidenced X post, retaining complete responsive copies."""
import copy
from collections import Counter
from urllib.parse import urlsplit


def select_target_article(soup, url):
    target=urlsplit(url).path.rstrip('/').lower()
    candidates=[]
    for article in soup.select('article'):
        owned=[a for a in article.select('a[href]') if a.find_parent('article') is article]
        if any(urlsplit(a['href']).path.rstrip('/').lower()==target for a in owned):
            candidates.append(article)
    # Duplicate wrapper markup may contain the same target again. Keep the
    # deepest matching target while retaining quotes inside it.
    leaves=[a for a in candidates if not any(b is not a and any(p is a for p in b.parents) for b in candidates)]
    def signature(a):
        quote_links=tuple(n['href'] for n in a.select('a[data-quote][href]') if n.find_parent('article') is a)
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
            quote_sets=[{signature(q) for q in a.select('article')} | {('quoted-link',href) for href in signature(a)[3]} for a in leaves]
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
