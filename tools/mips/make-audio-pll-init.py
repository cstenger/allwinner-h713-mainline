#!/usr/bin/env python3
"""Prepare a cold-only stock PLL init-on-zero experiment with metadata retry.

Functional bench experiment; host artifacts only. Stock SetAPLL selects its
existing full init, including stock PLL register programming, when the
control word is zero as well as negative. Every nonzero branch is unchanged.
The zero-word motivation was later weakened by scalar-byte read evidence;
this is historical experiment code, not a validated production fix.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'retry', Path(__file__).with_name('make-audio-pll-retry.py'))
retry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry)
monitor = retry.monitor
original_records = retry.records


def records():
    old = original_records()
    words = [w for _, _, w in old[:26]]
    # Restore sp in each jump's delay slot, freeing two records. The skip
    # restore block moves from word 21 to word 20; update its four branches.
    for i in (5, 7, 9, 14):
        words[i] -= 1
    words = words[:16] + [words[i] for i in (16, 17, 19, 18, 21, 22, 24, 23)] + [0]
    result = [(monitor.CAVE-0x40000000+i*4, 0, w)
              for i, w in enumerate(words)]
    result += old[26:28]
    # Original bltz s0 -> Init; blez additionally initializes a zero word.
    # Preserve its delay slot, stock arguments, calculation and return paths.
    result += [(0x4b13c628, 0x06000017, 0x1a000017)]
    result += [(monitor.CAVE-0x40000000+(25+i)*4, 0, 0x3c18ae34)
               for i in range(7)]
    result += [(monitor.CAVE-0x40000000+(32+i)*4, 0, 0xaf00006c)
               for i in range(7)]
    return result


monitor.monitor_records = records
if __name__ == '__main__':
    monitor.main()
