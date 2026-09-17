# MPEG-2 and VP8 on H713 — both work

**Result: the inherited capabilities are legitimate.** H713 decodes MPEG-2 and
VP8 in hardware. Neither should be removed.

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

**FIELD pictures** — `picture_structure` 1 or 2, where each coded picture is a
single field and two of them combine into one frame — are **not tested**.
ffmpeg's `mpeg2video` encoder cannot produce them, so a vector has to come from
elsewhere. Nothing in `cedrus_mpeg2.c` combines two coded fields into one
capture buffer; it forwards `picture_structure` to the hardware and decodes one
OUTPUT buffer into one CAPTURE buffer. Whether that is sufficient is an open
question, not a claim in either direction.

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
- Interlaced MPEG-2 is tested as FRAME pictures only. Field pictures are not,
  and are the case most likely to be broken.
- VP8 alpha (`v4l2slvp8alphadecodebin`) was not tested.
- Neither codec was tried through the scaler: `cedrus_can_scale()` admits only
  H.264 and HEVC, so a scaled or cropped MPEG-2 capture is not reachable and was
  not attempted.
