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
    ap.add_argument("--rotate-left", type=int, choices=range(WIDTH), default=0,
                    help="rotate each row left by this many pixels (default: 0)")
    ap.add_argument("--valid-rows", type=int, choices=range(1, HEIGHT + 1),
                    default=HEIGHT, help="rows to write; never invent missing rows")
    args = ap.parse_args()
    raw = args.input.read_bytes()
    if len(raw) != 2 * PLANE:
        ap.error(f"expected {2 * PLANE} bytes, got {len(raw)}")
    y, uv = memoryview(raw)[:PLANE], memoryview(raw)[PLANE:]
    scanlines = bytearray()
    for row in range(args.valid_rows):
        scanlines.append(0)  # PNG filter: none
        start = row * WIDTH
        for x in range(WIDTH):
            src_x = (x + args.rotate_left) % WIDTH
            i = start + src_x
            uv_i = start + (src_x & ~1)
            d, e = uv[uv_i] - 128, uv[uv_i + 1] - 128
            c = max(0, y[i] - 16)
            scanlines.extend((clip((298*c + 409*e + 128) >> 8),
                              clip((298*c - 100*d - 208*e + 128) >> 8),
                              clip((298*c + 516*d + 128) >> 8)))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, args.valid_rows, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(scanlines, 6))
           + chunk(b"IEND", b""))
    args.output.write_bytes(png)
    print(f"{args.output}: {WIDTH}x{args.valid_rows} RGB PNG ({len(png)} bytes)")


if __name__ == "__main__":
    main()
