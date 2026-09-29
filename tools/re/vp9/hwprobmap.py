#!/usr/bin/env python3
"""Map the vendor's software probability context (ctx+0x3cb8, 0xc57 bytes) to
the hardware buffer that Vp9GetEntrypointOffset builds (0x88000 bytes, handed to
the VE via register 0x64). Two tagged passes (index low byte, index high byte+1)
identify the source of every output byte; bytes identical across passes are
constants. Single tile (log2 cols/rows = 0)."""
import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from awemu import Lib
LIB = os.environ.get('VP9_LIB', os.path.join(os.path.dirname(__file__), '../../../local/h713-lab/ve-extract/libs/libawvp9HwAL.so'))
P0, PN = 0x3cb8, 0xc57

def run(tag):
    L = Lib(LIB); L.wr(L.data_imports['GLOBAL_CDC_LOG_LEVEL'], 7)
    ctx = L.alloc(0x10000); hw = L.alloc(0x88000); ops = L.alloc(0x100)
    def cp(lib, r): lib.uc.mem_write(r[0], bytes(lib.uc.mem_read(r[1], r[2]))); return 0
    stub_cp = L.add_stub('copy', cp); nop = L.add_stub('nop', lambda lib, r: 0)
    for i in range(0, 0x100, 4): L.wr(ops + i, nop)
    L.wr(ops + 0x3c, stub_cp)
    L.wr(ctx + 8, ops); L.wr(ctx + 0x89c, hw)
    if int(os.environ.get('KEY', '0')): L.wr(ctx + 0x188, 1)
    L.uc.mem_write(ctx + P0, bytes(tag(i) for i in range(PN)))
    L.call('Vp9GetEntrypointOffset', ctx, max_insns=50_000_000)
    return bytes(L.uc.mem_read(hw, 0x88000)), [c for c in L.calls if c[0] != 'nop']

KEY = int(os.environ.get("KEY", "0"))
a, ca = run(lambda i: i & 0xff)
b, cb = run(lambda i: (i >> 8) + 1)
c, _ = run(lambda i: (i * 7 + 3) & 0xff)
print('copy calls:', [(n, hex(r[2])) for n, r in ca])
m = {}
const = 0
for o in range(len(a)):
    if a[o] == c[o] and b[o] == a[o]:
        if a[o]: const += 1
        continue
    src = a[o] | ((b[o] - 1) << 8)
    ok = src < PN and ((src * 7 + 3) & 0xff) == c[o]
    m[o] = src if ok else None
bad = [o for o, s in m.items() if s is None]
print(f'hw bytes from probs: {len(m) - len(bad)}, unexplained: {len(bad)}, nonzero constants: {const}')
runs = []
for o in sorted(k for k in m if m[k] is not None):
    s = m[o]
    if runs and runs[-1][0] + runs[-1][2] == o and runs[-1][1] + runs[-1][2] == s: runs[-1][2] += 1
    else: runs.append([o, s, 1])
with open(os.path.join(os.path.dirname(__file__), 'hwprob-runs%s.txt' % ('-key' if int(os.environ.get('KEY','0')) else '')), 'w') as f:
    for o, s, n in runs: f.write(f'hw+{o:#07x} <- sw+{s:#05x} ({n})\n')
print(len(runs), 'runs; first/last:', runs[:3], runs[-3:])
used = set(m.values()); print('sw bytes never used:', len(set(range(PN)) - used))
extent = max(m) if m else 0; print('hw extent', hex(min(m)), hex(extent))
