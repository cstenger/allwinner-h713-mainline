#!/usr/bin/env python3
"""Annotate an Android ARM32 objdump listing with PLT import names, plus names for
the linker's __ThumbV7PILongThunk_* stubs from a MiniDebugInfo symtab.
usage: annotate-plt.py LIB DIS [DEBUGDATA_ELF] > OUT"""
import re, subprocess, sys
lib, dis = sys.argv[1], sys.argv[2]
sec = {}
for l in subprocess.run(['arm-none-eabi-readelf', '-SW', lib], capture_output=True, text=True).stdout.splitlines():
    m = re.match(r'\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)', l)
    if m: sec[m[1]] = (int(m[2], 16), int(m[3], 16))
names = [l.split()[4].split('@')[0] for l in subprocess.run(['arm-none-eabi-readelf', '-rW', lib],
         capture_output=True, text=True).stdout.splitlines() if 'R_ARM_JUMP_SLOT' in l]
plt0, pltsz = sec['.plt']
hdr = pltsz - 16 * len(names)
m = {plt0 + hdr + 16 * i: n for i, n in enumerate(names)}
if len(sys.argv) > 3:
    for l in subprocess.run(['arm-none-eabi-nm', sys.argv[3]], capture_output=True, text=True).stdout.splitlines():
        a, t, n = l.split()
        m.setdefault(int(a, 16), n.replace('__ThumbV7PILongThunk_', ''))
def sub(mo):
    a = int(mo[2], 16)
    return f'{mo[1]}{mo[2]} <{m[a]}>' if a in m else mo[0]
for l in open(dis):
    sys.stdout.write(re.sub(r'(\bbl?x?(?:eq|ne|cs|cc|mi|pl|vs|vc|hi|ls|ge|lt|gt|le)?(?:\.w)?\s+)([0-9a-f]+) <[^>]*>', sub, l))
