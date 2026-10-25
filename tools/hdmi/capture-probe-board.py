#!/usr/bin/env python3
"""Board side of characterise-capture.py: read-only probes of the HDMI capture front end.

docs/hdmi-panel-source-design-2026-10-23.md section 10.23.1.  Runs on our
Linux as root, fed over ssh stdin; /dev/mem opened O_RDONLY.  Reads only:
  - the MemoryAgent lock flag (global 0x8b499b14 -> object +0xb5)
  - the NR node (found by vptr 0x8b207a50) and its input frame buffer
    (NR +0x54 -> TVsFrameBuffer: w +0x50, h +0x58, compress +0x5c, colour +0x68)
  - the CapWinNode (vptr 0x8b207124), 0x50 words, raw
  - AFBD's capture pair 0x05600320/0x05600324 (hardware-updated; source 0 off)
  - one completed ring slot, Y and C, copied twice
Never 0x069xxxxx (capture DMA), 0x0709xxxx, or anything written.

    capture-probe-board.py state                # JSON: lock, geometry, pair, nodes
    capture-probe-board.py frame W H SPAN       # JSON line, then Y+C bytes (SPAN bytes per line read)
    capture-probe-board.py cadence SECONDS      # JSON: pair change times
"""
import json
import mmap
import os
import struct
import sys
import time

PHYS, KSEG0, IMG_END = 0x4B100000, 0x8B100000, 0x4BF41000
MEMAGENT_PTR = 0x8B499B14
VPTR_NR, VPTR_CAP = 0x8B207A50, 0x8B207124
PAIR = (0x05600320, 0x05600324)
POOL = (0x4BF41000, 0x4D941000)
SLOT_MAX = 0x1FF000


def phys(va):
    return va - KSEG0 + PHYS


class Probe:
    def __init__(self, word, raw):
        """word(pa) -> u32; raw(pa, n) -> bytes.  Both read-only."""
        self.word, self.raw = word, raw
        self.nr = None

    def find_nr(self):
        if self.nr is None:
            pat = struct.pack("<I", VPTR_NR)
            for base in range(0x4B800000, IMG_END, 0x100000):
                buf = self.raw(base, min(0x100000, IMG_END - base))
                i = buf.find(pat)
                while i >= 0 and i % 4:
                    i = buf.find(pat, i + 1)
                if i >= 0:
                    self.nr = KSEG0 + (base - PHYS) + i
                    break
        return self.nr

    def find_cap(self):
        pat = struct.pack("<I", VPTR_CAP)
        for base in range(0x4B800000, IMG_END, 0x100000):
            buf = self.raw(base, min(0x100000, IMG_END - base))
            i = buf.find(pat)
            while i >= 0 and i % 4:
                i = buf.find(pat, i + 1)
            if i >= 0:
                return KSEG0 + (base - PHYS) + i
        return None

    def state(self):
        obj = self.word(phys(MEMAGENT_PTR))
        locked = (self.word(phys(obj) + 0xB4) >> 8) & 0xFF
        nr = self.find_nr()
        out = {"locked": locked, "memagent": f"{obj:08x}",
               "pair": [f"{self.word(a):08x}" for a in PAIR]}
        if nr:
            w = lambda off: self.word(phys(nr) + off)
            fb = w(0x54)
            out.update(nr=f"{nr:08x}", afbd_source_mode=w(0x60), nr_colour_format=w(0x5C))
            if KSEG0 <= fb < KSEG0 + (IMG_END - PHYS):
                f = lambda off: self.word(phys(fb) + off)
                out["fb_in"] = {"addr": f"{fb:08x}", "w": f(0x50), "h": f(0x58),
                                "compress": f(0x5C), "colour_format": f(0x68)}
        cap = self.find_cap()
        if cap:
            out["cap"] = {"addr": f"{cap:08x}",
                          "words": [f"{self.word(phys(cap) + 4 * i):08x}" for i in range(0x50)]}
        return out

    def pairs(self, seconds, step=0.002):
        seen, t0, last = [], time.monotonic(), None
        while time.monotonic() - t0 < seconds:
            p = (self.word(PAIR[0]), self.word(PAIR[1]))
            if p != last:
                seen.append((round(time.monotonic() - t0, 4), p))
                last = p
            time.sleep(step)
        return seen

    def frame(self, h, span):
        """Copy a slot the writer is not on, twice; return (meta, y+c bytes) or raise."""
        size = h * span
        if size > SLOT_MAX:
            raise ValueError(f"{h}x{span} exceeds the ring slot ({SLOT_MAX:#x})")
        for attempt in range(8):
            hist = self.pairs(0.12)
            slots = list(dict.fromkeys(p for _, p in hist))
            if len(slots) < 2:
                raise RuntimeError("capture pair is not cycling (no signal?)")
            cur = slots[-1]
            y, c = slots[-2]  # the slot finished just before the current one
            for a in (y, c):
                if not (POOL[0] <= a and a + size <= POOL[1]):
                    raise ValueError(f"slot {a:#x} outside the frame-buffer pool")
            one = self.raw(y, size) + self.raw(c, size)
            if (self.word(PAIR[0]), self.word(PAIR[1])) == (y, c):
                continue  # writer came round to this slot while we read
            two = self.raw(y, size) + self.raw(c, size)
            diff = max((abs(a - b) for a, b in zip(one, two)), default=0) if one != two else 0
            if diff <= 1:
                return {"y": f"{y:08x}", "c": f"{c:08x}", "current": [f"{v:08x}" for v in cur],
                        "attempt": attempt, "copy_max_diff": diff, "bytes": len(one)}, one
        raise RuntimeError("no stable slot in 8 attempts")


def devmem_probe():
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)

    def raw(pa, n):
        if 0x06900000 <= pa < 0x06A00000 or 0x07090000 <= pa < 0x070A0000:
            raise ValueError(f"forbidden {pa:#x}")
        base = pa & ~0xFFF
        m = mmap.mmap(fd, (pa - base + n + 0xFFF) & ~0xFFF, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
        b = m[pa - base:pa - base + n]
        m.close()
        return b

    return Probe(lambda pa: struct.unpack("<I", raw(pa, 4))[0], raw)


def main():
    p = devmem_probe()
    cmd = sys.argv[1]
    if cmd == "state":
        print(json.dumps(p.state()))
    elif cmd == "frame":
        h, span = int(sys.argv[3]), int(sys.argv[4])
        meta, data = p.frame(h, span)
        sys.stdout.write(json.dumps(meta) + "\n")
        sys.stdout.flush()
        sys.stdout.buffer.write(data)
    elif cmd == "cadence":
        hist = p.pairs(float(sys.argv[2]))
        print(json.dumps({"changes": [[t, f"{y:08x}", f"{c:08x}"] for t, (y, c) in hist]}))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
