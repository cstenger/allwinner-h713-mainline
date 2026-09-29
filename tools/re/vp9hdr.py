#!/usr/bin/env python3
"""Print each VP9 frame's uncompressed-header essentials from an IVF file:
type, show, refs (ref_frame_idx), refresh mask, interp filter, sizes.
usage: ffmpeg -i x.webm -c copy x.ivf; vp9hdr.py x.ivf"""
import struct, sys
class B:
    def __init__(s, d): s.d, s.p = d, 0
    def f(s, n):
        v = 0
        for _ in range(n):
            v = v << 1 | (s.d[s.p >> 3] >> (7 - (s.p & 7))) & 1; s.p += 1
        return v
def frames(path):
    d = open(path, 'rb').read(); o = struct.unpack_from('<H', d, 6)[0]
    while o + 12 <= len(d):
        n = struct.unpack_from('<I', d, o)[0]; yield d[o + 12:o + 12 + n]; o += 12 + n
for i, fr in enumerate(frames(sys.argv[1]), 1):
    b = B(fr); b.f(2); prof = b.f(1) | b.f(1) << 1
    if prof == 3: b.f(1)
    if b.f(1): print(f'{i:3d} show_existing {b.f(3)}'); continue
    ft = b.f(1); show = b.f(1); er = b.f(1)
    if ft == 0:
        b.f(24); b.f(3); b.f(1)  # sync, color space (profile 0), range
        w = b.f(16) + 1; h = b.f(16) + 1
        print(f'{i:3d} KEY  show={show} er={er} {w}x{h} refresh=0xff'); continue
    intra = 0 if show else b.f(1)
    reset = 0 if er else b.f(2)
    if intra:
        b.f(24); rf = b.f(8); print(f'{i:3d} INTRA show={show} refresh={rf:#04x}'); continue
    rf = b.f(8); idx = []; bias = []
    for _ in range(3): idx.append(b.f(3)); bias.append(b.f(1))
    found = None
    for k in range(3):
        if b.f(1): found = k; break
    if found is None: b.f(32)
    if b.f(1): b.f(32)  # render size
    hp = b.f(1)
    interp = 4 if b.f(1) else [1, 0, 2, 3][b.f(2)]
    print(f'{i:3d} INTER show={show} er={er} refresh={rf:#04x} ref_idx(L,G,A)={idx} bias={bias} size_from_ref={found} hp={hp} interp={interp}')
