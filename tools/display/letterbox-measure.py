#!/usr/bin/env python3
"""Measure where a letterbox step put the picture, from a HANDHELD video.
Runs on the host.

    letterbox-measure.py VIDEO [--out DIR]           # the Phase 1 run: a, b, c
    letterbox-measure.py VIDEO c=852x480@214,120     # one step
    letterbox-measure.py --self-test
    letterbox-measure.py VIDEO --mirror --log mirror.log [--out DIR]   # WP5 Phase 1

MIRROR MODE (WP5, docs/mirror-plan.md). The card is nearly symmetric in luma
(circles, diagonals, ticks), so orientation comes from the corner patches'
COLOURS: TL red, TR green, BL blue, BR yellow on an upright card. A frame is
CONTROL only if it is also upright, so a full-panel mirrored step is a window.
A step whose bits change nothing on the glass leaves no window at all, so
windows are matched to steps by TIME, from the wall-clock stamps in the
executor's log (letterbox-test.sh mirror writes it), not by order; a step
with no window is reported as NO VISIBLE CHANGE -- itself a result.

WHY VIDEO, AND WHY IT NEEDS NO TRIPOD. Every Phase 1 step starts and ends on
the full-panel control card (letterbox-card), whose white frame IS the panel
edge. Film the whole step -- a few seconds of control card, the window, the
control card again -- and the frames either side of each transition are a
few tens of milliseconds apart: the hand has not moved. So each step frame is
rectified with the panel corners found in the control frame next to it, and
the picture's own white frame is measured in panel pixels. The step is
measured twice, from the first step frames (rectified with the control frame
before) and from the last ones (with the control frame after); their
disagreement is the error bar from hand motion. Black bars are never needed
for locating the panel.

Resolution about +-3 px in panel pixels (self-test). Reports, per side: the
picture rectangle (x, y, w, h) against the expected
one, MAGENTA pixels (the card's padding -- the display must never show it),
and the bar and card-grey brightness. Saves rectified PNGs of the control and
step frames to --out for a look.

Classification: a frame is CONTROL when, rectified on its own bright
quadrilateral, it correlates with a synthetic copy of the control card; it is
STEP when, rectified with the latest control homography, it correlates with
the expected step card better than with the control card.
"""
import argparse
import json
import os
import subprocess
import sys

import cv2
import numpy as np

PW, PH = 1280, 720
M = 16                   # margin around the panel when measuring, so lines on
                         # the panel's own edge are not clipped by the warp
ANALYSIS_W = 1920        # decode width; iPhone 4K is downscaled to this


# --- the card, as letterbox-card.c draws it (luma only) ----------------------

def card_luma(w, h):
    y, x = np.mgrid[0:h, 0:w]
    out = np.full((h, w), 100, np.uint8)
    m = min(w, h)
    r, rc = m * 2 // 5, m // 10
    out[(x == w // 2) | (x == w // 2 - 1) | (y == h // 2) | (y == h // 2 - 1)] = 235
    diag = (np.abs(x * h - y * w) < w * 3 // 2) | (np.abs((w - 1 - x) * h - y * w) < w * 3 // 2)
    out[diag] = 235

    def ring(cx, cy, rr, t):
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        return (d2 >= (rr - t) ** 2) & (d2 <= rr * rr)
    circ = (ring(w // 2, h // 2, r, 3) | ring(rc + 100, rc + 100, rc, 2) |
            ring(w - rc - 100, rc + 100, rc, 2) | ring(rc + 100, h - rc - 100, rc, 2) |
            ring(w - rc - 100, h - rc - 100, rc, 2))
    out[circ] = 235
    top, bot = (y >= 40) & (y < 88), (y >= h - 88) & (y < h - 40)
    lft, rgt = (x >= 40) & (x < 88), (x >= w - 88) & (x < w - 40)
    out[top & lft], out[top & rgt], out[bot & lft], out[bot & rgt] = 81, 145, 41, 210
    ticks = (((x % 64 < 2) & ((y < 28) | (y >= h - 28))) |
             ((x % 16 < 2) & ((y < 14) | (y >= h - 14))) |
             ((y % 64 < 2) & ((x < 28) | (x >= w - 28))) |
             ((y % 16 < 2) & ((x < 14) | (x >= w - 14))))
    out[ticks] = 235
    out[(x < 4) | (y < 4) | (x >= w - 4) | (y >= h - 4)] = 16
    out[(x < 2) | (y < 2) | (x >= w - 2) | (y >= h - 2)] = 235
    return out


def step_panel(w, h, dx, dy, bar=16):
    p = np.full((PH, PW), bar, np.uint8)
    p[dy:dy + h, dx:dx + w] = card_luma(w, h)
    return p


# --- orientation, from the chroma patches (letterbox-card.c colour_at) -------

PATCH_BGR = {"red": (0, 0, 255), "green": (0, 255, 0), "blue": (255, 0, 0),
             "yellow": (0, 255, 255)}
UPRIGHT = ("red", "green", "blue", "yellow")          # TL, TR, BL, BR
ORIENTS = {"": UPRIGHT,
           "x": ("green", "red", "yellow", "blue"),    # left/right swapped
           "y": ("blue", "yellow", "red", "green"),    # top/bottom swapped
           "xy": ("yellow", "blue", "green", "red")}   # rotated 180


def card_bgr(w, h, orient=""):
    """The card in colour (patches coloured), optionally mirrored."""
    out = cv2.cvtColor(card_luma(w, h), cv2.COLOR_GRAY2BGR)
    for (x0, y0), c in zip(((40, 40), (w - 88, 40), (40, h - 88), (w - 88, h - 88)), UPRIGHT):
        out[y0:y0 + 48, x0:x0 + 48] = PATCH_BGR[c]
    if "x" in orient:
        out = out[:, ::-1]
    if "y" in orient:
        out = out[::-1]
    return np.ascontiguousarray(out)


def step_panel_bgr(w, h, dx, dy, orient="", bar=16):
    p = np.full((PH, PW, 3), bar, np.uint8)
    p[dy:dy + h, dx:dx + w] = card_bgr(w, h, orient)
    return p


def patch_colour(bgr):
    """Name the patch colour of a small BGR box by hue, or None."""
    hsv = cv2.cvtColor(bgr.reshape(1, -1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    sat = hsv[:, 1] > 70
    if sat.mean() < 0.5:
        return None
    hue = np.median(hsv[sat, 0])           # OpenCV hue, 0..180
    if hue < 12 or hue >= 160:
        return "red"
    if 18 <= hue < 42:
        return "yellow"
    if 45 <= hue < 90:
        return "green"
    if 95 <= hue < 140:
        return "blue"
    return None


def orientation(bgr, rect):
    """Orientation of the card whose picture is `rect` (x, y, w, h) in `bgr`:
    '', 'x', 'y' or 'xy', or None if the four patches do not read as one."""
    x, y, w, h = (int(round(v)) for v in rect)
    seen = []
    for cx, cy in ((x + 64, y + 64), (x + w - 64, y + 64),
                   (x + 64, y + h - 64), (x + w - 64, y + h - 64)):
        box = bgr[max(cy - 10, 0):cy + 10, max(cx - 10, 0):cx + 10]
        seen.append(patch_colour(box) if box.size else None)
    # Three of four is enough when only one orientation fits: a projector's
    # falloff can leave one corner patch too dim to name (2026-10-06, pv).
    fits = [name for name, want in ORIENTS.items()
            if sum(s == c for s, c in zip(seen, want)) >= 3
            and all(s in (None, c) for s, c in zip(seen, want))]
    return (fits[0] if len(fits) == 1 else None), seen


# --- geometry -----------------------------------------------------------------

def order_corners(pts):
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def bright_quad(grey):
    g = cv2.GaussianBlur(grey, (7, 7), 0)
    _, mask = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.02 * grey.size:
        return None
    peri = cv2.arcLength(c, True)
    for frac in np.arange(0.005, 0.10, 0.005):
        a = cv2.approxPolyDP(c, frac * peri, True)
        if len(a) == 4:
            return refine(grey, order_corners(a.reshape(4, 2).astype(np.float32)))
    return None


def refine(grey, quad):
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01)
    q = quad.reshape(-1, 1, 2).copy()
    cv2.cornerSubPix(grey, q, (7, 7), (-1, -1), crit)
    return q.reshape(4, 2)


def homography(quad):
    dst = np.array([[0, 0], [PW, 0], [PW, PH], [0, PH]], np.float32)
    return cv2.getPerspectiveTransform(quad, dst)


def _highpass(a):
    a = cv2.resize(a, (640, 360), interpolation=cv2.INTER_AREA).astype(np.float32)
    a = cv2.GaussianBlur(a, (0, 0), 1.5)
    return a - cv2.GaussianBlur(a, (0, 0), 12)


def ncc(a, b):
    """Correlation of LINE STRUCTURE only. A real projector falls off in
    brightness toward its edges; a plain correlation is dominated by that
    gradient and scored the real control card 0.29 (2026-10-04 video).
    High-passed, it scores 0.81."""
    a, b = _highpass(a), _highpass(b)
    a -= a.mean()
    b -= b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den else 0.0


def picture_rect(grey_rect, ref_white):
    """Outer edges of the picture's white frame, in canvas pixels.

    Coarse: the outermost lines of a lightly smoothed white-pixel profile.
    Fine: along each edge, per row (or column) in its middle 60%, the
    half-maximum crossing on the line's OUTER flank; the median of those.
    Pixel i covers [i, i+1), so a hard edge at x0 measures x0. Per-line
    crossings and a median make this insensitive to the pixel or two of tilt
    a handheld homography leaves.
    """
    g = grey_rect.astype(np.float32)
    white = g > ref_white * 0.6
    k = np.ones(7) / 7

    def coarse(prof):
        sm = np.convolve(prof, k, mode="same")
        hi = np.nonzero(sm >= 0.4 * sm.max())[0]
        return (int(hi[0]), int(hi[-1])) if hi.size >= 2 else None
    xs, ys = coarse(white.sum(axis=0)), coarse(white.sum(axis=1))
    if xs is None or ys is None:
        return None

    def crossing(line, c, outward):
        lo, hi = max(c - 8, 1), min(c + 9, len(line) - 1)
        seg = line[lo:hi]
        bg, pk = float(seg.min()), float(seg.max())
        if pk - bg < 20:
            return None
        thr = 0.5 * (bg + pk)
        if outward < 0:                       # left/top: first sample above thr
            idx = np.nonzero(seg >= thr)[0]
            if not idx.size or lo + idx[0] == 0:
                return None
            j = lo + idx[0]
            return (j - 0.5) + (thr - line[j - 1]) / max(line[j] - line[j - 1], 1e-6)
        idx = np.nonzero(seg >= thr)[0]       # right/bottom: last sample above thr
        if not idx.size or lo + idx[-1] + 1 >= len(line):
            return None
        j = lo + idx[-1]
        return (j + 0.5) + (line[j] - thr) / max(line[j] - line[j + 1], 1e-6)

    def median_edge(c, outward, along, span):
        vals = []
        a0, a1 = span
        for t in range(int(a0 + 0.2 * (a1 - a0)), int(a1 - 0.2 * (a1 - a0))):
            line = g[t, :] if along == "rows" else g[:, t]
            v = crossing(line, c, outward)
            if v is not None:
                vals.append(v)
        return float(np.median(vals)) if len(vals) > 10 else None

    left = median_edge(xs[0], -1, "rows", ys)
    right = median_edge(xs[1], +1, "rows", ys)
    top = median_edge(ys[0], -1, "cols", xs)
    bottom = median_edge(ys[1], +1, "cols", xs)
    if None in (left, right, top, bottom):
        return None
    return left, top, right - left, bottom - top


def magenta(bgr_rect):
    hsv = cv2.cvtColor(bgr_rect, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] >= 140) & (hsv[..., 0] <= 165) & (hsv[..., 1] > 90) & (hsv[..., 2] > 60)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n = int(m.sum())
    if not n:
        return 0, None
    ys, xs = np.nonzero(m)
    return n, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


# --- video --------------------------------------------------------------------

def frames(path):
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,avg_frame_rate:stream_side_data=rotation",
         "-of", "json", path], capture_output=True, text=True, check=True).stdout)
    st = probe["streams"][0]
    w, h = st["width"], st["height"]
    rot = 0
    for sd in st.get("side_data_list", []):
        rot = int(sd.get("rotation", 0))
    if rot % 180:
        w, h = h, w
    ow = ANALYSIS_W if w >= h else ANALYSIS_W * w // h
    oh = (h * ow // w) & ~1
    num, den = (int(v) for v in st["avg_frame_rate"].split("/"))
    fps = num / den if den else 30.0
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={ow}:{oh}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    n = 0
    while True:
        buf = p.stdout.read(ow * oh * 3)
        if len(buf) < ow * oh * 3:
            break
        yield n / fps, np.frombuffer(buf, np.uint8).reshape(oh, ow, 3)
        n += 1
    p.wait()


PHASE1 = "a=1280x536@0,0 b=1280x536@0,92 c=852x480@214,120"
STEP_ORIENT = {}


def log_windows(path):
    """{step name: wall-clock time its window opened}, from letterbox-apply's log."""
    out = {}
    for line in open(path):
        if "WINDOW OPEN: step" in line and " wall " in line:
            name = line.split("WINDOW OPEN: step", 1)[1].split()[0]
            out[name] = float(line.rsplit(" wall ", 1)[1].split()[0])
    return out


def assign_by_time(run_times, steps, opens, slack=2.5):
    """Match windows (video times) to steps (board wall times) under the one
    clock offset that explains the most windows. -> {step index: run index}."""
    names = [s[0] for s in steps]
    want = [(i, opens[n]) for i, n in enumerate(names) if n in opens]
    best = {}
    for ri, rt in enumerate(run_times):
        for si, wt in want:
            shift = rt - wt
            m = {}
            for sj, wt2 in want:
                cands = [(abs(rt2 - (wt2 + shift)), rj) for rj, rt2 in enumerate(run_times)
                         if abs(rt2 - (wt2 + shift)) <= slack]
                if cands:
                    m[sj] = min(cands)[1]
            if len(m) > len(best):
                best = m
    return best


# What each mirror step should show, in panel coordinates as seen on the glass
# (letterbox-test.sh mirror). p* are the primary-route hypotheses: a
# mismatch or NO VISIBLE CHANGE there is the finding, not a tool failure.
MIRROR = ("h=1280x720@0,0:x v=1280x720@0,0:y hv=1280x720@0,0:xy "
          "ch=852x480@428,0:x abv=1280x536@0,184:y "
          "pv=1280x720@0,0:y php=1280x720@0,0:x pho=1280x720@0,0:x")


def parse_steps(specs):
    """'name=WxH@X,Y[:x|y|xy]' (name optional) -> [(name, w, h, dx, dy)].
    The orientation, when given, goes to STEP_ORIENT[name]."""
    out = []
    for i, spec in enumerate(specs):
        name, _, geo = spec.rpartition("=")
        geo, _, orient = geo.partition(":")
        STEP_ORIENT[name or f"step{i + 1}"] = orient if orient in ORIENTS else ""
        size, at = geo.split("@")
        w, h = (int(v) for v in size.lower().split("x"))
        dx, dy = (int(v) for v in at.split(","))
        out.append((name or f"step{i + 1}", w, h, dx, dy))
    return out


def analyse(path, steps, outdir=None, verbose=True, dump=False, min_run_s=2.0,
            opens=None, mirror=False):
    """Measure every step window in one video.

    Frames are CONTROL (the full-panel card) or not. Windows are the runs of
    non-control frames at least min_run_s long, taken IN ORDER as the expected
    steps -- not by best template match, which would quietly measure a
    misplaced step b as a perfect step a. Each run is measured against its own
    expected rectangle, rectified on the control frame just before it and
    just after it.
    """
    native_t = card_luma(PW, PH)
    temps = [step_panel(w, h, dx, dy) for _, w, h, dx, dy in steps]
    seq = []            # (t, is_control, H_or_None, frame, best_step_index)
    last_h, last_area = None, None
    fps = None
    for n, (t, bgr) in enumerate(frames(path)):
        if n == 1:
            fps = 1.0 / t if t else 30.0
        grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        s_nat, s_steps = -1.0, [-1.0] * len(temps)
        if last_h is not None:
            r = cv2.warpPerspective(grey, last_h, (PW, PH))
            s_nat, s_steps = ncc(r, native_t), [ncc(r, tt) for tt in temps]
        q = bright_quad(grey)
        # CONTROL is decided from the frame alone, never from an older
        # homography (a 10-s window's worth of hand drift spoils that). The
        # bright outline must be the whole panel -- with black bars a step
        # frame's outline is just its picture, smaller -- and the frame,
        # rectified on it, must match the control card better than any step.
        control, hm = False, None
        if q is not None:
            area = cv2.contourArea(q.reshape(-1, 1, 2))
            own = cv2.warpPerspective(grey, homography(q), (PW, PH))
            s_own = ncc(own, native_t)
            # Full-panel step templates ARE the control card in luma (mirror
            # steps differ only in patch colour): orientation decides those.
            rivals = [ncc(own, tt) for tt, st in zip(temps, steps)
                      if (st[1], st[2], st[3], st[4]) != (PW, PH, 0, 0)]
            if (s_own > 0.55 and s_own > max(rivals, default=-1.0) + 0.05
                    and (last_area is None or area >= 0.9 * last_area)):
                # mirror mode: a full-panel card is CONTROL only if upright
                if mirror and orientation(cv2.warpPerspective(bgr, homography(q), (PW, PH)),
                                          (0, 0, PW, PH))[0] != "":
                    pass
                else:
                    control, hm = True, homography(q)
                    last_h, last_area = hm, area
        best = int(np.argmax(s_steps)) if s_steps and max(s_steps) > 0.45 else -1
        if dump and last_h is not None and n % 15 == 0:
            os.makedirs(outdir, exist_ok=True)
            tag = "control" if control else steps[best][0] if best >= 0 else "other"
            cv2.imwrite(os.path.join(outdir, f"frame-{t:07.2f}-{tag}.png"),
                        cv2.warpPerspective(bgr, last_h, (PW, PH)))
        seq.append((t, control, hm, bgr, best))
    fps = fps or 30.0
    if verbose:
        marks = "".join("C" if c else (steps[b][0][0] if b >= 0 else ".")
                        for _, c, _, _, b in seq)
        print(f"{len(seq)} frames at {fps:.1f} fps (C control, letter = best-matching "
              f"step template, . neither):")
        for i in range(0, len(marks), 120):
            print("  " + marks[i:i + 120])

    runs, i = [], 0
    while i < len(seq):
        if seq[i][1]:
            i += 1
            continue
        j = i
        while j < len(seq) and not seq[j][1]:
            j += 1
        # A window needs control frames on BOTH sides; runs touching the
        # start or end of the recording (walking up, the console after) are not.
        if (j - i) / fps >= min_run_s and i > 0 and j < len(seq):
            runs.append((i, j))          # frames i .. j-1
        i = j
    if opens:
        amap = assign_by_time([seq[r0][0] for r0, _ in runs], steps, opens)
        pairs = []
        for si, st in enumerate(steps):
            if si in amap:
                pairs.append((st, runs[amap[si]]))
            elif st[0] in opens:
                print(f"step {st[0]}: NO VISIBLE CHANGE (no window at its log time)")
        spare = sorted(set(range(len(runs))) - set(amap.values()))
        for ri in spare:
            print(f"  unassigned window {seq[runs[ri][0]][0]:.2f}-{seq[runs[ri][1] - 1][0]:.2f} s "
                  "(e.g. the holder switch)")
    else:
        if len(runs) != len(steps):
            print(f"*** found {len(runs)} window(s) of >= {min_run_s:g} s, expected "
                  f"{len(steps)}: measuring the first {min(len(runs), len(steps))} in order")
        pairs = list(zip(steps, runs))

    T = np.array([[1, 0, M], [0, 1, M], [0, 0, 1]], np.float64)
    CW, CH = PW + 2 * M, PH + 2 * M

    def warp(img, hm):
        return cv2.warpPerspective(img, T @ hm, (CW, CH))

    results = {}
    for (name, w, h, dx, dy), (r0, r1) in pairs:
        frames_in = list(range(r0, r1))
        votes = [seq[k][4] for k in frames_in]
        looks = max(set(votes), key=votes.count)
        looks_name = steps[looks][0] if looks >= 0 else "none"
        if verbose:
            print(f"step {name}: {seq[r0][0]:.2f}-{seq[r1 - 1][0]:.2f} s, "
                  f"expect {w}x{h} at ({dx},{dy}); frames look most like: {looks_name}"
                  + ("" if looks_name == name else "   *** NOT the expected template"))
        before = [k for k in range(r0 - 1, -1, -1) if seq[k][1]][:1]
        after = [k for k in range(r1, len(seq)) if seq[k][1]][:1]
        res = {"looks_like": looks_name}
        # Nearest usable step frames: skip the switch frame itself (it can be
        # mid-transition), stay close to the control frame (less hand drift).
        for side, ctl, picks in (("before", before, frames_in[1:5] or frames_in[:3]),
                                 ("after", after, frames_in[-5:-1] or frames_in[-3:])):
            if not ctl:
                print(f"  {side}: no control frame on this side")
                continue
            hm = seq[ctl[0]][2]
            cgrey = warp(cv2.cvtColor(seq[ctl[0]][3], cv2.COLOR_BGR2GRAY), hm)
            ref_white = np.percentile(cgrey, 99.5)
            grey_level = np.median(cgrey[M + 200:M + 520, M + 300:M + 980])
            # Calibration: the control card's own frame IS the panel edge, so
            # the same edge measurement must give (0, 0, PW, PH) on it. What it
            # gives instead is this camera's bias (outline threshold vs line
            # half-maximum, blur), removed from the step measurement below.
            cr = picture_rect(cgrey, ref_white)
            bias = (cr[0] - M, cr[1] - M, cr[2] - PW, cr[3] - PH) if cr else (0, 0, 0, 0)
            if max(abs(b) for b in bias) > 6:
                # A real projector's falloff can defeat the edge finder at the
                # panel border (2026-10-04 footage gave biases of hundreds of
                # px); an implausible calibration is dropped, not applied.
                print(f"  {side}: control-frame calibration implausible {tuple(round(b) for b in bias)}, not applied")
                bias = (0, 0, 0, 0)
            rects, mags, orients = [], [], []
            for k in picks:
                bgr_r = warp(seq[k][3], hm)
                g = cv2.cvtColor(bgr_r, cv2.COLOR_BGR2GRAY)
                rr = picture_rect(g, ref_white)
                if rr:
                    rects.append((rr[0] - M, rr[1] - M, rr[2], rr[3]))
                # Patches are read at the EXPECTED rectangle: on real footage
                # the edge finder loses the far edges (projector falloff; the
                # 2026-10-06 run measured a 1280-wide card 717-910 wide), and
                # sampling relative to those edges missed every patch.
                orients.append(orientation(bgr_r, (dx + M, dy + M, w, h)))
                mags.append(magenta(bgr_r))
                last = (bgr_r, g)
            if outdir:
                os.makedirs(outdir, exist_ok=True)
                cv2.imwrite(os.path.join(outdir, f"{name}-{side}-control.png"),
                            warp(seq[ctl[0]][3], hm))
                cv2.imwrite(os.path.join(outdir, f"{name}-{side}-step.png"), last[0])
            if not rects:
                print(f"  {side}: picture frame not found (see {name}-{side}-step.png)")
                continue
            x, y, rw, rh = np.median(np.array(rects), axis=0) - np.array(bias)
            g = last[1][M:M + PH, M:M + PW]
            bars = np.ones_like(g, bool)
            bars[max(0, int(y) - 8):int(y + rh) + 8, max(0, int(x) - 8):int(x + rw) + 8] = False
            bar_level = float(np.median(g[bars])) if bars.any() else float("nan")
            n_mag, box = max(mags, key=lambda m: m[0])
            err = (x - dx, y - dy, rw - w, rh - h)
            names = [o[0] for o in orients]
            orient = max(set(names), key=names.count) if names else None
            res[side] = dict(x=x, y=y, w=rw, h=rh, err=err, bias=bias, bar=bar_level,
                             grey=float(grey_level), magenta=n_mag, magenta_box=box,
                             orient=orient, patches=orients[0][1] if orients else None)
            if verbose:
                flag = "" if max(abs(e) for e in err) <= TOL else "   *** OFF"
                print(f"  {side:6}: picture x {x:7.1f} y {y:6.1f} w {rw:7.1f} h {rh:6.1f}"
                      f"   error {err[0]:+.1f} {err[1]:+.1f} {err[2]:+.1f} {err[3]:+.1f} px{flag}")
                print(f"          bias removed {bias[0]:+.1f} {bias[1]:+.1f} {bias[2]:+.1f} {bias[3]:+.1f}; "
                      f"bars {bar_level:.0f} vs card grey {grey_level:.0f} "
                      f"(control white {ref_white:.0f}); magenta {n_mag} px"
                      + (f" in {box}" if box else ""))
                if mirror or STEP_ORIENT.get(name):
                    want = STEP_ORIENT.get(name, "")
                    got = res[side]["orient"]
                    print(f"          orientation {got if got else 'upright' if got == '' else 'UNREAD'}"
                          f" (expected {want or 'upright'}); patches TL/TR/BL/BR "
                          f"{res[side]['patches']}"
                          + ("" if got == want else "   *** ORIENTATION DIFFERS"))
        results[name] = res
    if verbose and outdir:
        print(f"rectified frames in {outdir}")
    return results


# --- self-test: a synthetic handheld video with known placement ----------------

# Resolution, from the self-test: the edge measurement's own bias is
# calibrated out on each control frame; what is left is hand drift between
# the control frame and the step frames next to it. Enough to tell a correct
# placement from a wrong one; not enough to resolve a 1-px offset.
TOL = 3.0


def synth(path, segments, rng, fw=1920, fh=1080):
    """A handheld-looking video: segments of (panel image, frames), with drift."""
    base = np.array([[290, 190], [1650, 230], [1600, 960], [330, 900]], np.float32)
    src = np.array([[0, 0], [PW, 0], [PW, PH], [0, PH]], np.float32)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (fw, fh))
    drift = np.zeros((4, 2), np.float32)
    for img, count in segments:
        for _ in range(count):
            drift += rng.normal(0, 0.6, (4, 2)).astype(np.float32)   # hand wobble
            m = cv2.getPerspectiveTransform(src, base + drift)
            cam = cv2.warpPerspective(img, m, (fw, fh), borderValue=(8, 8, 8))
            cam = cv2.GaussianBlur(cam, (3, 3), 0)
            cam = np.clip(cam.astype(np.float32) * 0.9 + rng.normal(0, 3, cam.shape),
                          0, 255).astype(np.uint8)
            writer.write(cam if cam.ndim == 3 else cv2.cvtColor(cam, cv2.COLOR_GRAY2BGR))
    writer.release()


def self_test(tmp="/tmp/letterbox-measure-selftest"):
    os.makedirs(tmp, exist_ok=True)
    rng = np.random.default_rng(7)
    steps = parse_steps(PHASE1.split())
    native, blank = card_luma(PW, PH), np.full((PH, PW), 16, np.uint8)
    ok = True

    def check(label, results, want_ok):
        nonlocal ok
        for name, *_ in steps:
            for side in ("before", "after"):
                e = results.get(name, {}).get(side, {}).get("err")
                good = bool(e) and max(abs(v) for v in e) <= TOL
                if good != want_ok:
                    ok = False
                print(f"self-test {label} {name} {side}: "
                      + (f"error {e[0]:+.2f} {e[1]:+.2f} {e[2]:+.2f} {e[3]:+.2f} px" if e else "NOT MEASURED")
                      + ("" if good == want_ok else "   *** FAIL"))

    # The Phase 1 run as one video: lead, z (a blink), a, gap, b, gap, c, tail.
    segs = [(native, 60), (blank, 1), (native, 150)]
    for _, w, h, dx, dy in steps:
        segs += [(blank, 1), (step_panel(w, h, dx, dy, bar=20), 300), (blank, 1), (native, 150)]
    vid = os.path.join(tmp, "phase1.mp4")
    synth(vid, segs, rng)
    check("sequence", analyse(vid, steps, verbose=False), True)

    # A misplaced step b (offset ignored: picture at y=0) must be reported OFF,
    # not matched to a's template and passed.
    segs = [(native, 60)]
    for name, w, h, dx, dy in steps:
        if name == "b":
            dy = 0
        segs += [(blank, 1), (step_panel(w, h, dx, dy, bar=20), 300), (blank, 1), (native, 150)]
    vid = os.path.join(tmp, "misplaced-b.mp4")
    synth(vid, segs, rng)
    r = analyse(vid, steps, verbose=False)
    eb = [r.get("b", {}).get(s, {}).get("err") for s in ("before", "after")]
    caught = all(e and abs(e[1] + 92) <= TOL for e in eb)
    ok &= caught
    print("self-test misplaced b " + ("reported y error -92 on both sides" if caught
                                      else f"*** NOT caught: {eb}"))
    ok &= mirror_self_test(tmp, rng)
    print("self-test", "PASS" if ok else "FAIL")
    return ok


def mirror_self_test(tmp, rng):
    """A synthetic mirror session: every step at its expected place and
    orientation, except pho, which changes nothing (no window). Windows are
    found by the log's times under an unknown clock offset, with the holder
    switch (a dark console) as an extra, unassigned window."""
    ok = True
    steps = parse_steps(MIRROR.split())
    native = card_bgr(PW, PH)
    dark = np.full((PH, PW, 3), 12, np.uint8)
    segs, t, opens, wall0 = [(native, 90)], 3.0, {}, 1000.0
    for name, w, h, dx, dy in steps:
        if name == "pv":                     # the holder switch: 4 s of console
            segs += [(dark, 120), (native, 60)]
            t += 6.0
        img = native if name == "pho" else step_panel_bgr(w, h, dx, dy, STEP_ORIENT[name])
        opens[name] = wall0 + t
        segs += [(img, 150), (native, 75)]
        t += 7.5
    vid = os.path.join(tmp, "mirror.mp4")
    synth(vid, segs, rng)
    r = analyse(vid, steps, verbose=False, opens=opens, mirror=True)
    for name, *_ in steps:
        if name == "pho":
            good = name not in r
            print(f"self-test mirror pho: " + ("no window, as built" if good else "*** got a window"))
            ok &= good
            continue
        for side in ("before", "after"):
            d = r.get(name, {}).get(side, {})
            e, o = d.get("err"), d.get("orient")
            good = bool(e) and max(abs(v) for v in e) <= TOL and o == STEP_ORIENT[name]
            ok &= good
            print(f"self-test mirror {name} {side}: orient {o!r} (want {STEP_ORIENT[name]!r}), "
                  + (f"error {e[0]:+.1f} {e[1]:+.1f} {e[2]:+.1f} {e[3]:+.1f}" if e else "NOT MEASURED")
                  + ("" if good else "   *** FAIL"))
    # A wrong expectation must be caught: say v was expected to swap left/right.
    if r.get("v", {}).get("before", {}).get("orient") == "x":
        ok = False
        print("self-test mirror: *** v read as 'x' -- a wrong expectation would pass")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", nargs="?")
    ap.add_argument("steps", nargs="*",
                    help=f"expected windows in order, name=WxH@X,Y (default: {PHASE1})")
    ap.add_argument("--out", help="directory for rectified frames")
    ap.add_argument("--dump", action="store_true",
                    help="also save every 15th frame, rectified, to --out")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--mirror", action="store_true",
                    help=f"WP5 Phase 1: orientation-aware control frames; default steps {MIRROR}")
    ap.add_argument("--log", help="letterbox-apply log with 'WINDOW OPEN ... wall T' stamps: "
                                  "windows are matched to steps by time (needed with --mirror)")
    a = ap.parse_args()
    if a.self_test:
        return 0 if self_test() else 1
    if not a.video:
        ap.error("VIDEO [name=WxH@X,Y ...], or --self-test")
    if a.dump and not a.out:
        ap.error("--dump needs --out")
    if a.mirror and not a.log:
        ap.error("--mirror needs --log (steps with no visible effect leave no window)")
    steps = parse_steps(a.steps or (MIRROR if a.mirror else PHASE1).split())
    opens = log_windows(a.log) if a.log else None
    return 0 if analyse(a.video, steps, a.out, dump=a.dump, opens=opens,
                        mirror=a.mirror) else 1


if __name__ == "__main__":
    sys.exit(main())
