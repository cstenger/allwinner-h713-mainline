#!/usr/bin/env python3
"""Hash, without exposing pixels, each page of the reserved framebuf carveout.

This is a read-only DRAM probe for the board. The range is fixed by the merged
kernel's reserved-memory node; no peripheral/MMIO register is touched.
"""

import json
import mmap
import os
import zlib

BASE = 0x4BF41000
SIZE = 26 * 1024 * 1024
PAGE = 4096

fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
try:
    with mmap.mmap(fd, SIZE, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ,
                   offset=BASE) as mem:
        hashes = [f"{zlib.crc32(mem[i:i + PAGE]):08x}" for i in range(0, SIZE, PAGE)]
finally:
    os.close(fd)
print(json.dumps({"base": f"0x{BASE:08x}", "page_size": PAGE, "crc32": hashes},
                 separators=(",", ":")))
