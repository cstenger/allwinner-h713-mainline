#!/usr/bin/env python3
"""Read fb-vsize's stripe geometry out of a capture.

fb-vsize paints four red/blue horizontal stripes of 180 rows, so boundaries sit
at 25%, 50% and 75% of the panel height. A register that carries vertical
geometry moves a boundary, truncates the pattern, or repeats it. This measures
those positions per frame so the five steps can be compared as numbers instead
of impressions.

Keystone makes the projected image a trapezoid, so positions are reported as a
fraction of the lit height rather than in pixels.
"""
import subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

VID = Path(sys.argv[1])
N = int(sys.argv[2]) if len(sys.argv) > 2 else 48


def frame(t, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(VID),
                    "-frames:v", "1", "-q:v", "2", str(dest), "-y"], check=True)


def analyse(p):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    lum = r.astype(np.int32) + g + b
    lit = lum > lum.max() * 0.35
    w = lit.sum(1)
    if w.max() < 200:
        return None
    rows = np.flatnonzero(w > 0.6 * w.max())
    if rows.size < 200:
        return None
    lo, hi = rows[0], rows[-1]
    h = hi - lo

    # Per-row redness, averaged across the lit part of that row only.
    redness = []
    for y in range(lo, hi + 1):
        cols = np.flatnonzero(lit[y])
        if cols.size < 50:
            redness.append(0.0)
            continue
        redness.append(float((r[y, cols] - b[y, cols]).mean()))
    redness = np.array(redness)

    # Smooth, then threshold about its own midpoint: absolute levels drift with
    # lamp falloff down the frame, the sign of the red/blue difference does not.
    k = 15
    sm = np.convolve(redness, np.ones(k) / k, mode="same")
    mid = (sm.max() + sm.min()) / 2.0
    sign = sm > mid

    edges = np.flatnonzero(np.diff(sign.astype(np.int8)) != 0)
    edges = [e for e in edges if 0.02 * h < e < 0.98 * h]      # ignore rim
    # merge edges closer than 2% of height (smoothing ripple)
    merged = []
    for e in edges:
        if not merged or e - merged[-1] > 0.02 * h:
            merged.append(e)
    return {
        "top_is_red": bool(sign[int(0.05 * h)]),
        "n_edges": len(merged),
        "edges_pct": [round(100.0 * e / h, 1) for e in merged],
        "contrast": float(sm.max() - sm.min()),
    }


dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of",
                            "default=noprint_wrappers=1:nokey=1", str(VID)],
                           capture_output=True, text=True).stdout)
print(f"{VID.name}: {dur:.1f}s, sampling {N} frames")
print(f"{'t(s)':>6} {'top':>5} {'edges':>5}  positions (% of lit height)")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td) / "f.jpg"
    for t in np.linspace(0.5, dur - 0.5, N):
        frame(t, tmp)
        res = analyse(tmp)
        if not res:
            print(f"{t:6.1f}   -- no lit image")
            continue
        print(f"{t:6.1f} {'RED' if res['top_is_red'] else 'BLUE':>5} "
              f"{res['n_edges']:>5}  {res['edges_pct']}"
              f"   contrast {res['contrast']:.0f}")
