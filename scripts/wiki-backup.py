#!/usr/bin/env python3
"""Immutable Vault snapshots. Python standard library; no account credentials."""
import argparse
import contextlib
import ctypes
import errno
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import shlex
import subprocess
import sys
import tarfile
import threading
from uuid import uuid4

CHUNK = 1024 * 1024
LOCK = '.personal-wiki/protected.lock'


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parts(path):
    result = path.split('/')
    if any(p in ('', '.', '..') or '\\' in p or '\0' in p for p in result):
        raise ValueError('Unsafe relative path')
    return result


class Root:
    """Keep every traversal anchored to an open directory, rejecting symlinks."""
    def __init__(self, path):
        absolute = str(Path(path).absolute())
        self.fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in parts(absolute[1:]) if absolute != '/' else []:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
                os.close(self.fd)
                self.fd = child
        except BaseException:
            os.close(self.fd)
            raise

    def close(self):
        os.close(self.fd)

    @contextlib.contextmanager
    def parent(self, path, create=False):
        names = parts(path)
        fd = os.dup(self.fd)
        try:
            for name in names[:-1]:
                if create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            yield fd, names[-1]
        finally:
            os.close(fd)

    def file(self, path):
        with self.parent(path) as (fd, name):
            stream = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        if not stat.S_ISREG(os.fstat(stream).st_mode):
            os.close(stream)
            raise ValueError('Only regular files can be backed up')
        return os.fdopen(stream, 'rb')

    def mkdir(self, path):
        with self.parent(path, True) as (fd, name):
            try:
                os.mkdir(name, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(child)
            os.fsync(fd)

    def write(self, path, stream, expected=None):
        with self.parent(path, True) as (fd, name):
            temp = '.upload-' + uuid4().hex
            h = hashlib.sha256()
            size = 0
            try:
                out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
                with os.fdopen(out, 'wb') as output:
                    while True:
                        block = stream.read(CHUNK)
                        if not block:
                            break
                        size += len(block)
                        h.update(block)
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                if expected and (size != expected['size'] or h.hexdigest() != expected['sha256']):
                    raise ValueError('File hash mismatch')
                rename_exclusive(self, temp, path)
            finally:
                try:
                    os.unlink(temp, dir_fd=self.fd)
                except FileNotFoundError:
                    pass


@contextlib.contextmanager
def opened(path):
    root = Root(path)
    try:
        yield root
    finally:
        root.close()


def fingerprint(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def inventory(root, skip_lock=False):
    result = {}

    def visit(fd, prefix):
        result[prefix] = {'kind': 'directory', 'stamp': fingerprint(os.fstat(fd))}
        with os.scandir(fd) as listing:
            for entry in sorted(listing, key=lambda e: e.name):
                path = prefix + '/' + entry.name if prefix else entry.name
                parts(path)
                if skip_lock and path == LOCK:
                    continue
                info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        if fingerprint(os.fstat(child)) != fingerprint(info):
                            raise ValueError('Source changed while scanning')
                        visit(child, path)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    result[path] = {'kind': 'file', 'stamp': fingerprint(info)}
                else:
                    raise ValueError('Symlink or special file refused')
    visit(root.fd, '')
    return result


def file_hash(root, path):
    h = hashlib.sha256()
    with root.file(path) as stream:
        while True:
            block = stream.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


@contextlib.contextmanager
def protected_writer_lease(root):
    """Do not create state in a Vault merely to back it up."""
    lease = None
    try:
        try:
            with root.parent(LOCK) as (fd, name):
                lease = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:
            pass
        if lease is not None:
            if not stat.S_ISREG(os.fstat(lease).st_mode):
                raise ValueError('Invalid protected writer lock')
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        if lease is not None:
            os.close(lease)


def manifest_for(root, baseline):
    entries = []
    for path, item in sorted(baseline.items()):
        if not path:
            continue
        entry = {'path': path, 'kind': item['kind']}
        if item['kind'] == 'file':
            entry.update(size=item['stamp'][3], sha256=file_hash(root, path))
        entries.append(entry)
    return {'version': 1, 'scope': 'vault-only', 'entries': entries}


def validate_manifest(manifest):
    if manifest.get('version') != 1 or manifest.get('scope') != 'vault-only':
        raise ValueError('Unsupported manifest')
    seen = set()
    for entry in manifest['entries']:
        path = entry['path']
        parts(path)
        if path in seen or entry['kind'] not in ('file', 'directory'):
            raise ValueError('Invalid manifest entry')
        seen.add(path)
        if entry['kind'] == 'file' and (not re.fullmatch('[a-f0-9]{64}', entry['sha256']) or type(entry['size']) is not int or entry['size'] < 0):
            raise ValueError('Invalid file hash or size')
    kinds = {entry['path']: entry['kind'] for entry in manifest['entries']}
    for path in kinds:
        names = parts(path)
        for length in range(1, len(names)):
            if kinds.get('/'.join(names[:length])) != 'directory':
                raise ValueError('Missing parent directory')


def verify_data(root, prefix, manifest, complete=True):
    missing = []
    for entry in manifest['entries']:
        path = prefix + '/' + entry['path']
        if entry['kind'] == 'directory':
            if not complete:
                root.mkdir(path)
            with root.parent(path) as (fd, name):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(child)
            continue
        try:
            with root.file(path) as stream:
                size = os.fstat(stream.fileno()).st_size
            if size != entry['size'] or file_hash(root, path) != entry['sha256']:
                raise ValueError('Snapshot data is corrupt')
        except FileNotFoundError:
            if complete:
                raise ValueError('Snapshot data is missing')
            missing.append(entry)
    with root.parent(prefix) as (fd, name):
        subtree = Root.__new__(Root)
        subtree.fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
    try:
        actual = inventory(subtree)
        expected = {e['path']: e['kind'] for e in manifest['entries']}
        observed = {path: item['kind'] for path, item in actual.items() if path}
        if any(expected.get(path) != kind for path, kind in observed.items()) or (complete and observed != expected):
            raise ValueError('Snapshot has unexpected or missing payload entries')
    finally:
        subtree.close()
    return missing


def rename_exclusive(root, source, destination):
    """Publish a directory without ever replacing an existing destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    with root.parent(source) as (srcfd, src), root.parent(destination) as (dstfd, dst):
        if sys.platform == 'darwin':
            rc = libc.renameatx_np(srcfd, src.encode(), dstfd, dst.encode(), 4)
        elif hasattr(libc, 'renameat2'):
            rc = libc.renameat2(srcfd, src.encode(), dstfd, dst.encode(), 1)
        else:
            raise ValueError('Exclusive directory rename is unavailable')
        if rc:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
        os.fsync(srcfd)
        os.fsync(dstfd)


@contextlib.contextmanager
def repository(path):
    with opened(path) as root:
        with root.parent('.backup.lock') as (fd, name):
            lease = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            root.mkdir('pending')
            root.mkdir('snapshots')
            yield root
        finally:
            os.close(lease)


def load_manifest(root, snapshot, pending=False):
    if not re.fullmatch('[a-f0-9]{64}', snapshot):
        raise ValueError('Invalid snapshot ID')
    prefix = ('pending/' if pending else 'snapshots/') + snapshot
    with root.file(prefix + '/manifest.json') as stream:
        manifest = json.load(stream)
    validate_manifest(manifest)
    if digest(encode(manifest)) != snapshot:
        raise ValueError('Manifest hash mismatch')
    return prefix, manifest


def receipt(snapshot, manifest, status):
    files = [e for e in manifest['entries'] if e['kind'] == 'file']
    return {'status': status, 'snapshot': snapshot, 'scope': 'vault-only', 'files': len(files), 'bytes': sum(e['size'] for e in files)}


def read_payload(root, prefix, manifest, stream):
    expected = {e['path']: e for e in manifest['entries'] if e['kind'] == 'file'}
    seen = set()
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for item in archive:
            if not item.isfile() or item.name not in expected or item.name in seen or item.size != expected[item.name]['size']:
                raise ValueError('Unexpected transfer entry')
            seen.add(item.name)
            path = prefix + '/' + item.name if prefix else item.name
            with archive.extractfile(item) as content:
                root.write(path, content, expected[item.name])
    return seen


def write_payload(root, prefix, entries, stream):
    with tarfile.open(fileobj=stream, mode='w|') as archive:
        for entry in entries:
            if entry['kind'] != 'file':
                continue
            item = tarfile.TarInfo(entry['path'])
            item.size = entry['size']
            path = prefix + '/' + entry['path'] if prefix else entry['path']
            with root.file(path) as content:
                archive.addfile(item, content)


def serve(request, incoming, outgoing):
    """One operation per SSH process; data never becomes remote shell code."""
    method = request['method']
    with repository(request['repository']) as repo:
        if method == 'list':
            with repo.parent('snapshots/placeholder') as (fd, _):
                snapshots = sorted(os.listdir(fd))
            for snapshot in snapshots:
                load_manifest(repo, snapshot)
            return {'status': 'listed', 'snapshots': snapshots}
        snapshot = request['snapshot']
        if method == 'prepare':
            manifest = request['manifest']
            validate_manifest(manifest)
            if digest(encode(manifest)) != snapshot:
                raise ValueError('Manifest hash mismatch')
            try:
                prefix, old = load_manifest(repo, snapshot)
            except FileNotFoundError:
                prefix = 'pending/' + snapshot
                repo.mkdir(prefix)
                try:
                    repo.write(prefix + '/manifest.json', io.BytesIO(encode(manifest)))
                except FileExistsError:
                    load_manifest(repo, snapshot, True)
                repo.mkdir(prefix + '/data')
                missing = verify_data(repo, prefix + '/data', manifest, False)
                return {'status': 'pending', 'missing': missing}
            verify_data(repo, prefix + '/data', old)
            return receipt(snapshot, old, 'existing')
        pending = method in ('receive', 'commit')
        prefix, manifest = load_manifest(repo, snapshot, pending)
        if method == 'receive':
            missing = verify_data(repo, prefix + '/data', manifest, False)
            allowed = {'entries': missing}
            read_payload(repo, prefix + '/data', allowed, incoming)
            verify_data(repo, prefix + '/data', manifest)
            return receipt(snapshot, manifest, 'received')
        verify_data(repo, prefix + '/data', manifest)
        if method == 'commit':
            rename_exclusive(repo, prefix, 'snapshots/' + snapshot)
            return receipt(snapshot, manifest, 'committed')
        if method == 'manifest':
            return {'status': 'verified', 'manifest': manifest}
        if method == 'verify':
            return receipt(snapshot, manifest, 'verified')
        if method == 'export':
            write_payload(repo, prefix + '/data', manifest['entries'], outgoing)
            return None
        raise ValueError('Unsupported repository operation')


class Drain:
    """Continuously consume child output without unbounded diagnostic storage."""
    def __init__(self, stream, limit, tail=False):
        self.stream, self.limit, self.tail = stream, limit, tail
        self.data = bytearray()
        self.overflow = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while True:
                block = self.stream.read1(65536)
                if not block:
                    break
                if self.tail:
                    self.data = (self.data + block)[-self.limit:]
                elif len(self.data) + len(block) <= self.limit:
                    self.data.extend(block)
                else:
                    self.overflow = True
        finally:
            self.stream.close()

    def result(self):
        self.thread.join()
        if self.overflow:
            raise ValueError('Repository response exceeds the 64 MiB metadata limit')
        return bytes(self.data)


def transport_cause(diagnostics, code):
    # Do not echo arbitrary SSH banners/diagnostics which may contain secrets.
    text = diagnostics.decode(errors='replace').lower()
    causes = {'permission denied': 'SSH authentication denied; configure existing key access',
              'host key verification failed': 'SSH host key is unverified; verify Mini identity',
              'could not resolve hostname': 'SSH host name could not be resolved',
              'connection refused': 'SSH connection refused',
              'timed out': 'SSH connection timed out',
              'no route to host': 'SSH host is unreachable',
              'python3: command not found': 'Remote Python 3 is unavailable'}
    return next((message for pattern, message in causes.items() if pattern in text), 'Repository process/connection failed (exit ' + str(code) + ')')


class Endpoint:
    """Same repository protocol for mounted storage and an SSH Python process."""
    def __init__(self, target, ssh=None):
        self.ssh = ssh
        self.target = str(Path(target).absolute()) if not ssh else target
        if not self.target.startswith('/'):
            raise ValueError('Repository must be an absolute path')
        if ssh and not re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9_.@-]*', ssh):
            raise ValueError('Invalid SSH host; use user@host or an SSH alias')
        if ssh:
            code = Path(__file__).read_text()
            self.command = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2',
                            '--', ssh, 'python3 -c ' + shlex.quote(code) + ' --serve']
        else:
            self.command = [sys.executable, str(Path(__file__).absolute()), '--serve']

    def start(self, method, **kwargs):
        process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.diagnostics = Drain(process.stderr, 4096, tail=True)
        process.response = None if method == 'export' else Drain(process.stdout, 64 * 1024 * 1024)
        try:
            process.stdin.write(encode({'method': method, 'repository': self.target, **kwargs}) + b'\n')
            process.stdin.flush()
        except BrokenPipeError:
            self.finish(process)
            raise
        return process

    @staticmethod
    def finish(process):
        export_start_failed = process.response is None
        if export_start_failed:
            # Called only when submitting an export request hit a broken pipe.
            # Drain/discard binary stdout; it is never a JSON response.
            process.response = Drain(process.stdout, 4096, tail=True)
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        process.stdin = None
        process.wait()
        output, errors = process.response.result(), process.diagnostics.result()
        if export_start_failed:
            raise ValueError('Export request could not be submitted: ' + transport_cause(errors, process.returncode))
        if process.returncode:
            try:
                cause = json.loads(output)['cause']
            except (ValueError, KeyError):
                cause = transport_cause(errors, process.returncode)
            raise ValueError(cause)
        return json.loads(output)

    def call(self, method, **kwargs):
        return self.finish(self.start(method, **kwargs))

    def upload(self, root, snapshot, entries):
        process = self.start('receive', snapshot=snapshot)
        try:
            write_payload(root, '', entries, process.stdin)
            return self.finish(process)
        except BrokenPipeError:
            return self.finish(process)
        except BaseException:
            if process.stdin:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                process.stdin = None
            if process.poll() is None:
                process.kill()
            process.wait()
            process.response.result()
            process.diagnostics.result()
            raise

    def download(self, root, snapshot, manifest):
        process = self.start('export', snapshot=snapshot)
        process.stdin.close()
        process.stdin = None
        try:
            seen = read_payload(root, '', manifest, process.stdout)
            while process.stdout.read(CHUNK):
                pass
            if process.wait() or len(seen) != sum(e['kind'] == 'file' for e in manifest['entries']):
                raise ValueError('Restore transfer incomplete: ' + transport_cause(process.diagnostics.result(), process.returncode))
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
            process.wait()
            process.diagnostics.result()


def backup(vault, endpoint):
    source = Path(vault).absolute()
    dest = Path(endpoint.target).absolute()
    resolved_source, resolved_dest = source.resolve(), dest.resolve()
    if not endpoint.ssh and (resolved_source == resolved_dest or resolved_source in resolved_dest.parents or resolved_dest in resolved_source.parents):
        raise ValueError('Vault and repository must be separate')
    with opened(source) as root, protected_writer_lease(root):
        baseline = inventory(root, skip_lock=True)
        manifest = manifest_for(root, baseline)
        if inventory(root, skip_lock=True) != baseline:
            raise ValueError('Source changed; no snapshot committed')
        snapshot = digest(encode(manifest))
        prepared = endpoint.call('prepare', snapshot=snapshot, manifest=manifest)
        if prepared['status'] != 'existing':
            endpoint.upload(root, snapshot, prepared['missing'])
        if inventory(root, skip_lock=True) != baseline:
            raise ValueError('Source changed; no snapshot committed')
        if prepared['status'] == 'existing':
            return prepared
        try:
            return endpoint.call('commit', snapshot=snapshot)
        except ValueError:
            # Lost commit acknowledgement: read back; never blindly replay.
            verified = endpoint.call('verify', snapshot=snapshot)
            return {**verified, 'status': 'committed', 'reconciled': True}


def restore(endpoint, snapshot, destination):
    dest = Path(destination).absolute()
    if not endpoint.ssh:
        repository_path = Path(endpoint.target).resolve()
        restored_path = dest.resolve()
        if restored_path == repository_path or repository_path in restored_path.parents or restored_path in repository_path.parents:
            raise ValueError('Restore destination and repository must be separate')
    if dest.exists() or dest.is_symlink():
        raise ValueError('Restore destination must not exist')
    with opened(dest.parent) as parent:
        manifest = endpoint.call('manifest', snapshot=snapshot)['manifest']
        validate_manifest(manifest)
        if digest(encode(manifest)) != snapshot:
            raise ValueError('Manifest hash mismatch')
        staging = '.wiki-restore-' + uuid4().hex
        parent.mkdir(staging)
        with parent.parent(staging) as (fd, name):
            stagefd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        stage = Root.__new__(Root)
        stage.fd = stagefd
        try:
            for entry in manifest['entries']:
                if entry['kind'] == 'directory':
                    stage.mkdir(entry['path'])
            endpoint.download(stage, snapshot, manifest)
            # Readback every restored file before exposing the finished directory.
            restored = manifest_for(stage, inventory(stage))
            if restored != manifest:
                raise ValueError('Restored contents differ')
        except Exception as error:
            error.restore_staging = str(dest.parent / staging)
            raise
        finally:
            stage.close()
        try:
            rename_exclusive(parent, staging, dest.name)
        except Exception as error:
            error.restore_staging = str(dest.parent / staging)
            raise
        return receipt(snapshot, manifest, 'restored')


def failure_receipt(error):
    cause = str(error)
    lower = cause.lower()
    if isinstance(error, BlockingIOError) or 'temporarily unavailable' in lower:
        next_action = 'Wait for the existing writer/backup to finish, then retry; do not delete lock files.'
    elif 'source changed' in lower:
        next_action = 'Pause Vault editing and retry when the source is stable; pending files are retained.'
    elif isinstance(error, OSError) and error.errno == errno.ENOSPC:
        next_action = 'Check available target space without deleting old snapshots, then retry the same backup.'
    elif any(word in lower for word in ('hash', 'corrupt', 'missing', 'unexpected')):
        next_action = 'Run list and verify on the target; use an intact snapshot. Do not overwrite or delete recovery data.'
    elif any(word in lower for word in ('symlink', 'unsafe', 'invalid', 'not a directory', 'too many levels', 'must not exist', 'separate')):
        next_action = 'Check explicit real paths and choose a new isolated restore directory; do not follow symlinks or overwrite data.'
    else:
        next_action = 'Check connection, authentication and filesystem support; read back list/verify before retrying any unknown commit.'
    result = {'status': 'failed', 'cause': cause, 'preserved': 'Vault and committed snapshots; pending data retained', 'next': next_action}
    if getattr(error, 'restore_staging', None):
        result['restoreStaging'] = error.restore_staging
        result['next'] += ' Retain the reported restore staging directory for inspection.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['backup', 'verify', 'restore', 'list'])
    parser.add_argument('--repository', required=True, help='Existing dedicated backup directory (including a mounted SMB share)')
    parser.add_argument('--vault')
    parser.add_argument('--snapshot')
    parser.add_argument('--destination')
    parser.add_argument('--ssh', help='Mac mini user@host or existing SSH alias; no interactive password prompts')
    args = parser.parse_args()
    endpoint = Endpoint(args.repository, args.ssh)
    if args.command == 'backup':
        if not args.vault:
            parser.error('backup requires --vault')
        return backup(args.vault, endpoint)
    if args.command == 'restore':
        if not args.snapshot or not args.destination:
            parser.error('restore requires --snapshot and --destination')
        return restore(endpoint, args.snapshot, args.destination)
    return endpoint.call(args.command, snapshot=args.snapshot or '')


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--serve']:
            request = json.loads(sys.stdin.buffer.readline())
            result = serve(request, sys.stdin.buffer, sys.stdout.buffer)
        else:
            result = main()
        if result is not None:
            print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print(json.dumps(failure_receipt(error)))
        sys.exit(1)
