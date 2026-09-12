#!/usr/bin/env python3
"""Compare the two candidate 1080p->720p routes on the H713.

  ROUTE A (composite, both halves hardware-confirmed)
      VE power-of-two scale-down to 960x544, then the proc upscaler at
      0x05180000 magnifying 1/ratio with ratio_h = 0xC000 (1.333x).
      The 960x544 stage is REAL hardware output, dumped from the board. The
      upscale stage is MODELLED, because the proc scaler's tap set is unknown --
      so it is bracketed with a bilinear and a Lanczos model to show how much
      the answer depends on that assumption.

  ROUTE B (arbitrary-ratio, NOT available on this silicon)
      A single 1.5x polyphase downscale, modelled with the GENUINE coefficients
      extracted from libawh264.so (bucket 4, 32 phases x 4 int8 taps, each
      phase summing to 128). This is what the hardware would have produced if
      group 7's datapath existed -- see SELECTION-FOUND.md. Included to price
      what the composite route actually costs us.

Both routes start from the SAME VE-decoded frame, so encoder loss cancels and
the comparison isolates scaling. Reference points:

  native      the test card rasterised natively at 1280x720 -- the ideal
  lanczos     Lanczos 1920->1280 of the same decoded frame -- best-software

    tools/video/compare-scale-routes.py <workdir>

expects in <workdir>:
    primary-1920x1080.png   the VE's primary decoded frame (luma)
    hw-960x544.png          the VE's power-of-two secondary output (luma)
    card/scaler-testcard-1280x720.png   the native reference
    ve-scaler-coefficients.bin          14 x 128 bytes
"""
import sys
import os
import numpy as np
from PIL import Image

PHASES = 32
TAPS = 4
UNITY = 128


def load_coef(path, bucket):
    raw = np.fromfile(path, dtype=np.int8)
    c = raw[bucket * 128:(bucket + 1) * 128].reshape(PHASES, TAPS).astype(np.int32)
    assert (c.sum(axis=1) == UNITY).all(), 'coefficient phases must sum to 128'
    return c


def polyphase_1d(src, dst_len, coef):
    """One axis of the hardware's resampler: step by src/dst, quantise the
    fractional position to 32 phases, apply 4 taps at floor-1..floor+2.

    Tap index 1 is the integer position -- bucket 0 phase 0 is (0,127,1,0), an
    impulse at index 1, which is what fixes the alignment."""
    src = src.astype(np.int32)
    n = src.shape[-1]
    ratio = n / dst_len
    pos = (np.arange(dst_len) + 0.5) * ratio - 0.5
    base = np.floor(pos).astype(np.int64)
    frac = pos - base
    ph = np.clip((frac * PHASES).astype(np.int64), 0, PHASES - 1)
    idx = base[:, None] + np.arange(-1, TAPS - 1)[None, :]
    idx = np.clip(idx, 0, n - 1)
    w = coef[ph]                                     # (dst_len, 4)
    gathered = src[..., idx]                         # (..., dst_len, 4)
    out = (gathered * w).sum(axis=-1)
    return np.clip((out + UNITY // 2) // UNITY, 0, 255).astype(np.uint8)


def polyphase_2d(img, dst_w, dst_h, coef_h, coef_v):
    horiz = polyphase_1d(img, dst_w, coef_h)                 # rows resampled
    vert = polyphase_1d(horiz.T, dst_h, coef_v).T            # then columns
    return vert


def psnr(a, b):
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mse = ((a - b) ** 2).mean()
    return float('inf') if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def box(a, k):
    """Uniform filter via cumulative sums -- avoids a scipy dependency."""
    pad = k // 2
    p = np.pad(a, pad, mode='edge')
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    s = (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k])
    return s / (k * k)


def ssim(a, b, k=7):
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = box(a, k), box(b, k)
    va = box(a * a, k) - ma * ma
    vb = box(b * b, k) - mb * mb
    cab = box(a * b, k) - ma * mb
    s = ((2 * ma * mb + C1) * (2 * cab + C2)) / \
        ((ma ** 2 + mb ** 2 + C1) * (va + vb + C2))
    return float(s.mean())


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    wd = argv[1]
    g = lambda *p: os.path.join(wd, *p)

    prim = np.asarray(Image.open(g('primary-1920x1080.png')).convert('L'))
    hw = np.asarray(Image.open(g('hw-960x544.png')).convert('L'))
    native = np.asarray(Image.open(g('card', 'scaler-testcard-1280x720.png')
                                  ).convert('L'))
    coef_b4 = load_coef(g('ve-scaler-coefficients.bin'), 4)

    # The VE pads 1080 -> 1088, so its 544 rows cover 8 rows of padding.
    # Keep only the 540 that correspond to real picture.
    hw540 = hw[:540, :]

    DW, DH = 1280, 720
    results = {}

    # ---- ROUTE A: hardware 960x540, then a modelled 1.333x upscale ----
    for name, resample in (('A bilinear', Image.BILINEAR),
                           ('A lanczos', Image.LANCZOS)):
        up = np.asarray(Image.fromarray(hw540).resize((DW, DH), resample))
        results[name] = up

    # ---- ROUTE B: single 1.5x polyphase downscale, real coefficients ----
    results['B polyphase'] = polyphase_2d(prim, DW, DH, coef_b4, coef_b4)

    # ---- reference: best-software resample of the same decoded frame ----
    results['lanczos ref'] = np.asarray(
        Image.fromarray(prim).resize((DW, DH), Image.LANCZOS))

    lan = results['lanczos ref']
    print(f'source: VE-decoded 1920x1080; hardware stage: 960x540 (of 960x544)')
    print(f'{"route":<14} {"PSNR vs native":>15} {"SSIM vs native":>15}'
          f' {"PSNR vs lanczos":>16} {"SSIM vs lanczos":>16}')
    for name, img in results.items():
        print(f'{name:<14} {psnr(img, native):>15.2f} {ssim(img, native):>15.4f}'
              f' {psnr(img, lan):>16.2f} {ssim(img, lan):>16.4f}')
        Image.fromarray(img).save(g(f'route-{name.replace(" ", "-")}.png'))

    # How much detail each route can even carry, independent of any upscaler.
    print()
    print('information available to each route, before any upscale:')
    print(f'  route A carries 960x540  = {960*540:>7} luma samples'
          f'  ({960*540/(DW*DH)*100:.0f}% of the panel)')
    print(f'  route B carries 1280x720 = {DW*DH:>7} luma samples  (100%)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
