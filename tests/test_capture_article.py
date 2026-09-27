import unittest
try:
    from scripts.capture_article import select_target_article
    from bs4 import BeautifulSoup
except ImportError:
    select_target_article = None

@unittest.skipUnless(select_target_article, 'capture dependencies required')
class TargetTest(unittest.TestCase):
    def test_long_comment_and_nested_quote(self):
        soup=BeautifulSoup('<article><a href="/a/status/1">target</a>body<article><a href="/b/status/2">quote</a>quoted text</article></article><article><a href="/c/status/3">comment</a>'+('long comment '*100)+'</article>','html.parser')
        article=select_target_article(soup,'https://x.com/a/status/1?s=20')
        self.assertIn('quoted text',article.get_text())
        self.assertNotIn('long comment',article.get_text())
    def test_equivalent_responsive_copies(self):
        soup=BeautifulSoup('<article class="mobile"><a href="/a/status/1">post</a></article><article class="desktop"><a href="/a/status/1">post</a></article>','html.parser')
        self.assertEqual(select_target_article(soup,'https://x.com/a/status/1').get_text(),'post')
    def test_unknown_target_fails(self):
        with self.assertRaises(ValueError):
            select_target_article(BeautifulSoup('<article>unidentified</article>','html.parser'),'https://x.com/a/status/1')
