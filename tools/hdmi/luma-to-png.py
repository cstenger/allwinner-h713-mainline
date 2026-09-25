#!/usr/bin/env python3
"""Convert a fixed 640x480 Y8 candidate dump to a grayscale PNG.

Only the first 307200 bytes are image data; the remainder of the 320 KiB
diagnostic dump is padding. Uses the Python standard library only.
"""

import argparse
import struct
import zlib
from pathlib import Path

WIDTH, HEIGHT = 640, 480
PIXELS = WIDTH * HEIGHT


def chunk(tag, data):
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    raw = args.input.read_bytes()
    if len(raw) < PIXELS:
        ap.error(f"need at least {PIXELS} bytes for a 640x480 Y8 frame")
    pixels = raw[:PIXELS]
    scanlines = b"".join(b"\0" + pixels[y * WIDTH:(y + 1) * WIDTH]
                         for y in range(HEIGHT))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(scanlines, 6))
           + chunk(b"IEND", b""))
    args.output.write_bytes(png)
    print(f"{args.output}: {WIDTH}x{HEIGHT} grayscale PNG ({len(png)} bytes)")


if __name__ == "__main__":
    main()
