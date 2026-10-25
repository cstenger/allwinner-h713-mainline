#!/usr/bin/env python3
"""The Test 2 band chart: 16 flat colour bands with large row labels, 1280x720.

docs/hdmi-panel-source-design-2026-10-23.md sections 10.18 / 10.23.2.  Each
band is 45 lines tall and one flat colour; its row number (0-15) is drawn in
the luma channel with a black-on-white outline, so the label stays readable
whatever happens to chroma.  On the panel, the colour seen behind label n
names the source band whose chroma reached that row: n (correct), n/2 (the
T5/T6 defect) or n/4.  The palette order keeps adjacent bands far apart in
hue so the three mappings give visibly different colours.  Shown 1:1 as the
HDMI-A-1 wallpaper at 1280x720 (no scaling).

    make-band-chart.py OUT.png
    make-band-chart.py --self-test
"""
import argparse
import colorsys
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, BANDS = 1280, 720, 16
ROWS = H // BANDS  # 45
# 16 hues (multiples of 22.5 degrees) ordered by search so that every pair that matters --
# (n, n/2), (n, n/4), (n/2, n/4) -- is at least 67.5 degrees apart
HUES = [k / 16 for k in (12, 4, 0, 9, 11, 13, 15, 1, 8, 6, 7, 10, 2, 3, 14, 5)]


def palette():
    return [tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, 0.85, 0.9)) for h in HUES]


def chart():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=36)
    except TypeError:
        font = ImageFont.load_default()
    for n, rgb in enumerate(palette()):
        y0 = n * ROWS
        d.rectangle([0, y0, W - 1, y0 + ROWS - 1], fill=rgb)
        for x in (40, W // 2 - 20, W - 100):  # left, centre, right copies of the label
            d.text((x, y0 + 4), f"{n:2d}", font=font, fill=(0, 0, 0), stroke_width=4, stroke_fill=(255, 255, 255))
    return img


def self_test():
    fails = []
    img = np.asarray(chart())
    if img.shape != (H, W, 3):
        fails.append(f"size {img.shape}")
    pal = palette()
    # each band's background (a column clear of labels) is its palette colour, flat
    for n, rgb in enumerate(pal):
        col = img[n * ROWS:(n + 1) * ROWS, 300]
        if not (col == rgb).all():
            fails.append(f"band {n} background not flat {rgb}")
    # the three mappings are distinguishable: for every row n >= 2, colour(n), colour(n//2), colour(n//4)
    # differ in hue by at least 60 degrees wherever they are different bands
    def hue(rgb):
        return colorsys.rgb_to_hsv(*[c / 255 for c in rgb])[0] * 360
    for n in range(2, BANDS):
        for a, b in ((n, n // 2), (n, n // 4), (n // 2, n // 4)):
            if a != b:
                dh = abs(hue(pal[a]) - hue(pal[b]))
                if min(dh, 360 - dh) < 60:
                    fails.append(f"bands {a} and {b} too close in hue ({min(dh, 360 - dh):.0f} deg)")
    # labels are present in every band (dark pixels inside the band)
    for n in range(BANDS):
        band = img[n * ROWS:(n + 1) * ROWS]
        if (band.sum(2) < 60).sum() < 200:
            fails.append(f"band {n} has no visible label")
    for f in fails[:10]:
        print("FAIL:", f)
    print("self-test", "FAILED" if fails else f"passed ({BANDS} bands x {ROWS} lines)")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.out:
        ap.error("OUT.png required")
    chart().save(a.out)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
