#!/usr/bin/env python3
"""Decode an AV1-block register dump ("aaaaaaaa 0xVVVVVVVV" per line, from
tools/stock/stock-capture.sh) into named fields using swregisters-bits.txt.
Prints non-zero fields only (or all with --all)."""
import os, sys
here = os.path.dirname(__file__)
words = {}
for l in open(sys.argv[1]):
    p = l.split()
    if len(p) >= 2 and p[1].startswith('0x'):
        words[int(p[0], 16) & 0xfff] = int(p[1], 16)
img = 0
for off, v in words.items():
    img |= v << (8 * off)
for l in open(os.path.join(here, 'swregisters-bits.txt')):
    f = l.split()
    if f[3] == 'NONE':
        continue
    lo, hi = int(f[3]), int(f[4])
    if lo // 32 * 4 not in words:
        continue
    v = (img >> lo) & ((1 << (hi - lo + 1)) - 1)
    if v or '--all' in sys.argv:
        print(f'{f[-1][7:]} {f[0]:40s} = {v:#x}')
