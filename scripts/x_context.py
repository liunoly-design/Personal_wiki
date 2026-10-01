"""Collect only connected same-author posts and explicitly linked quotes."""
import copy
import json
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup


def post_url(value):
    u=urlsplit(urljoin('https://x.com',value))
    match=re.fullmatch(r'/([\w]+)/status/(\d+)/?',u.path)
    if u.scheme!='https' or u.hostname not in ('x.com','twitter.com','www.x.com','www.twitter.com') or u.username or u.password or u.port not in (None,443) or not match:
        return None
    return f'https://x.com/{match[1].lower()}/status/{match[2]}'


def parse_posts(soup):
    posts={}
    for node in soup.select('article'):
        links=[a for a in node.select('a[href]') if a.find_parent('article') is node and not a.has_attr('data-quote')]
        own=next((post_url(a['href']) for a in links if post_url(a['href'])),None)
        if not own:continue
        quotes=[post_url(a['href']) for a in node.select('a[data-quote][href]')]
        for nested in node.select('article'):
            quote=next((post_url(a['href']) for a in nested.select('a[href]') if post_url(a['href'])),None)
            if quote:quotes.append(quote)
        clean=copy.copy(node)
        for nested in clean.select('article'):nested.decompose()
        item=dict(url=own,id=own.rsplit('/',1)[1],author=own.split('/')[3],parent=node.get('data-reply-to'),html=str(clean),quotes=list(dict.fromkeys(q for q in quotes if q)))
        if own not in posts:posts[own]=item
        else:posts[own]['quotes']=list(dict.fromkeys(posts[own]['quotes']+item['quotes']))
    # Browser/API envelopes and embedded public JSON use X's explicit reply IDs.
    def walk(value):
        if isinstance(value,list):
            for v in value:walk(v)
        elif isinstance(value,dict):
            legacy=value.get('legacy',{})
            user=value.get('core',{}).get('user_results',{}).get('result',{})
            name=user.get('legacy',{}).get('screen_name') or user.get('core',{}).get('screen_name')
            ident=value.get('rest_id') or legacy.get('id_str')
            if name and ident and legacy.get('full_text'):
                url=post_url(f'/{name}/status/{ident}')
                if url:
                    body=BeautifulSoup('<article></article>','html.parser');p=body.new_tag('p');p.string=legacy['full_text'];body.article.append(p)
                    for media in legacy.get('extended_entities',{}).get('media',[]):
                        if media.get('type')=='photo':
                            img=body.new_tag('img',src=media.get('media_url_https',''));body.article.append(img)
                        elif media.get('type') in ('video','animated_gif'):
                            node=body.new_tag('video');body.article.append(node)
                    quoted=value.get('quoted_status_result',{}).get('result',{})
                    quser=quoted.get('core',{}).get('user_results',{}).get('result',{})
                    qname=quser.get('legacy',{}).get('screen_name') or quser.get('core',{}).get('screen_name')
                    qid=quoted.get('rest_id') or legacy.get('quoted_status_id_str')
                    qurl=post_url(f'/{qname}/status/{qid}') if qname and qid else None
                    # A missing quoted author still has a safe permalink via /i/web.
                    if qid and not qurl:qurl=f'https://x.com/i/status/{qid}'
                    posts[url]=dict(url=url,id=str(ident),author=name.lower(),parent=legacy.get('in_reply_to_status_id_str'),html=str(body.article),quotes=[qurl] if qurl else [])
            for v in value.values():walk(v)
    for script in soup.select('script[type="application/json"]'):
        try:walk(json.loads(script.string or script.get_text()))
        except (ValueError,TypeError):pass
    return posts


def collect_context(url,directory,fetch,initial_soup=None):
    target=post_url(url)
    if not target:raise ValueError('Unsupported X post URL')
    posts={};gaps=[];seen=set();pages=[]
    current=target
    for index in range(20):
        if current in seen:gaps.append('分页循环，未确认完整上下文');break
        seen.add(current);raw=directory/f'context-{index:02}.html'
        try:
            if index==0 and initial_soup is not None:soup=initial_soup
            else:
                if not raw.exists():fetch(current,raw)
                soup=BeautifulSoup(raw.read_bytes(),'html.parser')
        except Exception as error:
            if index==0:raise
            gaps.append(f'分页不可读取：{current}');break
        parsed=parse_posts(soup)
        if not parsed:
            raw.unlink(missing_ok=True)
            if index==0:raise ValueError('login/captcha required; X content unavailable')
            gaps.append(f'分页正文不可读取：{current}');break
        posts.update(parsed);pages.append(current)
        nxt=soup.select_one('a[rel="next"][href]')
        if not nxt:break
        candidate=urljoin(current,nxt['href']);u=urlsplit(candidate)
        if post_url(candidate)!=target or u.username or u.password or u.port not in (None,443):
            gaps.append('拒绝无关分页链接');break
        current=candidate
    else:gaps.append('达到20页上限')
    if target not in posts:raise ValueError('Cannot identify requested X post; login may be required')
    author=posts[target]['author'];chain=[target];ids={posts[target]['id']}
    # Walk ancestors only when fetched evidence explicitly identifies the parent.
    while posts[chain[0]].get('parent'):
        parent=posts[chain[0]]['parent']
        found=next((p for p,v in posts.items() if v['id']==parent and v['author']==author),None)
        if not found:
            candidate=f'https://x.com/{author}/status/{parent}';raw=directory/f'ancestor-{parent}.html'
            try:fetch(candidate,raw);posts.update(parse_posts(BeautifulSoup(raw.read_bytes(),'html.parser')))
            except Exception:gaps.append(f'父帖不可读取：{candidate}');break
            found=next((p for p,v in posts.items() if v['id']==parent and v['author']==author),None)
        if not found:gaps.append('父帖作者或正文不可验证');break
        if posts[found]['id'] in ids:gaps.append('回复链循环');break
        ids.add(posts[found]['id']);chain.insert(0,found)
        if len(chain)>=100:gaps.append('串文达到100帖上限');break
    while True:
        children=[p for p,v in posts.items() if v['author']==author and v.get('parent')==posts[chain[-1]]['id'] and v['id'] not in ids]
        if not children:break
        if len(children)>1:gaps.append('同作者回复分叉，顺序不能唯一确认');break
        child=children[0];chain.append(child);ids.add(posts[child]['id'])
        if len(chain)>=100:gaps.append('串文达到100帖上限');break
    quotes=[]
    for p in chain:
        for q in posts[p]['quotes']:
            if q in quotes or q in chain:continue
            if len(quotes)>=20:gaps.append('引用达到20帖上限');break
            if q not in posts:
                try:
                    raw=directory/f'quote-{len(quotes):02}.html';fetch(q,raw);posts.update(parse_posts(BeautifulSoup(raw.read_bytes(),'html.parser')))
                    # /i/status redirect: resolve by ID rather than inventing author.
                    found=next((key for key,v in posts.items() if v['id']==q.rsplit('/',1)[1]),None)
                    if found:q=found
                except Exception:pass
            if q not in posts:gaps.append(f'引用正文不可读取：{q}');continue
            quotes.append(q)
    # Public pages rarely prove that all replies were exposed. State that gap.
    if not any(v.get('parent') is not None for v in posts.values()):gaps.append('平台未提供回复关系，无法确认完整串文')
    return dict(posts=[posts[p] for p in chain]+[{**posts[p],'role':'quote','quoted_by':[q for q in chain if p in posts[q]['quotes']]} for p in quotes],gaps=list(dict.fromkeys(gaps)),pages=pages)
