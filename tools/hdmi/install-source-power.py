#!/usr/bin/env python3
"""Install exactly the power-reporting module, retry script and two manifests.

Disk changes only. Never restart services or unload a live receiver module.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import uuid

spec = importlib.util.spec_from_file_location('io_guard', Path(__file__).with_name('sync-shutdown-guard.py'))
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)
TARGETS = ('usr/lib/h713-hdmi-video/h713-hdmi-v4l2.ko',
           'usr/lib/h713-hdmi/h713-hdmi-readvertise.py',
           'usr/lib/h713-hdmi-video/SHA256SUMS', 'usr/lib/h713-hdmi/SHA256SUMS')
ATTRS = dict(mode=0o644, uid=0, gid=0)
BACKUP_PREFIX = 'source-power-'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(root, name):
    p = io.path(root, name)
    if io.metadata(p) != ATTRS or not p.is_file():
        raise RuntimeError('unexpected target metadata: ' + name)
    return p.read_bytes()


def verify_bundles(root):
    for bundle in ('h713-hdmi', 'h713-hdmi-video'):
        parent = 'usr/lib/' + bundle
        for name, expected in io.table(read(root, parent + '/SHA256SUMS')).items():
            if sha(io.path(root, parent + '/' + name).read_bytes()) != expected:
                raise RuntimeError('bundle differs: ' + parent + '/' + name)


def install(root, package, boot, manifest_sha, apply=False, rollback=None):
    io.identity(root)
    if (root / 'proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise RuntimeError('boot identity changed')
    if (root / 'sys/block/mmcblk0/device/cid').read_text().strip() != '15010038475446345208604bbe691991':
        raise RuntimeError('eMMC identity changed')
    raw = (package / 'manifest.json').read_bytes()
    if sha(raw) != manifest_sha:
        raise RuntimeError('package manifest changed')
    manifest = json.loads(raw)
    if set(manifest['before']) != set(TARGETS) or set(manifest['after']) != set(TARGETS):
        raise RuntimeError('package scope differs')
    state = io.path(root, io.STATE)
    fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if list(state.glob('*/INCOMPLETE')):
            raise RuntimeError('unfinished transaction exists')
        before = {n: read(root, n) for n in TARGETS}
        expected = manifest['after'] if rollback else manifest['before']
        after_hashes = manifest['before'] if rollback else manifest['after']
        if {n: sha(v) for n, v in before.items()} != expected:
            raise RuntimeError('installed generation differs')
        desired = {n: (rollback / str(i)).read_bytes() if rollback else io.path(package, n).read_bytes()
                   for i, n in enumerate(TARGETS)}
        if {n: sha(v) for n, v in desired.items()} != after_hashes:
            raise RuntimeError('payload differs')
        verify_bundles(root)
        result = dict(boot_id=boot, targets=list(TARGETS), applied=False,
                      services_restarted=False, modules_reloaded=False, rollback=bool(rollback))
        if not apply:
            return result
        backup = state / (BACKUP_PREFIX + uuid.uuid4().hex)
        backup.mkdir(mode=0o700)
        io.save(backup / 'INCOMPLETE', b'pending\n')
        for i, name in enumerate(TARGETS):
            io.save(backup / str(i), before[name])
        io.save(backup / 'transaction.json', json.dumps(dict(before=expected, after=after_hashes), indent=2).encode())
        io.fsync_dir(backup)
        io.fsync_dir(state)
        try:
            for name in TARGETS:
                io.atomic(io.path(root, name), desired[name], ATTRS, expected[name])
            if {n: sha(read(root, n)) for n in TARGETS} != after_hashes:
                raise RuntimeError('readback differs')
            verify_bundles(root)
        except BaseException:
            for name in reversed(TARGETS):
                current = sha(read(root, name))
                if current == expected[name]:
                    continue
                if current != after_hashes[name]:
                    raise RuntimeError('concurrent change; backup retained incomplete')
                io.atomic(io.path(root, name), before[name], ATTRS, current)
            io.save(backup / 'ROLLED_BACK', b'complete\n')
            (backup / 'INCOMPLETE').unlink()
            io.fsync_dir(backup)
            raise
        io.save(backup / 'COMMITTED', b'complete\n')
        (backup / 'INCOMPLETE').unlink()
        io.fsync_dir(backup)
        return dict(result, applied=True, backup=str(backup))
    finally:
        os.close(fd)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('/'))
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--boot', required=True)
    p.add_argument('--manifest-sha', required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--rollback', type=Path)
    a = p.parse_args()
    print(json.dumps(install(a.root, a.package, a.boot, a.manifest_sha, a.apply, a.rollback), indent=2))
