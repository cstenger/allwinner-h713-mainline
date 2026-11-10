# Composite route vs the arbitrary path: the composite costs ~8.5 dB

2026-09-11/12, headless. Prices the only surviving no-GPU route to 1080p on the
720p panel against the arbitrary-ratio path that [SELECTION-FOUND.md](SELECTION-FOUND.md)
established this silicon does not implement.

**Result: the composite route works but is measurably worse — 29.9 dB vs
38.3 dB against the same reference, and it carries only 56% of the panel's
samples.** It is still the only option.

## The two routes

| | route A (composite) | route B (arbitrary) |
| --- | --- | --- |
| stages | VE power-of-two -> 960x544, then proc upscaler 1.333x | one 1.5x polyphase downscale |
| availability | **both halves hardware-confirmed** | **not implemented on the H713** |
| samples before upscale | 960x540 = 518400 (56% of panel) | 1280x720 = 921600 (100%) |

Route A's first stage is **real hardware output**, dumped off the board. Its
second stage is modelled, because the proc upscaler's tap set is unknown — so it
is bracketed with bilinear and Lanczos models to show how much the answer
depends on that assumption. Route B is modelled with the **genuine** bucket-4
coefficients extracted from `libawh264.so` (32 phases x 4 int8 taps, each phase
summing to 128).

## Method

Both routes start from the **same VE-decoded frame**, so encoder loss cancels
and what is measured is scaling alone.

- Source: the purpose-built test card, rasterised natively at 1920x1080, encoded
  H.264 High profile CRF 12 all-I. It round-tripped bit-exact through a software
  decode before use, so the clip is not adding loss of its own.
- **An earlier attempt encoded it at `-qp 0`, which makes libx264 emit a
  lossless profile the VE cannot decode.** ffmpeg fell back to software, the
  scale-down harness never ran, and the dump came back pure poison. The tell was
  `Failed setup for format vaapi: hwaccel initialisation returned error` — worth
  checking explicitly, because an all-poison buffer looks identical to "the
  scaler did nothing".
- Hardware stage: `sd_ctrl=0x500`, `sd_fmt=1`, dumped from
  `/sys/kernel/debug/cedrus_sd_buf`. The VE pads 1080 -> 1088, so its 544 rows
  cover 8 rows of padding; only the 540 real rows are used.

Driven by `tools/video/compare-scale-routes.py`.

## Numbers

```
route           PSNR vs native  SSIM vs native  PSNR vs lanczos  SSIM vs lanczos
A bilinear               19.01          0.9066            27.59           0.9627
A lanczos                18.74          0.9067            29.86           0.9678
B polyphase              18.96          0.9347            38.31           0.9947
lanczos ref              18.66          0.9363              inf           1.0000
```

**Read the "vs lanczos" columns.** The "vs native" ones are confounded: the card
is regenerated per resolution, so its frequency-sweep band draws different bar
widths at 720p than at 1080p, and no resample of the 1080p raster can match it.
That depresses PSNR for *everything* including the Lanczos reference itself
(18.66 dB), which is the giveaway. The relative SSIM ordering there still holds
and agrees — A 0.907, B 0.935, reference 0.936.

Against a best-software resample of the identical decoded frame:

- **Route B lands at 38.3 dB / SSIM 0.995** — essentially indistinguishable from
  the reference. That also independently validates the extracted coefficients
  and the polyphase model: a wrong tap set or a misaligned phase would not land
  within 0.005 SSIM of Lanczos.
- **Route A lands at 27.6 dB (bilinear) to 29.9 dB (Lanczos).** So the composite
  route costs roughly **8.5 dB** against what the arbitrary path would have
  delivered, and the choice of upscaler moves it by only ~2 dB — the loss is
  dominated by the 2x downscale, not by the interpolation afterwards.

That is the honest shape of it: route A throws away 44% of the panel's samples
in stage one and cannot get them back, whatever stage two does.

## Visually

[composite-vs-arbitrary-sweep.png](composite-vs-arbitrary-sweep.png) — the
frequency-sweep band, 2x nearest-neighbour, in route order: A bilinear,
A Lanczos, B polyphase, Lanczos reference, native 720p.

- **A bilinear** smears the fine groups; the fourth group collapses toward flat
  grey.
- **A Lanczos** is sharper but rings — irregular bar widths and dark halos,
  which is the 2x downscale's aliasing being re-sharpened rather than recovered.
- **B polyphase** holds even bars across all groups and tracks the reference.
- **native** draws different bar widths, which is the confound noted above.

The hardware 960x544 output itself is clean and unclipped —
[composite-hw-960x544.png](composite-hw-960x544.png), all four borders present,
corner markers intact, the expected aliasing in the finest sweep groups.

## Wiring it up: what is actually left

The measurement is done; the plumbing is not, and it is more than a script.

**1. One hardware fact is still unvalidated.** The proc upscaler has never been
driven with its geometry registers set. Every previous run deliberately left
`0x2c`/`0x30`/`0x34` alone and the magnified picture came back **clipped to a
hard-edged rectangle**; the standing hypothesis is that the clip window *is*
that untouched geometry. Until that is settled, the second stage is not known to
work at the sizes this route needs.

`tools/display/composite-route-test.sh` is built and ready for that. It asks the
geometric question without needing a 960x544 source or a kernel change: magnify
a 960x544 *region* of the existing 1280x720 card to full screen, which is the
same configuration. Gates verified before any register is touched, every write
read back, restore path included. **It needs one operator turn at the panel.**

**2. Then two driver changes**, neither small:

- *cedrus*: the 960x544 secondary output currently lands in a private debugfs
  buffer. To reach the display it has to be the V4L2 capture buffer — which
  means allocating internal full-size buffers for the primary reconstruction,
  redirecting `VE_PRIMARY_*` there, pointing `VE_H264_SDROT_*` at the V4L2 dst,
  reporting 960x544 as the capture format, and keeping the DPB reference
  pointers aimed at the internal primaries. That last part is what makes
  decoding correct at all, so it carries real risk.
- *KMS* (`sun50i-h713-afbd.c`): the video plane declares
  `DRM_PLANE_NO_SCALING` and `h713_afbd_video_atomic_check()` rejects any
  framebuffer, `src`, or `crtc` rectangle that is not exactly 1280x720. It would
  need to accept a 960x544 source, advertise a scaling range, and program the
  proc upscaler from `atomic_update` — plus the DECD source geometry for the
  smaller raster.

Sequencing matters: step 1 is one photograph and decides whether steps 2 and 3
are worth writing at all. If the upscaler still clips with geometry set, the
composite route dies and with it the last no-GPU option.

## Standing caveat

Route B's numbers are a **model**, not a measurement — the hardware will not run
it. They are the right model (real coefficients, validated against Lanczos), but
nothing here shows the H713 producing a 1.5x downscale, because it cannot. The
8.5 dB is the price of a capability this part does not have, quoted so the
composite route's cost is known rather than guessed.
