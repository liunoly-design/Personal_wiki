"""Opt-in real Chrome checks; synthetic pages and disposable profiles only."""
import os
from io import StringIO
import socket
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from scripts.browser_session import browser_html


@unittest.skipUnless(os.environ.get('WIKI_BROWSER_INTEGRATION') == '1', 'requires local Chrome')
class BrowserSessionTest(unittest.TestCase):
    def test_x_login_can_load_the_platform_onboarding_frame(self):
        from urllib.parse import urlsplit
        form_visible = Event()

        @contextmanager
        def synthetic_browser():
            with sync_playwright() as playwright:
                def launch(*args, **kwargs):
                    kwargs['args'] += ['--no-proxy-server']
                    context = playwright.chromium.launch_persistent_context(*args, **kwargs)
                    install_route = context.route

                    class SyntheticTransport:
                        def __init__(self, route):
                            self.route = route
                            self.request = route.request
                        def abort(self):self.route.abort()
                        def continue_(self):
                            host = urlsplit(self.request.url).hostname
                            body = '<iframe src="https://jf.x.com/onboarding/web"></iframe>' if host == 'x.com' else '<input aria-label="电子邮件或用户名">'
                            self.route.fulfill(body=body, content_type='text/html')

                    # Keep the production authorization handler; replace its network transport.
                    context.route = lambda pattern, handler: install_route(pattern, lambda route: handler(SyntheticTransport(route)))
                    page = context.pages[0]
                    wait = page.wait_for_timeout
                    def inspect_form(timeout):
                        wait(timeout)
                        for frame in page.frames:
                            if frame.url.startswith('https://jf.x.com/') and frame.get_by_role('textbox').is_visible():
                                form_visible.set()
                    page.wait_for_timeout = inspect_form
                    return context
                yield SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))

        with tempfile.TemporaryDirectory() as profile, \
             patch('scripts.browser_session.sync_playwright', synthetic_browser), \
             patch('scripts.browser_session.public_addresses', return_value=('x.com', ['93.184.216.34'])), \
             patch('builtins.input', side_effect=lambda _: form_visible.wait(5)):
            browser_html('https://x.com/synthetic', profile, login=True)
        self.assertTrue(form_visible.is_set(), 'platform onboarding was blocked and no account input appeared')

    def test_closing_login_page_or_context_exits_cleanly_and_releases_profile(self):
        import fcntl
        for close_context in (False, True):
            with self.subTest(close_context=close_context), tempfile.TemporaryDirectory() as directory:
                profile = os.path.join(directory, 'x.com')
                release_input = Event()
                output = StringIO()

                @contextmanager
                def synthetic_browser():
                    with sync_playwright() as playwright:
                        def launch(*args, **kwargs):
                            kwargs['args'] += ['--no-proxy-server']
                            context = playwright.chromium.launch_persistent_context(*args, **kwargs)
                            page = context.pages[0]
                            page.route('https://x.com/**', lambda route: route.fulfill(
                                body='<script>setTimeout(()=>console.log("close-login-window"),300)</script>',
                                content_type='text/html'))
                            cdp = context.new_cdp_session(page)
                            def close_on_signal(message):
                                if message.text == 'close-login-window':
                                    cdp.send('Browser.close' if close_context else 'Page.close')
                            page.on('console', close_on_signal)
                            return context
                        yield SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))

                try:
                    with patch('scripts.browser_session.sync_playwright', synthetic_browser), \
                         patch('scripts.browser_session.public_addresses', return_value=('x.com', ['93.184.216.34'])), \
                         patch('builtins.input', side_effect=lambda _: release_input.wait(10)), \
                         redirect_stdout(output):
                        self.assertEqual(browser_html('https://x.com/synthetic', profile, login=True), '')
                    self.assertIn('登录是否完成尚未核验', output.getvalue())
                    with open(profile + '.lock') as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    release_input.set()

    def test_manual_login_keeps_api_requests_running_without_local_websocket_access(self):
        api_seen = Event()
        api_processed_while_waiting = Event()
        waiting_for_input = Event()
        with socket.socket() as listener, tempfile.TemporaryDirectory() as profile:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            listener.settimeout(0.2)
            port = listener.getsockname()[1]

            @contextmanager
            def synthetic_browser():
                with sync_playwright() as playwright:
                    def launch(*args, **kwargs):
                        kwargs['args'] += ['--no-proxy-server']
                        context = playwright.chromium.launch_persistent_context(*args, **kwargs)
                        page = context.pages[0]
                        html = '<script>setTimeout(()=>{fetch("https://api.x.com/probe");new WebSocket("ws://127.0.0.1:%d/probe")},300)</script>' % port
                        page.route('https://x.com/**', lambda route: route.fulfill(body=html, content_type='text/html'))

                        def answer_api(route):
                            route.fulfill(body='{}', content_type='application/json')
                            if waiting_for_input.is_set():api_processed_while_waiting.set()
                            api_seen.set()

                        page.route('https://api.x.com/**', answer_api)
                        return context

                    yield SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))

            def user_finishes_after_api_response(_prompt):
                waiting_for_input.set()
                api_seen.wait(5)
                Event().wait(0.4)
                waiting_for_input.clear()
                return ''

            with patch('scripts.browser_session.sync_playwright', synthetic_browser), \
                 patch('scripts.browser_session.public_addresses', return_value=('x.com', ['93.184.216.34'])), \
                 patch('builtins.input', side_effect=user_finishes_after_api_response):
                browser_html('https://x.com/synthetic', profile, login=True)

            try:
                connection, _ = listener.accept()
                connection.close()
                local_connection = True
            except socket.timeout:
                local_connection = False
            self.assertTrue(api_processed_while_waiting.is_set(), 'manual login blocked the browser API request')
            self.assertFalse(local_connection, 'page reached a local WebSocket service')
