#!/usr/bin/env python3
"""Exact RC bootdelay=5 -> 0 update; preview by default, durable rollback backup."""
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
import zlib

OFFSET = 0x93D80000
SIZE = 65536
BEFORE = '89862e4ba5304fcae54affe09d87ff7da026316c80c8b4a5a17d7a44eb3ce206'
CID = '15010038475446345208604bbe691991'
PROTECTED = (
    ('spl', 8192, 32768, 'd593ab799b6d422523d67a33c7427c481765e5afac71f065cc2f16e162ce18cf'),
    ('proper', 2472017920, 955904, '326661503b28376284c3082477335f19c5908b5cd33c4970373df5fb8874746b'),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def parse(data):
    need(len(data) == SIZE, 'environment size differs')
    need(struct.unpack('<I', data[:4])[0] == zlib.crc32(data[4:]), 'environment CRC differs')
    need(b'\0\0' in data[4:], 'missing terminator')
    values = {}
    for entry in data[4:].split(b'\0\0', 1)[0].split(b'\0'):
        need(b'=' in entry, 'malformed entry')
        key, value = entry.split(b'=', 1)
        need(key and key not in values, 'duplicate/empty entry')
        values[key] = value
    return values


def candidate(data):
    values = parse(data)
    need(sha(data) == BEFORE, 'unrecognized RC environment')
    need(values.get(b'bootdelay') == b'5', 'expected five-second countdown')
    payload = data[4:]
    # Equal length replacement preserves order, padding, and all other bytes.
    entries = payload.split(b'\0')
    need(entries.count(b'bootdelay=5') == 1, 'ambiguous countdown entry')
    entries[entries.index(b'bootdelay=5')] = b'bootdelay=0'
    changed = b'\0'.join(entries)
    need(len(changed) == len(payload), 'environment length changed')
    result = struct.pack('<I', zlib.crc32(changed)) + changed
    expected = values.copy()
    expected[b'bootdelay'] = b'0'
    need(parse(result) == expected, 'unexpected environment policy change')
    need(sum(a != b for a, b in zip(payload, changed)) == 1, 'more than one payload byte changed')
    return result


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


def read(fd, offset, size):
    if stat.S_ISBLK(os.fstat(fd).st_mode):
        return subprocess.check_output(['dd', 'if=/dev/mmcblk0', 'iflag=direct', 'bs=512',
                                        'skip='+str(offset//512), 'count='+str(size//512), 'status=none'], timeout=30)
    return os.pread(fd, size, offset)


def write(fd, data):
    need(os.pwrite(fd, data, OFFSET) == SIZE, 'short environment write')
    os.fsync(fd)
    need(read(fd, OFFSET, SIZE) == data, 'environment readback differs')


def transaction(fd, before, after, backup, context):
    need(read(fd, OFFSET, SIZE) == before, 'environment changed before write')
    context()
    backup.mkdir(mode=0o700)
    save(backup/'environment-before.bin', before)
    save(backup/'environment-after.bin', after)
    save(backup/'INCOMPLETE', b'environment write intent\n')
    syncdir(backup)
    syncdir(backup.parent)
    try:
        write(fd, after)
        context()
    except BaseException:
        # A partial write is recoverable while Linux remains alive. The durable
        # backup/intent is retained if restoration itself fails.
        write(fd, before)
        context()
        save(backup/'ROLLED_BACK', b'original restored and verified\n')
        (backup/'INCOMPLETE').unlink()
        syncdir(backup)
        raise
    save(backup/'COMMITTED', b'candidate written and verified\n')
    (backup/'INCOMPLETE').unlink()
    syncdir(backup)


def identity(fd, boot):
    text = lambda p: Path(p).read_text().strip('\0\n')
    need(text('/proc/sys/kernel/random/boot_id') == boot, 'boot changed')
    need(text('/proc/device-tree/model') == 'HY200 QZ713DF_A1 (Allwinner H713)', 'wrong board')
    need(text('/sys/class/block/mmcblk0/device/cid') == CID, 'wrong eMMC')
    need(text('/sys/class/block/mmcblk0/device/type') == 'MMC', 'not eMMC')
    info = os.fstat(fd)
    need(stat.S_ISBLK(info.st_mode) and info.st_rdev == os.stat('/dev/mmcblk0').st_rdev, 'wrong device')
    need(struct.unpack('<Q', fcntl.ioctl(fd, 0x80081272, bytes(8)))[0] == 7818182656, 'capacity differs')
    need(struct.unpack('<I', fcntl.ioctl(fd, 0x1268, bytes(4)))[0] == 512, 'sector size differs')
    need(os.stat('/').st_dev == os.stat('/dev/mmcblk0p26').st_rdev, 'wrong root partition')
    part = Path('/sys/class/block/mmcblk0p18')
    need(int(text(part/'start'))*512 <= OFFSET and OFFSET+SIZE <= (int(text(part/'start'))+int(text(part/'size')))*512, 'environment outside reserved partition')
    need(not list((part/'holders').iterdir()), 'reserved partition has holders')
    need(not any(line.split()[2] == text(part/'dev') for line in Path('/proc/self/mountinfo').read_text().splitlines()), 'reserved partition mounted')
    for name, offset, size, expected in PROTECTED:
        need(sha(read(fd, offset, size)) == expected, 'protected boot region changed: '+name)


def live(boot, before, apply=False, rollback=False):
    after = candidate(before)
    source, target = (after, before) if rollback else (before, after)
    fd = os.open('/dev/mmcblk0', (os.O_RDWR if apply else os.O_RDONLY) | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity(fd, boot)
        need(read(fd, OFFSET, SIZE) == source, 'live environment differs from expected state')
        # Guard both neighboring sectors, both GPTs, and the preserved rescue
        # proper, in addition to the pinned SPL/proper above.
        spans = [(OFFSET-SIZE, SIZE), (OFFSET+SIZE, SIZE), (0, 34*512),
                 (7818182656-33*512, 33*512), (0x4A0C00*512, 2*1024*1024)]
        pins = [(offset, size, sha(read(fd, offset, size))) for offset, size in spans]
        def context():
            identity(fd, boot)
            for offset, size, digest in pins:
                need(sha(read(fd, offset, size)) == digest, 'adjacent/GPT/rescue region changed')
        result = dict(schema='h713-autoboot-countdown-v1', boot_id=boot, offset=OFFSET, bytes=SIZE,
                      before_sha256=sha(source), after_sha256=sha(target), before_seconds=0 if rollback else 5,
                      after_seconds=5 if rollback else 0, expected_saving_seconds=-5 if rollback else 5,
                      action='rollback' if rollback else 'install', applied=False)
        if apply:
            state = Path('/var/lib/h713-hdmi-startup')
            need(state.is_dir() and not state.is_symlink(), 'state directory missing/unsafe')
            need(not list(state.glob('*/INCOMPLETE')), 'unfinished transaction exists')
            backup = state/('autoboot-zero-'+uuid.uuid4().hex)
            transaction(fd, source, target, backup, context)
            result.update(applied=True, backup=str(backup))
            save(backup/'receipt.json', (json.dumps(result, indent=2)+'\n').encode())
            syncdir(backup)
        return result
    finally:
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('--output', type=Path, help='offline candidate; no hardware access')
    parser.add_argument('--boot', help='explicit current boot ID for live preview/apply')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', action='store_true', help='restore exact original image from the zero-delay state')
    args = parser.parse_args()
    before = args.before.read_bytes()
    if args.output:
        need(not args.apply and not args.boot and not args.rollback, 'offline mode cannot access board')
        save(args.output, candidate(before))
        print(json.dumps(dict(before_sha256=sha(before), after_sha256=sha(candidate(before)), bootdelay=0)))
    else:
        need(bool(args.boot), 'live mode requires expected boot')
        print(json.dumps(live(args.boot, before, args.apply, args.rollback), indent=2))
