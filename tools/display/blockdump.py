#!/usr/bin/env python3
"""Fast mmap dump of the display blocks. Read-only."""
import mmap, os, struct, sys

BLOCKS = [("afbd",  0x05600000, 0x400),
          ("comp",  0x05000000, 0x300),
          ("route", 0x05140000, 0x600),
          ("proc",  0x05180000, 0x100),
          ("lvds",  0x051c0000, 0x100),
          ("layer", 0x05280000, 0x200)]
PAGE = 4096
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
out = {}
for name, base, size in BLOCKS:
    assert base % PAGE == 0, f"{name}: base {base:#x} is not page aligned"
    span = (size + PAGE - 1) // PAGE * PAGE
    m = mmap.mmap(fd, span, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    for off in range(0, size, 4):
        out[f"{name}+{off:03x}"] = struct.unpack_from("<I", m, off)[0]
    m.close()
os.close(fd)
for k, v in out.items():
    print(f"{k}={v:08X}")
