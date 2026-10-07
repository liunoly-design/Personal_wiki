"""LAN backup acceptance through the public CLI, using synthetic Vaults."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'scripts/wiki-backup.py'


class BackupAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS's /var is itself a system symlink; pass its explicit real path.
        self.base = Path(self.temp.name).resolve()
        self.vault = self.base / 'vault'
        (self.vault / 'raw/空目录').mkdir(parents=True)
        (self.vault / '.personal-wiki/history').mkdir(parents=True)
        (self.vault / 'raw/原件.txt').write_text('原文，不可覆盖\n')
        (self.vault / '.personal-wiki/history/before.md').write_text('旧知识\n')
        self.repo = self.base / 'backup'
        self.repo.mkdir()

    def cli(self, *args, ok=True):
        run = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True, timeout=20)
        if ok:
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        else:
            self.assertNotEqual(run.returncode, 0)
        return json.loads(run.stdout)

    def backup(self):
        return self.cli('backup', '--vault', self.vault, '--repository', self.repo)

    def test_complete_backup_verifies_and_restores_originals_and_hidden_history(self):
        receipt = self.backup()
        self.assertEqual(receipt['status'], 'committed')
        snapshot = receipt['snapshot']
        self.assertEqual(self.cli('verify', '--repository', self.repo, '--snapshot', snapshot)['files'], 2)
        restored = self.base / 'isolated-restore'
        self.cli('restore', '--repository', self.repo, '--snapshot', snapshot, '--destination', restored)
        self.assertEqual((restored / 'raw/原件.txt').read_text(), '原文，不可覆盖\n')
        self.assertEqual((restored / '.personal-wiki/history/before.md').read_text(), '旧知识\n')
        self.assertTrue((restored / 'raw/空目录').is_dir())
        self.assertEqual((self.vault / 'raw/原件.txt').read_text(), '原文，不可覆盖\n')

    def test_repeat_delivery_reuses_snapshot_and_changes_create_a_new_one(self):
        first = self.backup()
        second = self.backup()
        self.assertEqual(second['status'], 'existing')
        self.assertEqual(second['snapshot'], first['snapshot'])
        (self.vault / 'raw/原件.txt').write_text('新增版本\n')
        third = self.backup()
        self.assertNotEqual(third['snapshot'], first['snapshot'])
        listed = self.cli('list', '--repository', self.repo)['snapshots']
        self.assertEqual(set(listed), {first['snapshot'], third['snapshot']})
        restored = self.base / 'old-version'
        self.cli('restore', '--repository', self.repo, '--snapshot', first['snapshot'], '--destination', restored)
        self.assertEqual((restored / 'raw/原件.txt').read_text(), '原文，不可覆盖\n')

    def test_corrupt_snapshot_is_rejected_and_never_repaired_by_overwriting_it(self):
        snapshot = self.backup()['snapshot']
        corrupt = self.repo / 'snapshots' / snapshot / 'data/raw/原件.txt'
        corrupt.write_text('损坏\n')
        self.cli('verify', '--repository', self.repo, '--snapshot', snapshot, ok=False)
        self.cli('restore', '--repository', self.repo, '--snapshot', snapshot, '--destination', self.base / 'bad-restore', ok=False)
        self.cli('backup', '--repository', self.repo, '--vault', self.vault, ok=False)
        self.assertEqual(corrupt.read_text(), '损坏\n')
        self.assertFalse((self.base / 'bad-restore').exists())

    def test_missing_payload_in_pending_snapshot_can_resume(self):
        snapshot = self.backup()['snapshot']
        pending = self.repo / 'pending' / snapshot
        (self.repo / 'snapshots' / snapshot).rename(pending)
        (pending / 'data/raw/原件.txt').unlink()
        resumed = self.backup()
        self.assertEqual(resumed['snapshot'], snapshot)
        self.assertEqual(resumed['status'], 'committed')
        self.assertFalse(pending.exists())

    def test_existing_restore_destination_is_preserved(self):
        snapshot = self.backup()['snapshot']
        self.cli('restore', '--repository', self.repo, '--snapshot', snapshot, '--destination', self.vault, ok=False)
        self.assertEqual((self.vault / 'raw/原件.txt').read_text(), '原文，不可覆盖\n')

    def test_symlink_source_and_repository_escape_are_refused(self):
        outside = self.base / 'private.txt'
        outside.write_text('不得读取')
        (self.vault / 'raw/link').symlink_to(outside)
        self.cli('backup', '--repository', self.repo, '--vault', self.vault, ok=False)
        self.assertEqual(self.cli('list', '--repository', self.repo)['snapshots'], [])
        (self.vault / 'raw/link').unlink()
        (self.repo / 'pending').rmdir()
        (self.repo / 'pending').symlink_to(self.base)
        self.cli('backup', '--repository', self.repo, '--vault', self.vault, ok=False)
        self.assertEqual(outside.read_text(), '不得读取')

    def test_vault_and_repository_cannot_overlap(self):
        nested = self.vault / 'backup'
        nested.mkdir()
        self.cli('backup', '--repository', nested, '--vault', self.vault, ok=False)

    def test_busy_protected_writer_is_reported_without_committing(self):
        import fcntl
        lock = self.vault / '.personal-wiki/protected.lock'
        with lock.open('w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.cli('backup', '--repository', self.repo, '--vault', self.vault, ok=False)
        self.assertEqual(self.cli('list', '--repository', self.repo)['snapshots'], [])

    def test_ssh_transport_uses_batch_auth_and_restores_through_same_protocol(self):
        # An SSH executable boundary fixture executes the actual remote program
        # on this machine; this is protocol acceptance, not LAN authentication.
        import os
        bin_dir = self.base / 'bin'
        bin_dir.mkdir()
        ssh = bin_dir / 'ssh'
        ssh.write_text('#!' + sys.executable + '\nimport os,sys\na=sys.argv[1:]\nassert "BatchMode=yes" in a and "StrictHostKeyChecking=yes" in a\nassert a[-2] == "mac@mini-test"\nos.execl("/bin/sh", "sh", "-c", a[-1])\n')
        ssh.chmod(0o700)
        old = os.environ.get('PATH', '')
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old
        self.addCleanup(os.environ.__setitem__, 'PATH', old)
        result = self.cli('backup', '--vault', self.vault, '--repository', self.repo, '--ssh', 'mac@mini-test')
        self.cli('verify', '--repository', self.repo, '--snapshot', result['snapshot'], '--ssh', 'mac@mini-test')
        destination = self.base / 'ssh-restored'
        self.cli('restore', '--repository', self.repo, '--snapshot', result['snapshot'], '--destination', destination, '--ssh', 'mac@mini-test')
        self.assertEqual((destination / 'raw/原件.txt').read_text(), '原文，不可覆盖\n')

    def test_untracked_snapshot_payload_and_restore_into_repository_are_refused(self):
        snapshot = self.backup()['snapshot']
        data = self.repo / 'snapshots' / snapshot / 'data'
        self.cli('restore', '--repository', self.repo, '--snapshot', snapshot, '--destination', self.repo / 'unsafe-restore', ok=False)
        (data / 'unexpected.txt').write_text('未列入清单')
        self.cli('verify', '--repository', self.repo, '--snapshot', snapshot, ok=False)

    def test_partial_stream_preserves_completed_files_and_resumes(self):
        import io
        import tarfile
        snapshot = self.backup()['snapshot']
        pending = self.repo / 'pending' / snapshot
        (self.repo / 'snapshots' / snapshot).rename(pending)
        for path in ['raw/原件.txt', '.personal-wiki/history/before.md']:
            (pending / 'data' / path).unlink()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as stream:
            body = '旧知识\n'.encode()
            item = tarfile.TarInfo('.personal-wiki/history/before.md')
            item.size = len(body)
            stream.addfile(item, io.BytesIO(body))
        request = json.dumps({'method': 'receive', 'repository': str(self.repo), 'snapshot': snapshot}).encode() + b'\n'
        run = subprocess.run([sys.executable, str(CLI), '--serve'], input=request + archive.getvalue(), capture_output=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual((pending / 'data/.personal-wiki/history/before.md').read_text(), '旧知识\n')
        self.assertEqual(self.backup()['snapshot'], snapshot)

    def test_manifest_path_escape_never_writes_outside_repository(self):
        import hashlib
        manifest = {'version': 1, 'scope': 'vault-only', 'entries': [{'path': '../escape', 'kind': 'directory'}]}
        identity = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        request = {'method': 'prepare', 'repository': str(self.repo), 'snapshot': identity, 'manifest': manifest}
        run = subprocess.run([sys.executable, str(CLI), '--serve'], input=json.dumps(request).encode() + b'\n', capture_output=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.base / 'escape').exists())

    def test_source_change_during_transfer_cannot_commit(self):
        import os
        bin_dir = self.base / 'change-bin'
        bin_dir.mkdir()
        ssh = bin_dir / 'ssh'
        ssh.write_text('#!' + sys.executable + '\nimport json,sys,subprocess\nfrom pathlib import Path\ndata=sys.stdin.buffer.read()\nr=json.loads(data.split(b"\\n",1)[0])\np=subprocess.run(["/bin/sh","-c",sys.argv[-1]],input=data,capture_output=True)\nif r["method"]=="prepare":\n    Path(' + repr(str(self.vault / 'created-during-backup')) + ').mkdir(exist_ok=True)\nsys.stdout.buffer.write(p.stdout)\nsys.stderr.buffer.write(p.stderr)\nsys.exit(p.returncode)\n')
        ssh.chmod(0o700)
        old = os.environ.get('PATH', '')
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old
        self.addCleanup(os.environ.__setitem__, 'PATH', old)
        failed = self.cli('backup', '--vault', self.vault, '--repository', self.repo, '--ssh', 'mac@mini-test', ok=False)
        self.assertIn('Source changed', failed['cause'])
        self.assertEqual(self.cli('list', '--repository', self.repo)['snapshots'], [])
        self.assertTrue(any((self.repo / 'pending').iterdir()))
        self.assertEqual((self.vault / 'raw/原件.txt').read_text(), '原文，不可覆盖\n')

    def test_symlink_ancestor_cannot_redirect_source_or_target(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.base, target_is_directory=True)
        self.cli('backup', '--vault', alias / 'vault', '--repository', self.repo, ok=False)
        self.cli('backup', '--vault', self.vault, '--repository', alias / 'backup', ok=False)
        snapshot = self.backup()['snapshot']
        self.cli('restore', '--repository', self.repo, '--snapshot', snapshot, '--destination', alias / 'restore', ok=False)
        self.assertFalse((self.base / 'restore').exists())

    def test_ssh_diagnostic_backpressure_cannot_stall_large_transfers(self):
        import os
        bin_dir = self.base / 'noisy-bin'
        bin_dir.mkdir()
        ssh = bin_dir / 'ssh'
        ssh.write_text('#!' + sys.executable + '\nimport os,sys\nos.write(2,b"diagnostic\\n"*40000)\nos.execl("/bin/sh","sh","-c",sys.argv[-1])\n')
        ssh.chmod(0o700)
        old = os.environ.get('PATH', '')
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old
        self.addCleanup(os.environ.__setitem__, 'PATH', old)
        (self.vault / 'raw/large.bin').write_bytes(b'large synthetic data\n' * 60000)
        result = self.cli('backup', '--vault', self.vault, '--repository', self.repo, '--ssh', 'mac@mini-test')
        destination = self.base / 'noisy-restored'
        self.cli('restore', '--repository', self.repo, '--snapshot', result['snapshot'], '--destination', destination, '--ssh', 'mac@mini-test')
        self.assertEqual((destination / 'raw/large.bin').stat().st_size, 1260000)

    def test_selected_identity_and_remote_python_are_used_for_backup_and_restore(self):
        import os
        bin_dir = self.base / 'selected-bin'
        bin_dir.mkdir()
        identity = self.base / 'synthetic-key'
        identity.write_text('Synthetic system-boundary fixture; never a real key')
        interpreter = self.base / 'remote python'
        interpreter.write_text('#!' + sys.executable + '\nimport os,sys\nos.execv(' + repr(sys.executable) + ',[' + repr(sys.executable) + ']+sys.argv[1:])\n')
        interpreter.chmod(0o700)
        ssh = bin_dir / 'ssh'
        ssh.write_text('#!' + sys.executable + '\nimport os,sys\na=sys.argv[1:]\nassert a[a.index("-i")+1] == ' + repr(str(identity)) + '\nassert "IdentitiesOnly=yes" in a\nos.execl("/bin/sh","sh","-c",a[-1])\n')
        ssh.chmod(0o700)
        old = os.environ.get('PATH', '')
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old
        self.addCleanup(os.environ.__setitem__, 'PATH', old)
        flags = ['--repository', self.repo, '--ssh', 'mac@mini-test', '--identity', identity, '--remote-python', interpreter]
        result = self.cli('backup', '--vault', self.vault, *flags)
        self.cli('verify', '--snapshot', result['snapshot'], *flags)
        destination = self.base / 'selected-restored'
        self.cli('restore', '--snapshot', result['snapshot'], '--destination', destination, *flags)
        self.assertEqual((destination / 'raw/原件.txt').read_text(), '原文，不可覆盖\n')


if __name__ == '__main__':
    unittest.main()
