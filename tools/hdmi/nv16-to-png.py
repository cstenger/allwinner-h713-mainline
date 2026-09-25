#!/usr/bin/env python3
"""Convert a 640x480 NV16 (Y + interleaved UV) sample to RGB PNG.

The conversion uses BT.601 limited-range coefficients and the standard library.
It assumes the two planes describe the same frame; the diagnostic DRAM reader
does not yet have a frame-completion signal or atomic snapshot guarantee.
"""

import argparse
import struct
import zlib
from pathlib import Path

WIDTH, HEIGHT = 640, 480
PLANE = WIDTH * HEIGHT


def chunk(tag, data):
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def clip(value):
    return min(255, max(0, value))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    raw = args.input.read_bytes()
    if len(raw) != 2 * PLANE:
        ap.error(f"expected {2 * PLANE} bytes, got {len(raw)}")
    y, uv = memoryview(raw)[:PLANE], memoryview(raw)[PLANE:]
    scanlines = bytearray()
    for row in range(HEIGHT):
        scanlines.append(0)  # PNG filter: none
        start = row * WIDTH
        for x in range(0, WIDTH, 2):
            i = start + x
            d, e = uv[i] - 128, uv[i + 1] - 128
            for pixel in (i, i + 1):
                c = max(0, y[pixel] - 16)
                scanlines.extend((clip((298*c + 409*e + 128) >> 8),
                                  clip((298*c - 100*d - 208*e + 128) >> 8),
                                  clip((298*c + 516*d + 128) >> 8)))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(scanlines, 6))
           + chunk(b"IEND", b""))
    args.output.write_bytes(png)
    print(f"{args.output}: {WIDTH}x{HEIGHT} RGB PNG ({len(png)} bytes)")


if __name__ == "__main__":
    main()
