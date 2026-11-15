#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check the comm-trace table after 0006 against the pre-0006 table.

- No cave word (expected == 0, not j/jal) names k0/k1, mirroring the guard in
  h713_mips_apply_comm_trace().
- Relocation counts stay 61 `lui t8,0xae34` bases and 80 `sw ...,<=0x7c(t8)`.
- Every changed word differs from the old one only by k0->t8 / k1->t9 in the
  rs/rt fields; addresses, expected words and everything else are identical.

usage: test-comm-trace-no-kregs.py OLD/h713_mips.c NEW/h713_mips.c
"""
import re, sys

TABLE = 'h713_mips_comm_trace_patches[] = {'


def table(path):
    s = open(path).read()
    a = s.index(TABLE); b = s.index('\n};', a)
    return [tuple(int(v, 16) for v in t) for t in
            re.findall(r'\{\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+),\s*(0x[0-9a-f]+)\s*\}', s[a:b])]


def kreg(w):
    op = w >> 26
    if op in (2, 3):
        return False
    return (((w >> 21) & 0x1e) == 0x1a or ((w >> 16) & 0x1e) == 0x1a or
            (op == 0 and ((w >> 11) & 0x1e) == 0x1a))


def main():
    old, new = table(sys.argv[1]), table(sys.argv[2])
    assert len(old) == len(new) == 446, (len(old), len(new))
    changed = 0
    for (oa, oe, ow), (na, ne, nw) in zip(old, new):
        assert (oa, oe) == (na, ne), hex(oa)
        if ne == 0:
            assert not kreg(nw), 'k-reg left in cave %#x: %08x' % (na, nw)
        if ow != nw:
            changed += 1
            mp = {26: 24, 27: 25}
            rs, rt = (ow >> 21) & 31, (ow >> 16) & 31
            want = (ow & ~((31 << 21) | (31 << 16))) | (mp.get(rs, rs) << 21) | (mp.get(rt, rt) << 16)
            assert oe == 0 and nw == want, '%#x: %08x -> %08x' % (na, ow, nw)
    bases = sum(1 for a, e, w in new if w >> 26 == 0x0f and (w >> 16) & 31 == 24 and w & 0xffff == 0xae34)
    stores = sum(1 for a, e, w in new if w >> 26 == 0x2b and (w >> 21) & 31 == 24 and w & 0xffff <= 0x7c)
    assert (bases, stores) == (61, 80), (bases, stores)
    old_k = sum(1 for a, e, w in old if e == 0 and kreg(w))
    assert old_k == 155 and changed == 155, (old_k, changed)
    print('PASS 155 cave words k0/k1 -> t8/t9 only, no k-regs left, relocation 61/80 unchanged')


if __name__ == '__main__':
    main()
