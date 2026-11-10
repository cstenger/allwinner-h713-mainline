#!/usr/bin/env python3
"""Extract (name, width, const|member offset) from a vendor debug printer
`operator<<(ostream&, T const&)` in a Ghidra decompile: each field prints as
"  sw_name (width) = " followed by either a constant or a member of the struct.

    printer-fields.py DECOMP.c GHIDRA_ADDR OUT.txt
"""
import re, sys
src = open(sys.argv[1]).read()
start = src.index(f'// ==== operator<< @ {int(sys.argv[2], 16):08x}')
end = src.index('// ==== ', start + 10)
body = src[start:end]
toks = re.findall(r'\(param_1,"  (\w+) \((\d+)\) = ",0x[0-9a-f]+\);\s*poVar1 = \(ostream \*\)([^\n]+)', body)
out = []
for name, w, expr in toks:
    m = re.search(r'operator<<\(poVar1,(-?(?:0x)?[0-9a-f]+)\)', expr)
    if m:
        out.append(f'{name} {w} const {m.group(1)}'); continue
    m = re.search(r'(FUN_[0-9a-f]+)\(poVar1,param_2(?: \+ (0x[0-9a-f]+|\d+))?\)', expr)
    if m:
        out.append(f'{name} {w} member {int(m.group(2) or "0", 0)} {m.group(1)}'); continue
    out.append(f'{name} {w} ? {expr.strip()[:40]}')
open(sys.argv[3], 'w').write('\n'.join(out) + '\n')
print(len(out), 'fields,', sum(int(l.split()[1]) for l in out), 'bits ->', sys.argv[3])
