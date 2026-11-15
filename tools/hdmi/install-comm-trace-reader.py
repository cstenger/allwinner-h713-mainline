#!/usr/bin/env python3
"""Install the U-Boot 0006-aware comm-trace reader; no service operations.

U-Boot 0006 moved the comm-trace markers from k0/k1 to t8/t9. The installed
read-comm-trace.py pins the old adapter-return words (0x4b101040 lui k0,
0x4b101048 sw k1), so h713-hdmi-prepare refuses a 0006 proper. The new reader
accepts the 0006 encoding or the complete pre-0006 pair (never a mixed slot),
so it works with either proper.

Replaces /usr/lib/h713-hdmi/read-comm-trace.py and its one SHA256SUMS line.
Pins the installed reader and manifest, verifies the whole bundle generation
before and after, backs up and reads back. Preview by default; --apply
installs; --rollback BACKUP restores exactly.
"""
import argparse, fcntl, hashlib, importlib.util, json, os, uuid
from pathlib import Path

spec = importlib.util.spec_from_file_location('guard_io', Path(__file__).with_name('sync-shutdown-guard.py'))
io = importlib.util.module_from_spec(spec); spec.loader.exec_module(io)
NAMES = ('read-comm-trace.py', 'SHA256SUMS')
OLD_READER = 'e8a689b283818338897d49f2d9a2193415c0cbb40a3db2bfb45dcb85406dc840'
NEW_READER = '0f8194cf9bd4078e2a5c107b9329158444cfa9e5e62acea344e5a57d158f470b'
OLD_MANIFEST = '074d9e27e9e0a4f647384ccd2c1021b25be881ca2975eb1777f1292e2860650a'
PREFIX = 'comm-trace-reader-'
SCHEMA = 'h713-comm-trace-reader-install-v1'


def sha(data): return hashlib.sha256(data).hexdigest()
def target(root, name): return io.path(root, io.BACKEND + '/' + name)


def identity(root, boot):
    io.identity(root)
    if (root / 'proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise RuntimeError('boot ID changed')


def current(root):
    for name in NAMES:
        if io.metadata(target(root, name)) != {'mode': 0o644, 'uid': 0, 'gid': 0}:
            raise RuntimeError('unexpected file metadata: ' + name)
    return [target(root, name).read_bytes() for name in NAMES]


def new_manifest(before):
    entries = io.table(before)
    found = [k for k in entries if str(Path(k)) == NAMES[0]]
    if len(found) != 1 or entries[found[0]] != OLD_READER:
        raise RuntimeError('missing or wrong reader manifest entry')
    line = OLD_READER + '  ' + found[0]
    lines = before.decode().splitlines(keepends=True)
    hits = [i for i, v in enumerate(lines) if v.rstrip('\r\n') == line]
    if len(hits) != 1:
        raise RuntimeError('ambiguous reader manifest entry')
    lines[hits[0]] = lines[hits[0]].replace(OLD_READER, NEW_READER, 1)
    return ''.join(lines).encode()


def preview(root, bundle, boot):
    identity(root, boot)
    before = current(root)
    if sha(before[0]) != OLD_READER or sha(before[1]) != OLD_MANIFEST:
        raise RuntimeError('unexpected installed reader/manifest')
    io.verify_generation(root, before[1])
    reader = io.path(bundle, io.BACKEND + '/' + NAMES[0]).read_bytes()
    if sha(reader) != NEW_READER:
        raise RuntimeError('payload checksum mismatch')
    return before, [reader, new_manifest(before[1])]


def install(root, bundle, boot, apply=False):
    identity(root, boot)
    fd = os.open(io.path(root, io.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if list((root / io.STATE).glob(PREFIX + '*/INCOMPLETE')):
            raise RuntimeError('incomplete reader transaction; inspect or roll back first')
        before, after = preview(root, bundle, boot)
        if not apply:
            return {'phase': 'would-install', 'targets': list(NAMES),
                    'before': list(map(sha, before)), 'after': list(map(sha, after))}
        backup = root / io.STATE / (PREFIX + uuid.uuid4().hex); backup.mkdir(mode=0o700)
        record = {'schema': SCHEMA, 'boot_id': boot, 'targets': list(NAMES),
                  'before': list(map(sha, before)), 'after': list(map(sha, after)),
                  'metadata': [io.metadata(target(root, n)) for n in NAMES]}
        for i, data in enumerate(before): io.save(backup / str(i), data)
        io.save(backup / 'record.json', (json.dumps(record, indent=2) + '\n').encode())
        io.save(backup / 'INCOMPLETE', b'Inspect or roll back before another update or shutdown.\n')
        io.fsync_dir(backup); io.fsync_dir(backup.parent)
        for i, name in enumerate(NAMES):           # reader first, manifest last
            identity(root, boot)
            io.atomic(target(root, name), after[i], record['metadata'][i], record['before'][i])
        if current(root) != after:
            raise RuntimeError('installation readback failed')
        io.verify_generation(root, after[1])
        io.save(backup / 'COMMITTED', b'0006-aware reader installed; no services operated\n')
        (backup / 'INCOMPLETE').unlink(); io.fsync_dir(backup)
        return {'phase': 'installed', 'backup': str(backup), 'record': record, 'services_changed': False}
    finally:
        os.close(fd)


def rollback(root, backup, boot, apply=False):
    identity(root, boot)
    if backup.parent != root / io.STATE or not backup.name.startswith(PREFIX) or backup.is_symlink():
        raise RuntimeError('invalid rollback location')
    fd = os.open(io.path(root, io.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rel = str(backup.relative_to(root))
        record = json.loads(io.path(root, rel + '/record.json').read_text())
        if (record['schema'] != SCHEMA or record['targets'] != list(NAMES)
                or record['before'] != [OLD_READER, OLD_MANIFEST] or record['after'][0] != NEW_READER):
            raise RuntimeError('invalid rollback scope')
        before = [io.path(root, rel + '/' + str(i)).read_bytes() for i in range(2)]
        if list(map(sha, before)) != record['before'] or sha(new_manifest(before[1])) != record['after'][1]:
            raise RuntimeError('rollback data corrupted')
        now = current(root)
        if any(sha(d) not in (record['before'][i], record['after'][i]) for i, d in enumerate(now)):
            raise RuntimeError('foreign target change; refusing rollback')
        for name, digest in io.table(before[1]).items():
            if str(Path(name)) != NAMES[0] and sha(target(root, name).read_bytes()) != digest:
                raise RuntimeError('unrelated backend changed: ' + name)
        if not apply:
            return {'phase': 'would-rollback', 'backup': str(backup)}
        for i, name in reversed(list(enumerate(NAMES))):   # manifest first, reader last
            identity(root, boot)
            io.atomic(target(root, name), before[i], record['metadata'][i], sha(now[i]))
        io.verify_generation(root, before[1])
        io.save(backup / 'ROLLED_BACK', b'reader and manifest restored\n')
        (backup / 'INCOMPLETE').unlink(missing_ok=True); io.fsync_dir(backup)
        return {'phase': 'rolled-back', 'backup': str(backup), 'services_changed': False}
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=Path('/'))
    p.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--rollback', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args(); root = a.root.resolve()
    if a.rollback:
        result = rollback(root, a.rollback.absolute(), a.boot_id, a.apply)
    else:
        result = install(root, a.bundle.resolve(), a.boot_id, a.apply)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
