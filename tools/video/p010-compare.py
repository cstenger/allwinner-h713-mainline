#!/usr/bin/env python3
"""Compare 10-bit decoder output against a yuv420p10le reference (dav1d -o).

  p010-compare.py REF.yuv OUT WIDTH HEIGHT --layout msb|lsb [--rows N] [--pitch B]

--layout msb  OUT is standard P010 (samples in bits 15:6), e.g. ffmpeg
              `-vf hwdownload,format=p010` from VA-API: compared as v >> 6,
              and the low 6 bits must be zero.
--layout lsb  OUT is the H713 AV1 core's raw LSB layout (V4L2 PL10, DRM P010 +
              ALLWINNER_LSB10), e.g. GStreamer filesink of the dma-buf:
              compared as v & 0x3ff, and the top 6 bits must be zero.
--rows        lines the luma plane occupies in OUT (hantro pads 720 to 768);
              chroma starts at pitch * rows. Default HEIGHT.
--pitch       bytes per line in OUT. Default 2 * WIDTH.

Prints per-plane exact-match percentages and the number of frames compared,
and exits non-zero unless every sample of every frame matched -- and at least
one frame was compared (a run that compares nothing must not pass).
"""
import argparse
import sys

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("out")
    ap.add_argument("width", type=int)
    ap.add_argument("height", type=int)
    ap.add_argument("--layout", choices=("msb", "lsb"), required=True)
    ap.add_argument("--rows", type=int)
    ap.add_argument("--pitch", type=int)
    a = ap.parse_args()

    w, h = a.width, a.height
    rows = a.rows or h
    pitch = a.pitch or 2 * w
    ref = np.fromfile(a.ref, dtype="<u2")
    out = np.fromfile(a.out, dtype="<u2")

    ref_frame = w * h * 3 // 2
    out_frame = pitch // 2 * rows * 3 // 2
    nref, nout = ref.size // ref_frame, out.size // out_frame
    if out.size % out_frame:
        print(f"warning: {out.size % out_frame} trailing samples in {a.out}")
    n = min(nref, nout)
    print(f"frames: reference {nref}, output {nout}, comparing {n}")
    if n == 0 or nref != nout:
        print("FAIL: frame counts differ or nothing to compare")
        return 1

    stride = pitch // 2
    bad = {"Y": 0, "U": 0, "V": 0}
    total = {"Y": 0, "U": 0, "V": 0}
    pad = 0
    for f in range(n):
        r = ref[f * ref_frame:(f + 1) * ref_frame]
        o = out[f * out_frame:(f + 1) * out_frame]
        ry = r[:w * h].reshape(h, w)
        ru = r[w * h:w * h * 5 // 4].reshape(h // 2, w // 2)
        rv = r[w * h * 5 // 4:].reshape(h // 2, w // 2)
        oy = o[:stride * rows].reshape(rows, stride)[:h, :w]
        oc = o[stride * rows:stride * rows * 3 // 2].reshape(rows // 2, stride)
        oc = oc[:h // 2, :w]
        ou, ov = oc[:, 0::2], oc[:, 1::2]
        for name, rp, op in (("Y", ry, oy), ("U", ru, ou), ("V", rv, ov)):
            if a.layout == "msb":
                pad += int(np.count_nonzero(op & 0x3f))
                val = op >> 6
            else:
                pad += int(np.count_nonzero(op & 0xfc00))
                val = op & 0x3ff
            bad[name] += int(np.count_nonzero(val != rp))
            total[name] += rp.size

    for name in "YUV":
        pct = 100.0 * (total[name] - bad[name]) / total[name]
        print(f"{name}: {pct:.3f}% exact ({bad[name]} of {total[name]} differ)")
    print(f"padding bits set: {pad}")
    ok = not any(bad.values()) and pad == 0
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
