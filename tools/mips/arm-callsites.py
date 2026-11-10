#!/usr/bin/env python3
"""Find real ARM/Thumb call sites in a stripped .so, including PLT-routed ones.

WHY NOT JUST DISASSEMBLE. Two independent traps make a naive search report zero
callers for functions that plainly have them:

  1. A linear disassembly of .text desynchronises. Thumb is variable-length and
     .text carries inline literal pools, so a sweep from the section start goes
     out of phase almost immediately and most real instructions are never
     decoded. This script instead decodes the Thumb BL/BLX encoding at every
     2-byte slot, which cannot desync.
  2. Exported functions are called through the PLT even from inside their own
     library, so call sites branch to a stub rather than to st_value. This
     resolves stub -> GOT slot -> .rel.plt symbol and folds those in.

Both bit on 2026-09-11, and each time the empty result looked like a finding:
the scaler selection in libawh264.so was invisible until both were fixed. A
scanner that reports zero callers for a function that must have some is broken,
not informative.

    tools/mips/arm-callsites.py <lib.so> [name ...]

With no names, lists every symbol that has call sites. Section geometry is read
from the ELF, so nothing needs to be passed by hand.
"""
import re
import struct
import subprocess
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import importlib.util

_spec = importlib.util.spec_from_file_location(
    'elf_addr', __file__.rsplit('/', 1)[0] + '/elf-addr.py')
_ea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ea)


def sections(path):
    out = subprocess.run(['readelf', '-S', '-W', path],
                         capture_output=True, text=True).stdout
    secs = {}
    for m in re.finditer(
            r'\]\s+(\.\S+)\s+\S+\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)',
            out):
        secs[m.group(1)] = (int(m.group(2), 16), int(m.group(3), 16),
                            int(m.group(4), 16))   # addr, off, size
    return secs


def bl_sites(e, text_va, text_sz):
    """Every Thumb BL/BLX, by decoding the encoding at each 2-byte slot."""
    d = e.blob(text_va, text_sz)
    out = {}
    for i in range(0, len(d) - 3, 2):
        hw1, hw2 = struct.unpack_from('<HH', d, i)
        if (hw1 & 0xF800) != 0xF000:
            continue
        is_bl = (hw2 & 0xD000) == 0xD000
        is_blx = (hw2 & 0xD001) == 0xC000
        if not (is_bl or is_blx):
            continue
        S = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        J1 = (hw2 >> 13) & 1
        J2 = (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF
        imm = ((S << 24) | ((1 - (J1 ^ S)) << 23) | ((1 - (J2 ^ S)) << 22) |
               (imm10 << 12) | (imm11 << 1))
        if S:
            imm -= 1 << 25
        tgt = text_va + i + 4 + imm
        if is_blx:
            tgt &= ~3
        out.setdefault(tgt, []).append(text_va + i)
    return out


def plt_map(e, path, plt_va, plt_sz):
    """PLT stub address -> imported/exported symbol name."""
    import capstone
    got2sym = {}
    out = subprocess.run(['readelf', '-r', '-W', path],
                         capture_output=True, text=True).stdout
    for ln in out.splitlines():
        f = ln.split()
        if len(f) >= 5 and f[2] == 'R_ARM_JUMP_SLOT':
            got2sym[int(f[0], 16)] = f[4]

    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    ins = list(md.disasm(e.blob(plt_va, plt_sz), plt_va))
    stubs = {}

    def imm(op):
        m = re.search(r'#(0x[0-9a-f]+|\d+)', op)
        return int(m.group(1), 0) if m else 0

    for i in range(len(ins) - 2):
        a, b, c = ins[i], ins[i + 1], ins[i + 2]
        if (a.mnemonic == 'add' and b.mnemonic == 'add' and
                c.mnemonic == 'ldr' and 'pc,' in c.op_str.replace(' ', '')):
            got = (a.address + 8) + imm(a.op_str) + imm(b.op_str) + imm(c.op_str)
            if got in got2sym:
                stubs[a.address] = got2sym[got]
    return stubs


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    want = set(argv[2:])

    secs = sections(path)
    e = _ea.ElfAddr(path)
    tva, _, tsz = secs['.text']
    sites = bl_sites(e, tva, tsz)

    stubs = {}
    if '.plt' in secs:
        pva, _, psz = secs['.plt']
        stubs = plt_map(e, path, pva, psz)

    # symbol name -> call sites, folding PLT stubs into their symbol
    byname = {}
    out = subprocess.run(['readelf', '--dyn-syms', '-W', path],
                         capture_output=True, text=True).stdout
    for ln in out.splitlines():
        f = ln.split()
        if len(f) >= 8 and f[3] == 'FUNC':
            va = int(f[1], 16) & ~1
            if va and sites.get(va):
                byname.setdefault(f[7], []).extend(sites[va])
    for stub, name in stubs.items():
        if sites.get(stub):
            byname.setdefault(name, []).extend(sites[stub])

    total = sum(len(v) for v in sites.values())
    print(f'{path}: {total} BL/BLX sites, {len(stubs)} PLT stubs resolved')
    for name in sorted(byname):
        if want and not any(w in name for w in want):
            continue
        s = sorted(set(byname[name]))
        print(f'  {name:<40} {len(s):>3} site(s)  {[hex(x) for x in s][:8]}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
