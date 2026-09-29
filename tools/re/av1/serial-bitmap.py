#!/usr/bin/env python3
"""Bit position of every member of a vendor HLS register struct in its
serialised byte array, by emulating T::ToByteArray with one member set to
all-ones at a time. Generalises bitmap.py (SwRegisters) to any T.

    serial-bitmap.py FIELDS.txt MANGLED_TOBYTEARRAY NBYTES OUT.txt
"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, '..'))
from awemu import Lib
LIB = os.environ.get('AV1_LIB', os.path.join(here, '../../../local/h713-lab/ve-extract/libs/libawav1.so'))
fields_path, fn, nbytes, out_path = sys.argv[1], sys.argv[2], int(sys.argv[3], 0), sys.argv[4]
L = Lib(LIB)
fields = [l.split() for l in open(fields_path)]
SZ = 8192
obj = L.alloc(SZ); out = L.alloc(nbytes)
def run():
    L.uc.mem_write(out, b'\0' * nbytes)
    L.call(fn, obj, out)
    return int.from_bytes(bytes(L.uc.mem_read(out, nbytes)), 'little')
L.uc.mem_write(obj, b'\0' * SZ)
base = run()
res, bad = [], []
for f in fields:
    name, w = f[0], int(f[1])
    if f[2] != 'member':
        res.append(f'{name} {w} {f[2]} NONE'); continue
    off = int(f[3]); n = 4 * max(1, (w + 31) // 32)
    L.uc.mem_write(obj, b'\0' * SZ); L.uc.mem_write(obj + off, b'\xff' * n)
    d = run() ^ base
    if not d:
        res.append(f'{name} {w} {off} NONE'); bad.append(name); continue
    lo = (d & -d).bit_length() - 1; hi = d.bit_length() - 1
    if hi - lo + 1 != w: bad.append(name)
    res.append(f'{name} {w} {off} {lo} {hi}')
open(out_path, 'w').write('\n'.join(res) + '\n')
print(len(res), 'fields; baseline bits', bin(base).count('1'), '; mismatched/unmapped:', bad[:12])
