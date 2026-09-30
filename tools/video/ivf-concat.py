#!/usr/bin/env python3
"""Concatenate IVF streams into one, renumbering timestamps.

Joining clips of different sizes gives a stream with a new sequence header
(and so a resolution change) at each join -- the mid-stream case a stateless
decoder has to renegotiate for.

  usage: ivf-concat.py out.ivf a.ivf b.ivf [...]
"""
import struct
import sys

out, ins = sys.argv[1], sys.argv[2:]
frames = []
header = None
for path in ins:
    d = open(path, "rb").read()
    assert d[:4] == b"DKIF", path
    hlen = struct.unpack_from("<H", d, 6)[0]
    header = header or bytearray(d[:hlen])
    o = hlen
    while o < len(d):
        n = struct.unpack_from("<I", d, o)[0]
        frames.append(d[o + 12:o + 12 + n])
        o += 12 + n
struct.pack_into("<I", header, 24, len(frames))
with open(out, "wb") as f:
    f.write(header)
    for i, fr in enumerate(frames):
        f.write(struct.pack("<IQ", len(fr), i) + fr)
print(f"{out}: {len(frames)} frames from {len(ins)} streams")
