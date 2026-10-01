import sys, tempfile, unittest, json, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from protected_store import Root, archive
from canonical_migration import plan, apply

class CanonicalMigrationTest(unittest.TestCase):
    def test_migration_preserves_originals_and_does_not_cleanup_without_verified_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); vault = base/'vault'; snapshot = base/'snapshot'; backup = base/'backup'
            for p in [vault, snapshot, backup]: p.mkdir()
            (snapshot/'article.md').write_text('完整原文。')
            record = archive(Root(vault), dict(url='https://x.com/a/status/1', snapshot=str(snapshot), slug='sample'))
            (vault/'wiki/sources').mkdir(parents=True)
            (vault/'wiki/sources/sample.md').write_text('# 原有资料卡\n手写备注必须保留。')
            (vault/'reading').mkdir(); (vault/'reading/sample.zh.md').write_text('完整中文正文。')
            (vault/'glossary').mkdir(); (vault/'glossary/example.md').write_text('# 示例\n基础解释。')
            value = plan(vault, backup); apply(vault, backup)
            body = (vault/'wiki/sources/sample.md').read_text()
            self.assertIn('手写备注必须保留', body); self.assertIn('完整中文正文', body)
            self.assertEqual((vault/'raw/assets'/record['id']/'article.md').read_text(), '完整原文。')
            self.assertEqual((vault/'wiki/concepts/example.md').read_text(), '# 示例\n基础解释。')
            with self.assertRaises(FileNotFoundError): apply(vault, backup, cleanup=True)
            self.assertTrue((vault/'reading/sample.zh.md').exists())
            (backup/'verified.json').write_text(json.dumps({'planHash':hashlib.sha256((backup/'plan.json').read_bytes()).hexdigest()}))
            apply(vault, backup, cleanup=True); apply(vault, backup, cleanup=True)
            self.assertFalse((vault/'reading').exists()); self.assertFalse((vault/'raw/inputs').exists())
            self.assertTrue((backup/'before/reading/sample.zh.md').exists())

    def test_concurrent_edit_after_inventory_stops_migration(self):
        with tempfile.TemporaryDirectory() as d:
            vault=Path(d)/'vault'; backup=Path(d)/'backup'
            (vault/'glossary').mkdir(parents=True); backup.mkdir()
            (vault/'glossary/example.md').write_text('# 示例')
            (vault/'wiki/concepts').mkdir(parents=True)
            target=vault/'wiki/concepts/example.md';target.write_text('旧内容')
            plan(vault,backup);target.write_text('新的手写内容')
            with self.assertRaisesRegex(ValueError,'Concurrent edit'):apply(vault,backup)
            self.assertEqual(target.read_text(),'新的手写内容')
