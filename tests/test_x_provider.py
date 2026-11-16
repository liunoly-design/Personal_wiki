import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.x_provider import capture


class XProviderTest(unittest.TestCase):
    def test_article_media_quote_and_self_reply_keep_their_distinct_positions(self):
        quote=dict(type='status',id='9',author=dict(id='b',screen_name='quoted'),replying_to=None,text='引用内容')
        post=dict(type='status',id='123',author=dict(id='a',screen_name='example'),replying_to=None,text='预览',quote=quote,
                  article=dict(title='文章',content=dict(blocks=[
                      dict(type='unstyled',text='图片之前',entityRanges=[]),
                      dict(type='atomic',text=' ',entityRanges=[dict(key=0,offset=0,length=1)]),
                      dict(type='unstyled',text='图片之后',entityRanges=[])
                  ],entityMap=[dict(key='0',value=dict(type='MEDIA',data=dict(mediaItems=[dict(mediaId='image1')])))]),
                  media_entities=[dict(media_id='image1',media_info=dict(original_img_url='https://pbs.twimg.com/media/synthetic.jpg'))]))
        child=dict(type='status',id='124',author=post['author'],replying_to=dict(status='123',screen_name='example'),text='连续串文的末节')
        def network(url,limit,destination):
            if '/thread/' in url:destination.write_text(json.dumps(dict(code=200,thread=[post,child])))
            else:destination.write_bytes(b'synthetic image')
            return url
        with tempfile.TemporaryDirectory() as temp,patch('scripts.x_provider.fetch_public',side_effect=network):
            result=capture('https://x.com/example/status/123',temp)
            body=(Path(result['directory'])/'article.md').read_text()
            self.assertLess(body.index('图片之前'),body.index('![图片]'))
            self.assertLess(body.index('![图片]'),body.index('图片之后'))
            self.assertIn('引用内容',body);self.assertIn('连续串文的末节',body)
            self.assertEqual(result['status'],'complete')

    def test_long_article_uses_all_blocks_not_the_short_preview(self):
        post = dict(type='status', id='123', url='https://x.com/example/status/123',
                    author=dict(id='a', screen_name='example'), replying_to=None,
                    text='只有预览', raw_text=dict(text='只有预览'),
                    article=dict(title='完整文章', content=dict(blocks=[
                        dict(type='unstyled', text='第一节完整内容', entityRanges=[], inlineStyleRanges=[]),
                        dict(type='header-two', text='最后一节', entityRanges=[], inlineStyleRanges=[]),
                        dict(type='unstyled', text='包含不可丢失的末尾。', entityRanges=[], inlineStyleRanges=[]),
                    ], entityMap=[]), media_entities=[]))
        def network(url, limit, destination):
            destination.write_text(json.dumps(dict(code=200, status='OK', thread=[post])))
            return url
        with tempfile.TemporaryDirectory() as temp, patch('scripts.x_provider.fetch_public', side_effect=network):
            result = capture('https://x.com/example/status/123', temp)
            body = (Path(result['directory']) / 'article.md').read_text()
            self.assertEqual(result['contextStatus'], 'complete')
            self.assertIn('第一节完整内容', body)
            self.assertIn('## 最后一节', body)
            self.assertIn('不可丢失的末尾', body)
            self.assertEqual(result['articleBlocks'], 3)
            self.assertTrue((Path(result['directory']) / 'provider.json').exists())

    def test_missing_reply_evidence_and_foreign_identity_are_rejected(self):
        for changes in ({'id':'999'}, {'replying_to':'missing'}):
            post=dict(type='status', id='123', url='https://x.com/example/status/123',
                      author=dict(id='a',screen_name='example'), text='正文', replying_to=None)
            if changes.get('replying_to')=='missing': del post['replying_to']
            else: post.update(changes)
            def network(url, limit, destination):
                destination.write_text(json.dumps(dict(code=200, status='OK', thread=[post])))
                return url
            with tempfile.TemporaryDirectory() as temp, patch('scripts.x_provider.fetch_public',side_effect=network):
                with self.assertRaises(ValueError):capture('https://x.com/example/status/123', temp)
