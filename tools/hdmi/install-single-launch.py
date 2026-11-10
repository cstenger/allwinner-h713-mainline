#!/usr/bin/env python3
"""Guarded single display-firmware launch update (U-Boot 0004 + boot script).

Two separate phases, each previewed by default and applied with --apply:

  --phase proper   write the candidate U-Boot proper over the pinned baseline
                   proper. The installed double-launch script is unchanged and
                   still runs on it (the old commands are kept), so this phase
                   is a regression check of the new binary by itself.
  --phase script   switch every installed copy of the startup script and its
                   manifests to `h713_disp auto 0x34 logo comm-trace`, FAT
                   copy last. Refused unless the candidate proper is in place:
                   an older proper parses `comm-trace` as a logo file name.

--rollback BACKUP restores one committed or interrupted transaction. A proper
rollback is refused while the single-launch script is active. Nothing here
reboots, starts services or touches RTC GP6/GP7; the caller owns the boot.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import uuid

CID = '15010038475446345208604bbe691991'
MODEL = 'HY200 QZ713DF_A1 (Allwinner H713)'
CAPACITY = 7818182656
PROPER = 2472017920           # LBA 0x49ac00
PROPER_BYTES = 955904
SPL = (8192, 32768, 'd593ab799b6d422523d67a33c7427c481765e5afac71f065cc2f16e162ce18cf')
ENV = (2480406528, 65536, 'e6a56d4c6f2703c9360c29da4d1e1aec2d35bafd57bc6ca8232896e0296bc3ab')
STATE = Path('/var/lib/h713-hdmi-startup')
FAT = Path('/mnt/boot')
BUNDLES = (Path('/usr/lib/h713-hdmi'), Path('/usr/lib/h713-hdmi-health'))
NAMES = ('h713-hdmi.cmd', 'h713-hdmi.scr')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def save(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def syncdir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data):
    need(not path.is_symlink(), 'unexpected symlink: ' + str(path))
    tmp = path.with_name(path.name + '.single-new')
    need(not tmp.exists(), 'unfinished staged file: ' + str(tmp))
    save(tmp, data)
    need(tmp.read_bytes() == data, 'staging mismatch: ' + str(path))
    os.replace(tmp, path)
    syncdir(path.parent)
    need(path.read_bytes() == data, 'readback mismatch: ' + str(path))


def load_bundle(directory):
    m = json.loads((directory / 'manifest.json').read_text())
    need(m.get('schema') == 'h713-single-launch-v1', 'unknown bundle schema')
    for name, digest in m['files'].items():
        need(sha((directory / name).read_bytes()) == digest, 'bundle file mismatch: ' + name)
    proper = (directory / 'u-boot-proper.itb').read_bytes()
    need(len(proper) == PROPER_BYTES, 'candidate proper size differs')
    need(struct.unpack('>I', proper[:4])[0] == 0xd00dfeed, 'candidate proper is not a FIT')
    need(m['proper']['candidate'] != m['proper']['baseline'], 'candidate equals baseline')
    return m


def read_raw(fd, offset, size):
    # O_DIRECT through dd: never trust the page cache for boot regions.
    return subprocess.check_output(['dd', 'if=/dev/mmcblk0', 'iflag=direct', 'bs=512',
                                    'skip=' + str(offset // 512), 'count=' + str(size // 512),
                                    'status=none'], timeout=60)


def text(path):
    return Path(path).read_text().strip('\0\n')


def partition_of(offset, size):
    for part in sorted(Path('/sys/class/block').glob('mmcblk0p*')):
        start = int(text(part / 'start')) * 512
        end = start + int(text(part / 'size')) * 512
        if start <= offset < end:
            need(offset + size <= end, 'range crosses a partition boundary')
            return part
    raise RuntimeError('range not inside a partition')


def identity(fd, boot):
    need(text('/proc/sys/kernel/random/boot_id') == boot, 'boot changed')
    need(text('/proc/device-tree/model') == MODEL, 'wrong board')
    need(text('/sys/class/block/mmcblk0/device/cid') == CID, 'wrong eMMC')
    info = os.fstat(fd)
    need(stat.S_ISBLK(info.st_mode) and info.st_rdev == os.stat('/dev/mmcblk0').st_rdev, 'wrong device')
    need(struct.unpack('<Q', fcntl.ioctl(fd, 0x80081272, bytes(8)))[0] == CAPACITY, 'capacity differs')
    need(os.stat('/').st_dev == os.stat('/dev/mmcblk0p26').st_rdev, 'root is not p26')
    part = partition_of(PROPER, PROPER_BYTES)
    need(not list((part / 'holders').iterdir()), 'proper partition has holders')
    mounted = {line.split()[2] for line in Path('/proc/self/mountinfo').read_text().splitlines()}
    need(text(part / 'dev') not in mounted, 'proper partition mounted')
    for name, (offset, size, digest) in (('spl', SPL), ('environment', ENV)):
        need(sha(read_raw(fd, offset, size)) == digest, 'protected region changed: ' + name)


def script_files():
    files = {}
    for bundle in BUNDLES:
        for name in NAMES + ('SHA256SUMS',):
            files[str(bundle / name)] = bundle / name
    files[str(FAT / 'h713-hdmi.scr')] = FAT / 'h713-hdmi.scr'
    return files


def script_state(m):
    """Return 'baseline' or 'candidate' only if every copy agrees."""
    need(subprocess.run(['findmnt', '-n', '-o', 'SOURCE', str(FAT)], capture_output=True,
                        text=True).stdout.strip() == '/dev/mmcblk0p2', 'boot FAT not mounted at /mnt/boot from p2')
    seen = set()
    for bundle in BUNDLES:
        sums = {}
        for line in (bundle / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            sums[name.removeprefix('./')] = digest
        for name in sums:
            need(sha((bundle / name).read_bytes()) == sums[name], 'manifest mismatch: ' + str(bundle / name))
        for which in ('baseline', 'candidate'):
            if all(sums.get(n) == m['script'][which][n] for n in NAMES):
                seen.add(which)
                break
        else:
            raise RuntimeError('unknown startup script in ' + str(bundle))
    fat = sha((FAT / 'h713-hdmi.scr').read_bytes())
    seen.add({m['script']['baseline']['h713-hdmi.scr']: 'baseline',
              m['script']['candidate']['h713-hdmi.scr']: 'candidate'}.get(fat, 'foreign'))
    need(len(seen) == 1 and 'foreign' not in seen, 'startup script copies disagree: ' + str(sorted(seen)))
    return seen.pop()


def proper_state(fd, m):
    digest = sha(read_raw(fd, PROPER, PROPER_BYTES))
    for which in ('baseline', 'candidate'):
        if digest == m['proper'][which]:
            return which
    raise RuntimeError('installed proper is neither baseline nor candidate: ' + digest)


def new_manifest(bundle, digests):
    lines = []
    for line in (bundle / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        short = name.removeprefix('./')
        lines.append((digests[short] if short in digests else digest) + '  ' + name)
    return ('\n'.join(lines) + '\n').encode()


def begin(kind, record):
    need(STATE.is_dir() and not STATE.is_symlink(), 'state directory missing/unsafe')
    need(not list(STATE.glob('*/INCOMPLETE')), 'unfinished transaction exists')
    backup = STATE / ('single-launch-' + kind + '-' + uuid.uuid4().hex)
    backup.mkdir(mode=0o700)
    return backup


def finish(backup, record, marker):
    save(backup / 'receipt.json', (json.dumps(record, indent=2) + '\n').encode())
    save(backup / marker, b'verified\n')
    (backup / 'INCOMPLETE').unlink()
    syncdir(backup)


def write_proper(fd, data, pins):
    need(os.pwrite(fd, data, PROPER) == PROPER_BYTES, 'short proper write')
    os.fsync(fd)
    need(read_raw(fd, PROPER, PROPER_BYTES) == data, 'proper readback differs')
    for offset, size, digest in pins:
        need(sha(read_raw(fd, offset, size)) == digest, 'neighbour/GPT/rescue region changed')


def run(bundle_dir, phase, boot, apply=False, rollback=None):
    m = load_bundle(bundle_dir)
    candidate = (bundle_dir / 'u-boot-proper.itb').read_bytes()
    fd = os.open('/dev/mmcblk0', (os.O_RDWR if apply else os.O_RDONLY) | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity(fd, boot)
        pstate = proper_state(fd, m)
        sstate = script_state(m)
        need(not (sstate == 'candidate' and pstate == 'baseline'), 'single-launch script on the old proper')
        result = dict(schema='h713-single-launch-result-v1', boot_id=boot, phase=phase,
                      proper=pstate, script=sstate, apply=apply, rollback=str(rollback) if rollback else None)
        if phase == 'proper':
            want_from, want_to = ('candidate', 'baseline') if rollback else ('baseline', 'candidate')
            need(pstate == want_from, 'proper is ' + pstate + ', expected ' + want_from)
            need(sstate == 'baseline', 'proper changes only with the double-launch script active')
            spans = [(PROPER - 65536, 65536), (PROPER + PROPER_BYTES, 1024 * 1024), (0, 34 * 512),
                     (CAPACITY - 33 * 512, 33 * 512), (0x4A0C00 * 512, 2 * 1024 * 1024)]
            pins = [(o, s, sha(read_raw(fd, o, s))) for o, s in spans]
            result['would'] = 'write ' + want_to + ' proper ' + m['proper'][want_to]
            if not apply:
                return result
            before = read_raw(fd, PROPER, PROPER_BYTES)
            if rollback:
                old = Path(rollback)
                need(old.parent == STATE and old.name.startswith('single-launch-proper-'), 'invalid backup')
                target = (old / 'proper-before.bin').read_bytes()
                need(sha(target) == m['proper']['baseline'], 'backup proper is not the baseline')
            else:
                target = candidate
            backup = begin('proper', result)
            save(backup / 'proper-before.bin', before)
            save(backup / 'INCOMPLETE', b'proper write intent; do not reboot\n')
            syncdir(backup)
            syncdir(STATE)
            try:
                write_proper(fd, target, pins)
                identity(fd, boot)
            except BaseException:
                write_proper(fd, before, pins)
                save(backup / 'RESTORED', b'original proper restored and verified\n')
                (backup / 'INCOMPLETE').unlink()
                syncdir(backup)
                raise
            result.update(applied=True, backup=str(backup), proper=want_to)
            finish(backup, result, 'COMMITTED')
            return result
        # Script phase.
        want_from, want_to = ('candidate', 'baseline') if rollback else ('baseline', 'candidate')
        need(sstate == want_from, 'script is ' + sstate + ', expected ' + want_from)
        need(pstate == 'candidate', 'single-launch script requires the candidate proper')
        files = script_files()
        if rollback:
            old = Path(rollback)
            need(old.parent == STATE and old.name.startswith('single-launch-script-'), 'invalid backup')
            originals = json.loads((old / 'files.json').read_text())
            targets = {path: (old / originals[path]).read_bytes() for path in files}
        else:
            data = {n: (bundle_dir / n).read_bytes() for n in NAMES}
            digests = {n: sha(d) for n, d in data.items()}
            targets = {}
            for bundle in BUNDLES:
                for n in NAMES:
                    targets[str(bundle / n)] = data[n]
                targets[str(bundle / 'SHA256SUMS')] = new_manifest(bundle, digests)
            targets[str(FAT / 'h713-hdmi.scr')] = data['h713-hdmi.scr']
        result['would'] = {p: sha(d) for p, d in targets.items()}
        if not apply:
            return result
        backup = begin('script', result)
        index = {}
        for i, (path, p) in enumerate(files.items()):
            save(backup / ('file-%d' % i), p.read_bytes())
            index[path] = 'file-%d' % i
        save(backup / 'files.json', (json.dumps(index, indent=2) + '\n').encode())
        save(backup / 'INCOMPLETE', b'script update intent; do not reboot\n')
        syncdir(backup)
        syncdir(STATE)
        fat = str(FAT / 'h713-hdmi.scr')
        order = [p for p in targets if p != fat] + [fat]   # activation last
        try:
            for path in order:
                atomic(Path(path), targets[path])
            subprocess.run(['sync'], check=True, timeout=60)
            need(script_state(m) == want_to, 'script state after update differs')
        except BaseException:
            for path in reversed(order):
                original = (backup / index[path]).read_bytes()
                Path(path).with_name(Path(path).name + '.single-new').unlink(missing_ok=True)
                if Path(path).read_bytes() != original:
                    atomic(Path(path), original)
            subprocess.run(['sync'], check=True, timeout=60)
            save(backup / 'RESTORED', b'original scripts restored\n')
            (backup / 'INCOMPLETE').unlink()
            syncdir(backup)
            raise
        result.update(applied=True, backup=str(backup), script=want_to)
        finish(backup, result, 'COMMITTED')
        return result
    finally:
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--phase', choices=('proper', 'script'), required=True)
    parser.add_argument('--boot', required=True, help='expected current boot ID')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', type=Path, help='backup directory of the transaction to undo')
    args = parser.parse_args()
    need(os.geteuid() == 0, 'root required')
    print(json.dumps(run(Path(__file__).resolve().parent, args.phase, args.boot, args.apply, args.rollback), indent=2))
