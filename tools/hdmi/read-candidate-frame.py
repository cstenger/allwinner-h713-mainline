#!/usr/bin/env python3
"""Stream a fixed 320 KiB candidate frame-memory window to stdout.

The six repeating 2 MiB-spaced regions were discovered by the page-hash
trial. It never accesses receiver MMIO or writes board memory.
"""

import mmap
import os
import sys
import argparse

BASE = 0x4C3EF000
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--full-slot", action="store_true", help="read the entire selected 2 MiB slot")
parser.add_argument("--slot", type=int, choices=range(6), default=0,
                    help="candidate region 0..5 (default: 0)")
args = parser.parse_args()
SIZE = 0x1FF000 if args.full_slot else 0x50000
BASE += args.slot * 0x1FF000
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, SIZE, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ,
                   offset=BASE) as mem:
        sys.stdout.buffer.write(mem[:])
finally:
    os.close(fd)
