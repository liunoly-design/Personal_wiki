"""Scheduled runner acceptance: real synthetic backup, external notification fixture."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'scripts/wiki-backup-run.py'


class PeriodicBackupAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.vault = self.base / 'vault'
        self.vault.mkdir()
        (self.vault / 'original.txt').write_text('Original data stays unchanged\n')
        self.repository = self.base / 'repository'
        self.repository.mkdir()
        self.alerts = self.base / 'alerts.jsonl'
        self.node = self.base / 'notification-fixture'
        self.node.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\nr=json.load(sys.stdin)\np=Path(' + repr(str(self.alerts)) + ')\nwith p.open("a") as f: f.write(json.dumps(r)+"\\n")\nprint(json.dumps({"status":"sent" if r["action"]=="send" else "verified","messageId":"om_fixture"}))\n')
        self.node.chmod(0o700)
        self.settings = {'vault': str(self.vault), 'repository': str(self.repository), 'python': sys.executable,
                         'node': str(self.node), 'hostConfig': str(self.base / 'host.json'),
                         'stateDir': str(self.base / 'state'), 'firstDueAt': '2020-01-01T00:00:00Z',
                         'notify': {'accountId': 'default', 'senderId': 'ou_user', 'chatId': 'oc_private'}}
        (self.base / 'host.json').write_text('{}')
        self.config = self.base / 'settings.json'

    def run_cli(self, *args):
        self.config.write_text(json.dumps(self.settings))
        result = subprocess.run([sys.executable, str(CLI), *args, '--settings', str(self.config)], capture_output=True, text=True, timeout=20)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_success_is_verified_silent_and_replay_does_not_repeat(self):
        code, result = self.run_cli('run', '--run-id', 'acceptance-success')
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['lastSuccess']['files'], 1)
        self.assertFalse(self.alerts.exists())
        code, repeated = self.run_cli('run', '--run-id', 'acceptance-success')
        self.assertEqual(repeated['lastSuccess'], result['lastSuccess'])
        self.assertEqual((self.vault / 'original.txt').read_text(), 'Original data stays unchanged\n')

    def test_failure_preserves_last_success_and_alert_is_read_back_once(self):
        _, good = self.run_cli('run', '--run-id', 'good')
        (self.repository / 'snapshots' / good['lastSuccess']['snapshot'] / 'data/original.txt').write_text('corrupt')
        code, failed = self.run_cli('run', '--force', '--run-id', 'bad')
        self.assertEqual(code, 1)
        self.assertEqual(failed['lastSuccess'], good['lastSuccess'])
        self.assertEqual(failed['alert'], 'verified')
        self.assertIn('完整性', failed['cause'])
        calls = [json.loads(line) for line in self.alerts.read_text().splitlines()]
        self.assertEqual([call['action'] for call in calls], ['send', 'verify'])
        self.assertIn('最后成功', calls[0]['text'])
        self.run_cli('run', '--force', '--run-id', 'bad')
        self.assertEqual(len(self.alerts.read_text().splitlines()), 2)
        self.assertEqual((self.vault / 'original.txt').read_text(), 'Original data stays unchanged\n')

    def test_unknown_send_is_retained_without_resending_and_test_leaves_schedule(self):
        _, good = self.run_cli('run', '--run-id', 'good')
        self.node.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\nr=json.load(sys.stdin)\np=Path(' + repr(str(self.alerts)) + ')\nwith p.open("a") as f: f.write(json.dumps(r)+"\\n")\nprint("{}")\nsys.exit(1)\n')
        code, result = self.run_cli('run', '--test-alert', '--run-id', 'drill')
        self.assertEqual(code, 1)
        self.assertEqual(result['alert'], 'unknown')
        self.assertEqual(result['lastSuccess'], good['lastSuccess'])
        self.assertEqual(result['nextDueAt'], good['nextDueAt'])
        self.run_cli('run', '--test-alert', '--run-id', 'drill')
        self.assertEqual(len(self.alerts.read_text().splitlines()), 1)
        self.assertIn('告警测试', json.loads(self.alerts.read_text().strip())['text'])

    def test_known_message_recovery_only_reads_back(self):
        self.node.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\nr=json.load(sys.stdin)\np=Path(' + repr(str(self.alerts)) + ')\nwith p.open("a") as f: f.write(json.dumps(r)+"\\n")\nprint(json.dumps({"status":"sent" if r["action"]=="send" else "failed","messageId":"om_fixture"}))\nsys.exit(0 if r["action"]=="send" else 1)\n')
        _, result = self.run_cli('run', '--test-alert', '--run-id', 'readback')
        self.assertEqual(result['alert'], 'readback_pending')
        self.node.write_text('#!' + sys.executable + '\nimport json,sys\nfrom pathlib import Path\nr=json.load(sys.stdin)\np=Path(' + repr(str(self.alerts)) + ')\nwith p.open("a") as f: f.write(json.dumps(r)+"\\n")\nprint(json.dumps({"status":"verified","messageId":"om_fixture"}))\n')
        code, recovered = self.run_cli('run', '--test-alert', '--run-id', 'readback')
        self.assertEqual(code, 0)
        self.assertEqual(recovered['alert'], 'verified')
        self.assertEqual([json.loads(line)['action'] for line in self.alerts.read_text().splitlines()], ['send', 'verify', 'verify'])

    def test_interrupted_attempt_does_not_replay_backup(self):
        _, baseline = self.run_cli('status')
        state = self.base / 'state'
        (state / 'runs').mkdir()
        record = {'runId':'interrupted','startedAt':'2020-01-01T00:00:00Z','phase':'started','testAlert':False,
                  'scheduleBefore':{'nextDueAt':baseline['nextDueAt'],'lastSuccess':baseline['lastSuccess']}}
        (state / 'runs/interrupted.json').write_text(json.dumps(record))
        code, result = self.run_cli('run', '--run-id', 'interrupted')
        self.assertEqual(code, 1)
        self.assertEqual(result['alert'], 'verified')
        self.assertFalse((self.repository / 'snapshots').exists())
        _, next_attempt = self.run_cli('run')
        self.assertEqual(next_attempt['status'], 'not_due')

    def test_stale_interrupted_run_cannot_regress_a_newer_success(self):
        _, baseline = self.run_cli('status')
        state = self.base / 'state'
        (state / 'runs').mkdir()
        (state / 'runs/stale.json').write_text(json.dumps({'runId':'stale','startedAt':'2020-01-01T00:00:00Z',
          'phase':'started','testAlert':False,'scheduleBefore':{'nextDueAt':baseline['nextDueAt'],'lastSuccess':None}}))
        _, success = self.run_cli('run', '--run-id', 'newer')
        _, failed = self.run_cli('run', '--run-id', 'stale')
        self.assertEqual(failed['lastSuccess'], success['lastSuccess'])
        _, current = self.run_cli('status')
        self.assertEqual(current['lastSuccess'], success['lastSuccess'])
        self.assertEqual(current['nextDueAt'], success['nextDueAt'])
        self.assertIn(success['lastSuccess']['at'], json.loads(self.alerts.read_text().splitlines()[0])['text'])

    def test_verified_old_run_records_current_verification_time(self):
        from datetime import datetime
        _, success = self.run_cli('run', '--run-id', 'new-success')
        state = self.base / 'state'
        record = json.loads((state / 'runs/new-success.json').read_text())
        record = {key: value for key, value in record.items() if key not in ['result', 'scheduleAfter']}
        record.update(runId='old-verified', phase='backup_complete', successAt='2020-01-01T00:00:00Z')
        (state / 'runs/old-verified.json').write_text(json.dumps(record))
        _, recovered = self.run_cli('run', '--run-id', 'old-verified')
        self.assertEqual(recovered['status'], 'succeeded')
        self.assertGreaterEqual(datetime.fromisoformat(recovered['lastSuccess']['at'].replace('Z','+00:00')), datetime.fromisoformat(success['lastSuccess']['at']))

    def test_missing_or_malformed_host_returns_durable_unknown_receipt(self):
        host = self.base / 'host.json'
        for run_id, content in [('missing', None), ('malformed', '{"plugins":[]}')]:
            if content is None:
                host.unlink()
            else:
                host.write_text(content)
            code, result = self.run_cli('run', '--test-alert', '--run-id', run_id)
            self.assertEqual(code, 1)
            self.assertEqual(result['alert'], 'unknown')
            record = json.loads((self.base / ('state/runs/' + run_id + '.json')).read_text())
            self.assertEqual(record['notification']['status'], 'unknown')
            self.assertFalse(self.alerts.exists())

    def test_notification_host_read_remains_anchored_after_ancestor_swap(self):
        import contextlib
        import runpy
        module = runpy.run_path(str(CLI))
        directory = self.base / 'host-directory'
        directory.mkdir()
        expected = {'channels':{'feishu':{'enabled':True,'accounts':{'default':{'appId':'selected'}}}}}
        (directory / 'host.json').write_text(json.dumps(expected))
        foreign = self.base / 'foreign'
        foreign.mkdir()
        (foreign / 'host.json').write_text('{"channels":{"feishu":{"enabled":false}}}')
        self.settings['hostConfig'] = str(directory / 'host.json')
        original_opened = module['STORE']['opened']
        @contextlib.contextmanager
        def swapped_opened(path):
            with original_opened(path) as root:
                directory.rename(self.base / 'retained-host')
                directory.symlink_to(foreign, target_is_directory=True)
                yield root
        module['STORE']['opened'] = swapped_opened
        try:
            request = module['notification_payload'](self.settings, {'action':'send'})
            self.assertTrue(request['hostConfig']['channels']['feishu']['enabled'])
            self.assertEqual(request['hostConfig']['channels']['feishu']['accounts']['default']['appId'], 'selected')
        finally:
            module['STORE']['opened'] = original_opened

    def test_notification_config_symlink_is_refused_before_external_send(self):
        protected = self.base / 'other-host.json'
        protected.write_text('{"private":"do not follow"}')
        (self.base / 'host.json').unlink()
        (self.base / 'host.json').symlink_to(protected)
        code, result = self.run_cli('run', '--test-alert', '--run-id', 'symlink-host')
        self.assertEqual(code, 1)
        self.assertEqual(result['alert'], 'unknown')
        self.assertFalse(self.alerts.exists())
        self.assertEqual(protected.read_text(), '{"private":"do not follow"}')

    def test_not_due_symlink_and_concurrent_lock_refuse_writes(self):
        import fcntl
        self.settings['firstDueAt'] = '2099-10-10T14:00:00Z'
        _, result = self.run_cli('run')
        self.assertEqual(result['status'], 'not_due')
        self.assertFalse((self.repository / 'snapshots').exists())
        with (self.base / 'state/.run.lock').open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, _ = self.run_cli('run', '--force')
            self.assertEqual(code, 1)
        destination = self.base / 'protected'
        destination.write_text('preserve')
        (self.base / 'state/schedule.json').symlink_to(destination)
        code, _ = self.run_cli('run', '--force')
        self.assertEqual(code, 1)
        self.assertEqual(destination.read_text(), 'preserve')
        self.assertFalse(self.alerts.exists())


if __name__ == '__main__':
    unittest.main()
