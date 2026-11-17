#!/usr/bin/env python3
"""Install and update the local Wiki client. Uses only the Python standard library."""
import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

REPOSITORY = 'liunoly-design/Personal_wiki'
API = 'https://api.github.com/repos/' + REPOSITORY + '/releases/latest'
DOWNLOAD = 'https://github.com/' + REPOSITORY + '/releases/download/'
SAMPLE = 'Pwiki 安装更新自检：完整中文正文必须原样保留。'


def regular(path):
    path = Path(path).absolute()
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise ValueError('Symlink configuration or installation path refused')
    return path


def private_json(path, value):
    path = regular(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')
    temporary.replace(path)


@contextmanager
def lease(path):
    path = regular(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def run(arguments, timeout=180):
    # No shell and no inherited account data in diagnostic output.
    result = subprocess.run([str(arg) for arg in arguments], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Subprocess failed: ' + Path(str(arguments[0])).name)
    return result.stdout


def fetch(url, destination, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'Personal-Wiki-installer', 'Accept': 'application/vnd.github+json' if url == API else 'application/octet-stream'})
    with urllib.request.urlopen(request, timeout=45) as response, destination.open('xb') as output:
        size = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError('Release download exceeds size limit')
            output.write(chunk)


def release_metadata(directory, work):
    path = Path(directory) / 'release.json' if directory else work / 'release.json'
    if not directory:
        fetch(API, path, 2 * 1024 * 1024)
    release = json.loads(path.read_text())
    match = re.fullmatch(r'distribution-v(\d+)\.(\d+)\.(\d+)', release.get('tag_name', ''))
    if not match or release.get('draft') is not False or release.get('prerelease') is not False:
        raise ValueError('Only stable distribution releases are supported')
    return release, tuple(int(value) for value in match.groups())


def package(release, component, directory, work):
    version = release['tag_name'].removeprefix('distribution-v')
    name = 'personal-wiki-' + component + '-' + version
    archive_name = name + '.tar.gz'
    archive, checksum = work / archive_name, work / (archive_name + '.sha256')
    if directory:
        shutil.copyfile(Path(directory) / archive.name, archive)
        shutil.copyfile(Path(directory) / checksum.name, checksum)
    else:
        base = DOWNLOAD + release['tag_name'] + '/'
        fetch(base + archive.name, archive, 64 * 1024 * 1024)
        fetch(base + checksum.name, checksum, 1024)
    line = checksum.read_text().strip()
    match = re.fullmatch(r'([a-f0-9]{64})\s+\*?' + re.escape(archive_name), line)
    if not match or hashlib.sha256(archive.read_bytes()).hexdigest() != match[1]:
        raise ValueError('Release archive SHA256 mismatch')
    published = next((asset for asset in release.get('assets', []) if asset['name'] == archive_name), {})
    if published.get('digest') and published['digest'] != 'sha256:' + match[1]:
        raise ValueError('GitHub release digest mismatch')
    output = work / ('unpacked-' + component)
    output.mkdir()
    seen, size = set(), 0
    with tarfile.open(archive) as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            size += member.size
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != name or str(path) in seen or not (member.isdir() or member.isfile()) or size > 128 * 1024 * 1024:
                raise ValueError('Unsafe release archive')
            seen.add(str(path))
            target = output.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open('xb') as dest:
                    shutil.copyfileobj(source, dest)
    root = output / name
    manifest = json.loads((root / 'distribution.json').read_text())
    if manifest.get('component') != component or manifest.get('version') != version or not re.fullmatch('[a-f0-9]{40}', manifest.get('revision', '')) or (not directory and manifest.get('source_dirty') is not False):
        raise ValueError('Distribution identity mismatch')
    for relative, expected in manifest['files'].items():
        parts = PurePosixPath(relative)
        if parts.is_absolute() or '..' in parts.parts or not parts.parts:
            raise ValueError('Unsafe distribution manifest')
        source = root.joinpath(*parts.parts)
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError('Distribution file integrity mismatch')
    return root


def smoke(node, candidate, python, work):
    config = work / 'smoke.json'
    private_json(config, {'stateDir': str(work / 'smoke-state'), 'python': str(python), 'autoStart': False})
    result = json.loads(run([node, candidate / 'runtime/scripts/wiki.mjs', 'convert', '--config', config, '--text', SAMPLE]))
    if result.get('status') != 'converted' or Path(result['bundle']['markdown']).read_text() != SAMPLE:
        raise ValueError('Candidate text conversion failed')


def installation(prefix):
    prefix = regular(prefix)
    owner = json.loads((prefix / '.installation.json').read_text())
    if owner.get('component') != 'cli' or owner.get('prefix') != str(prefix):
        raise ValueError('This updater requires a managed CLI installation')
    config_path = regular(owner['config'])
    info = config_path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Private owned configuration required')
    config = json.loads(config_path.read_text())
    if config.get('stateDir') != str(prefix / 'state') or config.get('runtimeRoot') != str(prefix / 'state/runtime'):
        raise ValueError('Installation configuration identity mismatch')
    current = prefix / 'state/runtime/current'
    release = current.resolve(strict=True)
    if not current.is_symlink() or release.parent != prefix / 'state/runtime/releases':
        raise ValueError('Managed current release required')
    manifest = json.loads((release / '.distribution.json').read_text())
    return owner, config, manifest


def recover_activation(prefix):
    root = prefix / 'state/runtime'
    journal = regular(root / 'activation.json')
    if not journal.exists():
        return
    transaction = json.loads(journal.read_text())
    if transaction.get('phase') != 'activating':
        return
    with lease(root / 'use.lock'):
        previous = transaction.get('previous')
        target = transaction.get('next')
        if not previous or not target:
            raise ValueError('Incomplete first installation; retain files and reinstall in a new prefix')
        previous, target = regular(previous), regular(target)
        if previous.parent != root / 'releases' or target.parent != root / 'releases' or not (previous / '.distribution.json').is_file():
            raise ValueError('Invalid recovery targets; retained')
        current = root / 'current'
        if not current.is_symlink() or current.resolve() not in (previous, target):
            raise ValueError('Current runtime changed outside this update; retained')
        link = root / ('recover-' + uuid.uuid4().hex)
        link.symlink_to(previous)
        link.replace(current)
        private_json(journal, {**transaction, 'phase': 'rolled_back'})


def update(args):
    prefix = regular(args.prefix)
    state = prefix / 'state/update-status.json'
    with lease(prefix / 'state/update-manager.lock'):
        recover_activation(prefix)
        owner, config, installed = installation(prefix)
        previous = json.loads(state.read_text()) if state.exists() else {}
        if args.scheduled and previous.get('checkedAt', 0) + 86400 > time.time() and previous.get('status') != 'deferred':
            return {'status': 'not_due'}
        with tempfile.TemporaryDirectory(prefix='pwiki-update-') as tmp:
            work = Path(tmp).resolve()
            release, version = release_metadata(args.release_dir, work)
            current_version = tuple(int(value) for value in installed['version'].split('.'))
            if version <= current_version:
                result = {'status': 'up_to_date', 'version': installed['version'], 'checkedAt': time.time()}
            elif version[0] != current_version[0]:
                result = {'status': 'manual_update_required', 'reason': 'major_version_changed', 'checkedAt': time.time()}
            else:
                candidate = package(release, 'cli', args.release_dir, work)
                current = (prefix / 'state/runtime/current').resolve()
                if any((candidate / 'runtime' / path).read_bytes() != (current / path).read_bytes() for path in ('requirements-capture.txt', 'upstream-nashsu.json')):
                    result = {'status': 'manual_update_required', 'reason': 'capture_dependencies_or_llm_wiki_pin_changed', 'checkedAt': time.time()}
                    private_json(state, result)
                    return result
                node = args.node or shutil.which('node')
                if not node:
                    raise ValueError('Node 24+ required; rerun installation bootstrap')
                smoke(node, candidate, config['python'], work)
                activated = json.loads(run([node, candidate / 'install.mjs', '--prefix', prefix, '--config', owner['config'], '--python', config['python'], '--idle-only']))
                result = {'status': 'updated', 'version': '.'.join(map(str, version)), 'checkedAt': time.time()} if activated['status'] == 'installed' else {'status': 'deferred', 'reason': activated['reason'], 'checkedAt': time.time()}
            private_json(state, result)
            return result


def schedule(args):
    prefix = regular(args.prefix)
    installation(prefix)
    executable = prefix / 'bin/pwiki-update'
    if not executable.is_file():
        raise ValueError('Install a client package with the updater first')
    label = 'com.personal-wiki.updater.' + hashlib.sha256(str(prefix).encode()).hexdigest()[:12]
    arguments = [str(executable), '--scheduled']
    plan = {'status': 'planned', 'label': label, 'arguments': arguments, 'intervalSeconds': 3600}
    if args.dry_run:
        return plan
    if args.remove and sys.platform != 'darwin':
        return {'status': 'removed', 'label': label}
    if sys.platform != 'darwin':
        raise ValueError('Daily scheduling requires macOS launchd')
    target = regular(Path.home() / 'Library/LaunchAgents' / (label + '.plist'))
    old = plistlib.loads(target.read_bytes()) if target.exists() else None
    if old and old.get('ProgramArguments') != arguments:
        raise ValueError('Another installation owns this update schedule')
    domain = 'gui/' + str(os.getuid())
    if args.remove:
        if old:
            subprocess.run(['/bin/launchctl', 'bootout', domain, str(target)], capture_output=True)
            target.unlink()
        return {'status': 'removed', 'label': label}
    body = {'Label': label, 'ProgramArguments': arguments, 'StartInterval': 3600, 'RunAtLoad': True, 'ProcessType': 'Background', 'StandardOutPath': str(prefix / 'state/update.log'), 'StandardErrorPath': str(prefix / 'state/update-error.log')}
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_name(target.name + '.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as output:
        plistlib.dump(body, output)
    temporary.replace(target)
    active = subprocess.run(['/bin/launchctl', 'print', domain + '/' + label], capture_output=True)
    if active.returncode:
        run(['/bin/launchctl', 'bootstrap', domain, target])
    run(['/bin/launchctl', 'print', domain + '/' + label])
    return {**plan, 'status': 'scheduled', 'plist': str(target)}


def install(args):
    if not args.release_dir and (sys.platform != 'darwin' or os.uname().machine != 'arm64'):
        raise ValueError('The supported installation target is macOS Apple Silicon')
    prefix = regular(args.prefix)
    prefix.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = regular(args.config or Path.home() / '.config/personal-wiki/cli.json')
    vault = regular(args.vault or Path.home() / 'Documents/Personal-Wiki-Vault')
    # Credentials remain a private file on this computer; never copy its contents.
    token = regular(args.media_token_file)
    info = token.stat()
    if not token.is_file() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Mini token must be an owned private file (chmod 600)')
    origin = urlsplit(args.media_url)
    if origin.scheme not in ('http', 'https') or not origin.hostname or origin.username or origin.password or origin.path not in ('', '/') or origin.query or origin.fragment:
        raise ValueError('Mini service origin required, without credentials or path')
    node = args.node or shutil.which('node')
    if not node or int(run([node, '-p', 'process.versions.node.split(".")[0]']).strip()) < 24:
        raise ValueError('Node 24+ required; use install-pwiki.sh to install prerequisites')
    node = str(Path(node).absolute())
    os.environ['PATH'] = str(Path(node).parent) + os.pathsep + os.environ.get('PATH', '')
    codex = args.codex or shutil.which('codex')
    with lease(prefix / '.setup.lock'), tempfile.TemporaryDirectory(prefix='pwiki-setup-') as tmp:
        work = Path(tmp).resolve()
        release, _ = release_metadata(args.release_dir, work)
        candidate = package(release, 'cli', args.release_dir, work)
        existing = installation(prefix)[1] if (prefix / '.installation.json').exists() else None
        python = Path(existing['python'] if existing else sys.executable)
        codex = existing.get('codexBinary') if existing else codex
        if not args.skip_dependencies and not existing:
            venv = prefix / 'capture-venv'
            if not (venv / 'bin/python').is_file():
                run([sys.executable, '-m', 'venv', venv])
            python = venv / 'bin/python'
            run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', candidate / 'runtime/requirements-capture.txt'], timeout=900)
            run([python, '-m', 'playwright', 'install', 'chromium'], timeout=900)
            if not codex:
                npm = shutil.which('npm')
                if not npm:
                    raise ValueError('npm required to install Codex CLI')
                tools = prefix / 'tools/codex'
                run([npm, 'install', '--prefix', tools, '@openai/codex'], timeout=900)
                codex = str(tools / 'node_modules/.bin/codex')
        smoke(node, candidate, python, work)
        command = [node, candidate / 'install.mjs', '--prefix', prefix, '--config', config_path, '--python', python, '--vault', vault, '--media-url', args.media_url, '--media-token-file', token, '--idle-only']
        if codex:
            command.extend(['--codex', codex])
        result = json.loads(run(command))
        if result['status'] != 'installed':
            return result
        skills = Path.home() / '.codex/skills/personal-wiki'
        skill_status = 'retained_existing'
        if not skills.exists():
            run([node, candidate / 'manage.mjs', '--prefix', prefix, 'skill-install'])
            skill_status = 'installed'
        app = Path.home() / 'Applications/LLM Wiki.app'
        system_app = Path('/Applications/LLM Wiki.app')
        if app.exists() or system_app.exists():
            app = app if app.exists() else system_app
            app_status = 'retained_existing'
        else:
            setup = package(release, 'llm-wiki-setup', args.release_dir, work)
            run([sys.executable, setup / 'llm-wiki-setup.py', 'install', '--destination', Path.home() / 'Applications'], timeout=900)
            app_status = 'installed'
        if args.worker:
            run([node, candidate / 'manage.mjs', '--prefix', prefix, 'worker-install'])
        if not args.no_schedule:
            schedule(argparse.Namespace(prefix=str(prefix), dry_run=False, remove=False))
        private_json(prefix / 'state/update-status.json', {'status': 'up_to_date', 'version': release['tag_name'].removeprefix('distribution-v'), 'checkedAt': time.time()})
        return {**result, 'skill': skill_status, 'llmWiki': app_status, 'application': str(app), 'dailyUpdates': not args.no_schedule, 'next': 'Open LLM Wiki, configure this local Vault and model login, enable local API, disable duplicate autoIngest and embedding; then run personal-wiki doctor.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    updater = commands.add_parser('update')
    updater.add_argument('--prefix', required=True)
    updater.add_argument('--release-dir', help='Explicit offline release directory containing release.json and packages')
    updater.add_argument('--node')
    updater.add_argument('--scheduled', action='store_true')
    scheduler = commands.add_parser('schedule')
    scheduler.add_argument('--prefix', required=True)
    scheduler.add_argument('--dry-run', action='store_true')
    scheduler.add_argument('--remove', action='store_true')
    installer = commands.add_parser('install')
    installer.add_argument('--prefix', default=str(Path.home() / '.local/share/pwiki'))
    installer.add_argument('--config')
    installer.add_argument('--vault')
    installer.add_argument('--media-url', required=True)
    installer.add_argument('--media-token-file', required=True)
    installer.add_argument('--node')
    installer.add_argument('--codex')
    installer.add_argument('--release-dir')
    installer.add_argument('--skip-dependencies', action='store_true', help='Explicitly reuse a prepared environment')
    installer.add_argument('--no-schedule', action='store_true')
    installer.add_argument('--worker', action='store_true', help='Also enable the ingestion worker after configuring the app')
    args = parser.parse_args()
    operation = {'schedule': schedule, 'update': update, 'install': install}[args.command]
    print(json.dumps(operation(args), ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except BlockingIOError:
        print(json.dumps({'status': 'deferred', 'reason': 'another_update_is_running'}))
    except Exception as error:
        print(json.dumps({'status': 'error', 'message': str(error)}))
        sys.exit(1)
