#!/usr/bin/env python3
"""Install source-aware elog confirmation; no service operations.

With no HDMI source at boot, `h713-mips-elog-level.service` sent `elog -l 2`
and got the exact reply, but the idle firmware left the new value unwritten
past the 5 s check, so the unit failed and the system was degraded
(2026-11-18; the word read 2 once a source locked, nothing re-sent). The new
mips-shell.py confirms after releasing the ring lock and waits for a source
before failing; the unit becomes Type=exec so that wait never holds boot.

Targets: the bundle's mips-shell.py and unit, the active unit copy in
/etc/systemd/system, and the two bundle manifest entries. Pins the installed
originals. Preview by default; --apply installs; --rollback BACKUP restores
exactly. Takes effect on the next boot (no daemon-reload, no restarts).
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import uuid

spec = importlib.util.spec_from_file_location('guard_io', Path(__file__).with_name('sync-shutdown-guard.py'))
io = importlib.util.module_from_spec(spec);spec.loader.exec_module(io)
SHELL, UNIT = 'mips-shell.py', 'h713-mips-elog-level.service'
OLD_SHELL = 'd7e505bb84278f36b952fb524b8a86a85422a46f6accbcc49c16373060fd9c06'
NEW_SHELL = '58b1183f62a7d626dfea281f7b4ca6be665d2263ef25e30ebf323c415929dae8'
OLD_UNIT = '31b07edd92def47d24068e638f409c8832a02e33362ea2816a24675164786b56'
NEW_UNIT = '002631aa5c176eda43d6ecc66ac3d0eea25f233bdcccb0ff4c2e00a02ce9fed5'
SYSTEMD = 'etc/systemd/system'
WANTS = SYSTEMD + '/multi-user.target.wants/' + UNIT
# (relative path, original, replacement); the manifest is derived, not pinned here.
FILES = ((io.BACKEND + '/' + SHELL, OLD_SHELL, NEW_SHELL),
         (io.BACKEND + '/' + UNIT, OLD_UNIT, NEW_UNIT),
         (SYSTEMD + '/' + UNIT, OLD_UNIT, NEW_UNIT))
MANIFEST = io.BACKEND + '/SHA256SUMS'
TARGETS = tuple(rel for rel, _, _ in FILES) + (MANIFEST,)
PREFIX = 'elog-confirm-'


def sha(data): return hashlib.sha256(data).hexdigest()


def identity(root, boot):
    io.identity(root)
    if (root/'proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise RuntimeError('boot ID changed')
    wants = root / WANTS
    if not wants.is_symlink() or os.readlink(wants) != '../' + UNIT:
        raise RuntimeError('elog unit is not enabled as installed')


def current(root):
    data = [io.path(root, rel).read_bytes() for rel in TARGETS]
    for rel in TARGETS:
        if io.metadata(io.path(root, rel)) != {'mode': 0o644, 'uid': 0, 'gid': 0}:
            raise RuntimeError('unexpected file metadata: ' + rel)
    return data


def candidate_manifest(before):
    entries = io.table(before)
    lines = before.decode().splitlines(keepends=True)
    for name, old, new in ((SHELL, OLD_SHELL, NEW_SHELL), (UNIT, OLD_UNIT, NEW_UNIT)):
        found = [key for key in entries if str(Path(key)) == name]
        if len(found) != 1 or entries[found[0]] != old:
            raise RuntimeError('missing or wrong original manifest entry: ' + name)
        matches = [i for i, value in enumerate(lines) if value.rstrip('\r\n') == old + '  ' + found[0]]
        if len(matches) != 1: raise RuntimeError('ambiguous original manifest entry')
        lines[matches[0]] = lines[matches[0]].replace(old, new, 1)
    return ''.join(lines).encode()


def preview(root, bundle, boot, before_manifest):
    identity(root, boot)
    data = current(root)
    if [sha(d) for d in data[:3]] != [old for _, old, _ in FILES] or sha(data[3]) != before_manifest:
        raise RuntimeError('unexpected installed files/manifest')
    io.verify_generation(root, data[3])
    payload = {SHELL: io.path(bundle, io.BACKEND + '/' + SHELL).read_bytes(),
               UNIT: io.path(bundle, io.BACKEND + '/' + UNIT).read_bytes()}
    if (sha(payload[SHELL]), sha(payload[UNIT])) != (NEW_SHELL, NEW_UNIT):
        raise RuntimeError('payload checksum mismatch')
    after = [payload[SHELL], payload[UNIT], payload[UNIT], candidate_manifest(data[3])]
    return data, after


def install(root, bundle, boot, before_manifest, apply=False):
    identity(root, boot)
    fd = os.open(io.path(root, io.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if list((root/io.STATE).glob(PREFIX + '*/INCOMPLETE')):
            raise RuntimeError('incomplete elog-confirm transaction; inspect or roll back first')
        before, after = preview(root, bundle, boot, before_manifest)
        if not apply:
            return {'phase': 'would-install', 'targets': list(TARGETS),
                    'before': list(map(sha, before)), 'after': list(map(sha, after))}
        backup = root/io.STATE/(PREFIX + uuid.uuid4().hex);backup.mkdir(mode=0o700)
        record = {'schema': 'h713-elog-confirm-install-v1', 'boot_id': boot,
                  'targets': list(TARGETS), 'before': list(map(sha, before)),
                  'after': list(map(sha, after)),
                  'metadata': [io.metadata(io.path(root, rel)) for rel in TARGETS]}
        for i, data in enumerate(before): io.save(backup/str(i), data)
        io.save(backup/'record.json', (json.dumps(record, indent=2) + '\n').encode())
        io.save(backup/'INCOMPLETE', b'Inspect or roll back before another update or shutdown.\n')
        io.fsync_dir(backup);io.fsync_dir(backup.parent)
        for i, rel in enumerate(TARGETS):
            identity(root, boot)
            io.atomic(io.path(root, rel), after[i], record['metadata'][i], record['before'][i])
        if current(root) != after: raise RuntimeError('installation readback failed')
        io.verify_generation(root, after[3])
        io.save(backup/'COMMITTED', b'source-aware elog confirmation installed; no services operated\n')
        (backup/'INCOMPLETE').unlink();io.fsync_dir(backup)
        return {'phase': 'installed', 'backup': str(backup), 'record': record, 'services_changed': False}
    finally:
        os.close(fd)


def rollback(root, backup, boot, apply=False):
    identity(root, boot)
    if backup.parent != root/io.STATE or not backup.name.startswith(PREFIX) or backup.is_symlink():
        raise RuntimeError('invalid rollback location')
    fd = os.open(io.path(root, io.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        relative = str(backup.relative_to(root))
        record = json.loads(io.path(root, relative + '/record.json').read_text())
        if (record['schema'] != 'h713-elog-confirm-install-v1' or record['targets'] != list(TARGETS)
                or record['before'][:3] != [old for _, old, _ in FILES]
                or record['after'][:3] != [new for _, _, new in FILES]):
            raise RuntimeError('invalid rollback scope')
        before = [io.path(root, relative + '/' + str(i)).read_bytes() for i in range(len(TARGETS))]
        if list(map(sha, before)) != record['before'] or sha(candidate_manifest(before[3])) != record['after'][3]:
            raise RuntimeError('rollback data corrupted')
        now = current(root)
        if any(sha(data) not in (record['before'][i], record['after'][i]) for i, data in enumerate(now)):
            raise RuntimeError('foreign target change; refusing rollback')
        for name, digest in io.table(before[3]).items():
            if str(Path(name)) not in (SHELL, UNIT) and sha(io.path(root, io.BACKEND + '/' + name).read_bytes()) != digest:
                raise RuntimeError('unrelated backend changed: ' + name)
        if not apply: return {'phase': 'would-rollback', 'backup': str(backup)}
        for i, rel in enumerate(TARGETS):
            identity(root, boot)
            io.atomic(io.path(root, rel), before[i], record['metadata'][i], sha(now[i]))
        io.verify_generation(root, before[3])
        if not (backup/'ROLLED_BACK').exists(): io.save(backup/'ROLLED_BACK', b'elog shell, units and manifest restored\n')
        (backup/'INCOMPLETE').unlink(missing_ok=True);io.fsync_dir(backup)
        return {'phase': 'rolled-back', 'backup': str(backup), 'services_changed': False}
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/'))
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--before-manifest-sha')
    parser.add_argument('--rollback', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args();root = args.root.resolve()
    if args.rollback:
        result = rollback(root, args.rollback.absolute(), args.boot_id, args.apply)
    else:
        if not args.before_manifest_sha: parser.error('--before-manifest-sha is required for install/preview')
        result = install(root, args.bundle.resolve(), args.boot_id, args.before_manifest_sha, args.apply)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
