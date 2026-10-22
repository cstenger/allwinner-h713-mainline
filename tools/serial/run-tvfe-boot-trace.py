#!/usr/bin/env python3
"""Guarded RAM-only diagnostic kernel boot after one reviewed warm logo.

The FIT must already be staged at the fixed rootfs path during the preceding
production boot. No firmware launch, domain write, saved environment or flash
operation. Captures for a fixed total duration, never a silence timeout.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import time
import zlib
from console import open_port, write_slow, drain

spec = importlib.util.spec_from_file_location('warm_retention', Path(__file__).with_name('warm-retention-uboot.py'))
warm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warm)
REMOTE_FIT = '/root/hdmi-tvfe-boot-trace-2026-10-21/kernel.fit'
BOOTARGS = ('console=ttyS0,115200 console=tty0 earlycon root=/dev/mmcblk0p26 rootwait '
            'rootfstype=ext4 rw net.ifnames=0 panic=0 clk_ignore_unused pd_ignore_unused '
            'cma=128M h713_tvfe_trace=1 loglevel=7')


def validate(prepared):
    manifest = json.loads((prepared / 'manifest.json').read_text())
    if not manifest.get('built') or not manifest.get('symvers_unchanged') or manifest.get('kernel_release') != '6.18.38':
        raise ValueError('requires built, ABI-checked 6.18.38 diagnostic')
    fit = (prepared / 'artifacts/kernel.fit').read_bytes()
    expected = manifest['artifacts']['kernel.fit']
    if len(fit) != expected['size'] or hashlib.sha256(fit).hexdigest() != expected['sha256']:
        raise ValueError('diagnostic FIT changed')
    return fit


def boot(con, expected_bootcmd, fit, before_load=None):
    # Every checked command must return its own prompt, not just an echo.
    r = warm.census(con)
    if r['bootcmd'] != expected_bootcmd:
        raise RuntimeError('production bootcmd mismatch')
    if r.get('ppu_tvfe_state') != 'on' or r.get('ppu_tvcap_state') != 'on':
        raise RuntimeError('post-logo PPU domains not both ON; stop')
    for addr, required in ((warm.GP6, 0x48444d49), (warm.MIPS_STATUS, 0)):
        value = warm.parse_md(con.run('md.l 0x%08x 1' % addr), addr)
        if value != required:
            raise RuntimeError('requires production warm latch and parked MIPS')
    if before_load:
        before_load(con)
    con.checked('ext4load mmc 1:1a 0x50000000 ' + REMOTE_FIT)
    # U-Boot filesize and RAM CRC pin the actual transfer before bootm verifies FIT hashes.
    con.checked('itest ${filesize} == %x' % len(fit))
    out = con.run('crc32 0x50000000 %x' % len(fit))
    m = re.search(rb'==>\s*([0-9a-fA-F]{8})\b', out)
    if not m or int(m.group(1), 16) != zlib.crc32(fit):
        raise RuntimeError('RAM CRC mismatch; no boot')
    con.checked('setenv fdt_high 0x4f000000')
    con.checked('setenv initrd_high 0x4f000000')
    con.checked('setenv bootargs ' + BOOTARGS)
    # Last PPU observation after ext4load, immediately before bootm.
    final = warm.census(con)
    if final['bootcmd'] != expected_bootcmd or final.get('ppu_tvfe_state') != 'on' or final.get('ppu_tvcap_state') != 'on':
        raise RuntimeError('state changed during RAM preparation; no boot')
    return r, final


class Console:
    def __init__(self, fd, raw):
        self.fd, self.raw, self.step = fd, raw, 0

    def run(self, line):
        write_slow(self.fd, (line + '\n').encode())
        out = drain(self.fd, 2, echo=False)
        self.raw.write(out)
        if not re.search(rb'=>\s*$', out):
            raise RuntimeError('missing U-Boot prompt; stop without retry')
        return out

    def checked(self, line):
        self.step += 1
        marker = 'H713_TVFE_STEP_%d_OK' % self.step
        out = self.run('if ' + line + '; then echo ' + marker + '; else echo H713_TVFE_STEP_FAILED; fi')
        if not re.search(rb'(?m)^' + marker.encode() + rb'\r?$', out):
            raise RuntimeError('command failed or acknowledgment missing: ' + line)


def capture(fd, raw, seconds):
    deadline, tail = time.monotonic() + seconds, b''
    while time.monotonic() < deadline:
        if not select.select([fd], [], [], min(1, max(0, deadline - time.monotonic())))[0]:
            continue
        data = os.read(fd, 65536)
        if not data:
            raise RuntimeError('lost UART during diagnostic boot')
        raw.write(data)
        tail = (tail + data)[-4096:]
        if b'U-Boot SPL ' in tail:
            raise RuntimeError('unexpected reset during trace; no retry')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', required=True)
    p.add_argument('--prepared', required=True, type=Path)
    p.add_argument('--expected-bootcmd', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--post-logo-ack', required=True, choices=['one-reviewed-warm-logo'])
    p.add_argument('--capture-seconds', type=int, default=60)
    args = p.parse_args()
    if not 30 <= args.capture_seconds <= 300:
        p.error('--capture-seconds must be 30..300')
    fit = validate(args.prepared)
    expected = args.expected_bootcmd.read_text().rstrip('\n')
    args.output.mkdir(parents=True, exist_ok=False)
    fd = open_port(args.port)
    try:
        with (args.output / 'serial.log').open('xb', buffering=0) as raw:
            write_slow(fd, b'\n')
            initial = drain(fd, 1, echo=False)
            raw.write(initial)
            if not re.search(rb'=>\s*$', initial):
                raise RuntimeError('not at U-Boot prompt; no boot')
            before, final = boot(Console(fd, raw), expected, fit)
            (args.output / 'preboot.json').write_text(json.dumps({'before': before, 'final': final,
                'bootargs': BOOTARGS, 'fit_sha256': hashlib.sha256(fit).hexdigest(),
                'boot_intent': True, 'post_logo_ack': args.post_logo_ack}, indent=2) + '\n')
            write_slow(fd, b'bootm 0x50000000\n')
            capture(fd, raw, args.capture_seconds)
    finally:
        os.close(fd)
    print('Trace capture ended; verify a fresh Linux boot ID and journal before interpretation.')


if __name__ == '__main__':
    main()
