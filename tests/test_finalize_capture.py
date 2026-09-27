import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/finalize_capture.py'


class FinalizeTest(unittest.TestCase):
    def test_repairs_known_raw_link_and_preserves_generated_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'raw/assets/abc').mkdir(parents=True)
            (root / 'raw/assets/abc/article.md').write_text('original')
            (root / 'wiki/sources').mkdir(parents=True)
            page = root / 'wiki/sources/abc.md'
            original = '# Source\n[raw](../assets/abc/article.md)\n'
            page.write_text(original)
            result = subprocess.run([sys.executable, str(SCRIPT), '--vault', temp, '--source-id', 'abc'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('../../raw/assets/abc/article.md', page.read_text())
            history = list((root/'.personal-wiki/generated-history').rglob('*.md'))
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].read_text(), original)
            self.assertEqual((root/'raw/assets/abc/article.md').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
