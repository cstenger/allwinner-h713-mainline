#!/usr/bin/env python3
"""vaddr -> file-offset translation for the vendor ARM shared objects.

WHY THIS EXISTS. Symbol addresses from `readelf --dyn-syms` are VIRTUAL
addresses. Indexing a .so's bytes with one reads the wrong place, because the
skew between virtual address and file offset is PER-SEGMENT, not per-file. In
libVE.so, .rodata has Addr == Off (skew 0) while .text has skew 0x1000 and
.data skew 0x3000.

Getting this wrong is expensive because it fails quietly:

  - Misaligned Thumb decodes into plausible code. H264ConfigNewScaler
    disassembled as a coherent bitstream reader and a conclusion was drawn from
    it, then had to be withdrawn.
  - A table address translated with the wrong segment's skew landed in a run of
    ASCII strings, which reads as "the table is not there" rather than "you
    looked in the wrong place".

Use this instead of subtracting a constant.

    from elf_addr import ElfAddr
    e = ElfAddr('libVE.so')
    e.u32(0x4d44)              # read a word at a virtual address
    e.thumb(0x4ced, 116)       # disassemble a Thumb function by symbol value

    tools/mips/elf-addr.py libVE.so 0x4d44 0x4d48      # words, from the shell
    tools/mips/elf-addr.py libVE.so --thumb 0x4ced 116
"""
import re
import struct
import subprocess
import sys


class ElfAddr:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        self.segs = []
        out = subprocess.run(['readelf', '-l', '-W', path],
                             capture_output=True, text=True).stdout
        # LOAD  Offset  VirtAddr  PhysAddr  FileSiz  MemSiz  Flg Align
        for m in re.finditer(
                r'LOAD\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+'
                r'(0x[0-9a-f]+)', out):
            off, va, filesz = (int(m.group(i), 16) for i in (1, 2, 3))
            self.segs.append((va, va + filesz, off))
        if not self.segs:
            raise RuntimeError(f'{path}: no LOAD segments found')

    def off(self, va):
        """File offset for a virtual address, or ValueError."""
        for lo, hi, off in self.segs:
            if lo <= va < hi:
                return off + (va - lo)
        raise ValueError(f'{va:#x} is not in any LOAD segment of {self.path}')

    def u32(self, va):
        return struct.unpack_from('<I', self.data, self.off(va))[0]

    def s32(self, va):
        return struct.unpack_from('<i', self.data, self.off(va))[0]

    def blob(self, va, n):
        o = self.off(va)
        return self.data[o:o + n]

    def literal(self, insn_va, imm, addpc_va):
        """Resolve the `ldr rX,[pc,#imm]` + `add rX,pc` pair Thumb-2 uses for
        PC-relative data. The literal sits at Align(insn+4,4)+imm; the `add`
        adds its own PC, which is that instruction's address plus 4."""
        lit = self.s32(((insn_va + 4) & ~3) + imm)
        return lit + addpc_va + 4

    def thumb(self, va, size):
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
        va &= ~1          # symbol values have bit 0 set for Thumb
        for i in md.disasm(self.blob(va, size), va):
            yield f'{i.address:#08x}  {i.mnemonic:<10} {i.op_str}'


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    e = ElfAddr(argv[1])
    if argv[2] == '--thumb':
        va, size = int(argv[3], 0), int(argv[4], 0)
        for line in e.thumb(va, size):
            print(line)
        return 0
    print('segments (va_lo, va_hi, file_off):',
          [(hex(a), hex(b), hex(c)) for a, b, c in e.segs])
    for a in argv[2:]:
        va = int(a, 0)
        print(f'{va:#x} -> file {e.off(va):#x} = {e.u32(va):#010x} '
              f'(signed {e.s32(va)})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
