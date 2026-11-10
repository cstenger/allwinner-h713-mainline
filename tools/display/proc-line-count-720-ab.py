#!/usr/bin/env python3
"""Board-only, operator-observed A/B for the line-count boundary discriminator.

Run only after a fresh watching confirmation. Changes only PROC_FRAME_LINES[15:0]
while a 1280x240 black frame is held. Restores the exact register before KMS teardown.
"""
import argparse
import mmap
import os
import struct
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--watching-confirmed', action='store_true', required=True)
args = parser.parse_args()
root = Path('/mnt/media-data')
log_path = root / 'h713-gst-transform-20260914/line-count-720-ab-panel.log'
fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
page = mmap.mmap(fd, 4096, flags=mmap.MAP_SHARED,
                 prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=0x05180000)
def read(off):
    return struct.unpack_from('<I', page, off)[0]
def write_checked(off, value):
    struct.pack_into('<I', page, off, value)
    actual = read(off)
    print(f'proc+{off:02x}: wrote {value:08x}, read {actual:08x}', flush=True)
    if actual != value:
        raise RuntimeError('MMIO readback mismatch')

proc = None
saved = None
try:
    with log_path.open('w') as log:
        proc = subprocess.Popen(
            ['/root/kms-nv12-plane-test', '/dev/null', '60'],
            env=dict(os.environ, ARMED='yes', SRC='1280x240', SYNTH_BLACK='1'),
            stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError('KMS harness exited before active frame')
            if read(0x34) == 0x050000f0 and read(0x14) & (1 << 27) == 0:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError('Expected active 1280x240 geometry not seen')
        saved = read(0x50)
        if saved != 0x001b00f0:
            raise RuntimeError(f'Unexpected baseline {saved:08x}; no A/B write')
        print('A: original line count 240, 8 seconds', flush=True)
        time.sleep(8)
        if proc.poll() is not None:
            raise RuntimeError('KMS harness stopped before line-count update')
        write_checked(0x50, (saved & ~0xffff) | 720)
        print('B: line count 720, 12 seconds', flush=True)
        time.sleep(12)
        write_checked(0x50, saved)
        saved = None
        print('A: exact original restored, 8 seconds', flush=True)
        time.sleep(8)
finally:
    try:
        if saved is not None and proc is not None and proc.poll() is None:
            write_checked(0x50, saved)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        page.close()
        os.close(fd)
    print(log_path.read_text() if log_path.exists() else 'No panel log', flush=True)
