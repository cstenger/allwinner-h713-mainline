#!/usr/bin/env python3
"""Refuse to write to the wrong H713 board.

The bench (HY200_QZ713DF_A1, DDR3) and the projector (HY200_QZ713_V2, LPDDR3)
share a GPT, a SoC and most of a boot chain, so an installer pointed at the
wrong one fails late and badly: a DDR3 first stage on the LPDDR3 board "trains
OK, reads hang". Every installer that writes a board calls this first.

  board-guard.py --expect BOARD_ID [--root DIR] [--dev BLOCK]   on the board
  board-guard.py --expect BOARD_ID --dev /dev/sdX               UMS block device
  board-guard.py --expect BOARD_ID --fastboot                   board in fastboot
  board-guard.py --expect BOARD_ID --fel                        board in FEL
  board-guard.py --expect BOARD_ID --ssh root@HOST              board over ssh
  board-guard.py --expect BOARD_ID --ssh-cmd "ssh -F /dev/null root@HOST"

BOARD_ID names boards/<id>/board.env. Exit 0 when every check that the
transport allows matches it, 3 on a mismatch, 2 when the identity cannot be
read. Nothing is written.

Checks:
  DT       /proc/device-tree/compatible must list DT_COMPATIBLE (on-board, ssh)
  boot0    the stock boot0's declared DRAM type and clock must match. It is
           read at LBA 16, or at LBA 0x100 (the vendor's second copy) when
           LBA 16 holds our SPL (on-board, ssh, block device)
  serial   U-Boot's serialno (fastboot), or the SID as U-Boot forms serial#
           (FEL), must equal UBOOT_SERIAL
"""
import argparse
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BOOT0_LBAS = (16, 0x100)


class Unknown(Exception):
    pass


def board_env(board_id):
    path = ROOT / 'boards' / board_id / 'board.env'
    if not path.is_file():
        known = sorted(p.name for p in (ROOT / 'boards').iterdir() if p.is_dir())
        print(f'board-guard: unknown board {board_id!r} (known: {", ".join(known)})',
              file=sys.stderr)
        raise SystemExit(2)
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = shlex.split(v)[0] if v else ''
    return env


def boot0_info(read_block):
    """(lba, dram_type, dram_clk) of the first stock boot0 found, else Unknown."""
    seen = []
    for lba in BOOT0_LBAS:
        d = read_block(lba, 64)
        if len(d) < 64 or d[4:12] != b'eGON.BT0':
            seen.append(f'LBA {lba:#x}: no eGON.BT0')
            continue
        if d[0x14:0x17] == b'SPL':
            seen.append(f'LBA {lba:#x}: our SPL')
            continue
        length = struct.unpack_from('<I', d, 16)[0]
        if length < 64 or length > 0x100000 or length % 512:
            seen.append(f'LBA {lba:#x}: bad length {length}')
            continue
        whole = read_block(lba, length)
        words = list(struct.unpack(f'<{length // 4}I', whole))
        stored, words[3] = words[3], 0x5F0A6C39
        if sum(words) & 0xffffffff != stored:
            seen.append(f'LBA {lba:#x}: eGON checksum mismatch')
            continue
        clk, typ = struct.unpack_from('<II', d, 0x38)
        return lba, typ, clk
    raise Unknown('no stock boot0: ' + '; '.join(seen))


def block_reader(dev):
    def read(lba, n):
        with open(dev, 'rb') as f:
            f.seek(lba * 512)
            return f.read(n)
    return read


def ssh_reader(ssh):
    def read(lba, n):
        cmd = f'dd if=/dev/mmcblk0 bs=512 skip={lba} count={(n + 511) // 512} 2>/dev/null'
        return subprocess.run([*ssh, cmd], check=True, capture_output=True,
                              timeout=30).stdout[:n]
    return read


def ssh_compatible(ssh):
    out = subprocess.run([*ssh, 'cat /proc/device-tree/compatible'], check=True,
                         capture_output=True, timeout=30).stdout
    return [c for c in out.decode(errors='replace').split('\0') if c]


def local_compatible(root):
    p = Path(root) / 'proc/device-tree/compatible'
    if not p.exists():
        raise Unknown(f'{p} missing')
    return [c for c in p.read_bytes().decode(errors='replace').split('\0') if c]


def fastboot_serial():
    r = subprocess.run(['fastboot', 'getvar', 'serialno'], capture_output=True,
                       text=True, timeout=30)
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith('serialno:'):
            return line.split(':', 1)[1].strip()
    raise Unknown('fastboot getvar serialno gave no answer')


def fel_serial():
    fel = ROOT / 'external' / 'sunxi-tools' / 'sunxi-fel'
    r = subprocess.run([str(fel), 'sid'], capture_output=True, text=True, timeout=30)
    words = r.stdout.strip().split(':')
    if r.returncode or len(words) != 4:
        raise Unknown(f'sunxi-fel sid gave {r.stdout.strip() or r.stderr.strip()!r}')
    return words[0] + words[3]     # U-Boot's serial#: sid[0] then sid[3]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--expect', required=True, help='board id under boards/')
    ap.add_argument('--root', help='root of the running board (on-board use)')
    ap.add_argument('--dev', help='eMMC block device or image to read boot0 from')
    ap.add_argument('--fastboot', action='store_true')
    ap.add_argument('--fel', action='store_true', help='board in FEL: compare its SID')
    ap.add_argument('--ssh', metavar='TARGET', help='user@host, default ssh options')
    ap.add_argument('--ssh-cmd', metavar='CMD',
                    help='the caller\'s full ssh command, e.g. "ssh -F /dev/null root@HOST"')
    a = ap.parse_args()
    want = board_env(a.expect)
    checks, bad = [], []

    def check(name, got, expect):
        ok = got == expect
        checks.append(f'{name}: {got} ({"ok" if ok else "WANT " + str(expect)})')
        if not ok:
            bad.append(name)

    try:
        if a.fastboot:
            check('serialno', fastboot_serial(), want['UBOOT_SERIAL'])
        elif a.fel:
            check('SID serial', fel_serial(), want['UBOOT_SERIAL'])
        else:
            if a.ssh or a.ssh_cmd:
                ssh = (shlex.split(a.ssh_cmd) if a.ssh_cmd else
                       ['ssh', '-F', '/dev/null', '-o', 'ConnectTimeout=5', a.ssh])
                if '-o' not in ssh or 'BatchMode=yes' not in ssh:
                    ssh[1:1] = ['-o', 'BatchMode=yes']
                compat, reader = ssh_compatible(ssh), ssh_reader(ssh)
            elif a.root or not a.dev:
                root = a.root or '/'
                compat = local_compatible(root)
                reader = block_reader(a.dev or '/dev/mmcblk0')
            else:
                compat, reader = None, block_reader(a.dev)
            if compat is not None:
                hit = want['DT_COMPATIBLE'] in compat
                checks.append(f'DT compatible: {compat[0] if compat else "?"} '
                              f'({"ok" if hit else "WANT " + want["DT_COMPATIBLE"]})')
                if not hit:
                    bad.append('DT')
            lba, typ, clk = boot0_info(reader)
            check(f'boot0 DRAM type (LBA {lba:#x})', typ, int(want['DRAM_TYPE']))
            check(f'boot0 DRAM clock (LBA {lba:#x})', clk, int(want['DRAM_CLK']))
    except Unknown as e:
        print(f'board-guard: {a.expect}: cannot identify the board: {e}', file=sys.stderr)
        for c in checks:
            print(f'  {c}', file=sys.stderr)
        return 2
    except (subprocess.SubprocessError, OSError) as e:
        print(f'board-guard: {a.expect}: cannot read the board: {e}', file=sys.stderr)
        return 2

    for c in checks:
        print(f'  {c}', file=sys.stderr)
    if bad:
        print(f'board-guard: REFUSED: this is not {a.expect} ({", ".join(bad)} differ)',
              file=sys.stderr)
        return 3
    print(f'board-guard: {a.expect} confirmed', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
