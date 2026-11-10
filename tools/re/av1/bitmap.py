#!/usr/bin/env python3
"""Bit position of every SwRegisters member in the 1168-byte register image,
by emulating SwRegisters::ToByteArray with one member set to all-ones."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from awemu import Lib
LIB = os.environ.get('AV1_LIB', os.path.join(os.path.dirname(__file__), '../../../local/h713-lab/ve-extract/libs/libawav1.so'))
L = Lib(LIB)
fields = [l.split() for l in open(os.path.join(os.path.dirname(__file__), 'swregisters-fields.txt'))]
SZ = 4096
obj = L.alloc(SZ); out = L.alloc(1168)
fn = '_ZNK11SwRegisters11ToByteArrayERA1168_c'
def run():
    L.uc.mem_write(out, b'\0' * 1168)
    L.call(fn, obj, out)
    return int.from_bytes(bytes(L.uc.mem_read(out, 1168)), 'little')
L.uc.mem_write(obj, b'\0' * SZ)
base = run()
print('baseline nonzero bits:', bin(base).count('1'), 'fn', fn)
res = []
for f in fields:
    name, w = f[0], int(f[1])
    if f[2] != 'member':
        continue
    off = int(f[3]); nbytes = 4 * max(1, (w + 31) // 32)
    L.uc.mem_write(obj, b'\0' * SZ)
    L.uc.mem_write(obj + off, b'\xff' * nbytes)
    d = run() ^ base
    if not d:
        res.append((name, w, off, None, None)); continue
    lo = (d & -d).bit_length() - 1; hi = d.bit_length() - 1
    res.append((name, w, off, lo, hi))
with open(os.path.join(os.path.dirname(__file__), 'swregisters-bits.txt'), 'w') as fo:
    for name, w, off, lo, hi in res:
        fo.write(f'{name} {w} {off} ' + (f'{lo} {hi} reg={lo//32:#05x}[{hi%32 if hi//32==lo//32 else "x"}:{lo%32}] regoff={4*(lo//32):#05x}' if lo is not None else 'NONE') + '\n')
bad = [r for r in res if r[3] is None or r[4] - r[3] + 1 != r[1]]
print(len(res), 'members;', len(bad), 'with width mismatch or no bits:', [(b[0], b[1], b[3], b[4]) for b in bad[:10]])
