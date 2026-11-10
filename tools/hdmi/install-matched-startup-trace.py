#!/usr/bin/env python3
"""Switch exact RC startup test arms on disk; never restart services or modules."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import uuid

spec = importlib.util.spec_from_file_location('guard_io', Path(__file__).with_name('sync-shutdown-guard.py'))
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)
PINS = '7e9263a2ab767c3e28b228c8d0590aab87b3c1df20ba01772fff6477858fe82c'
ATTRS = dict(mode=0o644, uid=0, gid=0)


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read(root, name):
    p = io.path(root, name)
    if not p.exists():
        return None
    if not p.is_file() or io.metadata(p) != ATTRS:
        raise RuntimeError('unexpected file/metadata: ' + name)
    return p.read_bytes()


def put(root, name, data, expected):
    p = io.path(root, name)
    if sha(read(root, name)) != expected:
        raise RuntimeError('file changed: ' + name)
    if data is None:
        p.unlink()
        io.fsync_dir(p.parent)
    elif expected is not None:
        io.atomic(p, data, ATTRS, expected)
    else:
        fd, tmp = tempfile.mkstemp(prefix='.matched-startup-', dir=p.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
                os.fchmod(f.fileno(), 0o644)
                if os.geteuid() == 0:
                    os.fchown(f.fileno(), 0, 0)
                f.flush()
                os.fsync(f.fileno())
            os.link(tmp, p)
            io.fsync_dir(p.parent)
        finally:
            Path(tmp).unlink(missing_ok=True)


def verify_bundles(root):
    for bundle in ('h713-hdmi', 'h713-hdmi-video'):
        parent = 'usr/lib/' + bundle
        manifest = io.path(root, parent + '/SHA256SUMS').read_bytes()
        for name, expected in io.table(manifest).items():
            if sha(io.path(root, parent + '/' + name).read_bytes()) != expected:
                raise RuntimeError('bundle differs: ' + parent + '/' + name)


def identity(root, boot):
    io.identity(root)
    if (root / 'proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise RuntimeError('boot changed')
    if (root / 'sys/block/mmcblk0/device/cid').read_text().strip() != '15010038475446345208604bbe691991':
        raise RuntimeError('wrong eMMC')
    for name in ('h713-hdmi-capture.service', 'h713-hdmi-prepare.service'):
        for parent in ('etc/systemd/system', 'run/systemd/system'):
            p = root / parent / (name + '.d')
            if p.exists() or p.is_symlink():
                raise RuntimeError('unreviewed drop-in: ' + str(p))
    for parent in ('etc/systemd/system', 'run/systemd/system'):
        for p in (root / parent).glob('*.wants/h713-hdmi-prepare.service'):
            raise RuntimeError('independently enabled prepare: ' + str(p))


def switch(root, package, boot, arm, apply=False):
    identity(root, boot)
    raw = (package / 'pins.json').read_bytes()
    if sha(raw) != PINS:
        raise RuntimeError('unreviewed package pins')
    pins = json.loads(raw)
    targets = list(pins['baseline'])
    if any(set(p) != set(targets) for p in pins.values()):
        raise RuntimeError('inconsistent target scope')
    desired = {n: io.path(package, arm + '/' + n).read_bytes() if pins[arm][n] else None for n in targets}
    if {n: sha(v) for n, v in desired.items()} != pins[arm]:
        raise RuntimeError('payload differs')
    state = io.path(root, io.STATE)
    fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if list(state.glob('*/INCOMPLETE')):
            raise RuntimeError('incomplete transaction exists')
        before = {n: read(root, n) for n in targets}
        hashes = {n: sha(v) for n, v in before.items()}
        matches = [name for name, pin in pins.items() if hashes == pin]
        if len(matches) != 1:
            raise RuntimeError('installed files are not an exact recognized arm')
        verify_bundles(root)
        result = dict(schema='h713-matched-startup-switch-v1', boot_id=boot,
                      before=matches[0], after=arm, targets=targets,
                      services_restarted=False, modules_reloaded=False, applied=False)
        if not apply or matches[0] == arm:
            return result
        backup = state / ('matched-trace-' + uuid.uuid4().hex)
        backup.mkdir(mode=0o700)
        io.save(backup / 'INCOMPLETE', b'pending\n')
        for index, name in enumerate(targets):
            if before[name] is not None:
                io.save(backup / str(index), before[name])
        result['backup'] = str(backup)
        io.save(backup / 'transaction.json', (json.dumps(dict(result, before_hashes=hashes, after_hashes=pins[arm]), indent=2)+'\n').encode())
        io.fsync_dir(backup)
        try:
            for name in targets:
                if before[name] != desired[name]:
                    put(root, name, desired[name], hashes[name])
            if {n: sha(read(root, n)) for n in targets} != pins[arm]:
                raise RuntimeError('installed readback differs')
            verify_bundles(root)
        except BaseException:
            # Restore every changed target, including the operation that failed.
            for name in reversed(targets):
                current = sha(read(root, name))
                if current == hashes[name]:
                    continue
                if current != pins[arm][name]:
                    raise RuntimeError('concurrent mutation; incomplete backup retained')
                put(root, name, before[name], current)
            io.save(backup / 'ROLLED_BACK', b'complete\n')
            (backup / 'INCOMPLETE').unlink()
            io.fsync_dir(backup)
            raise
        io.save(backup / 'COMMITTED', b'complete\n')
        (backup / 'INCOMPLETE').unlink()
        io.fsync_dir(backup)
        io.fsync_dir(state)
        result['applied'] = True
        return result
    finally:
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/'))
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--boot', required=True)
    parser.add_argument('--arm', choices=('original', 'optimized'), required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(switch(args.root, args.package, args.boot, args.arm, args.apply), indent=2))
