#!/usr/bin/env python3
"""Synchronize only the two HDMI shutdown guards and backend checksum entry.

No service, module, firmware, boot, RTC or panel operations. Default is a
read-only preview. Install and rollback need separate explicit CLI switches.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

GUARD = 'h713-hdmi-hold-guard'
BACKEND = 'usr/lib/h713-hdmi'
STATE = 'var/lib/h713-hdmi-startup'
TARGETS = (BACKEND + '/' + GUARD,
           'usr/lib/systemd/system-shutdown/' + GUARD,
           BACKEND + '/SHA256SUMS')
OLD = '9140e3104042cd291496f3c238d1c3ef151184d362f32752c7179f9b25483db7'
NEW = '96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def path(root, relative):
    p = root
    for part in Path(relative).parts:
        if part in ('..', '/'):
            raise RuntimeError('unsafe path: ' + relative)
        p = p / part
        if p.is_symlink():
            raise RuntimeError('symlink refused: ' + str(p))
    return p


def table(data):
    entries = {}
    for line in data.decode().splitlines():
        h, name = line.split('  ', 1)
        if len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
            raise RuntimeError('invalid checksum')
        if not name or name in entries or Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('invalid checksum path')
        entries[name] = h
    if not entries:
        raise RuntimeError('empty checksum manifest')
    return entries


def verify_generation(root, data, skip_guard=False):
    for name, expected in table(data).items():
        if skip_guard and name == GUARD:
            continue
        p = path(root, BACKEND + '/' + name)
        if not p.is_file() or digest(p.read_bytes()) != expected:
            raise RuntimeError('installed generation differs: ' + name)


def package(bundle):
    checks = table((bundle / 'SHA256SUMS').read_bytes())
    if set(checks) != {GUARD, 'sync-shutdown-guard.py', 'manifest.json'}:
        raise RuntimeError('unexpected package scope')
    for name, expected in checks.items():
        if digest(path(bundle, name).read_bytes()) != expected:
            raise RuntimeError('package checksum mismatch: ' + name)
    m = json.loads((bundle / 'manifest.json').read_text())
    if m['schema'] != 'h713-shutdown-guard-sync-v1' or m['before_guard'] != OLD or m['after_guard'] != NEW:
        raise RuntimeError('unsupported guard generation')
    if digest((bundle / GUARD).read_bytes()) != NEW:
        raise RuntimeError('candidate guard differs')
    return m


def identity(root):
    # /proc/device-tree is normally a kernel-provided symlink: do not apply
    # the persistent-file no-symlink policy to this read-only identity path.
    model = (root / 'proc/device-tree/model').read_text().strip('\0\n')
    if model != 'HY200 QZ713DF_A1 (Allwinner H713)':
        raise RuntimeError('wrong board model')
    for directory in (BACKEND, STATE, 'usr/lib/systemd/system-shutdown'):
        if not path(root, directory).is_dir():
            raise RuntimeError('installation directory missing: ' + directory)


def metadata(p):
    s = p.stat()
    return {'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid, 'gid': s.st_gid}


def preview(root, bundle):
    identity(root)
    m = package(bundle)
    current = [path(root, p).read_bytes() for p in TARGETS]
    for relative, mode in zip(TARGETS, (0o755, 0o755, 0o644)):
        if metadata(path(root, relative))['mode'] != mode:
            raise RuntimeError('unexpected installed permissions: ' + relative)
    if digest(current[2]) == m['after_manifest'] and all(digest(c) == NEW for c in current[:2]):
        verify_generation(root, current[2])
        return m, current, 'already-current'
    if digest(current[2]) != m['before_manifest'] or any(digest(c) != OLD for c in current[:2]):
        raise RuntimeError('unexpected installed guards/manifest; inspect or rollback pending transaction')
    verify_generation(root, current[2])
    if table(current[2]).get(GUARD) != OLD:
        raise RuntimeError('guard entry missing from installed manifest')
    return m, current, 'would-install'


def fsync_dir(p):
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(p, data, attrs, expected):
    if digest(p.read_bytes()) != expected:
        raise RuntimeError('target changed during transaction: ' + str(p))
    fd, temp = tempfile.mkstemp(prefix='.' + p.name + '.guard-sync-', dir=p.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            if os.geteuid() == 0:
                os.fchown(f.fileno(), attrs['uid'], attrs['gid'])
            os.fchmod(f.fileno(), attrs['mode'])
            f.flush()
            os.fsync(f.fileno())
        if Path(temp).read_bytes() != data:
            raise RuntimeError('staging readback failed')
        os.replace(temp, p)
        fsync_dir(p.parent)
    finally:
        Path(temp).unlink(missing_ok=True)


def save(p, data):
    with p.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def install(root, bundle, dry_run=True):
    # Directory flock serializes this updater without creating a lock file.
    identity(root)
    fd = os.open(path(root, STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any(path(root, STATE).glob('guard-sync-*/INCOMPLETE')):
            raise RuntimeError('incomplete guard transaction; rollback before retry')
        m, before, phase = preview(root, bundle)
        if dry_run or phase == 'already-current':
            return {'phase': phase, 'dry_run': dry_run, 'targets': list(TARGETS), 'services_changed': False}
        candidate = (bundle / GUARD).read_bytes()
        after = [candidate, candidate, before[2].replace((OLD + '  ' + GUARD).encode(), (NEW + '  ' + GUARD).encode())]
        if digest(after[2]) != m['after_manifest']:
            raise RuntimeError('unexpected resulting checksum manifest')
        attrs = [metadata(path(root, p)) for p in TARGETS]
        backup = path(root, STATE) / ('guard-sync-' + uuid.uuid4().hex)
        backup.mkdir(mode=0o700)
        record = {'schema': m['schema'], 'targets': list(TARGETS),
                  'before': [digest(b) for b in before], 'after': [digest(a) for a in after], 'metadata': attrs}
        for i, data in enumerate(before):
            save(backup / str(i), data)
        save(backup / 'record.json', (json.dumps(record, indent=2)+'\n').encode())
        save(backup / 'INCOMPLETE', b'Guard transaction; finish or rollback before shutdown.\n')
        fsync_dir(backup)
        fsync_dir(backup.parent)
        try:
            for i, relative in enumerate(TARGETS):
                atomic(path(root, relative), after[i], attrs[i], record['before'][i])
            preview(root, bundle)  # verify both copies and the full installed manifest
            save(backup / 'COMMITTED', b'guard sync installed; no services changed\n')
            (backup / 'INCOMPLETE').unlink()
            fsync_dir(backup)
        except Exception as error:
            raise RuntimeError(f'guard update incomplete; rollback {backup}: {error}') from error
        return {'phase': 'installed', 'backup': str(backup), 'targets': list(TARGETS), 'services_changed': False}
    finally:
        os.close(fd)


def rollback(root, backup, dry_run=True):
    identity(root)
    state = path(root, STATE)
    if backup.parent != state or not backup.name.startswith('guard-sync-') or backup.is_symlink():
        raise RuntimeError('invalid backup location')
    fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = json.loads(path(root, str(backup.relative_to(root)) + '/record.json').read_text())
        if r['schema'] != 'h713-shutdown-guard-sync-v1' or r['targets'] != list(TARGETS):
            raise RuntimeError('invalid backup scope')
        before = [path(root, str(backup.relative_to(root)) + '/' + str(i)).read_bytes() for i in range(3)]
        if [digest(b) for b in before] != r['before'] or r['before'][:2] != [OLD, OLD] or r['after'][:2] != [NEW, NEW]:
            raise RuntimeError('backup checksum mismatch')
        current = [path(root, p).read_bytes() for p in TARGETS]
        if any(digest(b) not in (r['before'][i], r['after'][i]) for i, b in enumerate(current)):
            raise RuntimeError('target changed outside transaction; refusing rollback')
        verify_generation(root, before[2], skip_guard=True)
        if dry_run:
            return {'phase': 'would-rollback', 'dry_run': True, 'backup': str(backup)}
        # Restore functional hook first; then recorded copy and manifest.
        for i in (1, 0, 2):
            atomic(path(root, TARGETS[i]), before[i], r['metadata'][i], digest(current[i]))
        verify_generation(root, before[2])
        save_marker = backup / 'ROLLED_BACK'
        if not save_marker.exists():
            save(save_marker, b'guard sync rolled back; no services changed\n')
        (backup / 'INCOMPLETE').unlink(missing_ok=True)
        fsync_dir(backup)
        return {'phase': 'rolled-back', 'backup': str(backup), 'services_changed': False}
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    action = p.add_mutually_exclusive_group()
    action.add_argument('--install', action='store_true')
    action.add_argument('--rollback', type=Path)
    p.add_argument('--dry-run', action='store_true', help='Preview rollback; install preview is the default')
    p.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--root', type=Path, default=Path('/'), help='Offline fixture root; never redirects hardware operations')
    a = p.parse_args()
    root = a.root.resolve()
    if root == Path('/') and os.geteuid() != 0:
        p.error('run target checks/install as root')
    result = rollback(root, a.rollback.absolute(), a.dry_run) if a.rollback else install(root, a.bundle.resolve(), not a.install or a.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        raise SystemExit(str(error))
