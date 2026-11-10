#!/usr/bin/env python3
"""Differential field map for the libawvp9HwAL.so register setters.

For each setter: run it on a zeroed decoder context, recording every context
read. Then, per field read, rerun with that field set to all-ones and to 1, and
report which bits of which register moved. Output: register offset, bit range,
context offset and width -- the setter's packing, without reading its code.

Fields read through a pointer held in the context are reported too, as
"ptr@<ctx offset>+<offset>", by pointing each pointer field at its own zeroed
block before the run.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from awemu import Lib
from unicorn import UC_HOOK_MEM_READ

LIBPATH = os.environ.get('VP9_LIB', os.path.join(os.path.dirname(__file__), '../../../local/h713-lab/ve-extract/libs/libawvp9HwAL.so'))
CTX_SZ = 0x10000
REGNAME = {}
for l in open(os.path.join(os.path.dirname(__file__), 'regmap-named.txt')):
    g, o, n = l.split(); REGNAME.setdefault((g, int(o, 16)), n)

# SCENARIO="0x270=1,0x188=1": context fields held at these values in every run
SCENARIO = {int(k, 16): int(v, 0) for k, v in (kv.split('=') for kv in os.environ.get('SCENARIO', '').split(',') if kv)}
FORCEPTR = [int(x, 16) for x in os.environ.get('FORCEPTR', '').split(',') if x]
SETTERS = sys.argv[1:] or ['VP9SetBasicReg', 'Vp9SetTopSecReg', 'VP9SetSecReg', 'Vp9AsicSetTileInfo',
                           'Vp9ConfigOutputRegister', 'VP9RefFrameConfig', 'VP9Set10BitReg',
                           'VP9SetSramReg', 'Vp9ConfigBitStreamRegister', 'VP9SetTopReg',
                           'Vp9AsicSetSegmentation']


PTR = 0x50000000        # pointer blocks: one 64 KiB block per discovered pointer
PTR_BLK = 0x10000
PTR_N = 128


class Run:
    """A context plus the pointers discovered in it. A 'slot' is an absolute
    address in the context or in a pointer block; labels read like C:
    ctx+0x12c, or *(ctx+0xc)+0x8 for a field reached through a pointer."""

    def __init__(self):
        self.L = L = Lib(LIBPATH)
        L.wr(L.data_imports['GLOBAL_CDC_LOG_LEVEL'], 7)   # silence the library's logging
        L.add_mmio('vp9', 0x100, 'uVp9RegisterBaseAddr')
        L.add_mmio('top', 0x100, 'uVp9TopBaseAddr')
        self.ctx = L.alloc(CTX_SZ)
        L.uc.mem_map(PTR, PTR_BLK * PTR_N)
        self.ptrs = {}      # slot address -> block index
        self.fnptrs = {}    # slot address -> stub address (identity: returns r0)
        self.ident = L.add_stub('ident', lambda lib, r: r[0])
        self.reads = {}
        c = self.ctx
        def hook(uc, acc, a, sz, v, _):
            if c <= a < c + CTX_SZ or PTR <= a < PTR + PTR_BLK * PTR_N:
                self.reads.setdefault(a, sz)
        L.uc.hook_add(UC_HOOK_MEM_READ, hook, begin=c, end=c + CTX_SZ - 1)
        L.uc.hook_add(UC_HOOK_MEM_READ, hook, begin=PTR, end=PTR + PTR_BLK * PTR_N - 1)

    def label(self, a):
        if self.ctx <= a < self.ctx + CTX_SZ:
            return f'ctx+{a - self.ctx:#x}'
        blk, off = divmod(a - PTR, PTR_BLK)
        slot = next(s for s, b in self.ptrs.items() if b == blk)
        return f'*({self.label(slot)})+{off:#x}'

    def run(self, fn, patch=None, extra_ptr=None, extra_fn=None, write_hw=True):
        L, c = self.L, self.ctx
        L.uc.mem_write(c, b'\0' * CTX_SZ)
        L.uc.mem_write(PTR, b'\0' * PTR_BLK * (len(self.ptrs) + 1))
        ptrs = dict(self.ptrs)
        if extra_ptr is not None: ptrs[extra_ptr] = len(self.ptrs)
        for slot, blk in ptrs.items(): L.wr(slot, PTR + blk * PTR_BLK)
        for slot in self.fnptrs: L.wr(slot, self.ident)
        if extra_fn is not None: L.wr(extra_fn, self.ident)
        if write_hw: L.wr(c + 0x71, 1, 1)
        for off, val in SCENARIO.items(): L.wr(c + off, val)
        for a, (val, n) in (patch or {}).items(): L.wr(a, val, n)
        for (g, o), name in REGNAME.items():
            if name in L.exports: L.wr(L.sym(name), 0)
        L.trace.clear(); self.reads.clear()
        err = None
        try: L.call(fn, c)
        except RuntimeError as e: err = str(e)
        regs = {}
        for k, g, o, v in L.trace:
            if k == 'W': regs[(g, o)] = v
        return regs, dict(self.reads), err

    def discover(self, fn, limit=40):
        """Grow the pointer set until fn runs clean (or stops improving)."""
        self.ptrs = {self.ctx + o: i for i, o in enumerate(FORCEPTR)}; self.fnptrs = {}
        for _ in range(limit):
            _, reads, err = self.run(fn)
            if not err or 'UNMAPPED' not in err: return err
            if 'FETCH_UNMAPPED' in err and 'pc=0x0 ' in err:
                for slot, sz in reversed(list(reads.items())):
                    if sz != 4 or slot in self.ptrs or slot in self.fnptrs: continue
                    _, _, e2 = self.run(fn, extra_fn=slot)
                    if e2 != err:
                        self.fnptrs[slot] = 1; break
                else:
                    return err
                continue
            if len(self.ptrs) >= PTR_N - 1: return err
            blk = len(self.ptrs)
            lo, hi = PTR + blk * PTR_BLK, PTR + (blk + 1) * PTR_BLK
            found = None
            # newest reads first: the faulting load is usually the last pointer read
            for slot, sz in reversed(list(reads.items())):
                if sz != 4 or slot in self.ptrs or slot == self.ctx + 0x70: continue
                _, r2, _ = self.run(fn, extra_ptr=slot)
                if any(lo <= a < hi for a in r2):
                    found = slot; break
            if found is None: return err
            self.ptrs[found] = blk
        return err


def bits(x):
    out, i = [], 0
    while x:
        if x & 1:
            j = i
            while x >> (j - i + 1) & 1: j += 1
            out.append((i, j)); x >>= j - i + 1; i = j + 1
        else:
            x >>= 1; i += 1
    return out


def main():
    R = Run()
    for fn in SETTERS:
        err0 = R.discover(fn)
        base, reads, err = R.run(fn)
        if R.ptrs or R.fnptrs:
            print(f'\n## {fn}: pointers ' + ', '.join(R.label(p) for p in R.ptrs)
                  + ' | fn pointers ' + ', '.join(R.label(p) for p in R.fnptrs))
        print(f'\n## {fn}' + (f'   [baseline error: {err}]' if err else ''))
        for (g, o), v in sorted(base.items()):
            print(f'   base  {g}+{o:#04x} = {v:#010x}  {REGNAME.get((g, o), "")}')
        fields = sorted(a for a in reads if a not in R.ptrs and a not in R.fnptrs and a not in (R.ctx + 0x70, R.ctx + 0x71) and a - R.ctx not in SCENARIO)
        rows = []
        for off in fields:
            n = reads[off]
            for probe in ((1 << 8 * n) - 1, 1):
                regs, _, err2 = R.run(fn, {off: (probe, n)})
                diff = {k: regs.get(k, 0) ^ base.get(k, 0) for k in set(regs) | set(base)
                        if regs.get(k, 0) != base.get(k, 0)}
                if err2 and not err: diff[('ERR', 0)] = 0
                rows.append((off, n, probe, diff))
        for off, n, probe, diff in rows:
            if not diff: continue
            desc = ', '.join(f'{g}+{o:#04x}' + ''.join(f'[{a}' + (f':{b}]' if b != a else ']') for a, b in bits(x))
                             if g != 'ERR' else 'ERROR' for (g, o), x in sorted(diff.items()))
            print(f'   {R.label(off)}/{n} = {probe:#x}:  {desc}')
        quiet = [R.label(o) for o in fields if not any(r[0] == o and r[3] for r in rows)]
        if quiet: print(f'   read but no register effect: {" ".join(quiet)}')


if __name__ == '__main__':
    main()
