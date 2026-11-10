#!/usr/bin/env python3
"""Guarded early-DDC experiment install; preview by default.

Replaces h713-hdmi-session.py and h713-hdmi-signal.py in /usr/lib/h713-hdmi
(both keep their installed behaviour without --early-ddc), updates that
bundle's SHA256SUMS, then activates the experiment LAST with one drop-in on
h713-hdmi-prepare.service. --rollback BACKUP restores the exact files and
removes the drop-in. Never starts, stops or restarts a service; the change
takes effect on the next boot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

BUNDLE = Path('/usr/lib/h713-hdmi')
DROPIN = Path('/etc/systemd/system/h713-hdmi-prepare.service.d/50-early-ddc.conf')
STATE = Path('/var/lib/h713-hdmi-startup')
NAMES = ('h713-hdmi-session.py', 'h713-hdmi-signal.py')
MODEL = 'HY200 QZ713DF_A1 (Allwinner H713)'
CID = '15010038475446345208604bbe691991'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def save(path, data):
    with path.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def syncdir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data):
    need(not path.is_symlink(), 'unexpected symlink: ' + str(path))
    tmp = path.with_name(path.name + '.early-new')
    tmp.unlink(missing_ok=True)
    save(tmp, data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    syncdir(path.parent)
    need(path.read_bytes() == data, 'readback mismatch: ' + str(path))


def sums(path):
    table = {}
    for line in path.read_text().splitlines():
        digest, name = line.split('  ', 1)
        table[name.removeprefix('./')] = (digest, name)
    return table


def manifest_with(digests):
    lines = []
    for line in (BUNDLE / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        short = name.removeprefix('./')
        lines.append((digests.get(short, digest)) + '  ' + name)
    return ('\n'.join(lines) + '\n').encode()


def state(m):
    table = sums(BUNDLE / 'SHA256SUMS')
    for short, (digest, _) in table.items():
        need(sha((BUNDLE / short).read_bytes()) == digest, 'manifest mismatch: ' + short)
    have = {n: table[n][0] for n in NAMES}
    dropin = DROPIN.read_bytes() if DROPIN.exists() else None
    if have == m['baseline'] and dropin is None:
        return 'baseline'
    if have == m['candidate'] and dropin is not None and sha(dropin) == m['dropin']:
        return 'candidate'
    raise RuntimeError('installed session/signal/drop-in state is neither baseline nor candidate')


def identity(boot):
    text = lambda p: Path(p).read_text().strip('\0\n')
    need(text('/proc/sys/kernel/random/boot_id') == boot, 'boot changed')
    need(text('/proc/device-tree/model') == MODEL, 'wrong board')
    need(text('/sys/class/block/mmcblk0/device/cid') == CID, 'wrong eMMC')
    need(os.stat('/').st_dev == os.stat('/dev/mmcblk0p26').st_rdev, 'root is not p26')


def run(bundle_dir, boot, apply=False, rollback=None):
    m = json.loads((bundle_dir / 'manifest.json').read_text())
    need(m.get('schema') == 'h713-early-ddc-v1', 'unknown bundle schema')
    for name, digest in m['files'].items():
        need(sha((bundle_dir / name).read_bytes()) == digest, 'bundle file mismatch: ' + name)
    identity(boot)
    current = state(m)
    want_from = 'candidate' if rollback else 'baseline'
    need(current == want_from, 'state is ' + current + ', expected ' + want_from)
    result = dict(schema='h713-early-ddc-result-v1', boot_id=boot, state=current, apply=apply,
                  rollback=str(rollback) if rollback else None)
    if not apply:
        result['would'] = 'restore baseline' if rollback else 'install candidate + drop-in'
        return result
    need(STATE.is_dir() and not list(STATE.glob('*/INCOMPLETE')), 'state directory missing or unfinished transaction')
    if rollback:
        old = Path(rollback)
        need(old.parent == STATE and old.name.startswith('early-ddc-'), 'invalid backup')
        targets = {str(BUNDLE / n): (old / n).read_bytes() for n in NAMES}
        targets[str(BUNDLE / 'SHA256SUMS')] = (old / 'SHA256SUMS').read_bytes()
        need({n: sha(targets[str(BUNDLE / n)]) for n in NAMES} == m['baseline'], 'backup is not the baseline')
    else:
        data = {n: (bundle_dir / n).read_bytes() for n in NAMES}
        targets = {str(BUNDLE / n): d for n, d in data.items()}
        targets[str(BUNDLE / 'SHA256SUMS')] = manifest_with({n: sha(d) for n, d in data.items()})
    backup = STATE / ('early-ddc-' + uuid.uuid4().hex)
    backup.mkdir(mode=0o700)
    for n in NAMES + ('SHA256SUMS',):
        save(backup / n, (BUNDLE / n).read_bytes())
    save(backup / 'INCOMPLETE', b'early-ddc transaction; do not reboot\n')
    syncdir(backup)
    syncdir(STATE)
    try:
        if rollback:
            # Deactivate FIRST, then restore files.
            if DROPIN.exists():
                DROPIN.unlink()
                syncdir(DROPIN.parent)
            for path, d in targets.items():
                atomic(Path(path), d)
        else:
            for path, d in targets.items():
                atomic(Path(path), d)
            DROPIN.parent.mkdir(mode=0o755, exist_ok=True)
            atomic(DROPIN, (bundle_dir / '50-early-ddc.conf').read_bytes())  # activation last
        subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=60)
        subprocess.run(['sync'], check=True, timeout=60)
        need(state(m) == ('baseline' if rollback else 'candidate'), 'post-install state differs')
    except BaseException:
        DROPIN.unlink(missing_ok=True)
        for n in NAMES + ('SHA256SUMS',):
            atomic(BUNDLE / n, (backup / n).read_bytes())
        subprocess.run(['systemctl', 'daemon-reload'], check=False, timeout=60)
        save(backup / 'RESTORED', b'restored pre-transaction files\n')
        (backup / 'INCOMPLETE').unlink()
        raise
    result.update(applied=True, backup=str(backup), state='baseline' if rollback else 'candidate')
    save(backup / 'receipt.json', (json.dumps(result, indent=2) + '\n').encode())
    save(backup / 'COMMITTED', b'verified\n')
    (backup / 'INCOMPLETE').unlink()
    syncdir(backup)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--boot', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', type=Path)
    a = parser.parse_args()
    need(os.geteuid() == 0, 'root required')
    print(json.dumps(run(Path(__file__).resolve().parent, a.boot, a.apply, a.rollback), indent=2))
