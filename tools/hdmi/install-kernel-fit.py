#!/usr/bin/env python3
"""Guarded kernel FIT update together with the startup script that pins it.

The startup script refuses any FIT whose size differs from the one it pins
(the "image" stage), so the FIT and the script change as one transaction:

  1. back up every copy (FAT FIT + script, both bundle cmd/scr/SHA256SUMS),
  2. update the inactive bundle copies,
  3. stage the FIT and script on the FAT as *.kfit-new, fsync, read back,
  4. rename the FIT, then the script (the only window where the pair is
     mismatched is between these two renames), sync, verify every copy.

Any failure restores every original. Preview by default; --apply installs;
--rollback BACKUP restores exactly. No reboot, service, module, proper or RTC
operation; the caller owns the boot. Out-of-tree modules are not touched: the
bundle builder refuses a candidate whose Module.symvers or release differs.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

MODEL = 'HY200 QZ713DF_A1 (Allwinner H713)'
STATE = 'var/lib/h713-hdmi-startup'
FAT = 'mnt/boot'
BUNDLES = ('usr/lib/h713-hdmi', 'usr/lib/h713-hdmi-health')
SCRIPT_NAMES = ('h713-hdmi.cmd', 'h713-hdmi.scr')
PREFIX = 'kernel-fit-'
SUFFIX = '.kfit-new'
SCHEMA = 'h713-kernel-fit-v1'


def sha(data): return hashlib.sha256(data).hexdigest()


def need(ok, message):
    if not ok: raise RuntimeError(message)


def under(root, relative):
    p = root
    for part in Path(relative).parts:
        need(part not in ('..', '/'), 'unsafe path: '+relative)
        p = p/part
        need(not p.is_symlink(), 'symlink refused: '+str(p))
    return p


def fsync_dir(p):
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def save(p, data):
    with p.open('xb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())


def stage(p, data):
    """Write <p>.kfit-new completely and read it back; returns the staged path."""
    tmp = p.with_name(p.name+SUFFIX)
    need(not tmp.exists(), 'unfinished staged file: '+str(tmp))
    save(tmp, data)
    need(tmp.read_bytes() == data, 'staging readback failed: '+str(p))
    return tmp


def replace(p, data):
    """Stage then rename over p (keeps p's mode on the root filesystem)."""
    mode = p.stat().st_mode & 0o7777
    tmp = stage(p, data)
    try:
        os.chmod(tmp, mode)
    except PermissionError:
        pass  # vfat: mode comes from the mount options
    os.replace(tmp, p);fsync_dir(p.parent)
    need(p.read_bytes() == data, 'readback mismatch: '+str(p))


def fat_mounted(root):
    """The FAT must be p2 mounted at /mnt/boot (only checked on the real root)."""
    if root != Path('/'): return True
    out = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', '/'+FAT], capture_output=True, text=True)
    return out.stdout.strip() == '/dev/mmcblk0p2'


def load_bundle(bundle):
    m = json.loads((bundle/'manifest.json').read_text())
    need(m.get('schema') == SCHEMA, 'unknown bundle schema')
    for name, digest in m['files'].items():
        need(sha((bundle/name).read_bytes()) == digest, 'bundle file mismatch: '+name)
    need(set(m['files']) >= {'h713-kernel.fit', *SCRIPT_NAMES}, 'bundle incomplete')
    for key in ('h713-kernel.fit', *SCRIPT_NAMES):
        need(m['baseline'][key] != m['files'][key], 'candidate equals baseline: '+key)
    need(m['checks'] == {'module_symvers_equal': True, 'kernel_release_equal': True,
                         'config_diff': ['CONFIG_LEGACY_PTYS', 'CONFIG_LEGACY_PTY_COUNT']},
         'bundle checks missing')
    return m


def targets(root):
    """Every file the transaction owns, FAT activation pair last (FIT, then script)."""
    files = []
    for b in BUNDLES:
        files += [b+'/'+n for n in SCRIPT_NAMES]+[b+'/SHA256SUMS']
    return files+[FAT+'/h713-kernel.fit', FAT+'/h713-hdmi.scr']


def kind(relative):
    name = Path(relative).name
    return 'h713-kernel.fit' if name.endswith('.fit') else name


def sums(data):
    out = {}
    for line in data.decode().splitlines():
        digest, name = line.split('  ', 1)
        out[name.removeprefix('./')] = digest
    return out


def state(root, m):
    """'baseline' or 'candidate' only when every copy agrees."""
    need(fat_mounted(root), 'boot FAT not mounted at /mnt/boot from p2')
    seen = set()
    for b in BUNDLES:
        listed = sums(under(root, b+'/SHA256SUMS').read_bytes())
        for name, digest in listed.items():
            need(sha(under(root, b+'/'+name).read_bytes()) == digest, 'manifest mismatch: '+b+'/'+name)
    for rel in targets(root):
        k = kind(rel)
        if k == 'SHA256SUMS': continue
        digest = sha(under(root, rel).read_bytes())
        seen.add({m['baseline'][k]: 'baseline', m['files'][k]: 'candidate'}.get(digest, 'foreign:'+rel))
    for b in BUNDLES:
        listed = sums(under(root, b+'/SHA256SUMS').read_bytes())
        for n in SCRIPT_NAMES:
            seen.add({m['baseline'][n]: 'baseline', m['files'][n]: 'candidate'}.get(listed.get(n), 'foreign:'+b))
    need(len(seen) == 1 and not next(iter(seen)).startswith('foreign'),
         'kernel/script copies disagree: '+str(sorted(seen)))
    return seen.pop()


def new_sums(data, digests):
    lines = []
    for line in data.decode().splitlines():
        digest, name = line.split('  ', 1)
        short = name.removeprefix('./')
        lines.append((digests.get(short, digest))+'  '+name)
    return ('\n'.join(lines)+'\n').encode()


def identity(root, boot):
    need((root/'proc/device-tree/model').read_text().strip('\0\n') == MODEL, 'wrong board')
    need((root/'proc/sys/kernel/random/boot_id').read_text().strip() == boot, 'boot changed')
    for d in (STATE, FAT, *BUNDLES): need(under(root, d).is_dir(), 'missing directory: '+d)


def apply_files(root, wanted, originals):
    """Write wanted{rel: data}: bundle copies, then stage+rename FIT, then script."""
    order = targets(root)
    fat = [r for r in order if r.startswith(FAT+'/')]
    try:
        for rel in order:
            if rel not in fat and under(root, rel).read_bytes() != wanted[rel]:
                replace(under(root, rel), wanted[rel])
        staged = {rel: stage(under(root, rel), wanted[rel]) for rel in fat
                  if under(root, rel).read_bytes() != wanted[rel]}
        subprocess.run(['sync'], check=True, timeout=120)
        for rel in fat:                     # FIT first, script last
            if rel in staged:
                os.replace(staged[rel], under(root, rel));fsync_dir(under(root, FAT))
        subprocess.run(['sync'], check=True, timeout=120)
        for rel in order:
            need(under(root, rel).read_bytes() == wanted[rel], 'readback mismatch: '+rel)
    except BaseException:
        for rel in reversed(order):
            p = under(root, rel)
            p.with_name(p.name+SUFFIX).unlink(missing_ok=True)
            if p.read_bytes() != originals[rel]:
                replace(p, originals[rel])
        subprocess.run(['sync'], check=True, timeout=120)
        raise


def run(root, bundle, boot, apply=False, rollback=None):
    m = load_bundle(bundle)
    identity(root, boot)
    fd = os.open(under(root, STATE), os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(not list(under(root, STATE).glob('*/INCOMPLETE')), 'unfinished transaction exists')
        for rel in targets(root):
            p = under(root, rel);need(not p.with_name(p.name+SUFFIX).exists(), 'staged file left: '+rel)
        now = state(root, m)
        want_from, want_to = ('candidate', 'baseline') if rollback else ('baseline', 'candidate')
        need(now == want_from, 'installed pair is '+now+', expected '+want_from)
        originals = {rel: under(root, rel).read_bytes() for rel in targets(root)}
        if rollback:
            old = Path(rollback)
            need(old.parent == under(root, STATE) and old.name.startswith(PREFIX) and not old.is_symlink(),
                 'invalid backup')
            need((old/'COMMITTED').exists(), 'backup is not a committed install')
            index = json.loads((old/'files.json').read_text())
            need(sorted(index) == sorted(targets(root)), 'backup scope differs')
            wanted = {rel: (old/index[rel]).read_bytes() for rel in targets(root)}
            for rel, data in wanted.items():
                k = kind(rel)
                if k != 'SHA256SUMS': need(sha(data) == m['baseline'][k], 'backup is not the baseline: '+rel)
        else:
            data = {k: (bundle/k).read_bytes() for k in ('h713-kernel.fit', *SCRIPT_NAMES)}
            wanted = {}
            for rel in targets(root):
                k = kind(rel)
                wanted[rel] = (new_sums(originals[rel], {n: m['files'][n] for n in SCRIPT_NAMES})
                               if k == 'SHA256SUMS' else data[k])
        result = dict(schema=SCHEMA+'-result', boot_id=boot, state=now, apply=apply,
                      rollback=str(rollback) if rollback else None,
                      would={rel: sha(d) for rel, d in wanted.items()})
        if not apply: return result
        backup = under(root, STATE)/(PREFIX+('rollback-' if rollback else '')+uuid.uuid4().hex)
        backup.mkdir(mode=0o700)
        index = {}
        for i, rel in enumerate(targets(root)):
            save(backup/('file-%d' % i), originals[rel]);index[rel] = 'file-%d' % i
        save(backup/'files.json', (json.dumps(index, indent=2)+'\n').encode())
        save(backup/'INCOMPLETE', b'kernel FIT/script transaction in progress; do not reboot\n')
        fsync_dir(backup);fsync_dir(backup.parent)
        try:
            apply_files(root, wanted, originals)
            identity(root, boot)
            need(state(root, m) == want_to, 'state after update differs')
        except BaseException:
            save(backup/'RESTORED', b'originals restored\n');(backup/'INCOMPLETE').unlink();fsync_dir(backup)
            raise
        result.update(applied=True, backup=str(backup), state=want_to)
        save(backup/'receipt.json', (json.dumps(result, indent=2)+'\n').encode())
        save(backup/'COMMITTED', b'verified\n');(backup/'INCOMPLETE').unlink();fsync_dir(backup)
        return result
    finally:
        os.close(fd)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=Path('/'))
    p.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--rollback', type=Path)
    a = p.parse_args()
    need(a.root != Path('/') or os.geteuid() == 0, 'root required')
    print(json.dumps(run(a.root.resolve(), a.bundle.resolve(), a.boot_id, a.apply, a.rollback), indent=2))
