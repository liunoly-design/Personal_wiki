import json, tempfile, unittest, os
from pathlib import Path
from scripts.protected_store import Root, archive, publish_source

class PublishSourceTest(unittest.TestCase):
 def test_source_is_visible_with_working_media_and_requires_watcher_exclusion(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);vault=base/'vault';vault.mkdir();snapshot=base/'capture';snapshot.mkdir();(snapshot/'images').mkdir()
   original=b'# Full article\n\n![Photo](images/photo.jpg)\n';(snapshot/'article.md').write_bytes(original);(snapshot/'images/photo.jpg').write_bytes(b'photo')
   root=Root(vault)
   try:
    record=archive(root,dict(url='https://x.com/a/status/1',snapshot=str(snapshot),slug='full-article'))
    state=base/'app-state.json';state.write_text(json.dumps({'projectRegistry':{'id':{'path':str(vault)}},'sourceWatchConfig':{'id':{'excludeGlobs':[]}}}))
    req={'sourceId':record['id'],'appStatePath':str(state)}
    with self.assertRaisesRegex(ValueError,'exclusion'):publish_source(root,req)
    target=vault/'raw/sources/collected/full-article.md';self.assertFalse(target.exists())
    state.write_text(json.dumps({'projectRegistry':{'id':{'path':str(vault)}},'sourceWatchConfig':{'id':{'excludeGlobs':['raw/sources/collected/*']}}}))
    result=publish_source(root,req);self.assertEqual(result['path'],str(target));text=target.read_text();self.assertIn('# Full article',text)
    self.assertIn('../../../raw/assets/'+record['id']+'/images/photo.jpg',text)
    self.assertEqual((Path(record['archive'])/'article.md').read_bytes(),original)
    self.assertEqual((vault/'raw/inputs/full-article.md').read_bytes(),original)
    publish_source(root,req);target.write_text('manual changes')
    with self.assertRaises(ValueError):publish_source(root,req)
    self.assertEqual(target.read_text(),'manual changes')
   finally:os.close(root.fd)
