# MPEG-2 and VP8 on H713 — both work

**Result: the inherited capabilities are legitimate.** H713 decodes MPEG-2 and
VP8 in hardware. Neither should be removed. Field-coded MPEG-2 was refused
outright and now works — see kernel patch 0123 below.

This closes a long-standing suspicion. H713 has no cedrus variant of its own: it
binds to `allwinner,sun50i-h6-video-engine` and takes the H6 capability set
whole, `CEDRUS_CAPABILITY_MPEG2_DEC` and `CEDRUS_CAPABILITY_VP8_DEC` included,
with POLYPHASE added afterwards by an `of_machine_is_compatible()` check at
probe. Because no VA profile exposes either codec, nobody had ever run them, and
the project's notes recorded them as advertised-but-untested — with the implied
worry that the driver was promising something it could not deliver.

It was delivering.

## Numbers

75 frames of the [test card](scaler-testcard.md) at 1280x720, decoded through
GStreamer's stateless V4L2 elements and compared against ffmpeg's software
decoder.

| codec | element | frames | luma PSNR vs software | bit-exact | VE interrupts |
| --- | --- | --- | --- | --- | --- |
| MPEG-2 progressive | `v4l2slmpeg2dec` | 75 / 75 | mean 72.70 dB, min 72.47 | 0 / 75 | **+75** |
| MPEG-2 **interlaced** | `v4l2slmpeg2dec` | 75 / 75 | mean 70.29 dB, min 70.04 | 0 / 75 | **+75** |
| VP8 | `v4l2slvp8dec` | 75 / 75 | — | **75 / 75** | **+75** |

The interlaced clip is 720x576 PAL, the classic MPEG-2 case, with a bar crossing
the frame at 700 px/s so the two fields genuinely differ.

**MPEG-2 is not bit-exact and that is correct.** MPEG-2 specifies an IDCT
*accuracy requirement* rather than an exact transform, so a conformant hardware
IDCT is permitted to differ slightly from any particular software one. 72 dB is
what that looks like. H.264, HEVC and VP8 all define exact integer
reconstruction, which is why VP8 comes back bit-exact and MPEG-2 does not.

## The check that makes it evidence

Frames on disk prove the pipeline ran, not that the hardware did anything. The
VE interrupt counter settles it: `/proc/interrupts` for `1c0e000.video-codec`
rises by **exactly 75 for 75 frames**, and the same clip through
`avdec_mpeg2video` moves it by **zero**. One interrupt per frame is this
engine's established signature.

Without the software control the delta would only have shown that *something*
touched the VE during the run.

## Interlaced, and the check that gives it meaning

Decoding with the fields swapped produces a picture that looks plausible, and
PSNR against a mostly-static card barely notices. So field order was tested for
directly: each hardware frame was rebuilt with its two fields exchanged and
re-scored against software.

| frame 37 | PSNR |
| --- | --- |
| as decoded | **70.45 dB** |
| fields swapped | **26.32 dB** |

A 44 dB gap. The test would unambiguously have caught a swap, which is what
makes "the field order is right" a result rather than an absence of evidence.
Without the moving bar the two fields would be identical and the same test would
have returned ~70 dB either way — passing while blind.

**What this covers, and what it does not.** Parsing the
`picture_coding_extension` of the stream shows all 75 pictures are
`picture_structure = 3`, FRAME pictures with field DCT and field motion
prediction, top-field-first. That is what DVDs and most broadcast MPEG-2 use.

### FIELD pictures: fixed, kernel patch 0123

**They work now.** What follows is what was wrong; the fix is two changes, both
needed.

| | mean luma PSNR vs ffmpeg | frames > 60 dB |
| --- | --- | --- |
| before | rejected outright, VE never ran | — |
| hold-capture-buffer granted | 35.73 dB | 0 / 31 |
| **plus half-height PICCODEDSIZE** | **63.70 dB** | **30 / 31** |

The per-frame profile after the fix is a clean GOP sawtooth — 69 dB at each
I-field, decaying to 62 by the end of the GOP, resetting at the next one. That
is what MPEG-2's IDCT accuracy tolerance looks like on a conformant decoder.
The single outlier is the last frame at 24 dB, whose bad macroblocks begin at
`(0, 22)` — exactly where ffmpeg reports `ac-tex damaged at 0 22` in this
sample. That frame is the stream's damage, not the decoder's.

Frame-picture MPEG-2 output is **byte-identical** before and after, progressive
and interlaced alike, because the new height applies only when
`picture_structure` is not FRAME.

**Second bug, found only after the first was fixed.** With the capability
granted the stream decoded, but the last macroblock row of every field was
wrong — a fixed cluster at the bottom right, present even in an intra picture
with no prediction history, and *not* where ffmpeg reported the stream's damage.
`PICCODEDSIZE`'s height field is macroblock ROWS, and a field picture has half
of them: the engine was told 36 rows where the field carried 18, and ran past
the end of its data.

### The truncated last frame, and why it stays

The sample's final picture is incomplete — the file ends with no
`sequence_end_code`, and with bottom-field-first that last picture is the top
field of frame 30. Which is exactly what the engine reports:

| | error register | correct macroblocks |
| --- | --- | --- |
| 61 pictures | `0x00000000` | `0x32a` = 810 = 45x18, a full field |
| last picture | `0x00000001` | `0x1ef` = **495 = 11x45** |

It stopped at field macroblock row 11 of 18 — the same place the pixel
comparison independently puts the corruption. The data is not there and cannot
be reconstructed; ffmpeg fills the gap from the reference frame, we leave the
buffer, and MPEG-2 defines no required behaviour for truncated input. Matching
ffmpeg would be copying a concealment policy, not fixing a defect.

**The error propagates correctly, verified at all three levels:**

1. the engine sets its error bit and reports 495 of 810 macroblocks;
2. the driver decides `VB2_BUF_STATE_ERROR` **exactly once**, on the field that
   releases the capture buffer (`src_hold=0`), so `v4l2_m2m_buf_done()` carries
   the state through rather than dropping it on a held buffer;
3. `strace` on the client shows **31 CAPTURE dequeues, exactly one flagged**,
   and it is the 31st:

```
VIDIOC_DQBUF {type=V4L2_BUF_TYPE_VIDEO_CAPTURE, index=0, ...
              flags=V4L2_BUF_FLAG_MAPPED|V4L2_BUF_FLAG_ERROR|...}
```

GStreamer then passes the partial frame downstream anyway. That is a userspace
policy choice — the flag is there for a client that wants to act on it — and
not a driver defect.

That one is worth remembering as a method note. The first fix produced output
that looked like success — right frame count, right interrupt count, correct
field parity — and was still wrong in a way only a pixel comparison caught.

### Why it was refused in the first place

Tested with `samples.ffmpeg.org/MPEG2/mpeg2_field_encoding.ts` (781 KB, md5
`66f0a668713955d370aa4050b63088c3`, kept in the ignored `local/video-samples/`).
Parsing it confirms real field coding: **31 TOP FIELD + 31 BOTTOM FIELD
pictures, zero frame pictures**, 720x576 PAL, bottom-field-first.

```
ERROR: v4l2slmpeg2dec: Driver did not accept the decode request.
VE interrupts delta = 0
```

The hardware never ran. No kernel message either, so this is not
`cedrus_request_validate()` refusing — it is a QBUF-level rejection.

**The cause is one switch in `cedrus_s_fmt_vid_out_p()`:**

```c
case V4L2_PIX_FMT_H264_SLICE:
case V4L2_PIX_FMT_HEVC_SLICE:
        vq->subsystem_flags |= VB2_V4L2_FL_SUPPORTS_M2M_HOLD_CAPTURE_BUF;
        break;
default:
        vq->subsystem_flags &= ~VB2_V4L2_FL_SUPPORTS_M2M_HOLD_CAPTURE_BUF;
```

Two coded fields have to land in **one** capture buffer, which means holding
that buffer across the first field's job — `V4L2_BUF_FLAG_M2M_HOLD_CAPTURE_BUF`.
Cedrus grants the capability to H.264 and HEVC and explicitly clears it for
everything else, so the decoder cannot express "this is only half a frame".

Confirmed per format on the device with
[`tools/video/v4l2-holdcap-probe.c`](../../tools/video/v4l2-holdcap-probe.c),
rather than read off the source alone:

| OUTPUT format | REQBUFS capabilities | hold capture buffer |
| --- | --- | --- |
| `MG2S` MPEG-2 | `0x1d` | **no** |
| `S264` H.264 | `0x3d` | yes |
| `S265` HEVC | `0x3d` | yes |
| `VP8F` VP8 | `0x1d` | **no** |

This is upstream cedrus behaviour, not an H713 quirk, and it is a deliberate
exclusion rather than an oversight. Supporting field pictures would mean adding
MPEG-2 to that switch **and** teaching `cedrus_mpeg2.c` to program the second
field into the same buffer at the right line offset — real work, for a codec no
VA profile on this device exposes.

### Generating one locally was impossible

ffmpeg's `mpeg2video` encoder only ever emits frame pictures; the parse above
confirms it. mjpegtools' `mpeg2enc` does have a per-field mode, `-I 2`, and it
**segfaults**:

```
Program received signal SIGSEGV
#0  MacroBlock::FieldME() () from /usr/lib/libmpeg2encpp-2.2.so.0
#1  MacroBlock::MotionEstimateAndModeSelect()
#2  Despatcher::Despatch(Picture&, ...)
```

Field motion estimation, inside mjpegtools 2.2.1. Every option combination tried
crashes identically — `-f 0/3/8`, `-N 0`, `-R 0`, `-M 1`, `-g 1 -G 1` — while
`-I 1` (interlaced *frame* pictures) encodes fine on the same input. It is a bug
in the one code path we need.

So a field-picture vector has to come from a conformance suite or a real
broadcast capture. Until one exists, this is untested and should not be claimed
either way. It is also the likeliest place for a fault: nothing in
`cedrus_mpeg2.c` combines two coded fields into one capture buffer — it forwards
`picture_structure` to the hardware and decodes one OUTPUT buffer into one
CAPTURE buffer.

## Method, which was much cheaper than expected

The obstacle was assumed to be the VA driver: its `src/mpeg2.c` is still on the
pre-stabilisation control uAPI, and porting it looked like the price of finding
out — the same rewrite HEVC needed. It was not necessary. GStreamer's
`v4l2codecs` plugin talks straight to the kernel:

```sh
gst-launch-1.0 -q filesrc location=clip.m2v ! mpegvideoparse \
    ! v4l2slmpeg2dec ! video/x-raw,format=NV12 ! filesink location=hw.raw
gst-launch-1.0 -q filesrc location=clip.webm ! matroskademux \
    ! v4l2slvp8dec ! video/x-raw,format=NV12 ! filesink location=hw.raw
```

VP8 needs no parser element — the demuxer emits whole frames. Both negotiate
either the tiled `NV12_32L32` or linear `NV12`; force the latter with a caps
filter to compare against a software reference directly.

The board carries `v4l2slh264dec`, `v4l2slh265dec`, `v4l2slmpeg2dec`,
`v4l2slvp8dec` and `v4l2slvp8alphadecodebin`, so this route is available for any
codec the kernel advertises, whatever the VA driver supports.

## What follows

- **Keep both capabilities.** There is no correctness case for an H713 variant
  that drops them. A variant may still be worth adding to give POLYPHASE a home
  instead of the `of_machine_is_compatible()` patch-up, but that is tidiness,
  not a fix.
- **The default-format question is now cosmetic.** MPEG-2 is the default OUTPUT
  format because it is first in `cedrus_formats[]`, and that is why
  v4l2-compliance probes a context where `cedrus_can_scale()` is false and
  reports `Scaling: Not Supported`. Reordering the array to make one test
  reachable would change the default for every SoC, and now has no correctness
  argument behind it. Leave it, or make the test reachable another way.
- **VA-API exposure is a separate, optional question.** Porting `mpeg2.c` to the
  stabilised uAPI is now known to be worth something rather than speculative,
  but GStreamer already reaches both codecs, and neither is likely to matter on
  this device.

## Limits

- One clip per codec, 1280x720, progressive, generated by ffmpeg rather than
  taken from a conformance suite. This establishes "the hardware decodes it
  correctly", not "every stream in the wild decodes".
- Interlaced MPEG-2 works as FRAME pictures and, since patch 0123, as FIELD
  pictures. The only field-coded sample available is partly damaged, so the
  63.70 dB figure carries that stream's own corruption in its last frame; a
  clean field-coded vector would tighten it.
- VP8 alpha (`v4l2slvp8alphadecodebin`) was not tested.
- Neither codec was tried through the scaler: `cedrus_can_scale()` admits only
  H.264 and HEVC, so a scaled or cropped MPEG-2 capture is not reachable and was
  not attempted.
