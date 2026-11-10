#!/usr/bin/env python3
"""Measure the scaler test card's border in a raw NV12 capture.

The card carries a border on all four edges, so in a decoded dump the last
bright row IS the bottom of the visible picture. That makes the border a direct
readout of whether the scaler consumed the coded raster or only the visible
part: H.264 stores 1080p as 1088 rows, and scaling all 1088 into 720 leaves the
bottom border roughly twice as thick, because encoders pad by replicating the
last row and that row is the border itself.

    python3 tools/video/measure-nv12-border.py \\
        "label=dump.nv12" [...] --size 1280x720 \\
        --reference local/testcards/scaler-testcard-1280x720.nv12

PSNR against the reference is a cross-check, not the finding: the reference is
independently rasterised, so fine detail can never match. The border row is what
carries the result.
"""
import argparse
import sys

import numpy as np


def luma(path, w, h):
    y = np.fromfile(path, dtype=np.uint8, count=w * h)
    if y.size != w * h:
        raise SystemExit(f"{path}: expected {w * h} luma bytes, got {y.size}")
    return y.reshape(h, w)


def report(label, path, w, h, ref):
    y = luma(path, w, h)
    rows = y.mean(axis=1)
    bright = rows > rows.max() * 0.6
    idx = np.nonzero(bright)[0]

    print(f"--- {label}")
    if not idx.size:
        print("    no bright rows; is this the right geometry?")
        return

    # Thickness of the bright run that reaches the bottom edge.
    last = int(idx[-1])
    run = 0
    while run < h and bright[h - 1 - run]:
        run += 1
    top = 0
    while top < h and bright[top]:
        top += 1

    print(f"    top border    : {top} rows")
    print(f"    bottom border : {run} rows, ending at row {last} of {h - 1}")
    print("    last 12 row means: " +
          " ".join(f"{int(v):3d}" for v in rows[-12:]))

    if ref is not None:
        d = y.astype(np.int32) - ref.astype(np.int32)
        mse = float((d * d).mean())
        psnr = float("inf") if mse == 0 else 10 * np.log10(255.0 * 255.0 / mse)
        print(f"    PSNR vs reference: {psnr:.2f} dB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help='"label=path" or just "path"')
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--reference")
    args = ap.parse_args()

    w, h = (int(v) for v in args.size.split("x"))
    ref = luma(args.reference, w, h) if args.reference else None
    if ref is not None:
        report("reference", args.reference, w, h, None)

    for item in args.inputs:
        label, _, path = item.partition("=")
        if not path:
            label, path = item, item
        report(label, path, w, h, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
