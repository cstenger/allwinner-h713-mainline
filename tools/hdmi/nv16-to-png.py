#!/usr/bin/env python3
"""Convert an NV16 (Y + interleaved UV) sample to RGB PNG.

The conversion uses BT.601 limited-range coefficients and the standard library.
It assumes the two planes describe the same frame; the diagnostic DRAM reader
does not yet have a frame-completion signal or atomic snapshot guarantee.
"""

import argparse
import struct
import zlib
from pathlib import Path

def chunk(tag, data):
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def clip(value):
    return min(255, max(0, value))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--width", type=int, choices=(640, 1280), default=640)
    ap.add_argument("--height", type=int, choices=(480, 720), default=480)
    ap.add_argument("--rotate-left", type=int, default=0,
                    help="rotate each row left by this many pixels (default: 0)")
    ap.add_argument("--valid-rows", type=int,
                    help="rows to write; never invent missing rows")
    args = ap.parse_args()
    if (args.width, args.height) not in ((640, 480), (1280, 720)):
        ap.error("supported formats are 640x480 and 1280x720")
    if not 0 <= args.rotate_left < args.width:
        ap.error("--rotate-left must be less than the width")
    valid_rows = args.valid_rows if args.valid_rows is not None else args.height
    if not 1 <= valid_rows <= args.height:
        ap.error("--valid-rows must be between 1 and the frame height")
    plane = args.width * args.height
    raw = args.input.read_bytes()
    if len(raw) != 2 * plane:
        ap.error(f"expected {2 * plane} bytes, got {len(raw)}")
    y, uv = memoryview(raw)[:plane], memoryview(raw)[plane:]
    scanlines = bytearray()
    for row in range(valid_rows):
        scanlines.append(0)  # PNG filter: none
        start = row * args.width
        for x in range(args.width):
            src_x = (x + args.rotate_left) % args.width
            i = start + src_x
            uv_i = start + (src_x & ~1)
            d, e = uv[uv_i] - 128, uv[uv_i + 1] - 128
            c = max(0, y[i] - 16)
            scanlines.extend((clip((298*c + 409*e + 128) >> 8),
                              clip((298*c - 100*d - 208*e + 128) >> 8),
                              clip((298*c + 516*d + 128) >> 8)))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", args.width, valid_rows, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(scanlines, 6))
           + chunk(b"IEND", b""))
    args.output.write_bytes(png)
    print(f"{args.output}: {args.width}x{valid_rows} RGB PNG ({len(png)} bytes)")


if __name__ == "__main__":
    main()
