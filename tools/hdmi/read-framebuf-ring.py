#!/usr/bin/env python3
"""Read-only 2.5-second CRC timeline of six candidate HDMI luma slots.

The six physical bases come from the page-hash trial. This samples only their
640x480 luma-sized prefixes and never writes DRAM or touches receiver MMIO.
"""

import json
import mmap
import os
import time
import zlib

CARVEOUT = 0x4BF41000
SIZE = 26 * 1024 * 1024
BASE = 0x4C3F0000
STEP = 0x1FF000
LUMA = 640 * 480
COUNT = 6
SAMPLES = 20
INTERVAL = 0.125

fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, SIZE, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ,
                   offset=CARVEOUT) as mem:
        records = []
        start = time.monotonic()
        for sample in range(SAMPLES):
            hashes = []
            for slot in range(COUNT):
                offset = BASE + STEP * slot - CARVEOUT
                hashes.append(f"{zlib.crc32(mem[offset:offset + LUMA]):08x}")
            records.append({"seconds": round(time.monotonic() - start, 3),
                            "crc32": hashes})
            deadline = start + (sample + 1) * INTERVAL
            if time.monotonic() < deadline:
                time.sleep(deadline - time.monotonic())
finally:
    os.close(fd)
print(json.dumps({"bases": [f"0x{BASE + STEP * n:08x}" for n in range(COUNT)],
                  "samples": records}, separators=(",", ":")))
