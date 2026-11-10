#!/usr/bin/env python3
"""Install an exact AIC8800 startup delta; no module/service start or stop."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('guard_io', HERE/'sync-shutdown-guard.py' if (HERE/'sync-shutdown-guard.py').exists() else HERE.parent/'hdmi/sync-shutdown-guard.py')
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)
spec = importlib.util.spec_from_file_location('parallel_io', HERE/'install-parallel-capture.py' if (HERE/'install-parallel-capture.py').exists() else HERE.parent/'hdmi/install-parallel-capture.py')
parallel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parallel)
OWNER = 'h713-aic8800-modules.service'
TARGETS = ('etc/modules-load.d/aic8800.conf', 'etc/systemd/system/h713-hotspot.service',
           'etc/systemd/system/h713-bt-attach.service', 'etc/modprobe.d/h713-aic8800-startup.conf',
           'etc/systemd/system/'+OWNER, 'etc/systemd/system/multi-user.target.wants/'+OWNER)
BEFORE = ('bd065eeb24c8c187efb10c97da84d3b32ed55b71b9936dedb98f4331b989cc19',
          'e034a3529650597cd3243f43027f9bf847852d1a446daf4a99edd642b42a35ee',
          '16e3f737f3f135ffc94c18fe15db904f97bf892b1b284142aaa6d02b22456822', None, None, None)
MODULES = ('aic8800_bsp', 'aic8800_fdrv', 'aic8800_btlpm')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def path(root, name):
    p = Path(name)
    return io.path(root, str(p.parent))/p.name


def entry(root, name):
    p = path(root, name)
    if p.is_symlink():
        s = p.lstat()
        if (s.st_uid, s.st_gid) != (0, 0):
            raise RuntimeError('link metadata differs: '+name)
        return dict(symlink=os.readlink(p))
    if not p.exists():
        return None
    if not p.is_file() or io.metadata(p) != parallel.ATTRS:
        raise RuntimeError('metadata differs: '+name)
    return dict(sha256=digest(p.read_bytes()))


def put(root, name, desired, data, expected):
    if entry(root, name) != expected:
        raise RuntimeError('target changed: '+name)
    p = path(root, name)
    if desired is None:
        p.unlink()
        io.fsync_dir(p.parent)
    elif 'symlink' in desired:
        if expected is not None:
            raise RuntimeError('link replacement is outside update scope')
        os.symlink(desired['symlink'], p)
        io.fsync_dir(p.parent)
    else:
        if digest(data) != desired['sha256']:
            raise RuntimeError('bad payload')
        parallel.atomic(p, data, expected['sha256'] if expected else None)


def identity(root, boot):
    io.identity(root)
    if (root/'proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise RuntimeError('boot changed')
    if (root/'sys/block/mmcblk0/device/cid').read_text().strip() != '15010038475446345208604bbe691991':
        raise RuntimeError('wrong eMMC')
    for unit in (OWNER, 'h713-hotspot.service', 'h713-bt-attach.service'):
        for directory in ('etc/systemd/system', 'run/systemd/system', 'usr/lib/systemd/system'):
            p = root/directory/(unit+'.d')
            if p.exists() or p.is_symlink():
                raise RuntimeError('unreviewed drop-in: '+str(p))
    # Explicit aliases are now gated. Reject any second global load request.
    sources = [root/'etc/modules']
    for directory in ('etc/modules-load.d', 'run/modules-load.d', 'usr/lib/modules-load.d'):
        sources.extend((root/directory).glob('*.conf'))
    for p in sources:
        if p == root/TARGETS[0] or not p.exists():
            continue
        for line in p.read_text().splitlines():
            if line.split('#', 1)[0].strip().replace('-', '_') in MODULES:
                raise RuntimeError('another global AIC load request: '+str(p))


def load(package, manifest_sha):
    raw = (package/'manifest.json').read_bytes()
    if digest(raw) != manifest_sha:
        raise RuntimeError('manifest differs')
    m = json.loads(raw)
    expected = [dict(sha256=h) if h else None for h in BEFORE]
    if m['schema'] != 'h713-parallel-wifi-v1' or m['targets'] != list(TARGETS) or m['before'] != expected:
        raise RuntimeError('unreviewed update scope/baseline')
    if len(m['after']) != len(TARGETS) or m['after'][-1] != dict(symlink='../'+OWNER):
        raise RuntimeError('unexpected enablement link')
    data = [io.path(package, n).read_bytes() for n in TARGETS[:-1]]+[None]
    if any(m['after'][i] != dict(sha256=digest(v)) for i, v in enumerate(data[:-1])):
        raise RuntimeError('package payload differs')
    return m, data


def install(root, package, boot, manifest_sha, apply=False):
    m, data = load(package, manifest_sha)
    identity(root, boot)
    state = io.path(root, io.STATE)
    fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if list(state.glob('*/INCOMPLETE')):
            raise RuntimeError('incomplete transaction exists')
        now = [entry(root, n) for n in TARGETS]
        if now != m['before']:
            raise RuntimeError('installed baseline differs')
        before_data = [path(root, n).read_bytes() if e else None for n, e in zip(TARGETS, now)]
        result = dict(schema=m['schema'], boot_id=boot, applied=False, services_restarted=False,
                      modules_reloaded=False, before=now, after=m['after'], targets=list(TARGETS))
        if not apply:
            return result
        backup = state/('parallel-wifi-'+uuid.uuid4().hex)
        backup.mkdir(mode=0o700)
        for i, value in enumerate(before_data):
            if value is not None:
                io.save(backup/str(i), value)
        io.save(backup/'manifest.json', (package/'manifest.json').read_bytes())
        io.save(backup/'INCOMPLETE', b'pending startup configuration update\n')
        io.fsync_dir(backup)
        io.fsync_dir(state)
        try:
            for i, name in enumerate(TARGETS):
                identity(root, boot)
                put(root, name, m['after'][i], data[i], now[i])
            if [entry(root, n) for n in TARGETS] != m['after']:
                raise RuntimeError('readback differs')
        except BaseException:
            restore(root, backup, boot, manifest_sha)
            raise
        io.save(backup/'COMMITTED', b'installed; daemon-reload required\n')
        (backup/'INCOMPLETE').unlink()
        io.fsync_dir(backup)
        return dict(result, applied=True, backup=str(backup))
    finally:
        os.close(fd)


def restore(root, backup, boot, manifest_sha):
    identity(root, boot)
    if backup.parent != root/io.STATE or backup.is_symlink() or not backup.name.startswith('parallel-wifi-'):
        raise RuntimeError('invalid rollback location')
    raw = (backup/'manifest.json').read_bytes()
    if digest(raw) != manifest_sha:
        raise RuntimeError('rollback manifest differs')
    m = json.loads(raw)
    expected = [dict(sha256=h) if h else None for h in BEFORE]
    if m['targets'] != list(TARGETS) or m['before'] != expected:
        raise RuntimeError('rollback scope differs')
    for i in reversed(range(len(TARGETS))):
        name = TARGETS[i]
        now = entry(root, name)
        if now == m['before'][i]:
            continue
        if now != m['after'][i]:
            raise RuntimeError('foreign mutation; incomplete backup retained')
        data = (backup/str(i)).read_bytes() if m['before'][i] else None
        put(root, name, m['before'][i], data, now)
    if [entry(root, n) for n in TARGETS] != m['before']:
        raise RuntimeError('rollback readback differs')
    if not (backup/'ROLLED_BACK').exists():
        io.save(backup/'ROLLED_BACK', b'original configuration restored; daemon-reload required\n')
    (backup/'INCOMPLETE').unlink(missing_ok=True)
    io.fsync_dir(backup)
    return dict(rolled_back=True, services_restarted=False, modules_reloaded=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/'))
    parser.add_argument('--package', type=Path, default=HERE)
    parser.add_argument('--boot', required=True)
    parser.add_argument('--manifest-sha', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if args.rollback:
        if not args.apply:
            parser.error('rollback requires --apply')
        state = io.path(args.root, io.STATE)
        fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = restore(args.root, args.rollback, args.boot, args.manifest_sha)
        finally:
            os.close(fd)
    else:
        result = install(args.root, args.package, args.boot, args.manifest_sha, args.apply)
    print(json.dumps(result, indent=2))
