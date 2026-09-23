# HEVC inter-frame chroma is wrong at unaligned geometry — 2026-09-23

Found by the rewritten 10-bit gate on its first run with a non-16-aligned
vector. **It is not a 10-bit defect**, and it is not in userspace. Luma is
unaffected, which is why nothing has ever caught it.

## The measurement

`h09-642x482-main10`, ten frames, `keyint=5` — so frames 0 and 5 are I-frames
and the rest are inter. Chroma MSE against a software decode of the same clip:

| frame | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Main10 chroma | **0.36** | 3677 | 3808 | 3688 | 3443 | **0.31** | 3393 | 3900 | 4640 | 3498 |
| 8-bit chroma | **0.00** | 3913 | 4279 | 3801 | 4418 | **0.00** | 3871 | 3833 | 5848 | 3868 |
| 8-bit luma | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 | **0.00** | 0.00 | 0.00 | 0.00 | 0.00 |

Exactly the I-frames are correct. Every inter frame's chroma is grossly wrong —
MSE ~3900 is about **12 dB**. Luma is bit-exact in all ten.

Through the gate that means:

```
h09  PSNR y/u/v  56.386944  15.022749  12.148009 dB
```

## Three controls, because one number proves nothing

**Aligned control.** `h07-640x480-main10` — chroma MSE 0.22–0.35 on *every*
frame, inter included. So it is geometry, not content, not inter prediction as
such, and not the vector's encoder settings.

**Bit-depth control.** An 8-bit Main stream at the same 642x482 shows the
identical pattern, and more crisply: 8-bit is otherwise bit-exact, so correct
frames read exactly `0.0000` and broken ones read in the thousands. **The bug
has nothing to do with 10 bit.** Generate it with:

```bash
ffmpeg -f lavfi -i "testsrc2=size=642x482:rate=25" -frames:v 10 -pix_fmt yuv420p -c:v libx265 -profile:v main -x265-params "keyint=5" -f hevc x-642x482-8bit.h265
```

**Userspace control.** GStreamer `v4l2slh265dec` and libva-v4l2-request both
show it. They differ from *each other* by 28,523 bytes of 4,641,660 — all of it
chroma, all of it in inter frames, luma byte-identical — and both are wrong
against software. Neither is the good one, so the defect is below both clients.

## Why nothing caught it

Two independent blindnesses, either of which alone would have hidden it:

1. **No unaligned vector exists.** h01–h08 are 640x480 and 1280x720. Both axes
   16-aligned, so canvas and picture coincide and the case never arose.
2. **The harnesses score luma.** `psnr_of` parsed `PSNR y:` and nothing else,
   so 12 dB chroma sat behind 56 dB luma and reported PASS. The md5 harnesses
   are no better here: their references were captured from this same path, so
   they would agree with the defect rather than detect it.

Fixed in the gate: arms 1 and 2 now threshold the **worst** of y/u/v.

## Where to start looking

Untested, but it is the first place to look, because the same confusion has
already been found once in this driver.

The capture canvas is 16-aligned (656x496) while the coded picture is 8-aligned
(coded_h 488). If the chroma plane offset used for **reference** frames is
computed from canvas_h where the writes use coded_h, references are read
8 rows — 5,248 bytes — off. That predicts exactly what is observed: intra needs
no reference and is correct, inter reads displaced chroma and is not, and luma
starts at offset 0 either way so it is never affected.

The 2-bit side plane has this same coded_h-vs-canvas_h trap, documented in
[hevc-10bit-findings.md](../hevc-10bit-findings.md), where getting it wrong
reads as 62.5 dB "rounding".

## Not yet done

- **The bug itself is unfixed.** This is a characterisation, not a fix.
- **Arm 3 cannot see it.** `hevc-10bit-verify.py` dumps `CEDRUS_DUMP_AT=1` —
  the first completed capture, which is an I-frame — so it reports h09 as
  bit-exact on all planes and is blind to every inter frame. Pointing it at a
  later capture would make it fail, correctly.
- **No unaligned vector is in the H1 gate.** Adding the 8-bit one above would
  turn that gate red until the defect is fixed, which is a call to make
  deliberately rather than as a side effect.
