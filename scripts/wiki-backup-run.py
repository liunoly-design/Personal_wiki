#!/usr/bin/env python3
"""Three-day backup runner. Durable receipts; no shell or credential logging."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import stat
import tempfile
import io
import json
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
from uuid import uuid4

BACKUP = Path(__file__).with_name('wiki-backup.py').absolute()
STORE = runpy.run_path(str(BACKUP))
Root = STORE['Root']
encode = STORE['encode']
PERIOD = 3 * 24 * 60 * 60


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp timezone required')
    return parsed.timestamp()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def read(root, path):
    try:
        with root.file(path) as stream:
            return json.load(stream)
    except FileNotFoundError:
        return None


def save(root, path, value):
    # Only dedicated schedule/run receipts are mutable, never Vault files.
    if path != 'schedule.json' and not re.fullmatch(r'runs/[a-zA-Z0-9_-]{1,100}\.json', path):
        raise ValueError('Invalid receipt path')
    temp = '.receipt-' + uuid4().hex
    root.write(temp, io.BytesIO(encode(value)))
    with root.parent(path, True) as (fd, name):
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not __import__('stat').S_ISREG(info.st_mode):
                raise ValueError('Receipt symlink or special file refused')
        except FileNotFoundError:
            pass
        os.replace(temp, name, src_dir_fd=root.fd, dst_dir_fd=fd)
        os.fsync(root.fd)
        os.fsync(fd)


def settings_file(path):
    path = Path(path).absolute()
    with STORE['opened'](path.parent) as root:
        value = read(root, path.name)
    if not isinstance(value, dict):
        raise ValueError('Settings unavailable')
    for field in ['vault', 'repository', 'python', 'node', 'stateDir', 'hostConfig']:
        if not Path(value.get(field, '')).is_absolute():
            raise ValueError('Absolute settings paths required')
    timestamp(value['firstDueAt'])
    source, state = Path(value['vault']).resolve(), Path(value['stateDir']).resolve()
    if source == state or source in state.parents or state in source.parents:
        raise ValueError('State and Vault must be separate')
    if not value.get('ssh'):
        repository = Path(value['repository']).resolve()
        if repository == state or repository in state.parents or state in repository.parents:
            raise ValueError('State and repository must be separate')
    return value


class ProcessFailure(ValueError):
    """Safe classification only; never retain child error bodies."""


def failure_category(result):
    cause = str(result.get('cause', '')).lower()
    for tokens, label in [
        (['temporarily unavailable', 'lock'], '资料或备份正在写入，未取得备份锁'),
        (['source changed'], '备份期间原件发生变化，一致性检查未通过'),
        (['no space', 'disk full'], '备份磁盘空间不足'),
        (['hash', 'corrupt', 'missing', 'unexpected', 'differs'], '备份完整性校验未通过'),
        (['symlink', 'unsafe', 'not a directory', 'too many levels'], '备份路径安全检查未通过'),
    ]:
        if any(token in cause for token in tokens):
            return label
    return '备份未完成；连接、认证或远端状态待核实'


def execute(command, payload=None):
    # Spool child output instead of retaining unbounded output in memory.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                                   stdout=output, stderr=errors, start_new_session=True)
        try:
            process.communicate(encode(payload) if payload is not None else None,
                                timeout=40 if payload is not None else 1800)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise ValueError('Process result requires readback') from None
        output.seek(0)
        data = output.read(131073)
        if len(data) > 131072:
            raise ValueError('Invalid process receipt')
        try:
            result = json.loads(data)
        except ValueError:
            raise ValueError('Process returned no valid receipt') from None
        if not isinstance(result, dict):
            raise ValueError('Process failed or result unknown')
        if process.returncode:
            raise ProcessFailure(failure_category(result))
        return result


def backup_command(settings, action, snapshot=None):
    command = [settings['python'], str(BACKUP), action, '--repository', settings['repository']]
    if action == 'backup':
        command += ['--vault', settings['vault']]
    else:
        command += ['--snapshot', snapshot]
    for field, flag in [('ssh', '--ssh'), ('identity', '--identity'), ('remotePython', '--remote-python')]:
        if settings.get(field):
            command += [flag, settings[field]]
    return command


def valid_receipt(receipt, statuses):
    if receipt.get('status') not in statuses or receipt.get('scope') != 'vault-only' or not re.fullmatch('[a-f0-9]{64}', receipt.get('snapshot', '')):
        raise ValueError('Invalid backup receipt')
    if any(type(receipt.get(key)) is not int or receipt[key] < 0 for key in ['files', 'bytes']):
        raise ValueError('Invalid backup counts')


def advance(schedule, now):
    result = dict(schedule)
    due = timestamp(result['nextDueAt'])
    if now >= due:
        result['nextDueAt'] = iso(due + (int((now - due) // PERIOD) + 1) * PERIOD)
    return result


def notification_payload(settings, request):
    path = Path(settings['hostConfig'])
    with STORE['opened'](path.parent) as root:
        host = read(root, path.name)
    def object_field(value, key):
        if not isinstance(value, dict) or not isinstance(value.get(key, {}), dict):
            raise ValueError('Notification configuration unavailable')
        return value.get(key, {})
    wiki = object_field(object_field(object_field(host, 'plugins'), 'entries'), 'personal-wiki')
    config = object_field(wiki, 'config')
    channel = object_field(object_field(host, 'channels'), 'feishu')
    selected = settings['notify']['accountId']
    account = object_field(channel, 'accounts').get(selected)
    if account is None and selected == 'default':
        account = {key: value for key, value in channel.items() if key != 'accounts'}
    narrowed = {'plugins': {'entries': {'personal-wiki': {
        'enabled': wiki.get('enabled'), 'config': {key: config.get(key) for key in
        ['accountId', 'allowedSenderIds', 'allowedConversationIds']}}}},
        'channels': {'feishu': {'enabled': channel.get('enabled'), 'domain': channel.get('domain'),
                               'accounts': {selected: account} if account is not None else {}}}}
    return {**request, 'scope': settings['notify'], 'hostConfig': narrowed}


def alert(root, record_path, record, settings, args):
    notification = record.get('notification')
    if notification is None:
        last = record['scheduleBefore'].get('lastSuccess')
        last_at = last['at'] if last else '尚无成功备份'
        text = ('【Personal-Wiki 备份告警测试】实际备份未受影响。' if args.test_alert else
                '【Personal-Wiki 备份失败】原始资料和已有快照保留。')
        text += '\n时间：' + record['startedAt'] + '\n原因：' + record['cause']
        text += '\n最后成功：' + last_at + '\n请检查来源 Mac、局域网和 Mac mini，然后查看备份状态。'
        notification = {'uuid': hashlib.sha256(record['runId'].encode()).hexdigest()[:32],
                        'text': text, 'status': 'intent'}
        record['notification'] = notification
        save(root, record_path, record)  # Intent is durable before sending.
        try:
            sent = execute([settings['node'], str(BACKUP.with_name('wiki-backup-notify.mjs'))],
                           notification_payload(settings, {'action': 'send', **notification}))
            if sent.get('status') != 'sent' or not re.fullmatch(r'om_[\w-]+', sent.get('messageId', '')):
                raise ValueError('Invalid send receipt')
            notification.update(messageId=sent['messageId'], status='sent')
            save(root, record_path, record)
        except (ValueError, OSError):
            notification['status'] = 'unknown'
            save(root, record_path, record)
            return 'unknown'
    if notification.get('status') == 'verified':
        return 'verified'
    if not notification.get('messageId'):
        return 'unknown'  # Never resend an intent whose outcome is unknown.
    try:
        verified = execute([settings['node'], str(BACKUP.with_name('wiki-backup-notify.mjs'))],
                           notification_payload(settings, {'action': 'verify', **notification}))
        if verified.get('status') != 'verified' or verified.get('messageId') != notification['messageId']:
            raise ValueError('Notification readback differs')
        notification['status'] = 'verified'
    except (ValueError, OSError):
        notification['status'] = 'readback_pending'
    save(root, record_path, record)
    return notification['status']


def finish(root, record_path, record, schedule, output):
    record.update(phase='complete', result=output, scheduleAfter=schedule)
    save(root, record_path, record)
    save(root, 'schedule.json', schedule)
    return output


def runner(settings, args):
    path = Path(settings['stateDir'])
    with STORE['opened'](path.parent) as parent:
        parent.mkdir(path.name)
    with STORE['opened'](path) as root:
        with root.parent('.run.lock') as (fd, name):
            lease = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(lease).st_mode):
                raise ValueError('Invalid runner lock')
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            identity = {key: settings.get(key) for key in ['vault', 'repository', 'ssh', 'identity', 'remotePython', 'hostConfig', 'notify']}
            previous = read(root, 'identity.json')
            if previous is None:
                root.write('identity.json', io.BytesIO(encode(identity)))
            elif previous != identity:
                raise ValueError('Backup settings changed; use a separate state directory after review')
            schedule = read(root, 'schedule.json') or {'nextDueAt': settings['firstDueAt'], 'lastSuccess': settings.get('initialLastSuccess')}
            if args.command == 'status':
                return {'status': 'ready', **schedule}
            if args.test_alert and not args.run_id:
                raise ValueError('Alert test requires an explicit run ID')
            now = datetime.now(timezone.utc).timestamp()
            run_id = args.run_id or 'due-' + str(int(timestamp(schedule['nextDueAt'])))
            if not re.fullmatch('[a-zA-Z0-9_-]{1,100}', run_id):
                raise ValueError('Invalid run ID')
            record_path = 'runs/' + run_id + '.json'
            record = read(root, record_path)
            if record and bool(record.get('testAlert')) != args.test_alert:
                raise ValueError('Run ID belongs to another operation')
            if record and record.get('result'):
                if schedule == record['scheduleBefore']:
                    save(root, 'schedule.json', record['scheduleAfter'])
                if record.get('notification', {}).get('status') == 'readback_pending':
                    record['result']['alert'] = alert(root, record_path, record, settings, args)
                    save(root, record_path, record)
                return record['result']
            if record is None and now < timestamp(schedule['nextDueAt']) and not args.force and not args.test_alert:
                return {'status': 'not_due', **schedule}
            if record is not None:
                # A recovered old run must never regress the current schedule or last success.
                record['scheduleBefore'] = schedule
            fresh = record is None
            record = record or {'runId': run_id, 'startedAt': iso(now), 'phase': 'started',
                                'scheduleBefore': schedule, 'testAlert': args.test_alert}
            save(root, record_path, record)
            try:
                if args.test_alert:
                    raise ValueError('Explicit notification test')
                if not record.get('backup'):
                    if not fresh:
                        raise ValueError('Interrupted backup requires manual readback')
                    result = execute(backup_command(settings, 'backup'))
                    valid_receipt(result, ['committed', 'existing'])
                    record.update(phase='backup_complete', backup=result)
                    save(root, record_path, record)
                result = record['backup']
                verified = execute(backup_command(settings, 'verify', result['snapshot']))
                valid_receipt(verified, ['verified'])
                if any(verified[key] != result[key] for key in ['snapshot', 'files', 'bytes']):
                    raise ValueError('Verification receipt differs from backup')
                record['successAt'] = iso(datetime.now(timezone.utc).timestamp())
                planned = advance(record['scheduleBefore'], datetime.now(timezone.utc).timestamp())
                planned['lastSuccess'] = {'at': record['successAt'], **{key: verified[key] for key in ['snapshot', 'files', 'bytes']}}
                output = {'status': 'succeeded', **planned, 'runId': run_id}
                return finish(root, record_path, record, planned, output)
            except (ValueError, OSError, KeyError, TypeError) as error:
                record.setdefault('cause', str(error) if isinstance(error, ProcessFailure) else '通知链路验收测试' if args.test_alert else
                                  ('备份校验未通过或结果待核实' if record.get('backup') else '备份未完成；连接、原件一致性或远端状态待核实'))
                record['phase'] = 'failed'
                save(root, record_path, record)
                alert_status = alert(root, record_path, record, settings, args)
                planned = record['scheduleBefore'] if args.test_alert else advance(record['scheduleBefore'], datetime.now(timezone.utc).timestamp())
                output = {'status': 'alert_test' if args.test_alert else 'failed', **planned,
                          'runId': run_id, 'cause': record['cause'], 'alert': alert_status}
                if not args.test_alert:
                    planned['lastFailure'] = {'at': record['startedAt'], 'runId': run_id, 'cause': record['cause'], 'alert': alert_status}
                    output['lastFailure'] = planned['lastFailure']
                return finish(root, record_path, record, planned, output)
        finally:
            os.close(lease)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'status'])
    parser.add_argument('--settings', required=True)
    parser.add_argument('--run-id')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--test-alert', action='store_true')
    args = parser.parse_args()
    return runner(settings_file(args.settings), args)


if __name__ == '__main__':
    try:
        result = main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        result = {'status': 'failed', 'cause': 'Backup runner failed; original data and receipts retained'}
    print(json.dumps(result, ensure_ascii=False))
    if result['status'] == 'failed' or (result['status'] == 'alert_test' and result['alert'] != 'verified'):
        raise SystemExit(1)
