"""Opt-in real Chrome checks; synthetic pages and disposable profiles only."""
import os
import socket
import tempfile
import unittest
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from scripts.browser_session import browser_html


@unittest.skipUnless(os.environ.get('WIKI_BROWSER_INTEGRATION') == '1', 'requires local Chrome')
class BrowserSessionTest(unittest.TestCase):
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
