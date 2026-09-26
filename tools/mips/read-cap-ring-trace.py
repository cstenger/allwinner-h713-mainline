#!/usr/bin/env python3
"""Correlate read-only MIPS VIncap counters with the HDMI frame ring.

The volatile U-Boot comm trace must include the guarded VIncap hook.  This
program never accesses capture-domain MMIO: it reads only the trace mailbox in
reserved DRAM and sparse pages from the already-identified NV16 frame ring.
Each ring sample is bracketed by capture-counter snapshots so events that land
during hashing remain distinguishable from unambiguous before/after ordering.
"""

import argparse
import importlib.util
import json
import mmap
import os
from pathlib import Path
import time
import zlib


MAILBOX = 0x4D980000
MAGIC = 0x434F4D4D
CANARY = 0x43414E31
CARVEOUT = 0x4BF41000
CARVEOUT_SIZE = 26 * 1024 * 1024
PLANE_BASE = 0x4C3EF000
PLANE_STEP = 0x1FF000
PROBE_PAGES = (0x10000, 0x20000, 0x30000, 0x40000)
PAGE_SIZE = 4096
CAPTURE_PATCHED_WORDS = (
    (0x4B100BA0, 0x27BDFFF8),
    (0x4B100BA4, 0xAFB80000),
    (0x4B100BA8, 0xAFB90004),
    (0x4B100BAC, 0x3C18AD98),
    (0x4B100BB0, 0x31390001),
    (0x4B100BB4, 0x13200003),
    (0x4B100BB8, 0x8F190088),
    (0x4B100BC0, 0xAF190088),
    (0x4B100BC4, 0x31390002),
    (0x4B100BC8, 0x13200003),
    (0x4B100BCC, 0x8F19008C),
    (0x4B100BD4, 0xAF19008C),
    (0x4B100BD8, 0x31390004),
    (0x4B100BDC, 0x13200003),
    (0x4B100BE0, 0x8F190090),
    (0x4B100BE8, 0xAF190090),
    (0x4B100BEC, 0x8F190084),
    (0x4B100BF4, 0xAF190084),
    (0x4B100BF8, 0x8FB80000),
    (0x4B100BFC, 0x8FB90004),
    (0x4B100C00, 0x27BD0008),
    (0x4B100C04, 0x8C470008),
    (0x4B100C08, 0x0AC618EB),
    (0x4B1863A4, 0x0AC402E8),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=6,
                        help="bounded trace duration, 0.1..30 seconds")
    parser.add_argument("--interval", type=float, default=0.003,
                        help="sample interval, 0.002..0.1 seconds")
    args = parser.parse_args()
    if not 0.1 <= args.seconds <= 30:
        parser.error("--seconds must be between 0.1 and 30")
    if not 0.002 <= args.interval <= 0.1:
        parser.error("--interval must be between 0.002 and 0.1")

    spec = importlib.util.spec_from_file_location(
        "mips_shell", Path(__file__).with_name("mips-shell.py"))
    shell = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shell)
    mem = shell.Mem()
    for address, expected in CAPTURE_PATCHED_WORDS:
        actual = mem.u32(address)
        if actual != expected:
            raise SystemExit(f"capture patch mismatch at {address:#x}: "
                             f"{actual:#010x} != {expected:#010x}")
    if mem.u32(MAILBOX + 4) != MAGIC:
        raise SystemExit("comm-trace magic absent")
    if (mem.u32(MAILBOX + 0x80) != CANARY or
            mem.u32(MAILBOX + 0xFFC) != CANARY):
        raise SystemExit("comm-trace page guard absent")

    def counters():
        values = [mem.u32(MAILBOX + offset) for offset in
                  (0x84, 0x88, 0x8C, 0x90)]
        return dict(zip(("irq", "vde", "vs", "mode_change"), values))

    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        with mmap.mmap(fd, CARVEOUT_SIZE, flags=mmap.MAP_SHARED,
                       prot=mmap.PROT_READ, offset=CARVEOUT) as ring:
            print(json.dumps({
                "type": "metadata", "seconds": args.seconds,
                "interval": args.interval,
                "planes": [f"0x{PLANE_BASE + i * PLANE_STEP:08x}"
                           for i in range(6)],
                "probe_pages": [f"0x{x:x}" for x in PROBE_PAGES],
            }, separators=(",", ":")), flush=True)
            started = time.monotonic_ns()
            deadline = started + int(args.seconds * 1_000_000_000)
            sample = 0
            while True:
                before_ns = time.monotonic_ns()
                before = counters()
                hashes = [None] * 6
                pair_windows = []
                for pair in range(3):
                    pair_before = counters()
                    for plane in (pair, pair + 3):
                        offset = PLANE_BASE + plane * PLANE_STEP - CARVEOUT
                        crc = 0
                        for page in PROBE_PAGES:
                            pos = offset + page
                            crc = zlib.crc32(ring[pos:pos + PAGE_SIZE], crc)
                        hashes[plane] = f"{crc:08x}"
                    pair_after = counters()
                    pair_windows.append({"pair": pair, "before": pair_before,
                                         "after": pair_after})
                after = counters()
                after_ns = time.monotonic_ns()
                print(json.dumps({
                    "type": "sample", "sample": sample,
                    "start_ns": before_ns - started,
                    "end_ns": after_ns - started,
                    "before": before, "crc32": hashes, "after": after,
                    "pair_windows": pair_windows,
                }, separators=(",", ":")), flush=True)
                sample += 1
                if after_ns >= deadline:
                    break
                next_sample = started + int(sample * args.interval * 1e9)
                now = time.monotonic_ns()
                if next_sample > now:
                    time.sleep((next_sample - now) / 1e9)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
