#!/usr/bin/env python3
"""Install the kmsg-cursor session update; no service operations.

Replaces h713-hdmi-session.py, whose stop() verified the DSP/TVFE restore by
requiring the post-rmmod dmesg to start with the pre-rmmod dmesg. Once the
kernel ring is full (CPU_COMM stress fills it) that check fails, the receiver
hold is retained and the H2 guard turns reboot into power-off. The new script
reads the restore records from a /dev/kmsg cursor taken before rmmod. Updates
the bundle manifest entry only. Pins the installed original, the capture unit
and the parallel prepare unit. Preview by default; --apply installs;
--rollback BACKUP restores exactly.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import uuid

spec = importlib.util.spec_from_file_location('guard_io', Path(__file__).with_name('sync-shutdown-guard.py'))
io = importlib.util.module_from_spec(spec);spec.loader.exec_module(io)
NAMES = ('h713-hdmi-session.py', 'SHA256SUMS')
OLD = ('06ab1e7a68da80f3eaff6689741c3f9f21c1d9171505d0ba9493bebc4060ec24',)
NEW = ('69c67f723458987c40fa511967a579a53491917eae2b1f96bab460c30637894a',)
UNIT_SHA = '35883a89cc756942ed1efc62e698b9940f1a8368c40ecd7713a95b5676603aae'
PREPARE_SHA = '64d4ecd6f4ec570a89d7cd87bb98820e99b05f8ae358d3ef89522a0ee3993b28'
PREFIX = 'session-kmsg-'


def sha(data): return hashlib.sha256(data).hexdigest()
def target(root, name): return io.path(root, io.BACKEND+'/'+name)


def identity(root, boot):
    io.identity(root)
    if (root/'proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise RuntimeError('boot ID changed')
    if sha(io.path(root, 'etc/systemd/system/h713-hdmi-capture.service').read_bytes()) != UNIT_SHA:
        raise RuntimeError('capture unit differs from measured RC')
    for base in ('etc/systemd/system/', io.BACKEND+'/'):
        p = io.path(root, base+'h713-hdmi-prepare.service')
        if p.is_symlink() or sha(p.read_bytes()) != PREPARE_SHA:
            raise RuntimeError('parallel prepare unit differs from the installed stage')


def current(root):
    data = [target(root, name).read_bytes() for name in NAMES]
    for name in NAMES:
        attrs = io.metadata(target(root, name))
        if attrs != {'mode': 0o644, 'uid': 0, 'gid': 0}:
            raise RuntimeError('unexpected file metadata: '+name)
    return data


def candidate_manifest(before):
    entries = io.table(before)
    lines = before.decode().splitlines(keepends=True)
    for name, old, new in zip(NAMES, OLD, NEW):
        found = [key for key in entries if str(Path(key)) == name]
        if len(found) != 1 or entries[found[0]] != old:
            raise RuntimeError('missing or wrong original manifest entry: '+name)
        line = old+'  '+found[0]
        matches = [i for i, value in enumerate(lines) if value.rstrip('\r\n') == line]
        if len(matches) != 1: raise RuntimeError('ambiguous original manifest entry')
        index = matches[0];lines[index] = lines[index].replace(old, new, 1)
    return ''.join(lines).encode()


def preview(root, bundle, boot, before_manifest):
    identity(root, boot)
    data = current(root)
    if tuple(map(sha, data[:1])) != OLD or sha(data[1]) != before_manifest:
        raise RuntimeError('unexpected installed scripts/manifest')
    io.verify_generation(root, data[1])
    after = [io.path(bundle, io.BACKEND+'/'+name).read_bytes() for name in NAMES[:1]]
    if tuple(map(sha, after)) != NEW: raise RuntimeError('payload checksum mismatch')
    after.append(candidate_manifest(data[1]))
    return data, after


def install(root, bundle, boot, before_manifest, apply=False):
    identity(root, boot)
    fd = os.open(io.path(root, io.STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if list((root/io.STATE).glob(PREFIX+'*/INCOMPLETE')):
            raise RuntimeError('incomplete session-kmsg transaction; inspect or roll back first')
        before, after = preview(root, bundle, boot, before_manifest)
        if not apply:
            return {'phase':'would-install', 'targets':list(NAMES),
                    'before':list(map(sha,before)), 'after':list(map(sha,after))}
        backup = root/io.STATE/(PREFIX+uuid.uuid4().hex);backup.mkdir(mode=0o700)
        record = {'schema':'h713-session-kmsg-install-v1', 'boot_id':boot,
                  'targets':list(NAMES), 'before':list(map(sha,before)),
                  'after':list(map(sha,after)),
                  'metadata':[io.metadata(target(root,name)) for name in NAMES]}
        for i, data in enumerate(before): io.save(backup/str(i), data)
        io.save(backup/'record.json', (json.dumps(record,indent=2)+'\n').encode())
        io.save(backup/'INCOMPLETE', b'Inspect or roll back before another update or shutdown.\n')
        io.fsync_dir(backup);io.fsync_dir(backup.parent)
        for i, name in enumerate(NAMES):
            identity(root, boot)
            io.atomic(target(root,name),after[i],record['metadata'][i],record['before'][i])
        if current(root) != after: raise RuntimeError('installation readback failed')
        io.verify_generation(root, after[1])
        io.save(backup/'COMMITTED',b'kmsg-cursor session installed; no services operated\n')
        (backup/'INCOMPLETE').unlink();io.fsync_dir(backup)
        return {'phase':'installed','backup':str(backup),'record':record,'services_changed':False}
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
        record = json.loads(io.path(root,relative+'/record.json').read_text())
        if (record['schema']!='h713-session-kmsg-install-v1' or record['targets']!=list(NAMES)
                or tuple(record['before'][:1])!=OLD or tuple(record['after'][:1])!=NEW):
            raise RuntimeError('invalid rollback scope')
        before = [io.path(root, relative+'/'+str(i)).read_bytes() for i in range(len(NAMES))]
        if list(map(sha,before)) != record['before'] or sha(candidate_manifest(before[1])) != record['after'][1]:
            raise RuntimeError('rollback data corrupted')
        now = current(root)
        if any(sha(data) not in (record['before'][i],record['after'][i]) for i,data in enumerate(now)):
            raise RuntimeError('foreign target change; refusing rollback')
        ignored = set(NAMES[:1])
        for name, digest in io.table(before[1]).items():
            if str(Path(name)) not in ignored and sha(target(root,name).read_bytes()) != digest:
                raise RuntimeError('unrelated backend changed: '+name)
        if not apply: return {'phase':'would-rollback','backup':str(backup)}
        for i,name in enumerate(NAMES):
            identity(root,boot)
            io.atomic(target(root,name),before[i],record['metadata'][i],sha(now[i]))
        io.verify_generation(root,before[1])
        if not (backup/'ROLLED_BACK').exists():io.save(backup/'ROLLED_BACK',b'session and manifest restored\n')
        (backup/'INCOMPLETE').unlink(missing_ok=True);io.fsync_dir(backup)
        return {'phase':'rolled-back','backup':str(backup),'services_changed':False}
    finally:
        os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/'))
    parser.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--boot-id',required=True)
    parser.add_argument('--before-manifest-sha')
    parser.add_argument('--rollback',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();root=args.root.resolve()
    if args.rollback:
        result=rollback(root,args.rollback.absolute(),args.boot_id,args.apply)
    else:
        if not args.before_manifest_sha:parser.error('--before-manifest-sha is required for install/preview')
        result=install(root,args.bundle.resolve(),args.boot_id,args.before_manifest_sha,args.apply)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
