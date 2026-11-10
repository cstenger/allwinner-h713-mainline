#!/usr/bin/env python3
"""Extract the MiniDebugInfo (.gnu_debugdata, xz ELF) symtab from a stripped ELF32/64.
usage: extract-debugdata.py LIB OUT.elf"""
import lzma, struct, sys
b = open(sys.argv[1], 'rb').read()
is64 = b[4] == 2
if is64:
    shoff, = struct.unpack_from('<Q', b, 0x28); shentsize, shnum, shstrndx = struct.unpack_from('<HHH', b, 0x3a)
else:
    shoff, = struct.unpack_from('<I', b, 0x20); shentsize, shnum, shstrndx = struct.unpack_from('<HHH', b, 0x2e)
def sh(i):
    o = shoff + i * shentsize
    if is64:
        name, typ, flags, addr, off, size = struct.unpack_from('<IIQQQQ', b, o)
    else:
        name, typ, flags, addr, off, size = struct.unpack_from('<IIIIII', b, o)
    return name, off, size
_, stroff, _ = sh(shstrndx)
for i in range(shnum):
    name, off, size = sh(i)
    n = b[stroff + name:b.index(b'\0', stroff + name)]
    if n == b'.gnu_debugdata':
        open(sys.argv[2], 'wb').write(lzma.decompress(b[off:off + size]))
        print(f"{sys.argv[1]}: {size} B xz -> {sys.argv[2]}"); break
else:
    sys.exit("no .gnu_debugdata")
