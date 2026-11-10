#!/usr/bin/env python3
"""Validate fixed 640x480 NV16 frames saved by a V4L2 capture stream."""

import argparse
import json
import zlib
from pathlib import Path

PLANE = 640 * 480
FRAME = 2 * PLANE


def summarize(path):
    size = path.stat().st_size
    if size % FRAME:
        raise ValueError(f"{path}: {size} bytes is not a whole number of frames")
    hashes = []
    blank_bottom = 0
    with path.open("rb") as stream:
        for _ in range(size // FRAME):
            frame = stream.read(FRAME)
            hashes.append(f"{zlib.crc32(frame):08x}")
            if not any(frame[PLANE - 4096:PLANE]) or not any(frame[-4096:]):
                blank_bottom += 1
    return {"file": str(path), "bytes": size, "frames": len(hashes),
            "unique_crc32": len(set(hashes)), "blank_bottom_frames": blank_bottom,
            "first_crc32": hashes[0] if hashes else None,
            "last_crc32": hashes[-1] if hashes else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", type=Path, nargs="+")
    args = ap.parse_args()
    print(json.dumps([summarize(path) for path in args.files], indent=2))


if __name__ == "__main__":
    main()
