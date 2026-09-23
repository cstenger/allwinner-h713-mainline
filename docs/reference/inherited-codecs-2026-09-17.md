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
- **VA-API exposure — DONE for MPEG-2** (libva patch 0011, hardware-validated
  2026-09-22). See "MPEG-2 through VA-API" below. VP8 remains GStreamer-only.

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

---

# MPEG-2 through VA-API (2026-09-22)

`src/mpeg2.c` spoke the pre-stabilisation interface — one
`V4L2_CID_MPEG_VIDEO_MPEG2_SLICE_PARAMS` control carrying a nested sequence and
picture — so `RequestCreateConfig` refused both profiles and nothing could reach
the decoder through VA-API. Libva patch **0011** ports it to
`V4L2_CID_STATELESS_MPEG2_{SEQUENCE,PICTURE,QUANTISATION}`.

## What the split forced

- **The picture booleans become one `flags` word**, and `bit_size`,
  `data_bit_offset` and `quantiser_scale_code` are gone — cedrus takes the
  bitstream extent from the buffer payload.
- **The quantisation matrices need driver-side state.** VA-API sends a `load_*`
  flag *per matrix* and leaves unloaded ones undefined; the V4L2 control is
  all-or-nothing. The driver now carries the matrices in force on the context,
  starts them at the ISO/IEC 13818-2 defaults, and overwrites only what the
  client loaded. That also matches MPEG-2 semantics, where a matrix persists
  until a quant matrix extension replaces it. Both APIs use zigzag order, so
  they copy straight across.
- **`SEQ_FLAG_PROGRESSIVE` is left clear.** VA-API carries `progressive_frame`
  but says nothing about the *sequence*, so it cannot be derived. cedrus does
  not read it.

## The bug that made the port look like a no-op

The first build changed nothing visible: `vainfo` listed the same seven
profiles as before. `RequestQueryConfigProfiles` had learned the two MPEG-2
profiles, but `RequestQueryConfigEntrypoints` still knew only H.264 and HEVC
and fell through to `*entrypoints_count = 0`.

**A profile with an empty entrypoint list is indistinguishable from an
unadvertised one** — `vainfo` drops it from its output and `vaCreateConfig` has
nothing to match. Adding a profile to one of those two functions and not the
other produces a driver that looks completely unported.

## Results

The oracle is `gst-launch-1.0 ... ! v4l2slmpeg2dec`, which drives the same
hardware through the kernel and needs none of this driver. Two hardware paths
should agree **bit-exactly**; hardware and software should *not*, because
MPEG-2 specifies IDCT accuracy rather than exact reconstruction.

| stream | kind | VA-API vs GStreamer | VE irq |
| --- | --- | --- | --- |
| `testcard-mpeg2.m2v` | progressive 1280x720 | **bit-exact** | +75 |
| `testcard-mpeg2i.m2v` | interlaced, frame pictures | **bit-exact** | +75 |
| `mm-short.mpg` | 720x576 real-world | **bit-exact** | +73 |
| `field.m2v` | field pictures | 30/31 frames bit-exact | +62 |
| `TITLE01-ANGLE1.VOB` | DVD extract, 720x576 | 197/198 frames bit-exact | +198 |

Software decode of the same streams gives a different md5 and moves the VE
interrupt counter by **zero**, so the matching hashes are the hardware's work
and not a silent fallback.

**Where these streams are** (established 2026-09-23, after an earlier claim that
two of them were lost — see the correction in `tools/video/vectors/README.md`):
`mm-short.mpg` and `TITLE01-ANGLE1.VOB` are in `local/video-samples/`, with the
`samples.ffmpeg.org/MPEG2/` manifest `md5sum.MPEG2` beside them. The VOB matches
that manifest and can be re-fetched upstream; `mm-short.mpg` does not and is a
local truncation to exactly 2,048,000 bytes. `testcard-mpeg2.m2v`,
`testcard-mpeg2i.m2v` and `field.m2v` came off the board's `/root/`; `field.m2v`
is now committed as `tools/video/vectors/m05-720x576-field.m2v`.

None of them is committed except m05, `local/` is gitignored, and nothing
regenerates any of them — so this table is reproducible only on a host that
still has those files. The committed MPEG-2 ladder (`mpeg2-decode-test.sh`,
m01–m06) exists to be the part that does not depend on that.

H.264 (5/5) and HEVC (12/12) remain bit-exact after the rebuild.

## The two incomplete frames are the streams', not ours

Neither file carries a `sequence_end_code`.

- **`field.m2v` frame 30** — divergence starts at luma row 352 and touches
  **only even rows** (112 even, 0 odd): the top field, at field macroblock row
  11 — exactly where the engine reported stopping, at 495 of 810 macroblocks.
- **`TITLE01-ANGLE1.VOB` frame 196** — starts at macroblock row 4, where ffmpeg
  reports `ac-tex damaged at 28 5` and calls the frame corrupt. The file's last
  picture start is 683 bytes from EOF.

The data is absent and MPEG-2 defines no behaviour for truncated input. The
undecoded region keeps whatever the client's buffer pool held, and the two
clients have different pools — both sit ~25 dB from software, i.e. equally
unlike ffmpeg's concealment. ffmpeg fills the gap from the reference frame;
matching it would be copying a concealment policy, not fixing a defect.

**To tell this apart from a real bug:** check that the divergence begins at the
macroblock row the engine reported stopping at. If it starts anywhere else, it
is not truncation.

## Robustness

Both truncation vectors (`field-shortfirst.m2v`,
`field-firstfield-damaged.m2v`) decode to a clean exit without wedging the VE,
and the good clip still produces its reference md5 afterwards.

## Not established — all closed, 2026-09-23

**The VA path surfaces no decoder-level error to the client.** CLOSED by libva
patch 0012 (`c193a4b`). The shim was discarding `V4L2_BUF_FLAG_ERROR` in
`v4l2_dequeue_buffer()`; it now returns `VA_STATUS_ERROR_DECODING_ERROR`
through `vaEndPicture`, which is what ffmpeg actually reads. Error counts track
the damage rather than merely being non-zero.

**Malformed-stream suite, soak, concurrency.** CLOSED (`f9fc0f3`). All three
now cover MPEG-2: `make-bad-streams.sh` gained an MPEG-2 source (b01–b08) plus
b09/b10, which are the two committed real-damage field-coded streams; soak runs
four MPEG-2 vectors; the concurrency pool carries m01 and field-coded m06.
Hardware: R1 26/26, C1 15/15, soak 234 iterations with zero software fallbacks.

## The scaler: MPEG-2 will not be wired to it, and the reason is not the obvious one

`cedrus_can_scale()` admits only `H264_SLICE` and `HEVC_SLICE`, which looks like
an arbitrary omission. It is not, but the first explanation reached for — "MPEG-2
is SD content, it needs upscaling, and the VE only downscales" — is **wrong**,
and worth recording as wrong because it is the plausible-sounding answer.
HD MPEG-2 exists (1080i broadcast), and downscaling it to this 1280x720 panel is
exactly the case the H.264/HEVC scaler was built for.

**The vendor does scale MPEG-2 in hardware.** `libawmpeg2.so` exports
`Mpeg2ComputeScaleRatio` and `Mpeg2SetRotateScaleBuf`. So the capability is real
and the omission is not "the hardware cannot".

**But it is the fixratio path, and fixratio cannot express what this panel
needs.** `Mpeg2ComputeScaleRatio` (40 bytes at `0x4509`) disassembles
**instruction-for-instruction identically** to `H264ComputeScaleRatio` (40 bytes
at `0x9d41`) — same opcodes, same immediates, same `cmp #3` / `movcc #1` /
`mov #2` structure. That function is already documented in
`ve-decode-time-scaledown-2026-09-11.md`: it returns 0 = none, 1 = half,
2 = quarter. Power-of-two only.

1920→1280 is 1.5x. Half gives 960x540, *below* panel height. This is precisely
the limitation that made H.264 and HEVC need the VE+0xf00 polyphase scaler
(patches 0118/0120) instead of the shifter — and MPEG-2 hits it identically.

**And there is no MPEG-2 precedent for the polyphase route.** The arbitrary-ratio
path needs a per-engine enable (H.264 uses `H264_CTRL` bit 11 plus
`VE_CHROMA_BUF_LEN` bit 29). `libawmpeg2.so` has no `ConfigNewScaler` and no
`ScaleCopyCoef` analogue — its only other scaler-adjacent symbol is
`dmcoeffrm_reg24`, which is the dequant-matrix register, not filter coefficients.
Routing MPEG-2 into VE+0xf00 would therefore be speculative RE with no vendor
implementation to check against, for a codec whose HD form is increasingly rare.

**Conclusion: not implemented, deliberately.** Not because MPEG-2 cannot be
scaled, but because the path that exists yields only 1/2 and 1/4 — neither of
which is the ratio this panel wants — and the path that yields the right ratio
has no reference to port.

**If it is ever wanted anyway**, the fixratio port is modest and well-bounded:
`Mpeg2SetRotateScaleBuf` is 508 bytes, the same SDROT family as H.264's
`H264ConfigureScaleRotateRegister` (432 bytes) which is already understood, and
the ratio computation needs no work at all since it is byte-identical to one
already ported. That buys 1080i → 960x540 or 480x270, and nothing else.
