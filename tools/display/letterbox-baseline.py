#!/usr/bin/env python3
"""Read-only dump of every display register the letterbox recipe touches.
RUNS ON THE TARGET, as root.

    letterbox-baseline.py > native.txt

WHAT IS READ, AND WHY ONLY THIS. Two sources, nothing else:

  * the ranges tools/display/blockdump.py has already mmapped on this board
    without incident (afbd, comp 0x000-0x2ff, route 0x000-0x5ff, proc, lvds
    0x000-0x0ff), and the vblender words U-Boot's md has read;
  * beyond those, only registers the MIPS display firmware itself loads or
    stores (tools/mips/block-map.py over display.bin, plus the two
    PanelWinNode::WriteReg reaches through `ori 0xfe00` that the linear scanner
    cannot see). A register the firmware programs is in a powered block;
  * for the WP5 mirror, a few readback words the stock capture
    (local/h713-lab/stock-capture-20261001, display.txt) read on this SoC
    with the same blocks powered and video on: proc instances 2-3's line
    window and the panel's mirror status. The firmware writes only proc
    instance 0, yet all four instances moved under stock's H mirror.

Never 0x07091000 (a read wedges the SoC) or 0x06940000 (unpowered capture
domain). Nothing here writes.

Each word is read with one aligned 32-bit load (memoryview cast to "I"), not
struct.unpack_from, which may copy byte by byte.
"""
import mmap
import os
import sys

PAGE = 4096

# name, base, contiguous span already proven safe, extra single registers
BLOCKS = [
    ("afbd", 0x05600000, 0x400, []),
    ("comp", 0x05000000, 0x300, [
        0x318, 0x434, 0x438, 0x440, 0x444, 0x44c, 0x468, 0x490,
        0x534, 0x538, 0x544, 0x550, 0x568, 0x590, 0x628, 0x71c,
        0x738, 0x73c, 0x7d0, 0x7d4,
        # NRWinNode::WriteReg's fetch window -- never dumped before
        0x804, 0x808, 0x80c, 0x82c, 0x840, 0x844, 0x854, 0x858,
        0x85c, 0x860,
    ]),
    ("route", 0x05140000, 0x600, [
        0xd40, 0xd44, 0xd4c, 0xd50, 0xd54, 0xe00,
    ]),
    ("proc", 0x05180000, 0x200, [
        # WP5: instances 2-3's +050, read by the stock capture
        0x250, 0x350,
    ]),
    ("lvds", 0x051c0000, 0x100, [
        0x120, 0x124, 0x128, 0x12c, 0x130, 0x134, 0x138, 0x170,
        0x1bc, 0x200, 0x204, 0x21c, 0x220, 0x228, 0x238, 0x23c,
        0x240, 0x244, 0x248, 0x250, 0x254, 0x258, 0x25c, 0x260,
        0x264, 0x270, 0x27c, 0x320, 0x324, 0x328, 0x32c, 0x330,
        0x334, 0x338, 0x364, 0x370, 0x374,
        # PanelWinNode::WriteReg crtc window, reached via `ori 0xfe00`
        0xfe00, 0xfe04,
        # WP5: H-mirror status (0 -> 1 with 0x0a0[0] in the stock capture)
        0x164,
    ]),
    ("vblend", 0x05200000, 0x80, []),
    # DETNWinNode::WriteReg (0x8b1a1a64) writes window geometry here in the
    # same transaction as NR/proc/panel. Read during the HDMI work too.
    ("detn", 0x050c0000, 0, [
        0x000, 0x00c, 0x040, 0x044, 0x048, 0x04c, 0x054, 0x068,
        0x06c, 0x070, 0x074, 0x244, 0x2e8, 0x2ec, 0x2f0, 0x2f4,
        0x314, 0x318, 0x31c, 0x420, 0x474, 0x478, 0x4a0, 0x4a4,
        0x4f4, 0x4f8, 0x520, 0x524, 0x574, 0x578, 0x5f4, 0x5f8,
        0x674, 0x678, 0x6a0, 0x6a4, 0x6f4, 0x6f8, 0x734, 0x738,
        0x7b4, 0x7b8, 0x83c, 0xc30, 0xc38, 0xc68, 0xc70, 0xc80,
        0xc84, 0xc88, 0xc8c,
    ]),
]


def read_block(fd, base, offsets):
    top = max(offsets) + 4
    span = (top + PAGE - 1) // PAGE * PAGE
    m = mmap.mmap(fd, span, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
    try:
        words = memoryview(m).cast("I")
        try:
            return {off: words[off // 4] for off in offsets}
        finally:
            words.release()
    finally:
        m.close()


def main():
    fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
    try:
        for name, base, span, extra in BLOCKS:
            assert base % PAGE == 0, f"{name}: base {base:#x} not page aligned"
            offsets = sorted(set(range(0, span, 4)) | set(extra))
            for off, val in read_block(fd, base, offsets).items():
                print(f"{name}+{off:03x} {base + off:#010x} {val:08X}")
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
