"""Dedicated local browser profile. Never imports personal browser cookies."""
import argparse
import fcntl
import json
import os
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlsplit
from playwright.sync_api import Error as PlaywrightError, sync_playwright
try:
    from .blog_capture import public_addresses
except ImportError:
    from blog_capture import public_addresses


def browser_html(url,profile,login=False):
    host=urlsplit(url).hostname
    if host not in ('x.com','mp.weixin.qq.com'):raise ValueError('Unsupported login platform')
    allowed=('x.com','jf.x.com','api.x.com','twitter.com','api.twitter.com','abs.twimg.com','pbs.twimg.com','video.twimg.com') if host=='x.com' else ('mp.weixin.qq.com','res.wx.qq.com','mmbiz.qpic.cn','mmbiz.qlogo.cn')
    profile=Path(profile);profile.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(profile,0o700)
    lock=(profile.parent/(profile.name+'.lock')).open('w')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rules=[]
        for domain in allowed:
            try:_,addresses=public_addresses('https://'+domain);rules.append(f'MAP {domain} {addresses[0]}')
            except OSError:pass
        # Chrome resolves the local system proxy through these rules too.
        # This permits its transport; the request route still denies local URLs.
        rules.extend(['MAP * ~NOTFOUND','EXCLUDE 127.0.0.1'])
        with sync_playwright() as p:
            context=p.chromium.launch_persistent_context(str(profile),channel='chrome',headless=not login,args=['--host-resolver-rules='+','.join(rules)],service_workers='block')
            envelopes=[];size=0
            def route(request):
                u=urlsplit(request.request.url)
                if u.scheme!='https' or u.hostname not in allowed or u.username or u.password or u.port not in (None,443):request.abort();return
                request.continue_()
            context.route('**/*',route)
            # Unconnected routed WebSockets cannot reach any server, including loopback.
            context.route_web_socket('**/*',lambda websocket:None)
            page=context.pages[0] if context.pages else context.new_page()
            window_closed=Event()
            page.on('close',lambda _:window_closed.set())
            context.on('close',lambda _:window_closed.set())
            def response(r):
                nonlocal size
                if 'json' not in r.headers.get('content-type','') or size>=16*1024*1024:return
                try:
                    raw=r.body()
                    if len(raw)>2*1024*1024:return
                    size+=len(raw);envelopes.append(json.loads(raw))
                except Exception:pass
            if not login:page.on('response',response)
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=60000)
                if login:
                    finished=Event()
                    def wait_for_user():
                        try:input('请在专用Wiki窗口完成当前平台登录/验证码，完成后在终端按回车。Cookie只保留在此隔离配置中。')
                        except EOFError:pass
                        finally:finished.set()
                    Thread(target=wait_for_user,daemon=True).start()
                    # Keep Playwright's HTTP callbacks running while the user logs in.
                    while not finished.is_set() and not window_closed.is_set():
                        try:page.wait_for_timeout(100)
                        except PlaywrightError:
                            if not window_closed.is_set() and not page.is_closed():raise
                            break
                    if window_closed.is_set() or page.is_closed():
                        print('\n专用Wiki窗口已关闭；登录是否完成尚未核验。若尚未登录，请重新打开；若已完成，请在原飞书会话发送“登录继续”。')
                else:
                    page.wait_for_timeout(2000)
                    if '/login' in page.url or '/i/flow' in page.url or page.locator('input[type="password"], #captcha, [data-testid="LoginForm"]').count():raise ValueError('login/captcha required; complete dedicated browser login')
                    if host=='x.com':
                        seen=set();articles=[]
                        for _ in range(20):
                            for html in page.locator('article').evaluate_all('(nodes)=>nodes.map(n=>n.outerHTML)'):
                                if html not in seen:seen.add(html);articles.append(html)
                            before=len(envelopes);page.mouse.wheel(0,1600);page.wait_for_timeout(700)
                            if len(envelopes)==before:break
                        html=''.join(articles)
                    else:html=page.content()
                if login:return ''
                return html+''.join('<script type="application/json">'+json.dumps(v,ensure_ascii=False).replace('</','<\\/')+'</script>' for v in envelopes)
            finally:context.close()
    except BlockingIOError:raise ValueError('Dedicated browser busy; finish login and close its window')
    finally:lock.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--profile',required=True);parser.add_argument('--login',action='store_true');args=parser.parse_args()
    if not args.login:raise ValueError('CLI only opens login; capture needs task authorization')
    browser_html(args.url,args.profile,True)
