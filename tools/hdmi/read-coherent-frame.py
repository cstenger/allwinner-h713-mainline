#!/usr/bin/env python3
"""Read one completed HDMI NV16 frame from the three-pair DRAM ring.

The observed writer visits Y/UV pairs 0/3, 1/4, then 2/5. When both planes of
one pair change, its predecessor has finished writing. Copy that predecessor
twice and accept only byte-identical copies with unchanged probe pages.
This is a read-only diagnostic, not a hardware frame-completion interrupt.
NV16 frames go to stdout consecutively; one JSON record per frame goes to
stderr. --count can collect a short sequence without repeated SSH startup.
"""

import argparse
import json
import mmap
import os
import sys
import time
import zlib

CARVEOUT = 0x4BF41000
SIZE = 26 * 1024 * 1024
BASE = 0x4C3EF000
STEP = 0x1FF000
PLANE = 640 * 480
PAGES = (0x10000, 0x20000, 0x30000, 0x40000)
PAGE_SIZE = 4096


def plane_hash(mem, index):
    base = BASE + STEP * index - CARVEOUT
    crc = 0
    for page in PAGES:
        offset = base + page
        crc = zlib.crc32(mem[offset:offset + PAGE_SIZE], crc)
    return crc


def read_pair(mem, pair):
    y = BASE + STEP * pair - CARVEOUT
    uv = BASE + STEP * (pair + 3) - CARVEOUT
    return mem[y:y + PLANE] + mem[uv:uv + PLANE]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeout", type=float, default=5,
                    help="seconds to look for a verified frame (default: 5)")
    ap.add_argument("--interval-ms", type=float, default=2,
                    help="minimum interval between ring probes (default: 2)")
    ap.add_argument("--count", type=int, choices=range(1, 9), default=1,
                    help="number of successive verified frames (default: 1)")
    args = ap.parse_args()
    if not 0 < args.timeout <= 15 or not 0 < args.interval_ms <= 20:
        ap.error("timeout must be 0..15 s and interval must be 0..20 ms")

    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, SIZE, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ,
                       offset=CARVEOUT) as mem:
            start = time.monotonic()
            previous = [plane_hash(mem, i) for i in range(6)]
            attempts = 0
            completed = 0
            last_pair = None
            while time.monotonic() - start < args.timeout and completed < args.count:
                time.sleep(args.interval_ms / 1000)
                current = [plane_hash(mem, i) for i in range(6)]
                changed = [i for i in range(3)
                           if current[i] != previous[i]
                           and current[i + 3] != previous[i + 3]]
                previous = current
                if len(changed) != 1:
                    continue
                active = changed[0]
                pair = (active - 1) % 3
                if pair == last_pair:
                    continue
                attempts += 1
                before = (plane_hash(mem, pair), plane_hash(mem, pair + 3))
                copy_start = time.monotonic()
                first = read_pair(mem, pair)
                second = read_pair(mem, pair)
                copy_ms = (time.monotonic() - copy_start) * 1000
                after = (plane_hash(mem, pair), plane_hash(mem, pair + 3))
                if first != second or before != after:
                    continue
                completed += 1
                last_pair = pair
                sys.stderr.write(json.dumps({
                    "frame": completed,
                    "active_pair": active,
                    "captured_pair": pair,
                    "attempts": attempts,
                    "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
                    "copy_ms": round(copy_ms, 3),
                    "bytes": len(first),
                    "crc32": f"{zlib.crc32(first):08x}",
                }) + "\n")
                sys.stdout.buffer.write(first)
            if completed != args.count:
                raise RuntimeError(f"only {completed}/{args.count} verified frames in "
                                   f"{args.timeout:g} s ({attempts} candidates)")
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as e:
        sys.exit(str(e))
