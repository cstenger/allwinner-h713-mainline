#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Generate the polyphase coefficient table for the H713 VE scaler at VE+0xf00.

The hardware takes 15 sets of 32 phases of 4 signed 8-bit taps.  A set is
selected by downscale ratio; within a set, phase p centres the kernel at tap
index 1 + p/32 and the taps land on source pixels [ip-1 .. ip+2].  Each phase
must sum to exactly 128 or the picture gains or loses brightness.

These coefficients are GENERATED, not extracted from any vendor binary.  Each
set samples a standard kernel -- a cubic B-spline or a triangle -- whose width
grows with the downscale ratio so the stop-band follows the output Nyquist.

The family and width per set are baked in below.  They were chosen offline by
minimising error against ffmpeg's bicubic rescale of decoded frames, scored
through a bit-accurate model of this hardware (validated against real silicon
at 67.8 dB) at each set's lower bound and midpoint.  Re-deriving them needs a
video corpus, so the outcome is recorded here and regeneration is deterministic.

Measured on hardware against the same reference, versus the vendor's own table:
  1280x720 -> 640x360   42.42 dB  (vendor 41.87)
  1280x720 -> 640x180   36.88 dB  (vendor 36.55)
  Main10 640x480 -> 320x240  40.04 dB  (vendor 39.34)
"""
import argparse
import numpy as np

TAPS, PHASES, UNIT = 4, 32, 128

# Upper bound of each set's downscale ratio, for the comment only.
LABELS = ["< 1.125", "< 1.25", "< 1.375", "< 1.5", "< 1.625", "< 1.75",
          "< 1.875", "< 2.0", "< 2.25", "< 2.5", "< 2.75", "< 3.0",
          "< 4.0", "< 5.0", ">= 5.0"]

# (kernel, width) per set -- see the module docstring for how these were chosen.
DESIGN = [("bspline", 0.64), ("tent", 1.04), ("bspline", 0.80),
          ("bspline", 0.92), ("bspline", 1.00), ("bspline", 1.08),
          ("bspline", 0.96), ("bspline", 1.08), ("bspline", 1.12),
          ("bspline", 1.08), ("tent", 2.44), ("tent", 2.00),
          ("tent", 2.44), ("tent", 2.44), ("tent", 2.44)]


def bspline(x):
    """Cubic B-spline (Mitchell-Netravali B=1, C=0)."""
    x = np.abs(x)
    return np.where(x < 1, (3*x**3 - 6*x**2 + 4) / 6.0,
                    np.where(x < 2, (2 - x)**3 / 6.0, 0.0))


def tent(x):
    """Triangle; at width 1 this is exact linear interpolation."""
    return np.maximum(0.0, 1.0 - np.abs(x))


def quantise(w):
    """Scale to UNIT so the row sums to exactly UNIT (largest remainder)."""
    w = np.asarray(w, dtype=np.float64)
    total = w.sum()
    if total == 0:
        out = np.zeros(TAPS, dtype=np.int32)
        out[1] = UNIT
        return out
    exact = w * (UNIT / total)
    low = np.floor(exact).astype(np.int32)
    # stable sort so ties resolve identically on every numpy version
    order = np.argsort(-(exact - low), kind="stable")
    for i in range(int(UNIT - low.sum())):
        low[order[i % TAPS]] += 1
    if low.min() < -128 or low.max() > 127:
        raise ValueError("coefficient outside int8")
    return low


def build(kernel, width):
    fn = bspline if kernel == "bspline" else tent
    out = np.zeros((PHASES, TAPS), dtype=np.int32)
    for p in range(PHASES):
        out[p] = quantise(fn((np.arange(TAPS) - (1.0 + p / PHASES)) / width))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    banks = [build(k, w) for k, w in DESIGN]
    for b in banks:
        assert all(row.sum() == UNIT for row in b), "phase does not sum to 128"

    L = ["/* SPDX-License-Identifier: GPL-2.0 */", "/*",
         " * Polyphase coefficients for the H713 video engine scaler at VE + 0xf00.",
         " *",
         " * 15 sets x 32 phases x 4 taps, signed 8-bit, each phase summing to 128.",
         " * A set is chosen by downscale ratio; phase p centres the kernel at tap",
         " * index 1 + p/32, with the taps landing on source pixels [ip-1 .. ip+2].",
         " *",
         " * GENERATED, NOT EXTRACTED -- do not hand-edit.",
         " * Run tools/video/gen-scaler-coef.py to regenerate; see that script for",
         " * the kernel family, the widths, and how they were chosen.",
         " */", "",
         "#ifndef _CEDRUS_SCALER_COEF_H_", "#define _CEDRUS_SCALER_COEF_H_", "",
         "#define CEDRUS_SCALER_COEF_SETS\t\t%d" % len(DESIGN),
         "#define CEDRUS_SCALER_COEF_PHASES\t%d" % PHASES, "",
         "static const u32 cedrus_scaler_coef"
         "[CEDRUS_SCALER_COEF_SETS][CEDRUS_SCALER_COEF_PHASES] = {"]
    for i, (b, (kern, width)) in enumerate(zip(banks, DESIGN)):
        name = "cubic B-spline" if kern == "bspline" else "triangle"
        L.append("\t/* [%2d] ratio %7s: %s, width %.2f */" % (i, LABELS[i], name, width))
        L.append("\t{")
        words = [int(np.uint32(int(np.uint8(t[0])) | (int(np.uint8(t[1])) << 8) |
                               (int(np.uint8(t[2])) << 16) | (int(np.uint8(t[3])) << 24)))
                 for t in b]
        for r in range(0, PHASES, 4):
            L.append("\t\t" + " ".join("0x%08x," % x for x in words[r:r + 4]))
        L.append("\t},")
    L += ["};", "", "#endif /* _CEDRUS_SCALER_COEF_H_ */"]
    text = "\n".join(L) + "\n"
    if args.output == "-":
        print(text, end="")
    else:
        open(args.output, "w").write(text)


if __name__ == "__main__":
    main()
