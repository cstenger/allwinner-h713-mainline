#!/usr/bin/env python3
"""Pack one frame captured by vendor-decode.py into a replay package for the
sunxi-h713-av1-probe debugfs interface (format in that driver's header).

    mkreplay.py OUTDIR/frameNNN.json pkg.bin

Each allocation is sent up to its last non-zero byte (the board zero-fills the
rest), so the 8 MiB stream ring costs only the data in it."""
import json, os, struct, sys

m = json.load(open(sys.argv[1]))
d = os.path.dirname(sys.argv[1])
img = open(os.path.join(d, m['regs']), 'rb').read()
assert len(img) == 1168
out = [b'H7AV', struct.pack('<II', len(m['allocs']), len(m['relocs'])), img]
for a in m['allocs']:
    data = open(os.path.join(d, a['file']), 'rb').read().rstrip(b'\0')
    out.append(struct.pack('<II', a['size'], len(data)))
    out.append(data + b'\0' * (-len(data) % 4))
for r in m['relocs']:
    assert r['width'] == 32
    out.append(struct.pack('<HHII', r['lo'], r['width'], r['alloc'], r['offset']))
blob = b''.join(out)
open(sys.argv[2], 'wb').write(blob)
print(f'{sys.argv[2]}: {len(blob)} bytes, {len(m["allocs"])} allocs, {len(m["relocs"])} relocs')
for i, a in enumerate(m['allocs']):
    print(f'  alloc{i}: {a["size"]:8d} B  <- ' + ', '.join(
        f'{r["field"][3:]}+{r["offset"]:#x}' for r in m['relocs'] if r['alloc'] == i))
