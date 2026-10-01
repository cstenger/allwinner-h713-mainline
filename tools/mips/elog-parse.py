#!/usr/bin/env python3
"""Decode a raw dump of the MIPS display firmware's elog buffer, on the host.

The firmware logs to DRAM when display_cfg.xml's elog_init_setting has
mode 2 (buf); level 5 makes the window layer (wce_*, win_mgr) print every
window, ratio and border it programs.  The buffer is static data inside the
firmware image, so with the same display.bin it sits at the same address on
both stacks:  0x4b270000 + 2 MiB (records start near 0x4b272000).

Raw dumps come from either side, byte-identical in layout:
    stock     hidtvreg-raw 4b270000 200000 > elog.bin
    ours      python3 rawread.py 4b270000 200000 > elog.bin   (/dev/mem mmap)

    elog-parse.py elog.bin                      every record, in time order
    elog-parse.py elog.bin --tags 'wce_|win_mgr'  window layer only
    elog-parse.py b.bin --since a.bin           only records b has that a lacks

HOLES.  Runs of zero bytes inside records are MIPS data-cache lines that had
not been written back when the ARM read DRAM (16/32/48-byte multiples, 2026-
10-01).  They are shown as '~' runs, never dropped: a record with a hole is a
damaged record, not a short one.  A second sample a few seconds later fills
most of them -- pass both and the later one wins where it has data (--merge).

LEVEL 5 COSTS THE VENDOR ~3 MINUTES OF BOOT (2026-10-01): with it, stock's
CPU_COMM handshake logged every spinlock step and took 184.7 s instead of ~1 s
("cpu comm init" in the sys records); Android sat at the logo until then and
recovered by itself. The ring is then full of cpucomm records, and wraps.

Same caveat as 2026-09-08: absence of a record is weak evidence.  A record
can sit in the cache past the read, and the ring may overwrite old records.
"""
import argparse
import re
import sys

BASE = 0x4B270000
START = re.compile(rb"\x1b\[[0-9;]*m(?=[A-Z]/[a-z_0-9]+\s*\[)")
HEAD = re.compile(rb"([A-Z])/([a-z_0-9]+)\s*\[\s*(\d+)\]\s*\(([^)]*)\)\s*(.*)", re.S)
END = b"\x1b[0m"


def records(blob):
    """Yield (offset, level, tag, ts, src, msg, damaged) in buffer order."""
    starts = [m.start() for m in START.finditer(blob)]
    for i, s in enumerate(starts):
        limit = starts[i + 1] if i + 1 < len(starts) else len(blob)
        body = blob[s:limit]
        body = body[body.index(b"m") + 1:]
        e = body.find(END)
        if e >= 0:
            body = body[:e]
        # A record that runs into the untouched tail of the buffer: cut the
        # trailing zeros, they are not part of it.
        body = body.rstrip(b"\x00\n")
        damaged = b"\x00" in body
        text = re.sub(rb"\x00+", lambda z: b"~" * len(z.group()), body)
        text = text.decode("latin-1").replace("\n", " ").strip()
        h = HEAD.match(text.encode("latin-1"))
        if not h:
            yield s, "?", "?", -1, "", text, damaged
            continue
        lvl, tag, ts, src, msg = (x.decode("latin-1") for x in h.groups())
        yield s, lvl, tag, int(ts), src.strip(), msg.strip(), damaged


def merge(blobs):
    """Later samples win wherever they hold a non-zero byte."""
    out = bytearray(blobs[0])
    for b in blobs[1:]:
        for i in range(0, min(len(out), len(b)), 16):
            chunk = b[i:i + 16]
            if any(chunk):
                out[i:i + len(chunk)] = chunk
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dumps", nargs="+", help="raw elog dumps, oldest first")
    ap.add_argument("--merge", action="store_true",
                    help="merge all dumps into one before decoding")
    ap.add_argument("--since", metavar="OLD",
                    help="print only records not present (same offset, same text) in OLD")
    ap.add_argument("--tags", metavar="REGEX", help="keep only tags matching REGEX")
    ap.add_argument("--base", type=lambda v: int(v, 16), default=BASE)
    ap.add_argument("--offsets", action="store_true", help="prefix each record's address")
    ap.add_argument("--stats", action="store_true", help="summary only")
    args = ap.parse_args()

    blobs = [open(p, "rb").read() for p in args.dumps]
    blob = merge(blobs) if args.merge else blobs[-1]
    # The buffer is a RING (stock, 2026-10-01: a full buffer keeps taking
    # records at a moving write pointer), so buffer order stops being time
    # order after the first wrap. Timestamps are ms since firmware start and
    # monotonic: sort on them, buffer offset breaking ties.
    recs = sorted(records(blob), key=lambda r: (r[3], r[0]))

    if args.since:
        old = {(o, f"{l}/{t}[{ts}]{s}{m}") for o, l, t, ts, s, m, _ in
               records(open(args.since, "rb").read())}
        recs = [r for r in recs if (r[0], f"{r[1]}/{r[2]}[{r[3]}]{r[4]}{r[5]}") not in old]
    if args.tags:
        keep = re.compile(args.tags)
        recs = [r for r in recs if keep.search(r[2])]

    if args.stats:
        from collections import Counter
        dmg = sum(1 for r in recs if r[6])
        ts = [r[3] for r in recs if r[3] >= 0]
        print(f"{len(recs)} records, {dmg} damaged, ts {min(ts, default=-1)}..{max(ts, default=-1)}")
        if recs:
            print(f"span {args.base + recs[0][0]:#x}..{args.base + recs[-1][0]:#x}")
        for tag, n in Counter(r[2] for r in recs).most_common():
            print(f"  {tag:14s} {n}")
        return

    for off, lvl, tag, ts, src, msg, damaged in recs:
        pre = f"{args.base + off:08x} " if args.offsets else ""
        mark = "!" if damaged else " "
        print(f"{pre}{mark}{lvl}/{tag:12s} [{ts:>6}] ({src:32s}) {msg}")


if __name__ == "__main__":
    sys.exit(main())
