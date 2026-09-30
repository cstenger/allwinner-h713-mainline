#!/usr/bin/env python3
"""Damaged AV1 streams for the robustness test (av1-robustness-test.sh).

Every damage keeps the IVF container and each frame's leading bytes (the
temporal delimiter and the OBU headers) intact, so the parser still hands the
decoder a frame and the damage reaches the hardware rather than stopping in
userspace. Deterministic: a fixed seed per stream.

  usage: make-av1-bad-streams.py good.ivf tiles.ivf OUTDIR
"""
import os, random, struct, sys

def read(path):
    d = open(path, 'rb').read()
    hl = struct.unpack_from('<H', d, 6)[0]
    frames, o = [], hl
    while o < len(d):
        n = struct.unpack_from('<I', d, o)[0]
        frames.append(bytearray(d[o + 12:o + 12 + n]))
        o += 12 + n
    return bytearray(d[:hl]), frames

def write(path, hdr, frames):
    hdr = bytearray(hdr)
    struct.pack_into('<I', hdr, 24, len(frames))
    with open(path, 'wb') as f:
        f.write(hdr)
        for i, fr in enumerate(frames):
            f.write(struct.pack('<IQ', len(fr), i) + fr)

def tail(fr, frac=0.3):		# the part past the headers
    return int(len(fr) * frac), len(fr)

def flip(fr, rng, n):
    a, b = tail(fr)
    for _ in range(n):
        fr[rng.randrange(a, b)] ^= 1 << rng.randrange(8)

good, tiles, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
streams = {}
h, f = read(good)
rng = random.Random(1); g = [bytearray(x) for x in f]
for i in range(1, len(g)): flip(g[i], rng, 8)
streams['bitflip-inter'] = (h, g)
rng = random.Random(2); g = [bytearray(x) for x in f]; flip(g[0], rng, 40)
streams['bitflip-key'] = (h, g)
g = [bytearray(x) for x in f]; a, b = tail(g[0]); g[0][a:b] = bytes(b - a)
streams['zero-key'] = (h, g)
rng = random.Random(3); g = [bytearray(x) for x in f]
for i in (3, 7): a, b = tail(g[i]); g[i][a:b] = bytes(rng.randrange(256) for _ in range(b - a))
streams['garbage-inter'] = (h, g)
g = [bytearray(x) for x in f]; g[4] = g[4][:len(g[4]) // 2]
streams['truncated'] = (h, g)
g = [bytearray(x) for x in f]; del g[5]
streams['dropped-frame'] = (h, g)
g = [bytearray(x) for x in f]; g[2], g[6] = g[6], g[2]
streams['swapped-frames'] = (h, g)
g = [bytearray(x) for x in f]; streams['no-key-start'] = (h, g[1:] if len(g) > 1 else g)
h, f = read(tiles)
rng = random.Random(4); g = [bytearray(x) for x in f]
for x in g: flip(x, rng, 30)
streams['bitflip-tiles'] = (h, g)
g = [bytearray(x) for x in f]; g[0] = g[0][:len(g[0]) * 2 // 3]
streams['truncated-tiles'] = (h, g)
for name, (hh, gg) in streams.items():
    write(os.path.join(out, f'bad-{name}.ivf'), hh, gg)
    print(f'bad-{name}.ivf: {len(gg)} frames')
