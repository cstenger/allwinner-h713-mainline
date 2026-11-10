#!/usr/bin/env python3
"""Generate a diagnostic test card for measuring the H713 scaler at 0x05180000.

VECTOR SOURCE, RASTERISED PER TARGET. The card is emitted as SVG and then
rasterised at the requested resolution. That is not tidiness -- the goal of this
whole exercise is 1920x1080 -> 1280x720, so a 1080p card has to be pixel-exact at
1080p. Rasterising once at 720p and upscaling would fold MY resampling blur into
the image, and the card is partly meant to measure the scaler's own filtering.
One vector source, rasterised natively at each size, keeps those separate.

WHY A CARD AT ALL. Every scaler measurement so far has been taken against
leota-av-720p.mp4 -- a moving face on a dark field with no reference marks. That
clip actively fights the measurement:

  * it MOVES, so any apparent change must be separated from content drift;
  * it is mostly DARK, so magnifying into a quiet passage yields a flat grey
    field and reads as "nothing" -- exactly what made steps 3 and 4 of the
    2026-09-11 ratio ramp unreadable;
  * it has no scale reference, so the horizontal factor had to be estimated from
    the width of a face and the width of an eye slit;
  * it has no edges of its own, so clipping stayed invisible until someone
    thought to look for a straight boundary at full resolution;
  * it runs 77 s and mpv free-runs at ~2.5x, leaving a ~31 s usable window.

A static, full-brightness, self-describing card fixes all of those, and
`decd-client show FRAME.nv12 <dwell-ms>` holds it indefinitely with no decoder
in the loop at all.

WHAT EACH ELEMENT IS FOR

  border, all four edges
      THE CLIPPING GAUGE. A missing edge means the output is clipped on that
      side. All four present means nothing is being cut.

  corner markers, each one different
      Orientation, mirroring, offset. TL solid square, TR three vertical bars,
      BL two horizontal bars, BR a wedge. Any flip or wrap is unmistakable.

  top and left tick rulers, 8 ticks per band
      Direct read-off of the horizontal and vertical factors, independently.
      The reading rule is proportional and so resolution-independent: 8 ticks
      per band, 10 bands across, 5 bands down, at every card size.

  column digits 0-9 / row digits 0-4
      WHICH SOURCE REGION SURVIVES. A clipped fragment now says where it came
      from -- the thing we could not tell from a piece of a cheek.

  circle row, with crosshairs
      THE ASPECT GAUGE, and the best single element. Anisotropic scaling turns a
      circle into an ellipse and the axis ratio IS the H:V factor -- no baseline
      comparison, no content drift to argue about. Five across the width also
      expose non-uniform scaling along a line.

  frequency blocks, periods 24/16/12/8/6/4/3/2 px
      The one element deliberately in ABSOLUTE pixels, because that is the
      point: a real polyphase filter takes the fine blocks smoothly to grey, a
      point sampler produces moire. Tick marks under each block count its index
      so a surviving block can be named.

  luma staircase, 16 steps
      Confirms the luma path and gain are NOT being disturbed, so a brightness
      change cannot be mistaken for a geometry change.

  resolution stamp
      The card says its own size, so a photograph of the panel identifies which
      card was loaded.

Monochrome on purpose: NV12 chroma is half-resolution and a colour pattern would
add its own artefacts to a measurement about geometry. UV is written neutral.

    make-scaler-testcard.py OUTDIR [--size 1280x720] [--size 1920x1080]

writes, per size:  scaler-testcard-WxH.svg    the vector source
                   scaler-testcard-WxH.png    reference for measurement
                   scaler-testcard-WxH.nv12   for `decd-client show`
"""
import argparse
import os
import shutil
import subprocess
import sys

BLACK, DARK, MID, WHITE = 16, 60, 128, 235

# 7-segment digits as rectangles: no font dependency, and chunky strokes stay
# legible when the card is squashed to a quarter of its width.
SEGMENTS = {
    "0": (1, 1, 1, 0, 1, 1, 1), "1": (0, 0, 1, 0, 0, 1, 0),
    "2": (1, 0, 1, 1, 1, 0, 1), "3": (1, 0, 1, 1, 0, 1, 1),
    "4": (0, 1, 1, 1, 0, 1, 0), "5": (1, 1, 0, 1, 0, 1, 1),
    "6": (1, 1, 0, 1, 1, 1, 1), "7": (1, 0, 1, 0, 0, 1, 0),
    "8": (1, 1, 1, 1, 1, 1, 1), "9": (1, 1, 1, 1, 0, 1, 1),
}


def grey(v):
    return f"#{v:02x}{v:02x}{v:02x}"


class Svg:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []

    def rect(self, x, y, w, h, fill=WHITE):
        if w <= 0 or h <= 0:
            return
        self.parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{grey(fill)}"/>')

    def frame(self, x, y, w, h, stroke, sw):
        self.parts.append(
            f'<rect x="{x + sw / 2:.2f}" y="{y + sw / 2:.2f}" '
            f'width="{w - sw:.2f}" height="{h - sw:.2f}" fill="none" '
            f'stroke="{grey(stroke)}" stroke-width="{sw:.2f}"/>')

    def circle(self, cx, cy, r, sw):
        self.parts.append(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="none" '
            f'stroke="{grey(WHITE)}" stroke-width="{sw:.2f}"/>')

    def line(self, x1, y1, x2, y2, sw, col=MID):
        self.parts.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{grey(col)}" stroke-width="{sw:.2f}"/>')

    def poly(self, pts):
        s = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        self.parts.append(f'<polygon points="{s}" fill="{grey(WHITE)}"/>')

    def digit(self, x, y, w, h, ch, t):
        top, tl, tr, mid, bl, br, bot = SEGMENTS[ch]
        half = h / 2
        for on, box in (
            (top, (x, y, w, t)), (mid, (x, y + half - t / 2, w, t)),
            (bot, (x, y + h - t, w, t)), (tl, (x, y, t, half)),
            (tr, (x + w - t, y, t, half)), (bl, (x, y + half, t, half)),
            (br, (x + w - t, y + half, t, half)),
        ):
            if on:
                self.rect(*box)

    def number(self, x, y, w, h, text, t, gap):
        for i, ch in enumerate(text):
            if ch == "x":
                self.rect(x + i * (w + gap) + w * 0.2, y + h / 2 - t / 2,
                          w * 0.6, t)
            else:
                self.digit(x + i * (w + gap), y, w, h, ch, t)

    def render(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
                f'height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
                f'<rect width="{self.w}" height="{self.h}" fill="{grey(DARK)}"/>'
                + "".join(self.parts) + "</svg>")


def build(w, h):
    s = Svg(w, h)
    sc = h / 720.0                     # layout scale; 1.0 at 720p
    band_w, band_h = w / 10.0, h / 5.0   # always 10 columns, 5 rows
    tick = band_w / 8.0                  # always 8 ticks per band
    bw = max(2.0, round(6 * sc))        # border weight
    left = round(120 * sc)              # content left margin
    right = w - round(10 * sc)

    s.frame(0, 0, w, h, WHITE, bw)

    # corner markers
    m = round(48 * sc)
    o = round(10 * sc)
    s.rect(o, o, m, m)
    for i in range(3):
        s.rect(w - o - m + i * (m / 2.7), o, m / 4.5, m)
    for i in range(2):
        s.rect(o, h - o - m + i * (m / 1.85), m, m / 3.4)
    s.poly([(w - o - m, h - o), (w - o, h - o), (w - o, h - o - m)])

    # top ruler
    ry = round(20 * sc)
    x = 0.0
    while x < w - 1:
        k = round(x / tick)
        ln = 38 * sc if k % 8 == 0 else (22 * sc if k % 4 == 0 else 10 * sc)
        s.rect(x, ry, 3 * sc if k % 8 == 0 else 1.5 * sc, ln)
        x += tick

    # column digits
    dh = round(66 * sc)
    dw = round(36 * sc)
    for i in range(10):
        s.digit(i * band_w + (band_w - dw) / 2, round(66 * sc), dw, dh,
                str(i), round(10 * sc))

    # left ruler
    y = 0.0
    tick_v = band_h / 8.0
    while y < h - 1:
        k = round(y / tick_v)
        ln = 30 * sc if k % 8 == 0 else (18 * sc if k % 4 == 0 else 8 * sc)
        s.rect(round(10 * sc), y, ln, 3 * sc if k % 8 == 0 else 1.5 * sc)
        y += tick_v

    # row digits. Row 0 is clamped below the column-digit band: centred in its
    # band it lands on top of column digit 0 and the pair reads as an "8".
    rdw, rdh = round(28 * sc), round(52 * sc)
    col_band_end = round(66 * sc) + dh + round(8 * sc)
    for j in range(5):
        ry_d = j * band_h + (band_h - rdh) / 2
        s.digit(round(48 * sc), max(ry_d, col_band_end), rdw, rdh,
                str(j), round(9 * sc))

    # frequency blocks -- ABSOLUTE pixel periods, the one element that must not
    # scale with the card, because the filter response is what is being probed
    y0, bh = round(150 * sc), round(62 * sc)
    s.rect(left, y0, right - left, bh, BLACK)
    periods = [24, 16, 12, 8, 6, 4, 3, 2]
    blk = (right - left) / len(periods)
    for k, p in enumerate(periods):
        bx = left + k * blk
        n = int((blk - 2) // p)
        for i in range(n):
            s.rect(bx + i * p, y0 + 2 * sc, max(1, p // 2), bh - 16 * sc)
        for mk in range(k + 1):
            s.rect(bx + 3 * sc + mk * 7 * sc, y0 + bh - 11 * sc,
                   3 * sc, 8 * sc)

    # circle row -- the aspect gauge
    cy, r = round(400 * sc), round(90 * sc)
    s.rect(left, cy - r - 22 * sc, right - left, 2 * (r + 22 * sc), BLACK)
    span = (right - 10 * sc) - (left + 10 * sc) - 2 * r
    for i in range(5):
        cx = left + 10 * sc + r + span * i / 4.0
        s.circle(cx, cy, r, 6 * sc)
        s.line(cx - r, cy, cx + r, cy, 2 * sc)
        s.line(cx, cy - r, cx, cy + r, 2 * sc)

    # luma staircase on black, so the dark steps stay visible
    y0, bh = round(600 * sc), round(90 * sc)
    s.rect(left, y0 - 6 * sc, right - left, bh + 12 * sc, BLACK)
    steps = 16
    sw = (right - left) / steps
    for i in range(steps):
        v = BLACK + round((WHITE - BLACK) * i / (steps - 1))
        s.rect(left + i * sw, y0, sw - 2 * sc, bh, v)

    # resolution stamp, in the clear band between the circles and the
    # staircase -- over the staircase it obscures two of the dark steps
    txt = f"{w}x{h}"
    sdw, sdh, st = round(20 * sc), round(38 * sc), round(6 * sc)
    s.number(left, round(528 * sc), sdw, sdh, txt, st, round(6 * sc))
    return s.render()


def rasterise(svg_path, png_path, w, h):
    if shutil.which("rsvg-convert"):
        cmd = ["rsvg-convert", "-w", str(w), "-h", str(h),
               svg_path, "-o", png_path]
    elif shutil.which("magick"):
        cmd = ["magick", "-background", "none", "-density", "96",
               svg_path, "-resize", f"{w}x{h}!", png_path]
    else:
        sys.exit("need rsvg-convert or magick to rasterise")
    subprocess.run(cmd, check=True)


def to_nv12(png_path, w, h):
    from PIL import Image
    img = Image.open(png_path).convert("L")
    if img.size != (w, h):
        sys.exit(f"rasteriser produced {img.size}, expected {(w, h)}")
    return img.tobytes() + bytes([128]) * (w * h // 2)


def marker_nv12(w, h, luma):
    """A flat cue frame at a GIVEN luma, coloured blue by chroma alone.

    Shown for a couple of seconds before each measurement so the operator knows
    a new value has landed and a photograph is due -- watching the panel, not
    the terminal, which is what went wrong when a printed schedule drifted out
    of step with the run.

    The luma is matched to the card's mean ON PURPOSE. A bright blue flash would
    make the camera re-expose, and the frame that matters comes immediately
    after it; auto-exposure recovering from the cue is indistinguishable from
    the scaler changing the picture. Matching the mean luma keeps the exposure
    metering still and puts the whole cue in chroma.

    It also degrades safely: if the chroma path is wrong the frame reads as flat
    grey rather than blue, which is still unmistakable against a card covered in
    rulers and circles.
    """
    y = bytes([luma]) * (w * h)
    # BT.601-ish blue at the given luma: U high, V low.
    uv = bytes([230, 110]) * (w * h // 4)
    return y + uv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--size", action="append", default=None,
                    help="WxH; repeatable. default 1280x720 and 1920x1080")
    a = ap.parse_args()
    sizes = a.size or ["1280x720", "1920x1080"]
    os.makedirs(a.outdir, exist_ok=True)
    for spec in sizes:
        w, h = (int(v) for v in spec.lower().split("x"))
        stem = os.path.join(a.outdir, f"scaler-testcard-{w}x{h}")
        with open(stem + ".svg", "w") as f:
            f.write(build(w, h))
        rasterise(stem + ".svg", stem + ".png", w, h)
        raw = to_nv12(stem + ".png", w, h)
        with open(stem + ".nv12", "wb") as f:
            f.write(raw)
        assert len(raw) == w * h * 3 // 2
        print(f"  {stem}.svg / .png / .nv12   "
              f"nv12 {len(raw)} bytes (= {w}x{h}x1.5)")

        # cue frame, luma-matched to this card so it cannot move the exposure
        from PIL import Image as _I
        import numpy as _np
        mean = int(round(_np.asarray(
            _I.open(stem + ".png").convert("L"), dtype=_np.float64).mean()))
        mk = os.path.join(a.outdir, f"scaler-cue-{w}x{h}.nv12")
        with open(mk, "wb") as f:
            f.write(marker_nv12(w, h, mean))
        print(f"  {mk}   flat blue at Y={mean} (the card's mean luma)")


if __name__ == "__main__":
    main()
