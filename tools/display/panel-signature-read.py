#!/usr/bin/env python3
"""Sample the display blocks DOWNSTREAM of AFBD, several times. READ-ONLY.
RUNS ON THE TARGET, as root.

    panel-signature-read.py [--samples 8] [--interval 0.1] > card.json

Looking for a word that summarises the picture the panel actually receives
(a CRC or other position-sensitive signature): with one, a hardware transform
(mirror, placement) can be checked without a camera. scanout-grab cannot do
this; it reads the framebuffer, upstream of everything.

WHAT IS READ: whole 4 KiB pages the stock capture of 2026-10-01 dumped on this
SoC with the display running (comp 0x05000000, route 0x05140000) and the
panel block 0x051c0000-0x3fc (stock's span). Not AFBD (its interrupt status
belongs to the KMS driver), not DETN, never 0x07091000 or 0x06940000.
Each word is one aligned 32-bit load.
"""
import argparse
import json
import mmap
import os
import time

BLOCKS = [("comp", 0x05000000, 0x1000), ("route", 0x05140000, 0x1000),
          ("lvds", 0x051c0000, 0x400)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--samples", type=int, default=8)
    ap.add_argument("--interval", type=float, default=0.1)
    a = ap.parse_args()
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    maps = []
    for name, base, span in BLOCKS:
        m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
        maps.append((name, base, span, m, memoryview(m).cast("I")))
    out = {}
    try:
        for _ in range(a.samples):
            for name, base, span, _m, mv in maps:
                for off in range(0, span, 4):
                    out.setdefault(f"{name}+{off:03x}", []).append(mv[off // 4])
            time.sleep(a.interval)
    finally:
        for *_x, m, mv in maps:
            mv.release()
            m.close()
        os.close(fd)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
