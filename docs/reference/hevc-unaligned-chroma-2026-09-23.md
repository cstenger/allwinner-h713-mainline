# HEVC inter-frame chroma is wrong when WIDTH is not a multiple of 16 — 2026-09-23

Found by the rewritten 10-bit gate on its first run with a non-16-aligned
vector. **It is not a 10-bit defect**, and it is not in userspace. Luma is
unaffected, which is why nothing has ever caught it.

**The rule, from an axis-isolation matrix (all 8-bit Main, all on hardware):**

| vector | width %16 | height %16 | result |
| --- | --- | --- | --- |
| 1920x1080 | 0 | **8** | **bit-exact, inf** |
| 640x482 | 0 | **2** | **bit-exact, inf** |
| 642x480 | **2** | 0 | u 14.08 / v 11.25 |
| 648x480 | **8** | 0 | u 14.65 / v 12.04 |
| 642x482 | **2** | **2** | u 15.02 / v 12.15 |

**Width alone decides it. Height misalignment is harmless.** 1920x1080 is
clean even though its canvas height (1088) differs from its coded height
(1080) — so the vertical canvas/coded mismatch is handled correctly, and an
earlier draft of this document that blamed it was wrong.

648 is the sharp case: it needs no coded padding at all (coded_w = 648 = the
picture width) and still breaks, because the 16-aligned canvas is 656. So the
trigger is **canvas_w != coded_w**, not "the picture needs padding".

Practically, most standard widths are safe — 640, 1280, 1920, 2560, 3840 are
all multiples of 16. The exposed ones are widths like **854** (854x480) and
**1366** (1366x768), which are common in real content.

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
such, and not the vector's encoder settings. See the axis matrix above for
which axis.

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

The axis matrix rules out the vertical explanation and points at chroma
**horizontal** addressing for reference frames.

Everything observed is consistent with the chroma reference read using one
width where the buffer uses the other — coded_w (648) against a canvas stride
of 656, or the reverse. A horizontal stride error displaces each row
progressively, which is why the damage is large and spread across rows rather
than a clean block offset. Luma is unaffected because it is addressed with the
correct stride; intra is unaffected because it reads no reference at all.

Note this is a *different* bug from the coded_h-vs-canvas_h trap in the 2-bit
side plane ([hevc-10bit-findings.md](../hevc-10bit-findings.md)) — that one is
vertical, this one is horizontal, and 1920x1080 proves the vertical case is
handled correctly here.

**An earlier revision of this file blamed canvas_h vs coded_h.** That was
written before the axis matrix existed, from the single 642x482 data point where
both axes were misaligned at once. 1920x1080 and 640x482 falsify it.

## Not yet done

- **The bug itself is unfixed.** This is a characterisation, not a fix.
- **Arm 3 cannot see it.** `hevc-10bit-verify.py` dumps `CEDRUS_DUMP_AT=1` —
  the first completed capture, which is an I-frame — so it reports h09 as
  bit-exact on all planes and is blind to every inter frame. Pointing it at a
  later capture would make it fail, correctly.
- **No unaligned vector is in the H1 gate.** Adding the 8-bit one above would
  turn that gate red until the defect is fixed, which is a call to make
  deliberately rather than as a side effect.
