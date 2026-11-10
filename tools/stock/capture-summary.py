#!/usr/bin/env python3
"""Summarise one stock-capture state on the host, while the session is running.

Reads what `stock-capture.sh play <tag>` (and `elog <tag>-early`) left in
OUT/<tag>-1, <tag>-2, <tag>-irq, and prints the handful of facts each case is
for, so the next file is chosen knowing what this one showed:

  * interrupt rates -- above all cedar_dev (the VE) vs sunxi_go_ctx (AV1):
    a VE that ticks while only the AV1 core decodes is the memory-to-memory
    path the plan is looking for;
  * the display geometry registers: AFBD source raster, composition line
    buffers, proc scaler (4 instances), panel down-scaler and selector;
  * which display words differ from the idle baseline, per block;
  * the window layer's own account from the elog (wce_*, win_mgr): windows,
    ratios, border widths, "No need to enable ...".

It interprets nothing beyond decoding fields already established in
docs/register-index.md. Full analysis is desk work afterwards.

    capture-summary.py OUT TAG [--baseline idle]
"""
import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "elog_parse", os.path.join(HERE, "..", "mips", "elog-parse.py"))
elog_parse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(elog_parse)

IRQS = ("cedar_dev", "sunxi_go_ctx", "dec", "osd-afbd", "5240000.ge2d", "1800000.gpu")
BLOCKS = {"05000": "composition", "05040": "comp+0x40000", "050c0": "DETN/NR",
          "05140": "route", "05180": "proc", "051c0": "panel", "05600": "AFBD"}
WINDOW_TAGS = r"wce_|win_mgr"
WINDOW_WORDS = re.compile(r"win|cfg|ratio|width|scal|bypass|aspect|rowbyte|line_num|"
                          r"No need|enable|mirror|rotat|flip", re.I)


def regs(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="latin-1"):
        f = line.split()
        if len(f) == 2 and len(f[0]) == 8 and f[1].startswith("0x"):
            out[int(f[0], 16)] = int(f[1], 16)
    return out


def irq_counts(path):
    d = {}
    for line in open(path, encoding="latin-1"):
        f = line.split()
        if not f or not f[0].endswith(":"):
            continue
        try:
            n = sum(int(x) for x in f[1:5])
        except ValueError:
            continue
        d[f[-1]] = d.get(f[-1], 0) + n
    return d


def print_irqs(out, tag):
    d = os.path.join(out, f"{tag}-irq")
    if not os.path.isdir(d):
        print("  (no irq window)")
        return
    a, b = irq_counts(f"{d}/interrupts-a"), irq_counts(f"{d}/interrupts-b")
    t = float(open(f"{d}/uptime-b").read().split()[0]) - float(open(f"{d}/uptime-a").read().split()[0])
    cells = [f"{n} {(b.get(n, 0) - a.get(n, 0)) / t:6.1f}/s" for n in IRQS]
    print(f"  irq over {t:.1f} s: " + " | ".join(cells))


def field(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def print_geometry(r):
    g = r.get
    if 0x05600030 not in r:
        print("  (no display capture)")
        return
    src = g(0x05600030, 0)
    # Only +0x30 is decoded (register index: [31:16] height, [15:0] width);
    # the upper halves of +0x48/+0x4c also carry a fetch budget (P010 work,
    # 2026-09-30), so those print raw.
    print(f"  AFBD    ctrl {g(0x05600010, 0):#010x}  src(+30) {field(src, 15, 0)}x{field(src, 31, 16)}"
          f"  +40 {g(0x05600040, 0):#010x}  +44 {g(0x05600044, 0):#010x}"
          f"  +48 {g(0x05600048, 0):#010x}  +4c {g(0x0560004c, 0):#010x}")
    print(f"  comp    0f0 {g(0x050000f0, 0):#010x}  174 {g(0x05000174, 0):#010x}  178 {g(0x05000178, 0):#010x}"
          f"  274 {g(0x05000274, 0):#010x}  278 {g(0x05000278, 0):#010x}")
    for i in range(4):
        b = 0x05180000 + i * 0x100
        h, v = field(g(b + 0x08, 0), 21, 0), field(g(b + 0x3c, 0), 21, 0)
        print(f"  proc{i}   ratio H {h:#08x} ({h / 65536:.4f}) V {v:#08x} ({v / 65536:.4f})"
              f"  in(+34) {g(b + 0x34, 0):#010x}  out(+2c/+30) {g(b + 0x2c, 0):#010x}/{g(b + 0x30, 0):#010x}"
              f"  +50 {g(b + 0x50, 0):#010x}")
    ds = [g(0x051c0120 + 4 * k, 0) for k in range(7)]
    byp = field(ds[1], 26, 25)
    print(f"  panel   sel 006c {g(0x051c006c, 0):#010x}  downscaler {'BYPASS' if byp == 3 else f'mode {byp}'}"
          f"  V ratio {field(ds[6], 21, 0) / 65536:.4f}  120..138 " + " ".join(f"{x:08x}" for x in ds))


def print_moved(r, base):
    if not base:
        return
    moved = {}
    for a, v in r.items():
        if a in base and base[a] != v:
            moved.setdefault(f"{a:08x}"[:5], []).append(a)
    parts = [f"{BLOCKS.get(k, k)} {len(v)}" for k, v in sorted(moved.items())]
    print("  vs baseline, words changed: " + (", ".join(parts) or "none"))
    for k in ("05600", "051c0", "05180"):
        if k in moved and len(moved[k]) <= 24:
            print(f"    {BLOCKS[k]}: " + " ".join(f"{a & 0xfff:03x}:{base[a]:08x}>{r[a]:08x}" for a in moved[k]))


def print_elog(out, tag, previous):
    paths = [os.path.join(out, t, "elog.bin") for t in (f"{tag}-early", f"{tag}-1", f"{tag}-2")]
    paths = [p for p in paths if os.path.exists(p) and os.path.getsize(p)]
    if not paths:
        print("  (no elog)")
        return
    blob = elog_parse.merge([open(p, "rb").read() for p in paths])
    recs = sorted(elog_parse.records(blob), key=lambda r: (r[3], r[0]))  # ring: time order
    old = set()
    if previous and os.path.exists(previous):
        old = {(o, m) for o, _, _, _, _, m, _ in elog_parse.records(open(previous, "rb").read())}
    new = [r for r in recs if (r[0], r[5]) not in old]
    ts = [r[3] for r in recs if r[3] >= 0]
    print(f"  elog: {len(recs)} records (ts {min(ts, default=-1)}..{max(ts, default=-1)}), {len(new)} new")
    shown = 0
    for off, lvl, t, ts_, src, msg, dmg in new:
        if re.search(WINDOW_TAGS, t) and WINDOW_WORDS.search(msg):
            print(f"    {'!' if dmg else ' '}{lvl}/{t:12s} [{ts_:>5}] {src.split()[-1] if src else '':>5} {msg[:110]}")
            shown += 1
            if shown >= 60:
                print("    ... (more: tools/mips/elog-parse.py --tags 'wce_|win_mgr')")
                break


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("tag")
    ap.add_argument("--baseline", default="idle")
    ap.add_argument("--previous-elog", help="elog.bin of the case before, to show only new records")
    a = ap.parse_args()

    print(f"== {a.tag}")
    print_irqs(a.out, a.tag)
    r = regs(os.path.join(a.out, f"{a.tag}-2", "display.txt"))
    print_geometry(r)
    print_moved(r, regs(os.path.join(a.out, f"{a.baseline}-2", "display.txt")))
    print_elog(a.out, a.tag, a.previous_elog)


if __name__ == "__main__":
    sys.exit(main())
