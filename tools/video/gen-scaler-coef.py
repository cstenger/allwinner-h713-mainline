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
  1280x720 -> 640x360        55.45 dB  (vendor 41.87)
  1280x720 -> 320x180        45.01 dB  (vendor 32.76)
  1280x720 -> 640x180        47.85 dB  (vendor 36.55)
  Main10 640x480 -> 320x240  53.62 dB  (vendor 39.34)

For reference, H.264's own power-of-two shifter scores 46.10 dB on the first of
those and 46.42 dB on a 4x/4x, so this scaler is now ahead of it at 2x and
close at 4x, where 4 taps cannot cover the source footprint.
"""
import argparse
import numpy as np

TAPS, PHASES, UNIT = 4, 32, 128

# Upper bound of each set's downscale ratio, for the comment only.
LABELS = ["< 1.125", "< 1.25", "< 1.375", "< 1.5", "< 1.625", "< 1.75",
          "< 1.875", "< 2.0", "< 2.25", "< 2.5", "< 2.75", "< 3.0",
          "< 4.0", "< 5.0", ">= 5.0"]

# Phase 0 is a special case worth solving exactly.
#
# The V4L2 compose rectangle is quantised to a power-of-two ratio, and at an
# exact power of two the step is a whole multiple of 4096, so (pos >> 7) & 31
# is zero for EVERY output pixel: the 32-phase bank collapses to phase 0 alone.
# A kernel averaged over a ratio bucket is then the wrong answer to a question
# with an exact one, and it costs a lot -- 13 dB at 2x.
#
# A true delta would need a tap of 128, which does not fit in a signed byte, so
# 1x uses the closest representable approximation.
#
# These are the least-squares optimal taps for the exact ratio that selects
# each set, fitted against a bicubic rescale of decoded frames and renormalised
# to sum to 128.  Sets 0, 8, 13 and 14 are the ones an exact 1x, 2x, 4x and 8x
# select; the other sets keep their bucket-averaged phase 0, which is right for
# the non-power-of-two ratios they would serve.
#
# Measured on hardware, 1280x720 -> 640x360:  42.42 dB -> 55.45 dB
#                       1280x720 -> 320x180:  35.78 dB -> 45.01 dB
#                       1280x720 -> 640x180:  36.88 dB -> 47.85 dB
EXACT_PHASE0 = {0: (0, 127, 1, 0), 8: (9, 55, 55, 9),
                13: (10, 29, 32, 57), 14: (11, 30, 31, 56)}

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
    for i, taps in EXACT_PHASE0.items():
        banks[i][0] = np.array(taps, dtype=np.int32)
    for b in banks:
        assert all(row.sum() == UNIT for row in b), "phase does not sum to 128"
        assert b.min() >= -128 and b.max() <= 127, "tap outside signed 8-bit"

    L = ["/* SPDX-License-Identifier: GPL-2.0 */", "/*",
         " * Polyphase coefficients for the H713 video engine scaler at VE + 0xf00.",
         " *",
         " * 15 sets x 32 phases x 4 taps, signed 8-bit, each phase summing to 128.",
         " * A set is chosen by downscale ratio; phase p centres the kernel at tap",
         " * index 1 + p/32, with the taps landing on source pixels [ip-1 .. ip+2].",
         " *",
         " * GENERATED, NOT EXTRACTED -- do not hand-edit.",
         " *",
         " * Phase 0 of the sets an exact power-of-two ratio selects is solved for",
         " * that ratio rather than averaged over the set's range; at an exact power",
         " * of two the phase index is always 0, so that one kernel is the whole",
         " * filter.  See the generator.",
         " *",
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
