#!/usr/bin/env python3
"""Read-only CRC timeline of six candidate HDMI NV16 planes.

The six physical bases were refined by image comparison. Each sample hashes
four interior 4 KiB pages per plane. Sparse reads can resolve the write order
without spending a full video frame hashing entire planes. This never writes
DRAM or touches receiver MMIO.
"""

import json
import mmap
import os
import time
import zlib

CARVEOUT = 0x4BF41000
SIZE = 26 * 1024 * 1024
BASE = 0x4C3EF000
STEP = 0x1FF000
PAGES = (0x10000, 0x20000, 0x30000, 0x40000)
PAGE_SIZE = 4096
COUNT = 6
SAMPLES = 600
INTERVAL = 0.003

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
                crc = 0
                for page in PAGES:
                    pos = offset + page
                    crc = zlib.crc32(mem[pos:pos + PAGE_SIZE], crc)
                hashes.append(f"{crc:08x}")
            records.append({"seconds": round(time.monotonic() - start, 3),
                            "crc32": hashes})
            deadline = start + (sample + 1) * INTERVAL
            if time.monotonic() < deadline:
                time.sleep(deadline - time.monotonic())
finally:
    os.close(fd)
print(json.dumps({"bases": [f"0x{BASE + STEP * n:08x}" for n in range(COUNT)],
                  "page_offsets": [f"0x{x:x}" for x in PAGES],
                  "samples": records}, separators=(",", ":")))
