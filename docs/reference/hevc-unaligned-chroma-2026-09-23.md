# Inter chroma is wrong when the PITCH is not a multiple of 32 — FIXED 2026-09-23

Found by the rewritten 10-bit gate on its first run with an unaligned vector.
**It is not a 10-bit defect, not an HEVC defect, and not in userspace.** Luma
is unaffected, which is why nothing caught it for so long.

**Fixed by patch 0125** (`media: cedrus: align the capture pitch to 32`).
Everything below is the investigation and the evidence.

## It affected every codec, not just HEVC

The sizing path is shared, so the defect was too. Measured at 656x480 by
swapping the pre-fix module back in, worst chroma MSE against a software decode
over ten frames:

| codec @ 656x480 | pre-fix chroma | bad frames | pre-fix luma | post-fix |
| --- | --- | --- | --- | --- |
| H.264 | 7772.6 | 8/10 | 0.000 | **bit-exact** |
| VP8 | 8868.6 | 8/10 | 0.000 | **bit-exact** |
| HEVC | 5828.2 | 8/10 | 0.000 | **bit-exact** |

8 of 10 is every frame except the two keyframes (`-g 5`). Luma is exactly
0.000 in all three, before and after — the signature is identical across
codecs, which is what a shared-path defect looks like.

This was originally filed as an HEVC bug because HEVC is where the gate that
found it happens to look. The title above has been corrected accordingly.

**The rule, from an axis-isolation matrix (all 8-bit Main, all on hardware):**

| vector | width %16 | width %32 | height %16 | result |
| --- | --- | --- | --- | --- |
| 1920x1080 | 0 | 0 | **8** | **bit-exact, inf** |
| 640x482 | 0 | 0 | **2** | **bit-exact, inf** |
| 642x480 | **2** | **2** | 0 | u 14.08 / v 11.25 |
| 648x480 | **8** | **8** | 0 | u 14.65 / v 12.04 |
| **656x480** | **0** | **16** | 0 | u 14.04 / v 11.47 |
| 642x482 | **2** | **2** | **2** | u 15.02 / v 12.15 |

**Width alone decides it, and the threshold is 32, not 16.** Height
misalignment is harmless: 1920x1080 is clean even though its canvas height
(1088) differs from its coded height (1080).

**656x480 is the vector that settles it**, and it was run specifically because
the first two broken widths could not distinguish the hypotheses. 656 *is* a
multiple of 16 and still breaks, so the trigger is the 32 boundary. Two earlier
revisions of this file got this wrong — first blaming canvas_h vs coded_h
(falsified by 1920x1080), then "not a multiple of 16" (falsified by 656).

Practically: 640, 1280, 1920, 2560 and 3840 are all multiples of 32 and were
never affected. The exposed widths are the likes of **854** (854x480), **1366**
(1366x768) and **656** — and anything reaching the decoder with a pitch chosen
by a client rather than by the picture.

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

## Root cause

One field, and a disagreement between the write and the read path over it.
`cedrus_dst_format_set()` programs:

```c
reg = VE_PRIMARY_FB_LINE_STRIDE_LUMA(stride) |
      VE_PRIMARY_FB_LINE_STRIDE_CHROMA(stride / 2);
```

The engine rounds that chroma field up to 16 **in its own units**, so the
chroma stride it uses is `ALIGN(stride, 32)`. At a 32-aligned pitch the
rounding is a no-op and the two agree. At a pitch that is 16- but not
32-aligned the engine writes chroma at the pitch and reads reference chroma one
16-byte step per line wider.

That accounts for every observation at once:

- **Intra is correct** — it reads no reference at all.
- **Every inter frame is wrong** — it reads displaced chroma.
- **Luma is never wrong** — it has its own field, with no rounding.
- **Width decides, height does not** — this is a stride, a per-line quantity.

The damage is large because a stride error displaces each row progressively
rather than by a constant offset.

This is a *different* bug from the coded_h-vs-canvas_h trap in the 2-bit side
plane ([hevc-10bit-findings.md](../hevc-10bit-findings.md)) — that one is
vertical, this one horizontal, and 1920x1080 proves the vertical case is
handled correctly here.

## The fix

Align the capture pitch to 32, so the engine's rounding is a no-op at every
width. Patch 0125, one line plus the comment explaining why it cannot go back
to 16.

The alternative — widening what `DEC_PIC_SIZE` advertises so the engine's own
derivation lands on 32 — was rejected: it changes what the engine *parses*, not
just where it puts the result.

A tempting shortcut that does **not** work: raising `bytesperline` from
userspace via `S_FMT`. The probe's `CEDRUS_STRIDE=672` produced a capture of
exactly 472320 bytes, the 656-pitch size, i.e. it never took effect — and the
corrupt luma that came back was my own de-pad misreading a 656-pitch buffer at
672, not a hardware result. Check the dump size before believing that test.

**After the fix, on hardware:**

| | before | after |
| --- | --- | --- |
| 642x480, 648x480, 656x480, 642x482 (8-bit) | chroma 12–15 dB | **bit-exact** |
| h09-642x482 Main10 | u 15.02 / v 12.15 | **u 53.26 / v 53.27** |
| 640x482, 1920x1080 | bit-exact | **unchanged** |
| h07 / h08 Main10 | 54.30 / 52.80 | **unchanged** |
| HEVC gate | 12 pass | **12 pass, 0 fail** |
| MPEG-2 gate | 6 pass | **6 pass, md5s identical** |

For 32-aligned widths the patch changes nothing — `ALIGN(w, 16)` and
`ALIGN(w, 32)` are the same number — so the regression surface is exactly the
widths that were already broken.

## Regression cover, and proof it can fail

Both gates were run against the pre-fix module to confirm they actually catch
this. A guard that has never failed is not a guard.

**`h10-656x480-unaligned`, in the H1 HEVC gate.** 656 is a multiple of 16 and
deliberately not of 32, so it pins the exact distinction that can regress.

| | pre-fix | post-fix |
| --- | --- | --- |
| h10 software arm | PASS — harness sound | PASS |
| h10 gst / va arms | **MISMATCH, both** | bit-exact |
| H1 total | 12 pass, **2 fail** | **14 pass, 0 fail** |

The software arm passing while both hardware arms fail is the shape you want:
it says the harness is right and the hardware is wrong.

**`hevc-10bit-verify.py` now checks an inter frame.** It dumped capture 1 and
nothing else — always an I-frame — so it reported h09 bit-exact on every plane
straight through this defect. It now checks captures 1 and 3, matching each
against whichever reference frame it actually equals, because completion order
is not display order once B-frames exist (h08's capture 3 is reference frame 2).
Against the pre-fix module it fails on h09, naming the pitch shortfall rather
than dying in an IndexError as the first version of that check did.

## Suite coverage

`h10` is now in the soak and concurrency pools as well as the H1 gate, so the
pitch alignment is exercised under sustained load and under contention rather
than only in a single-shot decode.

Two wiring bugs were found by running those suites rather than by reading them,
and both would have produced silent non-coverage:

- **`h10` was excluded by a prefix pattern.** The reference and stream dispatch
  in the soak and concurrency suites matched `h0*`, which predates a two-digit
  vector id. `h10` fell through to the H.264 arm; the concurrency run refused to
  start rather than scoring it blind, which is the harness working. `stream_of`
  had the same assumption and would have handed it a `.h264` path.
- **The concurrency pool grew past what its default reached.** Clients pick
  `POOL[(r + i) % len]`, so 5 rounds x 3 clients reaches indices 1..7 — all of a
  7-entry pool, by arithmetic accident. Adding two entries left `h01` and `h10`
  never selected, with nothing to report it. The default is now the pool size.

## Still open

- **No H.264 or VP8 vector guards the alignment.** Deliberate: the defect is in
  the shared sizing path, so `h10` catches any regression of it, and a second
  and third vector would cost gate time to re-prove the same line. Revisit if
  the sizing ever diverges per codec.
- **MPEG-2 was never tested at an unaligned width.** Its md5s are unchanged at
  720 wide, which shows no regression but not immunity.
