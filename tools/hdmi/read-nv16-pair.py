#!/usr/bin/env python3
"""Stream one read-only Y + interleaved UV frame candidate.

The page-hash and image trials show three Y regions followed by three matching
UV regions. Each plane starts one page before its first changing page; the
initial page can be constant when the top of the desktop does not change.
This reads pair 0/3 by default; --pair 1 or 2 selects 1/4 or 2/5.
The 614400-byte result is a candidate NV16 frame, not a synchronized capture.
"""

import argparse
import mmap
import os
import sys

CARVEOUT = 0x4BF41000
SIZE = 26 * 1024 * 1024
FIRST = 0x4C3EF000
STEP = 0x1FF000
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--pair", type=int, choices=range(3), default=0)
ap.add_argument("--width", type=int, choices=(640, 1280), default=640)
ap.add_argument("--height", type=int, choices=(480, 720), default=480)
args = ap.parse_args()
if (args.width, args.height) not in ((640, 480), (1280, 720)):
    ap.error("supported formats are 640x480 and 1280x720")
plane = args.width * args.height
if plane > STEP:
    ap.error("plane size exceeds the observed ring allocation step")

fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, SIZE, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ,
                   offset=CARVEOUT) as mem:
        y = FIRST + STEP * args.pair - CARVEOUT
        uv = FIRST + STEP * (args.pair + 3) - CARVEOUT
        sys.stdout.buffer.write(mem[y:y + plane])
        sys.stdout.buffer.write(mem[uv:uv + plane])
finally:
    os.close(fd)
