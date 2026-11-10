#!/usr/bin/env python3
"""Concatenate IVF streams into one, renumbering timestamps.

Joining clips of different sizes gives a stream with a new sequence header
(and so a resolution change) at each join -- the mid-stream case a stateless
decoder has to renegotiate for.

  usage: ivf-concat.py [--fps N] out.ivf a.ivf b.ivf [...]

--fps sets the header's time base to 1/N (frame i at i/N s). Without it the
first input's time base is kept: the committed vectors say 1/1000, which a
decoder test does not care about but a player shows at 1000 fps.
"""
import struct
import sys

args = sys.argv[1:]
fps = None
if args[:1] == ["--fps"]:
    fps, args = int(args[1]), args[2:]
out, ins = args[0], args[1:]
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
if fps:
    struct.pack_into("<II", header, 16, fps, 1)
with open(out, "wb") as f:
    f.write(header)
    for i, fr in enumerate(frames):
        f.write(struct.pack("<IQ", len(fr), i) + fr)
print(f"{out}: {len(frames)} frames from {len(ins)} streams")
