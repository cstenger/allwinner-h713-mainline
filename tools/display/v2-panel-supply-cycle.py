#!/usr/bin/env python3
"""Ordered V2 panel supply cycle from Linux: clears the lit-but-black latch.

Runs ON THE BOARD as root (pipe it over ssh: `ssh root@board python3 - BOOT_ID
< v2-panel-supply-cycle.py`). It refuses unless BOOT_ID is the running boot
and PH16/PH19 are outputs (U-Boot leaves both high: reset released, supply
on). Sequence, as U-Boot's h713_disp_panel_initial_off() and the A1 history:

  save and quiet the LVDS/route words (0x051c00d4/d8/dc/e0 = 0,
  0x051c0014 = 0x18000000, 0x051c0028 = 0x30, 0x05140054 = 0x40000000),
  20 ms, PH16 low (reset), 75 ms, PH19 low (supply off), OFF_S (default 5 s),
  PH19 high, 2 ms, PH16 high, 25 ms, then restore the saved words.

It writes /dev/mem directly behind the kernel's vcc-panel regulator (0221),
leaving both lines as found. It cleared the latch 4 of 4 times on
2026-11-22 with 5 s off. PIO base 0x02000000, bank stride 0x30 (PH = bank 7).
"""
import mmap
import os
import struct
import sys
import time

PIO, LVDS, ROUTE = 0x02000000, 0x051C0000, 0x05140000
PH_CFG, PH_DATA = 7 * 0x30, 7 * 0x30 + 0x10


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: v2-panel-supply-cycle.py BOOT_ID [OFF_S]')
    boot, off_s = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    if open('/proc/sys/kernel/random/boot_id').read().strip() != boot:
        sys.exit('refused: not the expected boot')
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    win = lambda base: mmap.mmap(fd, 0x1000, mmap.MAP_SHARED,
                                 mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
    pio, lvds, route = win(PIO), win(LVDS), win(ROUTE)
    rd = lambda m, o: struct.unpack('<I', m[o:o + 4])[0]

    def wr(m, o, v):
        m[o:o + 4] = struct.pack('<I', v)

    def ph(n, level):
        v = rd(pio, PH_DATA)
        wr(pio, PH_DATA, (v | (1 << n)) if level else (v & ~(1 << n)))

    cfg = lambda n: (rd(pio, PH_CFG + (n // 8) * 4) >> ((n % 8) * 4)) & 0xF
    if cfg(16) != 1 or cfg(19) != 1 or (rd(pio, PH_DATA) >> 16) & 9 != 9:
        sys.exit('refused: PH16/PH19 are not outputs driven high')
    t0 = time.monotonic()
    log = lambda s: print('%6.3f %s' % (time.monotonic() - t0, s), flush=True)
    quiet = [(lvds, 0x0D4, 0), (lvds, 0x0D8, 0), (lvds, 0x0DC, 0), (lvds, 0x0E0, 0),
             (lvds, 0x014, 0x18000000), (lvds, 0x028, 0x30), (route, 0x054, 0x40000000)]
    name = lambda m: 'lvds' if m is lvds else 'route'
    saved = [(m, o, rd(m, o)) for m, o, _ in quiet]
    log('saved ' + ' '.join('%s+%03x=%08x' % (name(m), o, v) for m, o, v in saved))
    for m, o, v in quiet:
        wr(m, o, v)
    time.sleep(0.02)
    ph(16, 0)
    time.sleep(0.075)
    ph(19, 0)
    log('supply off for %.1f s' % off_s)
    time.sleep(off_s)
    ph(19, 1)
    time.sleep(0.002)
    ph(16, 1)
    time.sleep(0.025)
    for m, o, v in saved:
        wr(m, o, v)
    bad = [(o, v) for m, o, v in saved if rd(m, o) != v]
    log('restored%s, PH data %08x' % (' MISMATCH %r' % bad if bad else '', rd(pio, PH_DATA)))


if __name__ == '__main__':
    main()
