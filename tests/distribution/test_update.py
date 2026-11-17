"""Exercise downloaded packages and the public offline update CLI, without accounts."""
import fcntl, hashlib, json, os, plistlib, subprocess, sys, tarfile, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / 'distribution/pwiki-setup.py'

class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.prefix = self.root / 'installed'
        self.config = self.root / 'private/config.json'
        self.home = self.root / 'home'
        self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home)}
        self.old = self.package('0.10.0')
        self.run_command(['node', str(self.old / 'install.mjs'), '--prefix', str(self.prefix), '--config', str(self.config), '--python', sys.executable])
        self.original = self.config.read_bytes()
        self.previous = (self.prefix / 'state/runtime/current').resolve()

    def run_command(self, args):
        result = subprocess.run(args, text=True, capture_output=True, env=self.env, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def package(self, version):
        out = self.root / version
        self.run_command([sys.executable, str(ROOT / 'distribution/build.py'), '--component', 'cli', '--version', version, '--output', str(out), '--allow-dirty'])
        archive = next(out.glob('*.tar.gz'))
        with tarfile.open(archive) as bundle:
            # Only our synthetic, locally built package; portable to system Python3.9.
            bundle.extractall(out / 'unpacked')
        (out / 'release.json').write_text(json.dumps({'tag_name': 'distribution-v' + version, 'draft': False, 'prerelease': False}))
        return next((out / 'unpacked').iterdir())

    def update(self, directory, success=True):
        result = subprocess.run([sys.executable, str(SETUP), 'update', '--prefix', str(self.prefix), '--release-dir', str(directory)], text=True, capture_output=True, env=self.env, timeout=45)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0)
        return json.loads(result.stdout)

    def test_updates_from_package_preserving_configuration_and_originals(self):
        new = self.package('0.10.1')
        vault = self.root / 'my-vault'
        vault.mkdir()
        original = vault / 'raw.txt'
        original.write_text('用户原件，不允许更改。')
        value = self.update(new.parent.parent)
        self.assertEqual(value['status'], 'updated')
        self.assertNotEqual((self.prefix / 'state/runtime/current').resolve(), self.previous)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(original.read_text(), '用户原件，不允许更改。')
        value = self.update(new.parent.parent)
        self.assertEqual(value['status'], 'up_to_date')
        converted = self.run_command([str(self.prefix / 'bin/personal-wiki'), 'convert', '--text', '升级后原样保留全文。'])
        self.assertEqual(json.loads(converted.stdout)['status'], 'converted')

    def test_busy_runtime_or_queued_task_defers_without_switching(self):
        new = self.package('0.10.1')
        with (self.prefix / 'state/runtime/use.lock').open('a') as active:
            fcntl.flock(active, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(self.update(new.parent.parent)['status'], 'deferred')
        self.assertEqual((self.prefix / 'state/runtime/current').resolve(), self.previous)
        submitted = self.run_command([str(self.prefix / 'bin/personal-wiki'), 'submit', '--text', '正在等待执行的资料。'])
        task = json.loads(submitted.stdout)
        self.assertEqual(task['status'], 'queued')
        self.assertEqual(self.update(new.parent.parent)['status'], 'deferred')
        self.assertEqual((self.prefix / 'state/runtime/current').resolve(), self.previous)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_daily_schedule_uses_managed_absolute_entry(self):
        result = self.run_command([sys.executable, str(SETUP), 'schedule', '--prefix', str(self.prefix), '--dry-run'])
        plan = json.loads(result.stdout)
        self.assertEqual(plan['intervalSeconds'], 3600)
        self.assertEqual(plan['arguments'], [str(self.prefix / 'bin/pwiki-update'), '--scheduled'])
        self.assertTrue((self.prefix / 'bin/pwiki-update').is_file())
        value = self.update(self.old.parent.parent)
        self.assertEqual(value['status'], 'up_to_date')
        due = self.run_command([str(self.prefix / 'bin/pwiki-update'), '--scheduled'])
        self.assertEqual(json.loads(due.stdout)['status'], 'not_due')

    def test_unified_install_replays_with_private_mini_configuration(self):
        prefix = self.root / 'another-client'
        token = self.root / 'mini-token'
        token.write_text('synthetic-test-token')
        token.chmod(0o600)
        app = self.home / 'Applications/LLM Wiki.app/Contents'
        app.mkdir(parents=True)
        (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.llmwiki.app', 'CFBundleShortVersionString': '0.6.11'}))
        args = [sys.executable, str(SETUP), 'install', '--prefix', str(prefix), '--release-dir', str(self.old.parent.parent), '--media-url', 'http://192.0.2.10:8765', '--media-token-file', str(token), '--skip-dependencies', '--no-schedule']
        first = json.loads(self.run_command(args).stdout)
        self.assertEqual(first['status'], 'installed')
        config = Path(first['config'])
        value = json.loads(config.read_text())
        self.assertEqual(value['mediaServiceUrl'], 'http://192.0.2.10:8765')
        self.assertEqual(value['mediaServiceTokenFile'], str(token))
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        before = config.read_bytes()
        self.assertEqual(json.loads(self.run_command(args).stdout)['status'], 'installed')
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(token.read_text(), 'synthetic-test-token')
        self.assertTrue((self.home / '.codex/skills/personal-wiki/SKILL.md').is_file())

    def rewrite_archive(self, package):
        manifest = json.loads((package / 'distribution.json').read_text())
        for name in manifest['files']:
            manifest['files'][name] = hashlib.sha256((package / name).read_bytes()).hexdigest()
        (package / 'distribution.json').write_text(json.dumps(manifest))
        archive = package.parent.parent / (package.name + '.tar.gz')
        with tarfile.open(archive, 'w:gz') as bundle:
            bundle.add(package, arcname=package.name)
        archive.with_name(archive.name + '.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')

    def test_bad_hash_and_failed_activation_preserve_previous_runtime(self):
        new = self.package('0.10.1')
        archive = new.parent.parent / (new.name + '.tar.gz')
        original = archive.read_bytes()
        archive.write_bytes(original + b'tampered')
        self.assertEqual(self.update(new.parent.parent, success=False)['status'], 'error')
        self.assertEqual((self.prefix / 'state/runtime/current').resolve(), self.previous)
        entry = new / 'runtime/scripts/wiki.mjs'
        entry.write_text(entry.read_text().replace('try{\n const {values', "try{\n if(process.argv.includes('--help'))throw Error('synthetic activation failure');\n const {values"))
        self.rewrite_archive(new)
        self.assertEqual(self.update(new.parent.parent, success=False)['status'], 'error')
        self.assertEqual((self.prefix / 'state/runtime/current').resolve(), self.previous)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_runtime_commands_cannot_enter_during_activation(self):
        with (self.prefix / 'state/runtime/use.lock').open('a') as activation:
            fcntl.flock(activation, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run([str(self.prefix / 'bin/personal-wiki'), 'convert', '--text', '等待升级完成。'], capture_output=True, text=True, env=self.env, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Runtime busy', result.stderr)
        self.assertFalse((self.prefix / 'state/ingestion/jobs').exists())

    def test_interrupted_activation_is_recovered_before_the_next_check(self):
        new = self.package('0.10.1')
        self.assertEqual(self.update(new.parent.parent)['status'], 'updated')
        current = (self.prefix / 'state/runtime/current').resolve()
        journal = self.prefix / 'state/runtime/activation.json'
        journal.write_text(json.dumps({'phase': 'activating', 'previous': str(self.previous), 'next': str(current)}))
        self.assertEqual(self.update(self.old.parent.parent)['status'], 'up_to_date')
        self.assertEqual((self.prefix / 'state/runtime/current').resolve(), self.previous)

if __name__ == '__main__':
    unittest.main()
