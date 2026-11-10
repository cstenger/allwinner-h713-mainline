#!/usr/bin/env python3
"""Read the NRWinNode::WriteReg mask trace (RUNS ON THE BOARD, read-only).

Pairs with tools/mips/make-nr-writereg-trace.py and U-Boot patch
patches/u-boot/0002-h713-trace-nrwinnode-writereg-masks.patch.  Verifies that
the hook and the cave are installed in the MIPS image and that the trace page
guards are intact before interpreting anything.  Only DRAM is read: the MIPS
image at 0x4b100000 and the trace page at 0x4d980000.

    python3 read-nr-writereg-trace.py          # JSON summary
"""
import json
import mmap
import os
import sys

TRACE = 0x4D980000
MAGIC, CANARY = 0x434F4D4D, 0x43414E31
CHECKS = [(0x4B1A48D0, 0x0AC40310), (0x4B1A48D4, 0x00000000),   # hook
          (0x4B100C40, 0x3C18AD98), (0x4B100CC0, 0x0AC69236)]   # cave start/end


def main():
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)

    def word(pa):
        base = pa & ~0xFFF
        m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
        v = memoryview(m).cast("I")
        try:
            return v[(pa - base) // 4]
        finally:
            v.release()
            m.close()

    bad = [f"{a:#x}={word(a):#010x} want {w:#010x}" for a, w in CHECKS if word(a) != w]
    if bad:
        print("NR_WRITEREG_TRACE_ABSENT: " + "; ".join(bad), file=sys.stderr)
        return 1
    if word(TRACE + 4) != MAGIC or word(TRACE + 0x80) != CANARY or word(TRACE + 0xFFC) != CANARY:
        print("NR_WRITEREG_TRACE_ABSENT: trace page guard", file=sys.stderr)
        return 1
    t = lambda o: word(TRACE + o)
    index = t(0x118)
    ring = []
    for k in range(min(index, 16)):
        slot = (index - min(index, 16) + k) % 16
        ring.append({"mask": f"{t(0x120 + 8 * slot):#010x}", "mode": t(0x124 + 8 * slot)})
    print(json.dumps({
        "calls": t(0x100), "last_mask": f"{t(0x104):#010x}", "or_mask": f"{t(0x108):#010x}",
        "calls_with_0x800": t(0x10C), "last_mask_mode1": f"{t(0x110):#010x}",
        "calls_mode1": t(0x114), "ring_oldest_first": ring,
        "frame_programmer_last": {"stage": f"{t(0x40):#06x}", "mask": f"{t(0x44):#010x}",
                                  "mode": t(0x48), "ctrl": f"{t(0x4c):#010x}"},
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
