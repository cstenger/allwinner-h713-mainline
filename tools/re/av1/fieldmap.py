#!/usr/bin/env python3
"""Which decoder-container fields drive which AV1 register fields.

Runs the vendor's per-frame setup, Vp9AsicInitPicture(Vp9DecContainer*,
VIDEOPICTURE*), in the emulator and reads the register image it leaves in the
container (taffel::ctypes::SwRegisters at +0x33550: the 1168-byte MMIO image
minus its two read-only ID words). Every container word the function reads is
then perturbed (all-ones, then 1) and the register fields that change are
reported BY NAME, using swregisters-bits.txt.

Pointers the function dereferences are discovered as in tools/re/vp9: a slot
is a pointer if pointing it at a fresh block makes reads land in that block.

    fieldmap.py [SCENARIO=off=val,...] > out.txt
"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, '..'))
from awemu import Lib
from unicorn import UC_HOOK_MEM_READ

LIB = os.environ.get('AV1_LIB', os.path.join(here, '../../../local/h713-lab/ve-extract/libs/libawav1.so'))
FN = '_Z18Vp9AsicInitPictureP15Vp9DecContainerP12VIDEOPICTURE'
CONT_SZ = 0x40000
REGS_OFF = 0x33550          # ctypes SwRegisters inside the container
REGS_SZ = 0x488
PTR, PTR_BLK, PTR_N = 0x50000000, 0x10000, 160
PIC_SZ = 0x1000

FIELDS = []                  # (name, lo, width) in image bits
for l in open(os.path.join(here, 'swregisters-bits.txt')):
    f = l.split()
    if f[3] != 'NONE':
        FIELDS.append((f[0], int(f[3]), int(f[1])))

SCENARIO = {int(k, 16): int(v, 0) for k, v in
            (kv.split('=') for kv in os.environ.get('SCENARIO', '').split(',') if kv)}


def decode(img):
    """img: the 0x488-byte ctypes copy; it starts at image byte 8."""
    v = int.from_bytes(img, 'little') << 64
    return {n: (v >> lo) & ((1 << w) - 1) for n, lo, w in FIELDS if lo >= 64}


class Run:
    def __init__(self):
        self.L = L = Lib(LIB)
        L.wr(L.data_imports.get('GLOBAL_CDC_LOG_LEVEL', L.alloc(4)), 7)
        self.cont = L.alloc(CONT_SZ)
        self.pic = L.alloc(PIC_SZ)
        L.uc.mem_map(PTR, PTR_BLK * PTR_N)
        self.ptrs, self.reads, self.fnptrs = {}, {}, {}
        self.ident = L.add_stub('ident', lambda lib, r: r[0])
        lo, hi = self.cont, self.cont + CONT_SZ
        def hook(uc, acc, a, sz, v, _):
            if lo <= a < hi or PTR <= a < PTR + PTR_BLK * PTR_N or \
               self.pic <= a < self.pic + PIC_SZ:
                self.reads.setdefault(a, sz)
        for b, e in ((lo, hi), (PTR, PTR + PTR_BLK * PTR_N), (self.pic, self.pic + PIC_SZ)):
            L.uc.hook_add(UC_HOOK_MEM_READ, hook, begin=b, end=e - 1)

    def label(self, a):
        if self.cont <= a < self.cont + CONT_SZ:
            return f'c+{a - self.cont:#x}'
        if self.pic <= a < self.pic + PIC_SZ:
            return f'pic+{a - self.pic:#x}'
        blk, off = divmod(a - PTR, PTR_BLK)
        slot = next(s for s, b in self.ptrs.items() if b == blk)
        return f'*({self.label(slot)})+{off:#x}'

    def run(self, patch=None, extra_ptr=None, extra_fn=None):
        L = self.L
        L.uc.mem_write(self.cont, b'\0' * CONT_SZ)
        L.uc.mem_write(self.pic, b'\0' * PIC_SZ)
        L.uc.mem_write(PTR, b'\0' * PTR_BLK * (len(self.ptrs) + 1))
        ptrs = dict(self.ptrs)
        if extra_ptr is not None:
            ptrs[extra_ptr] = len(self.ptrs)
        for slot, blk in ptrs.items():
            L.wr(slot, PTR + blk * PTR_BLK)
        for slot in list(self.fnptrs) + ([extra_fn] if extra_fn else []):
            L.wr(slot, self.ident)
        for off, val in SCENARIO.items():
            L.wr(self.cont + off, val)
        for a, (val, n) in (patch or {}).items():
            L.wr(a, val, n)
        self.reads.clear()
        err = None
        try:
            L.call(FN, self.cont, self.pic, max_insns=20_000_000)
        except RuntimeError as e:
            err = str(e)
        regs = decode(bytes(L.uc.mem_read(self.cont + REGS_OFF, REGS_SZ)))
        return regs, dict(self.reads), err

    def discover(self, limit=150):
        for _ in range(limit):
            _, reads, err = self.run()
            if not err or 'UNMAPPED' not in err:
                return err
            if 'FETCH_UNMAPPED' in err and 'pc=0x0 ' in err:
                for slot, sz in reversed(list(reads.items())):
                    if sz != 4 or slot in self.ptrs or slot in self.fnptrs:
                        continue
                    if self.run(extra_fn=slot)[2] != err:
                        self.fnptrs[slot] = 1
                        break
                else:
                    return err
                continue
            blk = len(self.ptrs)
            lo, hi = PTR + blk * PTR_BLK, PTR + (blk + 1) * PTR_BLK
            for slot, sz in reversed(list(reads.items())):
                if sz != 4 or slot in self.ptrs or slot in self.fnptrs:
                    continue
                _, r2, _ = self.run(extra_ptr=slot)
                if any(lo <= a < hi for a in r2):
                    self.ptrs[slot] = blk
                    break
            else:
                return err
        return err


def main():
    R = Run()
    err = R.discover()
    base, reads, err = R.run()
    print(f'# pointers: {", ".join(R.label(p) for p in R.ptrs)}')
    print(f'# fn pointers: {", ".join(R.label(p) for p in R.fnptrs)}')
    print(f'# baseline error: {err}')
    print(f'# {len(reads)} input bytes read')
    for n, v in sorted(base.items()):
        if v:
            print(f'base {n} = {v:#x}')
    regs_lo, regs_hi = R.cont + REGS_OFF, R.cont + REGS_OFF + REGS_SZ
    for a in sorted(reads):
        if a in R.ptrs or a in R.fnptrs or regs_lo <= a < regs_hi:
            continue
        n = reads[a]
        eff = []
        for probe in ((1 << 8 * n) - 1, 1):
            regs, _, e2 = R.run({a: (probe, n)})
            d = [f'{k}={regs[k]:#x}' for k in regs if regs[k] != base.get(k)]
            if e2 and not err:
                d.append('ERROR')
            eff.append(d)
        if eff[0] or eff[1]:
            print(f'{R.label(a)}/{n}: ff-> {" ".join(eff[0])} | 1-> {" ".join(eff[1])}')


if __name__ == '__main__':
    main()
