#!/usr/bin/env python3
"""Diff two display-register states, each sampled twice, and rank what is left.

docs/hdmi-panel-source-design-2026-10-23.md section 10.21.  Input is the
hidtvreg-read format (`aaaaaaaa 0xVVVVVVVV`) that both stock-capture.sh sweep
and display-sweep.py write, or the snapshot format (`name 0xAAAAAAAA VVVVVVVV`); a sample is a directory (its A.txt, A2.txt,
B.txt, display.txt) or a single file.

Every word present in both states is classed, first match wins:
  stat      differs between a state's own two samples (counters, statistics,
            free-running status), so it says nothing about configuration
  same      equal in both states
  geometry  a line-buffer / window word the KMS driver's letterbox table
            programs (parsed from sun50i-h713-afbd.c), or AFBD's size,
            stride and row words
  queue     AFBD address queue 0x070-0x0ac and the capture pair 0x300-0x33c
  CONFIG    everything else that differs: the candidates, ranked first

    diff-display-sweeps.py --x S2-a S2-b --y O2-a O2-b [--names stock ours]
    diff-display-sweeps.py --self-test
"""
import argparse
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINE = re.compile(r"^([0-9a-fA-F]{8})\s+0x([0-9a-fA-F]{8})\s*$")
SNAP = re.compile(r"^\S+\s+0x([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s*$")  # panel-source-snapshot / letterbox format
BLOCK = {"LB_COMP": 0x05000000, "LB_ROUTE": 0x05140000, "LB_PROC": 0x05180000,
         "LB_LVDS": 0x051C0000, "LB_VBLEND": 0x05200000}
NAMES = [(0x05000000, "comp"), (0x05040000, "blk504"), (0x050C0000, "detn"), (0x05140000, "route"),
         (0x05180000, "proc"), (0x051C0000, "lvds"), (0x05200000, "vblend"), (0x05240000, "blk524"),
         (0x0524C000, "de_osd"), (0x0525C000, "mixer"), (0x05280000, "layer"), (0x05600000, "afbd"),
         (0x05700000, "tvtop"), (0x05880000, "tcon"), (0x058C0000, "pll"), (0x02010000, "iommu"),
         (0x03061000, "mips")]
AFBD_GEOM = {0x05600000 + o for o in (0x20, 0x24, 0x30, 0x40, 0x44, 0x48, 0x4C, 0x160, 0x170)}
QUEUE = {0x05600000 + o for o in list(range(0x70, 0xB0, 4)) + list(range(0x300, 0x340, 4))}


def name(a):
    base, n = max((b, n) for b, n in NAMES if b <= a)
    return f"{n}+{a - base:03x}"


def driver_geometry():
    """(address) of every word the KMS letterbox table writes."""
    srcs = sorted(glob.glob(str(ROOT / "build/linux-*/drivers/gpu/drm/tiny/sun50i-h713-afbd.c")))
    if not srcs:
        raise FileNotFoundError("sun50i-h713-afbd.c not found under build/linux-*; rebuild the tree")
    t = Path(srcs[-1]).read_text()
    out = set()
    for blk, off in re.findall(r"\b(?:ABS|REL)\((LB_\w+),\s*(0x[0-9a-fA-F]+),", t):
        out.add(BLOCK[blk] + int(off, 16))
    return out


def load(path):
    p = Path(path)
    files = [p] if p.is_file() else [p / n for n in ("A.txt", "A2.txt", "B.txt", "display.txt") if (p / n).exists()]
    if not files:
        raise FileNotFoundError(f"no register files in {p}")
    d = {}
    for f in files:
        for line in open(f):
            m = LINE.match(line) or SNAP.match(line)
            if m:
                d[int(m.group(1), 16)] = int(m.group(2), 16)
    return d


def classify(x, y, geom):
    """x, y: lists of sample dicts (1 or 2 each). Returns {addr: (class, xv, yv)}."""
    common = set.intersection(*(set(s) for s in x + y))
    res = {}
    for a in sorted(common):
        xv, yv = x[0][a], y[0][a]
        if any(s[a] != xv for s in x[1:]) or any(s[a] != yv for s in y[1:]):
            c = "stat"
        elif xv == yv:
            c = "same"
        elif a in geom or a in AFBD_GEOM:
            c = "geometry"
        elif a in QUEUE:
            c = "queue"
        else:
            c = "CONFIG"
        res[a] = (c, xv, yv)
    return res


def report(res, names=("x", "y")):
    counts = {}
    for c, _, _ in res.values():
        counts[c] = counts.get(c, 0) + 1
    print(f"{len(res)} common words: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for cls in ("CONFIG", "geometry", "queue"):
        rows = [(a, xv, yv) for a, (c, xv, yv) in res.items() if c == cls]
        if not rows:
            continue
        print(f"\n== {cls} ({len(rows)})   {names[0]:>10} {names[1]:>10}   xor")
        for a, xv, yv in rows:
            print(f"  {name(a):<13} {a:08x}  {xv:08x}   {yv:08x}   {xv ^ yv:08x}")


def self_test():
    fails = []
    geom = driver_geometry()
    # 1. the parsed letterbox table contains words we know it writes
    for a in (0x05000278, 0x050002B8, 0x05000804, 0x05180008, 0x051C003C, 0x05200000):
        if a not in geom:
            fails.append(f"letterbox table parse misses {a:#x}")
    # 2. synthetic: one of each class lands where it should
    base = {0x05000030: 0xC00, 0x05000278: 0x60020168, 0x05600070: 0xF0E00000, 0x05600058: 0x47,
            0x05140168: 1, 0x05140E00: 0xFFFF}
    x1, x2 = dict(base), {**base, 0x05600058: 0x62}
    y1 = {**base, 0x05000030: 0x400000, 0x05000278: 0x600202D0, 0x05600070: 0, 0x05140E00: 0xFFBF}
    y2 = dict(y1)
    r = classify([x1, x2], [y1, y2], geom)
    want = {0x05000030: "CONFIG", 0x05000278: "geometry", 0x05600070: "queue", 0x05600058: "stat",
            0x05140168: "same", 0x05140E00: "CONFIG"}
    for a, c in want.items():
        if r[a][0] != c:
            fails.append(f"synthetic {a:#x}: {r[a][0]} != {c}")
    # 3. real data: the 08-28 stock vs 08-29 Linux sweeps; their header records
    #    37 AFBD differences (stock playing, ours idle) -- the parser must see them
    s = load(ROOT / "docs/reference/stock-android-block-sweep-2026-08-28.txt")
    l = load(ROOT / "docs/reference/linux-block-sweep-2026-08-29.txt")
    n = sum(1 for a in set(s) & set(l) if 0x05600000 <= a < 0x05601000 and s[a] != l[a])
    if n != 37:
        fails.append(f"08-28 vs 08-29 AFBD differences {n}, header says 37")
    # 4. the snapshot format parses to the same values as the address it names
    snap = load(ROOT / "docs/reference/letterbox-baseline-2026-10-04/native-720p.txt")
    if snap.get(0x05600010) != 0x03000013 or snap.get(0x051C006C) != 0x39000000:
        fails.append("snapshot-format parse wrong")
    # 5. a word missing from one state is not silently compared
    r = classify([{1: 1}], [{2: 2}], geom)
    if r:
        fails.append("words absent from one side were compared")
    for f in fails:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else f"passed (letterbox table: {len(geom)} words)")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--x", nargs="+")
    ap.add_argument("--y", nargs="+")
    ap.add_argument("--names", nargs=2, default=("x", "y"))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not (a.x and a.y) or len(a.x) > 2 or len(a.y) > 2:
        ap.error("--x and --y take one or two samples each")
    report(classify([load(p) for p in a.x], [load(p) for p in a.y], driver_geometry()), a.names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
