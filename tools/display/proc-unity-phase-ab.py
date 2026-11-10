#!/usr/bin/env python3
"""Board-only, operator-observed A/B for the H unity integer-phase mismatch.

Run only after a fresh watching confirmation. Changes only PROC_RATIO_H[30:28]
while a 1280x608 card is held. Restores the exact register before KMS teardown.
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
log_path = root / 'h713-gst-transform-20260914/unity-phase-ab-panel.log'
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
            [str(root / 'kms-nv12-plane-test'),
             str(root / 'h713-ruled-1280x608.nv12'), '60'],
            env=dict(os.environ, ARMED='yes', SRC='1280x608'),
            stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError('KMS harness exited before active frame')
            if read(0x34) == 0x05000260 and read(0x14) & (1 << 27) == 0:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError('Expected active 1280x608 geometry not seen')
        saved = read(0x08)
        if saved != 0x32010000:
            raise RuntimeError(f'Unexpected baseline {saved:08x}; no A/B write')
        print('A: original H integer phase 3, 8 seconds', flush=True)
        time.sleep(8)
        if proc.poll() is not None:
            raise RuntimeError('KMS harness stopped before phase update')
        write_checked(0x08, (saved & ~(7 << 28)) | (4 << 28))
        print('B: firmware H unity integer phase 4, 12 seconds', flush=True)
        time.sleep(12)
        write_checked(0x08, saved)
        saved = None
        print('A: exact original restored, 8 seconds', flush=True)
        time.sleep(8)
finally:
    try:
        if saved is not None and proc is not None and proc.poll() is None:
            write_checked(0x08, saved)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        page.close()
        os.close(fd)
    print(log_path.read_text() if log_path.exists() else 'No panel log', flush=True)
