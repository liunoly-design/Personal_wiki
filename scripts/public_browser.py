"""Ephemeral public-page renderer. All network goes through pinned HTTPS.

No profile, cookies, service workers, WebSockets or browser DNS/network escape.
Raw responses are retained separately from the rendered DOM.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
try:
    from . import blog_capture
except ImportError:
    import blog_capture


def render_public(url, directory):
    directory=Path(directory);network=directory/'browser-responses';network.mkdir(exist_ok=True)
    responses=[];total=0;main_error=None;final=url
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel='chrome',headless=True,args=['--host-resolver-rules=MAP * ~NOTFOUND','--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
        try:
            context=browser.new_context(service_workers='block',accept_downloads=False)
            context.route_web_socket('**/*',lambda ws:ws.close())
            def route_request(route):
                nonlocal total,main_error,final
                request=route.request
                if request.method!='GET' or urlsplit(request.url).scheme!='https' or request.resource_type in ('image','media','font') or len(responses)>=100 or total>=100*1024*1024:
                    route.abort();return
                destination=network/f'{len(responses):03}.body';record={'url':request.url,'file':destination.name};responses.append(record)
                try:
                    metadata={}
                    resolved=blog_capture.fetch_public(request.url,min(20*1024*1024,100*1024*1024-total),destination,response_metadata=metadata)
                    data=destination.read_bytes();total+=len(data);record.update(metadata)
                    if request.is_navigation_request() and request.frame==page.main_frame:
                        final=resolved
                        if resolved!=request.url:
                            route.fulfill(status=302,headers={'Location':resolved},body='');return
                    route.fulfill(status=200,content_type=metadata['content_type'],body=data)
                except Exception as error:
                    record['error']=type(error).__name__
                    if request.is_navigation_request() and request.frame==page.main_frame:main_error=error
                    route.abort()
            context.route('**/*',route_request)
            page=context.new_page()
            try:
                page.goto(url,wait_until='networkidle',timeout=60000)
                page.wait_for_timeout(1000)
                if main_error:raise main_error
                (directory/'rendered.html').write_text(page.content())
            finally:
                (directory/'browser-network.json').write_text(json.dumps(responses,ensure_ascii=False,indent=2))
        finally:browser.close()
    return final
