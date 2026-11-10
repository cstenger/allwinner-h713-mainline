#!/usr/bin/env python3
"""Read-only sweep of the display blocks on OUR Linux, matching stock's capture.

docs/hdmi-panel-source-design-2026-10-23.md section 10.21.  The same address
lists as `tools/stock/stock-capture.sh sweep`, and output byte-compatible with
stock's hidtvreg-read (`aaaaaaaa 0xVVVVVVVV`, upper-case value), so a stock
sweep and ours diff line for line (tools/hdmi/diff-display-sweeps.py).

  A   stock-capture.sh's DISPLAY_BLOCKS: read on stock and on our MIPS-live
      Linux on 08-31 (composition page, 0x05040000, DETN, route, proc,
      1 KiB panel block, AFBD 0x000-0x1fc)
  A'  the 08-28 stock / 08-29 Linux block-sweep windows A does not already
      cover (TVTOP, MIXER, DE_OSD, 0x05240000, LAYER, display PLL, MIPS
      status, IOMMU 0x000-0x07c)
  B   extended: AFBD 0x200-0x3fc, vblend, TCON, IOMMU 0x080-0x13c
  C   raw DRAM: the MIPS image 0x4b100000 + 0xe41000 (code, heap, window
      nodes, the loaded cfg and the elog), read in 1 MiB chunks

Lists are read in that order and every file is fsync'd before the next, so a
wedge can only lose the list being read.  Nothing here writes a register:
/dev/mem is opened O_RDONLY.  Refused, here and in stock-capture.sh:
0x069xxxxx, 0x0709xxxx (RTC GP6/GP7, CPUS), the composition page 0x05001xxx
(the 0x0500153x lock window), VE and AV1.

    display-sweep.py OUTDIR [--label L] [--no-raw]   # on the board, as root
    display-sweep.py --dry                           # the address plan, no reads
    display-sweep.py --self-test                     # offline
"""
import argparse
import hashlib
import json
import mmap
import os
import re
import sys
import time
from pathlib import Path

# (base, hex word count as hidtvreg-read takes it)
LIST_A = [(0x05000000, 0x400), (0x05040000, 0x400), (0x050C0000, 0x400), (0x05140000, 0x400),
          (0x05180000, 0x400), (0x051C0000, 0x100), (0x05600000, 0x80)]
LIST_A2 = [(0x05700000, 0x30), (0x0525C000, 0x20), (0x0524C000, 0x20), (0x05280080, 0x10),
           (0x058C0010, 0x08), (0x05240000, 0x10), (0x03061010, 0x04), (0x02010000, 0x20)]
LIST_B = [(0x05600200, 0x80), (0x05200000, 0x20), (0x05880000, 0x40), (0x02010080, 0x30)]
LIST_C = [(0x4B100000, 0xE41000, "mips-image.bin")]
FORBIDDEN = [(0x06900000, 0x069FFFFF, "0x069xxxxx (capture DMA / TV domains)"),
             (0x07090000, 0x0709FFFF, "0x0709xxxx (RTC GP6/GP7, CPUS 0x07091xxx)"),
             (0x05001000, 0x05001FFF, "composition page 0x05001xxx (0x0500153x lock window)"),
             (0x01C0D000, 0x01C0DFFF, "AV1"), (0x01C0E000, 0x01C0EFFF, "VE")]
RAW_WINDOW = (0x4B100000, 0x4BF41000)


def check_words(base, count):
    """Return the word addresses of one list entry, refusing anything unsafe."""
    if base & 3 or not 0 < count <= 0x400:
        raise ValueError(f"bad entry {base:#x}:{count:#x}")
    if (base & 0xFFF) + count * 4 > 0x1000:
        raise ValueError(f"{base:#x}:{count:#x} crosses a page (hidtvreg-read clamps; we refuse)")
    last = base + 4 * (count - 1)
    for lo, hi, why in FORBIDDEN:
        if base <= hi and last >= lo:
            raise ValueError(f"{base:#x}:{count:#x} touches {why}")
    return [base + 4 * i for i in range(count)]


def check_raw(base, size):
    if base & 0xFFF or size & 3 or not RAW_WINDOW[0] <= base < base + size <= RAW_WINDOW[1]:
        raise ValueError(f"raw {base:#x}+{size:#x} outside the MIPS DRAM window")


def plan():
    out = []
    for name, lst in (("A", LIST_A), ("A2", LIST_A2), ("B", LIST_B)):
        for base, count in lst:
            check_words(base, count)
            out.append(f"READ {name} {base:08x} {count:x}")
    for base, size, fn in LIST_C:
        check_raw(base, size)
        out.append(f"RAW C {base:08x} {size:x} {fn}")
    return out


def sweep(outdir, label, raw):
    outdir.mkdir(parents=True, exist_ok=False)
    for line in plan():  # validate everything before the first read
        pass
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    meta = {"label": label, "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip(),
            "uptime": open("/proc/uptime").read().split()[0], "files": {}}

    def put(name, data):
        p = outdir / name
        with open(p, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        meta["files"][name] = hashlib.sha256(data).hexdigest()

    try:
        for name, lst in (("A", LIST_A), ("A2", LIST_A2), ("B", LIST_B)):
            lines = []
            for base, count in lst:
                page = base & ~0xFFF
                m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=page)
                v = memoryview(m).cast("I")
                for a in check_words(base, count):
                    lines.append(f"{a:08x} 0x{v[(a - page) // 4]:08X}")
                v.release()
                m.close()
            put(f"{name}.txt", ("\n".join(lines) + "\n").encode())
        if raw:
            for base, size, fn in LIST_C:
                check_raw(base, size)
                buf = bytearray()
                for off in range(0, size, 0x100000):
                    n = min(0x100000, size - off)
                    m = mmap.mmap(fd, n, mmap.MAP_SHARED, mmap.PROT_READ, offset=base + off)
                    buf += m[:n]
                    m.close()
                put(fn, bytes(buf))
    finally:
        os.close(fd)
        meta["uptime_end"] = open("/proc/uptime").read().split()[0]
        (outdir / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps({k: (v if k != "files" else list(v)) for k, v in meta.items()}))


def stock_lists(script):
    t = Path(script).read_text()
    out = {}
    for var in ("DISPLAY_BLOCKS", "SWEEP_A2", "SWEEP_B"):
        m = re.search(rf'^{var}="([^"]*)"', t, re.M)
        out[var] = [(int(a, 16), int(c, 16)) for a, c in (e.split(":") for e in m.group(1).split())] if m else None
    m = re.search(r'^SWEEP_C="([^"]*)"', t, re.M)
    out["SWEEP_C"] = [(int(a, 16), int(s, 16)) for a, s, _ in (e.split(":") for e in m.group(1).split())] if m else None
    return out


def self_test():
    root = Path(__file__).resolve().parents[2]
    fails = []
    # 1. list A is exactly stock-capture.sh's DISPLAY_BLOCKS; A'/B/C equal its sweep lists
    s = stock_lists(root / "tools/stock/stock-capture.sh")
    for var, mine in (("DISPLAY_BLOCKS", LIST_A), ("SWEEP_A2", LIST_A2), ("SWEEP_B", LIST_B)):
        if s[var] != mine:
            fails.append(f"{var} in stock-capture.sh differs from ours: {s[var]}")
    if s["SWEEP_C"] != [(b, n) for b, n, _ in LIST_C]:
        fails.append(f"SWEEP_C differs: {s['SWEEP_C']}")
    # 2. A + A' cover every address of the 08-28 stock block sweep
    want = set()
    for line in open(root / "docs/reference/stock-android-block-sweep-2026-08-28.txt"):
        m = re.match(r"([0-9a-f]{8}) 0x", line)
        if m:
            want.add(int(m.group(1), 16))
    have = {a for b, c in LIST_A + LIST_A2 for a in check_words(b, c)}
    if want - have:
        fails.append(f"A+A' miss {len(want - have)} 08-28 addresses, e.g. {sorted(want - have)[:3]}")
    # ... and A covers the 08-31 pages exactly
    want31 = set()
    for line in open(root / "docs/reference/stock-firmware-blocks-4sample-2026-08-31.txt"):
        m = re.match(r"([0-9a-f]{8}) 0x", line)
        if m:
            want31.add(int(m.group(1), 16))
    haveA = {a for b, c in LIST_A for a in check_words(b, c)}
    if want31 - haveA - {a for b, c in LIST_A2 for a in check_words(b, c)}:
        fails.append("A misses 08-31 addresses")
    # 3. every exclusion refuses, and page crossings / raw outside the window refuse
    for base, count in ((0x06940928, 1), (0x0709011C, 1), (0x07091000, 1), (0x05001530, 1),
                        (0x05000FFC, 2), (0x05140FF8, 4), (0x01C0E000, 4), (0x01C0D010, 1), (0x0693FFFC, 0x10)):
        try:
            check_words(base, count)
            fails.append(f"{base:#x}:{count:#x} not refused")
        except ValueError:
            pass
    for base, size in ((0x4BF41000, 0x1000), (0x40000000, 0x1000), (0x4B100000, 0xE42000)):
        try:
            check_raw(base, size)
            fails.append(f"raw {base:#x}+{size:#x} not refused")
        except ValueError:
            pass
    # 4. the plan validates and is in A, A', B, C order
    p = plan()
    order = [l.split()[1] for l in p]
    if order != sorted(order, key=["A", "A2", "B", "C"].index):
        fails.append("plan out of order")
    for f in fails:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else f"passed (plan: {len(p)} entries, "
          f"{sum(c for _, c in LIST_A + LIST_A2 + LIST_B)} words + {LIST_C[0][1]} raw bytes)")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", nargs="?", type=Path)
    ap.add_argument("--label", default="")
    ap.add_argument("--no-raw", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.dry:
        print("\n".join(plan()))
        return 0
    if not a.outdir:
        ap.error("OUTDIR required")
    sweep(a.outdir, a.label or a.outdir.name, not a.no_raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
