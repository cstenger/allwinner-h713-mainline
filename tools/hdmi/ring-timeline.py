#!/usr/bin/env python3
"""Read-only timeline of the HDMI capture ring against the AFBD pair
(HDMI panel-source design 10.25.5).

Polls AFBD +0x320/+0x324 and the CRC of a few rows of each of the three Y
slots as fast as Python allows (about 1 ms) for SECS seconds. Each time a
row's CRC changes it records which slot, which row, the pair index at that
moment and the time since the pair last advanced. The summary answers:
while the pair names slot k, which slot is being written, and how far
into the pair period do writes land?

  ring-timeline.py [SECS]          (on the board, as root)

Reads only: AFBD page 0x05600000 and the ring carve-out in DRAM.
"""
import mmap
import os
import sys
import time
import zlib
from collections import Counter

AFBD = 0x05600000
FIRST = 0x4C3EF000
STEP = 0x1FF000
W = 1280
ROWS = (8, 180, 360, 540, 712)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    afbd = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=AFBD)
    ring = mmap.mmap(fd, STEP * 3, mmap.MAP_SHARED, mmap.PROT_READ, offset=FIRST)

    def pair():
        y = int.from_bytes(afbd[0x320:0x324], "little")
        c = int.from_bytes(afbd[0x324:0x328], "little")
        for i in range(3):
            if y == FIRST + STEP * i and c == FIRST + STEP * (i + 3):
                return i
        return -1

    def crcs():
        return [zlib.crc32(ring[s * STEP + r * W:s * STEP + r * W + W])
                for s in range(3) for r in ROWS]

    last = crcs()
    p = pair()
    t_pair = time.monotonic()
    pair_changes = []
    events = []  # (dt since pair change, pair, slot, row)
    t_end = t_pair + secs
    polls = 0
    while True:
        now = time.monotonic()
        if now > t_end:
            break
        polls += 1
        q = pair()
        if q >= 0 and q != p:
            pair_changes.append((now, p, q))
            p, t_pair = q, now
        cur = crcs()
        for k, (a, b) in enumerate(zip(last, cur)):
            if a != b:
                events.append((now - t_pair, p, k // len(ROWS), ROWS[k % len(ROWS)]))
        last = cur

    print(f"polls={polls} ({secs / polls * 1e3:.2f} ms/poll) pair changes={len(pair_changes)}")
    if len(pair_changes) > 1:
        gaps = [b[0] - a[0] for a, b in zip(pair_changes, pair_changes[1:])]
        print(f"pair period mean {sum(gaps) / len(gaps) * 1e3:.2f} ms, "
              f"min {min(gaps) * 1e3:.2f}, max {max(gaps) * 1e3:.2f}")
        steps = Counter((b - a) % 3 for _, a, b in pair_changes[1:])
        print("pair step (new - old mod 3):", dict(steps))
    rel = Counter((slot - pr) % 3 for _, pr, slot, _ in events if pr >= 0)
    print("row changes by (slot - pair) mod 3:", dict(rel))
    for d in range(3):
        for row in ROWS:
            dts = sorted(dt * 1e3 for dt, pr, slot, r in events
                         if pr >= 0 and (slot - pr) % 3 == d and r == row)
            if dts:
                print(f"  slot=pair+{d} row {row:3}: n={len(dts):3} "
                      f"dt ms min {dts[0]:6.2f} median {dts[len(dts) // 2]:6.2f} max {dts[-1]:6.2f}")


if __name__ == "__main__":
    main()
