#!/usr/bin/env python3
"""Load a stripped Android ARM32 vendor library (Allwinner CedarC codec plugins)
into Unicorn and call its functions, recording every MMIO access.

Written 2026-09-29 to recover the VE VP9 register bitfields from libawvp9HwAL.so
without a decompiler: the library exports each register's shadow word under a
name that carries its offset (vp9_func_ctrl_reg30, ...), so all that remains
unknown is which context field lands in which bits -- which is what calling a
setter with one field perturbed at a time answers mechanically.

Handles what makes these libraries awkward to load by hand:
  * ANDROID_REL (APS2 packed) and ANDROID_RELR relocations
  * PLT calls between the library's OWN exports (resolved to the local symbol)
  * a MiniDebugInfo .gnu_debugdata that is itself nested one level deep

    lib = Lib("libawvp9HwAL.so")
    lib.call("VP9SetBasicReg", ctx_addr)
"""
import lzma, struct
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, \
    UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_UNMAPPED, UC_PROT_ALL
from unicorn.arm_const import *

BASE = 0x10000000      # library load bias
STUBS = 0x20000000     # one 4-byte slot per import
HEAP = 0x30000000      # bump allocator for malloc and for callers
HEAP_SZ = 0x04000000     # default; Lib(heap=...) overrides
STACK = 0x60000000
STACK_SZ = 0x00100000
RET = 0x7ff00000       # return trampoline; hitting it ends a call
MMIO = 0x70000000      # fake register windows live here

PAGE = 0x1000


def _sleb(b, i):
    r = s = 0
    while True:
        x = b[i]; i += 1
        r |= (x & 0x7f) << s; s += 7
        if not x & 0x80:
            if x & 0x40: r -= 1 << s
            return r, i


def aps2(blob):
    """Decode an Android packed relocation section -> [(r_offset, r_info)]."""
    assert blob[:4] == b'APS2', blob[:4]
    i = 4
    n, i = _sleb(blob, i); off, i = _sleb(blob, i)
    out = []
    while len(out) < n:
        gsz, i = _sleb(blob, i); fl, i = _sleb(blob, i)
        if fl & 2: gdelta, i = _sleb(blob, i)
        if fl & 1: ginfo, i = _sleb(blob, i)
        assert not fl & 8, "RELA addends not handled"
        for _ in range(gsz):
            if fl & 2: off += gdelta
            else: d, i = _sleb(blob, i); off += d
            if not fl & 1: info, i = _sleb(blob, i)
            else: info = ginfo
            out.append((off, info))
    return out


def relr(blob):
    words = struct.unpack(f'<{len(blob)//4}I', blob)
    out, where = [], 0
    for w in words:
        if not w & 1:
            out.append(w); where = w + 4
        else:
            for k in range(31):
                if w >> (k + 1) & 1: out.append(where + 4 * k)
            where += 31 * 4
    return out


def debugdata_symbols(elf):
    """Walk nested .gnu_debugdata layers; return {addr: name} of FUNC/OBJECT syms."""
    syms = {}
    while True:
        s = elf.get_section_by_name('.symtab')
        if s:
            for y in s.iter_symbols():
                if y.name and y['st_value']:
                    syms[y['st_value'] & ~1] = y.name
        d = elf.get_section_by_name('.gnu_debugdata')
        if not d: return syms
        import io
        elf = ELFFile(io.BytesIO(lzma.decompress(d.data())))


class Lib:
    def __init__(self, path, log=None, heap=HEAP_SZ):
        self.path = path
        self.heap_sz = heap
        raw = open(path, 'rb').read()
        import io
        self.elf = elf = ELFFile(io.BytesIO(raw))
        self.uc = uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        # VFP/NEON: these libraries use vpush and double-precision math, which
        # fault as invalid instructions until the coprocessors are enabled.
        uc.reg_write(UC_ARM_REG_C1_C0_2, uc.reg_read(UC_ARM_REG_C1_C0_2) | (0xf << 20))
        uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.log = log or (lambda *a: None)
        self.mmio = {}          # name -> (base, size)
        self.mmio_state = {}    # abs addr -> value
        self.trace = []         # (kind, window, offset, value)
        self.read_hooks = {}    # abs addr -> fn(value) returns value

        hi = 0
        for seg in elf.iter_segments():
            if seg['p_type'] != 'PT_LOAD': continue
            hi = max(hi, seg['p_vaddr'] + seg['p_memsz'])
        size = (hi + PAGE) & ~(PAGE - 1)
        uc.mem_map(BASE, size, UC_PROT_ALL)
        for seg in elf.iter_segments():
            if seg['p_type'] != 'PT_LOAD': continue
            uc.mem_write(BASE + seg['p_vaddr'], seg.data())

        dsym = elf.get_section_by_name('.dynsym')
        self.dynsyms = list(dsym.iter_symbols())
        self.exports = {y.name: y['st_value'] for y in self.dynsyms
                        if y['st_shndx'] != 'SHN_UNDEF' and y.name}
        self.names = {v & ~1: k for k, v in self.exports.items()}
        for a, n in debugdata_symbols(elf).items():
            self.names.setdefault(a, n)
            self.exports.setdefault(n, a | 1 if self._is_thumb(a) else a)

        uc.mem_map(STUBS, 0x10000, UC_PROT_ALL)
        uc.mem_map(HEAP, heap, UC_PROT_ALL)
        uc.mem_map(STACK, STACK_SZ, UC_PROT_ALL)
        uc.mem_map(RET, PAGE, UC_PROT_ALL)
        self.brk = HEAP
        self.extern = {}        # stub name -> fn(lib, [r0..r3])
        self.calls = []         # (stub name, args) for add_stub stubs
        self.stubs = {}         # addr -> name
        self.data_imports = {}  # name -> addr of a heap word
        self._relocate()
        uc.hook_add(UC_HOOK_CODE, self._stub_hook, begin=STUBS, end=STUBS + 0x10000)

    def _is_thumb(self, addr):
        for y in self.dynsyms:
            if y['st_value'] & ~1 == addr and y['st_info']['type'] == 'STT_FUNC':
                return y['st_value'] & 1
        return 1  # these libraries are Thumb-2 throughout

    # -- relocation -----------------------------------------------------------
    def _sym_addr(self, idx, is_plt):
        y = self.dynsyms[idx]
        if y['st_shndx'] != 'SHN_UNDEF':
            return BASE + y['st_value']
        name = y.name.split('@')[0]
        if y['st_info']['type'] == 'STT_OBJECT' or name in ('GLOBAL_CDC_LOG_LEVEL', '__stack_chk_guard'):
            if name not in self.data_imports:
                self.data_imports[name] = self.alloc(16)
            return self.data_imports[name]
        for a, n in self.stubs.items():
            if n == name: return a
        a = STUBS + 4 * len(self.stubs)
        self.stubs[a] = name
        self.uc.mem_write(a, b'\x70\x47\x00\xbf')  # bx lr; nop (hook runs first)
        return a | 1

    def _relocate(self):
        uc, elf = self.uc, self.elf
        rels = []
        for s in elf.iter_sections():
            t = s['sh_type']
            if t in ('SHT_ANDROID_REL', 0x60000001):
                rels += aps2(s.data())
            elif t == 'SHT_REL':
                for r in s.iter_relocations():
                    rels.append((r['r_offset'], r['r_info']))
            elif t in ('SHT_ANDROID_RELR', 0x6fffff00, 'SHT_RELR', 19):
                for o in relr(s.data()):
                    v, = struct.unpack('<I', uc.mem_read(BASE + o, 4))
                    uc.mem_write(BASE + o, struct.pack('<I', v + BASE))
        for off, info in rels:
            typ, idx = info & 0xff, info >> 8
            p = BASE + off
            cur, = struct.unpack('<I', uc.mem_read(p, 4))
            if typ == 23:                         # R_ARM_RELATIVE
                v = cur + BASE
            elif typ in (21, 22):                 # GLOB_DAT, JUMP_SLOT
                v = self._sym_addr(idx, typ == 22)
            elif typ == 2:                        # ABS32
                v = self._sym_addr(idx, False) + cur
            else:
                raise NotImplementedError(f'reloc type {typ} at {off:#x}')
            uc.mem_write(p, struct.pack('<I', v))

    # -- runtime --------------------------------------------------------------
    def alloc(self, n, align=16):
        self.brk = (self.brk + align - 1) & ~(align - 1)
        a = self.brk; self.brk += n
        assert self.brk < HEAP + self.heap_sz, 'emulator heap exhausted'
        self.uc.mem_write(a, b'\0' * n)
        return a

    def rd(self, a, n=4):
        return int.from_bytes(self.uc.mem_read(a, n), 'little')

    def wr(self, a, v, n=4):
        self.uc.mem_write(a, int(v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little'))

    def cstr(self, a):
        s = bytearray()
        while True:
            c = self.uc.mem_read(a, 1)[0]
            if not c: return s.decode(errors='replace')
            s.append(c); a += 1

    def _stub_hook(self, uc, addr, size, _):
        name = self.stubs.get(addr & ~1)
        if name is None: return
        r = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        ret = 0
        if name == 'malloc': ret = self.alloc(r[0] or 1)
        elif name == 'calloc': ret = self.alloc((r[0] * r[1]) or 1)
        elif name == 'memset': uc.mem_write(r[0], bytes([r[1] & 0xff]) * r[2]); ret = r[0]
        elif name == 'memcpy': uc.mem_write(r[0], bytes(uc.mem_read(r[1], r[2]))); ret = r[0]
        elif name == '__android_log_print': self.log('LOG', self.cstr(r[2]))
        elif name in ('abort', '__stack_chk_fail'):
            raise RuntimeError(f'{name} called')
        elif name in ('free', 'usleep', 'fclose', 'fwrite_unlocked'): pass
        elif name == 'fopen': ret = 0
        elif name in self.extern:
            self.calls.append((name, r)); ret = self.extern[name](self, r) or 0
        else: self.log('STUB', name, [hex(x) for x in r])
        uc.reg_write(UC_ARM_REG_R0, ret & 0xffffffff)

    def add_stub(self, name, fn):
        """A callable address (Thumb) that runs fn(lib, [r0..r3]) and returns its
        result -- for function pointers a library expects to find in its context."""
        a = STUBS + 4 * len(self.stubs)
        self.stubs[a] = name
        self.uc.mem_write(a, b'\x70\x47\x00\xbf')
        self.extern[name] = fn
        return a | 1

    def intercept(self, addr, fn):
        """Replace the library function at addr (vaddr or symbol) with
        fn(lib, [r0..r3]) -> r0. The original code never runs."""
        if isinstance(addr, str):
            addr = self.exports[addr]
        a = (BASE + addr if addr < BASE else addr) & ~1
        uc = self.uc
        def hook(uc_, address, size, _):
            r = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1,
                                         UC_ARM_REG_R2, UC_ARM_REG_R3)]
            ret = fn(self, r)
            uc.reg_write(UC_ARM_REG_R0, (ret or 0) & 0xffffffff)
            lr = uc.reg_read(UC_ARM_REG_LR)
            uc.reg_write(UC_ARM_REG_PC, lr)
        uc.hook_add(UC_HOOK_CODE, hook, begin=a, end=a)

    def stack_arg(self, i):
        """The i-th stacked argument (after r0-r3) at a function's entry."""
        return self.rd(self.uc.reg_read(UC_ARM_REG_SP) + 4 * i)

    def add_mmio(self, name, size=0x1000, ptr_symbol=None):
        """Create a register window. If ptr_symbol names a library global, store
        the window's base there (how these libraries find their registers)."""
        base = MMIO + 0x10000 * len(self.mmio)
        self.uc.mem_map(base, (size + PAGE - 1) & ~(PAGE - 1), UC_PROT_ALL)
        self.mmio[name] = (base, size)
        def w(uc, acc, a, sz, v, _):
            self.trace.append(('W', name, a - base, v & 0xffffffff))
            self.mmio_state[a] = v
        def r(uc, acc, a, sz, v, _):
            val = self.read_hooks[a](self.rd(a, sz)) if a in self.read_hooks else self.rd(a, sz)
            self.wr(a, val, sz)
            self.trace.append(('R', name, a - base, val))
        self.uc.hook_add(UC_HOOK_MEM_WRITE, w, begin=base, end=base + size - 1)
        self.uc.hook_add(UC_HOOK_MEM_READ, r, begin=base, end=base + size - 1)
        if ptr_symbol:
            self.wr(BASE + self.exports[ptr_symbol], base)
        return base

    def sym(self, name):
        return BASE + (self.exports[name] & ~1)

    def call(self, fn, *args, max_insns=5_000_000):
        uc = self.uc
        a = self.exports[fn] if isinstance(fn, str) else fn
        a = BASE + a if a < BASE else a
        regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
        sp = STACK + STACK_SZ - 0x1000
        for i, v in enumerate(args[:4]): uc.reg_write(regs[i], v & 0xffffffff)
        for i, v in enumerate(args[4:]): self.wr(sp + 4 * i, v)
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.reg_write(UC_ARM_REG_LR, RET | 1)
        uc.mem_write(RET, b'\x00\xbf\x00\xbf')
        try:
            uc.emu_start(a | 1, RET, count=max_insns)
        except UcError as e:
            pc = uc.reg_read(UC_ARM_REG_PC)
            raise RuntimeError(f'{fn}: {e} at pc={pc:#x} ({self.where(pc)})') from None
        return uc.reg_read(UC_ARM_REG_R0)

    def where(self, pc):
        if not BASE <= pc < BASE + 0x1000000: return '?'
        o = pc - BASE
        best = max((a for a in self.names if a <= o), default=None)
        return f'{self.names[best]}+{o-best:#x}' if best is not None else f'{o:#x}'
