#!/usr/bin/env python3
"""Tests for tools/board-guard.py with synthetic images (no vendor binaries).

Each case builds an eMMC image and, for on-board mode, a fake root with
/proc/device-tree/compatible, then checks the guard's exit code. Run:
  python3 -I tools/test-board-guard.py
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / 'tools' / 'board-guard.py'
A1, V2 = 'hy200-qz713df-a1', 'hy200-qz713-v2'


def boot0(typ, clk, corrupt=False):
    d = bytearray(32768)
    d[0:4] = b'\xf0\x00\x00\xea'
    d[4:12] = b'eGON.BT0'
    struct.pack_into('<I', d, 16, 32768)
    struct.pack_into('<I', d, 0x14, 0x30)
    struct.pack_into('<II', d, 0x38, clk, typ)
    struct.pack_into('<I', d, 12, 0x5F0A6C39)
    struct.pack_into('<I', d, 12, sum(struct.unpack('<8192I', d)) & 0xffffffff)
    if corrupt:
        d[0x200] ^= 0xff
    return bytes(d)


def our_spl():
    # Like a real sunxi SPL: valid length and eGON checksum, "SPL\x02" at
    # +0x14, and non-boot0 data where boot0 keeps its DRAM clock and type.
    d = bytearray(32768)
    d[4:12] = b'eGON.BT0'
    struct.pack_into('<I', d, 16, 32768)
    d[0x14:0x18] = b'SPL\x02'
    struct.pack_into('<II', d, 0x38, 0x6930a06e, 0x31373e2d)
    struct.pack_into('<I', d, 12, 0x5F0A6C39)
    struct.pack_into('<I', d, 12, sum(struct.unpack('<8192I', d)) & 0xffffffff)
    return bytes(d)


def image(tmp, at16, at100):
    p = Path(tmp) / 'emmc.img'
    with open(p, 'wb') as f:
        f.truncate(0x200 * 512)
        if at16:
            f.seek(16 * 512); f.write(at16)
        if at100:
            f.seek(0x100 * 512); f.write(at100)
    return p


def rootfs(tmp, compatible):
    r = Path(tmp) / 'root'
    (r / 'proc/device-tree').mkdir(parents=True, exist_ok=True)
    (r / 'proc/device-tree/compatible').write_bytes(
        b'\0'.join(c.encode() for c in compatible) + b'\0')
    return r


def guard(*args):
    return subprocess.run([sys.executable, '-I', str(GUARD), *args],
                          capture_output=True, text=True).returncode


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def v2_block_device_matches():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, boot0(7, 720), boot0(7, 720))
        return guard('--expect', V2, '--dev', str(img)) == 0


@case
def v2_image_refused_as_bench():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, boot0(7, 720), None)
        return guard('--expect', A1, '--dev', str(img)) == 3


@case
def our_spl_at_16_falls_back_to_vendor_copy():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, our_spl(), boot0(3, 624))
        return (guard('--expect', A1, '--dev', str(img)) == 0 and
                guard('--expect', V2, '--dev', str(img)) == 3)


@case
def corrupt_boot0_is_skipped_not_trusted():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, boot0(3, 624, corrupt=True), boot0(7, 720))
        return guard('--expect', V2, '--dev', str(img)) == 0


@case
def no_stock_boot0_is_unknown():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, our_spl(), None)
        return guard('--expect', A1, '--dev', str(img)) == 2


@case
def onboard_dt_and_boot0_match():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, boot0(7, 720), None)
        r = rootfs(t, ['cstenger,hy200-qz713-v2', 'allwinner,sun50i-h713'])
        return guard('--expect', V2, '--root', str(r), '--dev', str(img)) == 0


@case
def onboard_dt_mismatch_refused():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, boot0(7, 720), None)
        r = rootfs(t, ['cstenger,hy200-qz713df-a1', 'allwinner,sun50i-h713'])
        return guard('--expect', V2, '--root', str(r), '--dev', str(img)) == 3


@case
def onboard_dt_and_boot0_disagree_refused():
    # A bench DT on an LPDDR3 boot0: refuse whichever board is expected.
    with tempfile.TemporaryDirectory() as t:
        img = image(t, boot0(7, 720), None)
        r = rootfs(t, ['cstenger,hy200-qz713df-a1', 'allwinner,sun50i-h713'])
        return (guard('--expect', A1, '--root', str(r), '--dev', str(img)) == 3 and
                guard('--expect', V2, '--root', str(r), '--dev', str(img)) == 3)


@case
def unknown_board_id():
    with tempfile.TemporaryDirectory() as t:
        img = image(t, boot0(7, 720), None)
        return guard('--expect', 'nosuch', '--dev', str(img)) == 2


fails = 0
for fn in CASES:
    ok = fn()
    fails += not ok
    print(f'{"PASS" if ok else "FAIL"} {fn.__name__}')
print(f'{len(CASES) - fails}/{len(CASES)} passed')
sys.exit(1 if fails else 0)
