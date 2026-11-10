#!/usr/bin/env python3
"""What the panel SHOULD show for a letterbox step, and the card itself.
Runs on the host.

    letterbox-reference.py panel OUT.png W H OW OH DX DY
        letterbox-card.c's card at W x H, magnified (nearest neighbour) to
        OW x OH and placed at (DX, DY) on a black 1280x720 panel: compare
        operator photos against it.
    letterbox-reference.py card OUT.png W H
        the card alone at W x H (square pixels), e.g. as a video source
        (tools/video/make-upscale-clips.sh).
    letterbox-reference.py phase3 OUTDIR
        reference panels for every letterbox-test.sh phase3 step.

The card is a transcription of colour_at() in tools/display/letterbox-card.c;
keep the two in step.
"""
import os
import sys

import numpy as np
from PIL import Image

RGB = {0: (110, 110, 110), 1: (255, 255, 255), 2: (0, 0, 0), 3: (220, 40, 40),
       4: (60, 180, 40), 5: (40, 90, 230), 6: (220, 210, 40)}
LUT = np.array([RGB[i] for i in range(7)], np.uint8)


def card(w, h):
    """Colour indices of letterbox-card.c's card at w x h."""
    y, x = np.mgrid[0:h, 0:w]
    m = min(w, h)
    r, rc = m * 2 // 5, m // 10
    c = np.zeros((h, w), int)

    def circ(cx, cy, rad, t):
        d = (x - cx) ** 2 + (y - cy) ** 2
        return (d >= (rad - t) ** 2) & (d <= rad * rad)

    lines = ((abs(x * h - y * w) < w * 3 / 2) | (abs((w - 1 - x) * h - y * w) < w * 3 / 2)
             | (x == w // 2) | (x == w // 2 - 1) | (y == h // 2) | (y == h // 2 - 1))
    cir = (circ(w // 2, h // 2, r, 3) | circ(rc + 100, rc + 100, rc, 2)
           | circ(w - rc - 100, rc + 100, rc, 2) | circ(rc + 100, h - rc - 100, rc, 2)
           | circ(w - rc - 100, h - rc - 100, rc, 2))
    c[cir | lines] = 1
    p1, p2 = (y >= 40) & (y < 88), (y >= h - 88) & (y < h - 40)
    xa, xb = (x >= 40) & (x < 88), (x >= w - 88) & (x < w - 40)
    c[p2 & xb] = 6
    c[p2 & xa] = 5
    c[p1 & xb] = 4
    c[p1 & xa] = 3
    tick = (((x % 64 < 2) & ((y < 28) | (y >= h - 28))) | ((x % 16 < 2) & ((y < 14) | (y >= h - 14)))
            | ((y % 64 < 2) & ((x < 28) | (x >= w - 28))) | ((y % 16 < 2) & ((x < 14) | (x >= w - 14))))
    c[tick] = 1
    c[(x < 4) | (y < 4) | (x >= w - 4) | (y >= h - 4)] = 2
    c[(x < 2) | (y < 2) | (x >= w - 2) | (y >= h - 2)] = 1
    return c


def panel(path, w, h, ow, oh, dx, dy):
    c = card(w, h)
    yi, xi = (np.arange(oh) * h) // oh, (np.arange(ow) * w) // ow
    img = np.zeros((720, 1280, 3), np.uint8)
    img[dy:dy + oh, dx:dx + ow] = LUT[c[yi][:, xi]]
    Image.fromarray(img).save(path)


PHASE3 = {"s1": (640, 360, 1280, 720, 0, 0), "s2": (852, 480, 1278, 720, 0, 0),
          "s3": (720, 576, 960, 720, 160, 0), "s4": (352, 288, 880, 720, 200, 0),
          "s5": (640, 360, 960, 540, 160, 90)}


def main(argv):
    if len(argv) == 9 and argv[1] == "panel":
        panel(argv[2], *map(int, argv[3:9]))
    elif len(argv) == 5 and argv[1] == "card":
        Image.fromarray(LUT[card(int(argv[3]), int(argv[4]))]).save(argv[2])
    elif len(argv) == 3 and argv[1] == "phase3":
        for name, g in PHASE3.items():
            panel(os.path.join(argv[2], f"ref-{name}.png"), *g)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
