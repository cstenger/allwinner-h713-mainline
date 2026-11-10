#!/usr/bin/env python3
"""Prepare a cold-start metadata retry using the stock SetAPLL path.

Functional bench experiment; host artifacts only. Same-size, identity-guarded
U-Boot table replacement.
Preserves every original status-change dispatch. For unchanged nonzero status,
dispatch only with nonzero N/Fs differing from the stock PLL history. Never
write receiver registers here or patch running MIPS. Stock SetAPLL still
programs the PLL and retains its original hardware waits. Failed history
updates can cause repeated attempts; this adds no retry limit.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'monitor', Path(__file__).with_name('make-audio-monitor-trace.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def records():
    c = monitor.CAVE
    def beq(i, target, rs, rt):
        return monitor.branch(c + 4*i, c + 4*target, rs, rt)
    def bne(i, target, rs, rt):
        return beq(i, target, rs, rt) | 0x04000000
    words = [
        0x27bdfff8, 0xafb80000, 0xafb90004,
        bne(3, 16, 3, 2), 0x8e380004,
        beq(5, 21, 2, 0), 0x8e390008,
        beq(7, 21, 24, 0), 0,
        beq(9, 21, 25, 0), 0x8e390030,
        bne(11, 16, 24, 25), 0x8e380008,
        0x8e390034, beq(14, 21, 24, 25), 0,
        0x8fb80000, 0x8fb90004, 0x27bd0008,
        monitor.jump(0x8b13a2fc), 0,
        0x8fb80000, 0x8fb90004, 0x27bd0008,
        monitor.jump(0x8b13a31c), 0,
    ]
    result = [(c - 0x40000000 + i*4, 0, w)
              for i, w in enumerate(words)]
    result += [(0x4b13a2f4, 0x10620009, monitor.jump(c)),
               (0x4b180128, monitor.jump(0x8b15b304),
                monitor.jump(0x8b15b348))]
    result += [(c - 0x40000000 + (26+i)*4, 0, 0x3c18ae34)
               for i in range(7)]
    result += [(c - 0x40000000 + (33+i)*4, 0, 0xaf00006c)
               for i in range(7)]
    return result


monitor.monitor_records = records
monitor.FIELDS = {}  # This functional experiment does not publish monitor fields.

if __name__ == '__main__':
    monitor.main()
