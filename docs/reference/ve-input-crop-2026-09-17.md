# The VE scaler honours a smaller input height — 2026-09-17

**Result: positive and decisive.** `TOP1_IN_SIZE` (VE + `0xf0c`) bounds what the
polyphase scaler actually reads. Pointing it at a stream's **visible** height
instead of its coded raster makes 1920x1080 → 1280x720 an exact 1.5 on both
axes, and reproduces a natively-rasterised 720p reference bottom-edge for
bottom-edge.

This answers ["Establish whether the hardware scaler can honor input
crop"](../handoff-2026-09-17-shared-scaler.md) — item 2 of that handoff — which
explicitly warned against assuming it. It does.

## Why it matters

H.264 stores 1080p as 1088 coded rows. The scaler was programmed from
`ctx->src_fmt`, so it consumed all 1088 and squeezed them into the 720 output
rows. Two consequences, both visible:

- the visible 1080 rows land on 714.7 of the 720, so everything is 0.74% short;
- the 8 rows of coded padding are scaled *into* the picture as ~5 rows at the
  bottom. Because encoders pad by replicating the last row, that reads as the
  bottom border of a frame becoming nearly twice as thick.

The display cannot crop it away afterwards: `h713_afbd_video_atomic_check`
accepts one framebuffer geometry and no other (1280x720, pitch 1280), so there
is no taller buffer to take a window out of. Fixing it at the scaler is the only
place it can be fixed.

## Method

A module parameter overriding the scaler's input height, nothing else touched:

```c
if (scaler_in_h)
        src_h = scaler_in_h;
```

Then decode the 1080p [scaler test card](scaler-testcard.md) to 1280x720 and
measure where its bottom border lands. The card is the right instrument here
precisely because it has a border on all four edges: the last bright row **is**
the bottom of the visible picture, so the measurement needs no interpretation.

Reference is `local/testcards/scaler-testcard-1280x720.nv12`, the same vector
source rasterised natively at 720p.

## Numbers

| scaler input height | border starts at row | bright rows | PSNR vs native 720p card |
| --- | --- | --- | --- |
| 1088 (coded) — old behaviour | ~709 | 11 | 15.63 dB |
| 1084 | ~711 | 9 | (not recomputed, see below) |
| **1080 (visible)** | **714** | **6** | **18.69 dB** |
| native 720p card | 714 | 6 | — |

The 1080 row matches the reference exactly: border six rows thick, ending at
719. The 1088 row shows the predicted doubled border. 1084 lands between the
two, which is what makes this a linear input-size control rather than a flag.

**The absolute PSNR is not the finding.** The two cards are independently
rasterised, so fine detail — the frequency blocks especially — can never match.
The 3.1 dB *difference* and the exact border alignment are what carry the
result.

### Correction: the first PSNR figures were wrong

This table originally read 20.93 / 22.14 / 27.10 dB, and claimed a 6.2 dB
improvement. Those numbers came from a throwaway script that took the difference
of two images as `np.int16` and then squared it. A squared 8-bit difference
reaches 65025 and int16 stops at 32767, so the large errors wrapped negative,
deflated the mean squared error, and inflated every PSNR.

It surfaced because the same file was measured twice by different code: a
capture with md5 `a1b57792782154dadf21a4eb1da64a77` scored 27.10 dB one day and
18.69 dB the next. Identical bytes cannot have two PSNRs, so one of the two
measurements had to be wrong.

The measurement now lives in
[`tools/video/measure-nv12-border.py`](../../tools/video/measure-nv12-border.py)
and uses int32, so it cannot recur silently. The 1084 case is not recomputed
because it needed a module built with an experiment parameter that was
deliberately removed; its border reading of 9 rows is unaffected, since the
border code never used PSNR.

**Nothing else moves.** The border readings, the byte-identical MD5 comparisons,
and the panel photographs are all independent of this arithmetic, and they are
what the conclusion rests on.

## The control that makes it believable

`scaler_in_h=0` and `scaler_in_h=1088` produce **byte-identical** output
(md5 `3fb46599f06f6fc27aaa0b3ca420ac92`). 1088 is the coded height, so the
override is a no-op there — which proves the parameter does not change the
picture merely by being set. 1080 (`a1b57792782154da…`) and 1084
(`fbc827e89cae28af…`) each differ from it and from each other.

Without that control the experiment could not distinguish "the register works"
from "writing this parameter perturbs something".

## What is NOT established

- **Horizontal.** `scaler_in_w` was implemented but not exercised: our case has
  coded width equal to visible width, so there was nothing to measure. The
  register's high half is the width field and is presumably symmetric, but that
  is an inference, not a measurement.
- **An input OFFSET.** Not needed here and not looked for. Visible rectangles in
  H.264 and HEVC start at (0,0) in every stream this project handles; a stream
  cropping from the top or left would need a register nobody has found.
- **HEVC and Main10.** Measured on H.264 only. They share the datapath, so the
  expectation is that they behave identically, but they were not tested.
- **Any effect on the reconstruction path.** The scaler feeds the secondary
  output only, and reconstruction stays full size, so there should be none. Not
  independently verified.

## Getting the visible height into the kernel

This is the whole remaining problem, and it is an interface question rather than
a hardware one.

The visible size is not in the stateless controls. `v4l2_ctrl_h264_sps` carries
no `frame_crop_*` fields at all, and `v4l2_ctrl_hevc_sps` carries
`pic_width_in_luma_samples` / `pic_height_in_luma_samples`, which are the coded
size. Userspace cannot simply set a smaller OUTPUT format either: reconstruction
needs all 1088 rows for the DPB.

The target for it is `V4L2_SEL_TGT_CROP` on the CAPTURE queue, which
`dev-decoder.rst` defines as "the rectangle **within the coded resolution** to be
output to CAPTURE", writable on hardware with compose/scaling capabilities. That
is exactly `TOP1_IN_SIZE`. cedrus does not implement it: `cedrus_g_selection`
returns `-EINVAL` for every CROP target and `cedrus_s_selection` accepts COMPOSE
alone.

**COMPOSE is not in the way.** An earlier draft of this document claimed the
spec wanted COMPOSE for the visible rectangle and that this driver had taken it
for something else. That was a misreading. The spec defines COMPOSE as "the
rectangle inside a CAPTURE buffer into which the cropped frame is written",
which is precisely what patch 0107 uses it for. CROP and COMPOSE are the input
and output rectangles of the same scaling operation, and the driver is simply
missing the input one. Adding it is therefore additive: no API break, and
`cedrus-scaler-api-test.c` keeps testing COMPOSE as it stands.

## Reproducing

The experiment module is not in the series and was loaded from `/tmp` so that a
reboot restores production. After it, the build tree was returned to the series
state and **verified by artifact identity** — the rebuilt module is md5
`772c6a46b668baafb98dcf00ddb15429`, byte-identical to the installed one, with no
leftover parameters. That check matters: the tree is named by a hash of the
series, so `build.sh` reuses it, and an edit left behind would have leaked
silently into the next build.
