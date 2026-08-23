<!--
POST THIS AS A COMMENT on https://github.com/bootlin/libva-v4l2-request/pull/44
Everything below the line is the comment body, ready to paste verbatim.
Nothing in it refers to this repository or needs editing first, except the
one bracketed link at the end if you want to point at the branch.
-->

---

I ported this PR onto PR #38 to get HEVC decoding on an Allwinner H713 (Cedrus,
kernel 6.18.38), driven by **unmodified** ffmpeg 7.1.5 through libva 1.22. It
works — HEVC decodes **bit-exact on the video engine**, five vectors, with
GStreamer's `v4l2slh265dec` scoring identically on the same streams as an
oracle. Thanks for doing the port; the reference-picture-set restructure is the
part that carried the real design risk, and it is correct.

Four things worth reporting back.

## 1. On cedrus, this PR alone decodes nothing — H.264 or HEVC — because of format ordering

Structural rather than a tuning issue, and it will hit anyone testing this PR on
a stateless V4L2 decoder.

`RequestCreateSurfaces2()` sets the **CAPTURE** format (`src/surface.c:103`),
and the **OUTPUT** (coded) format is only set later, in `RequestCreateContext()`
(`src/context.c:117`). Modern libva clients create surfaces before the context —
ffmpeg does — so the driver sees CAPTURE first.

The V4L2 stateless decoder interface requires the opposite: the coded format
goes on OUTPUT first and the CAPTURE format is *derived* from it
(`Documentation/userspace-api/media/v4l/dev-decoder.rst`, "Initialization").
cedrus enforces it in `cedrus_s_fmt_vid_out()`. What that produces here:

- the CAPTURE format is clamped to **16x16**, the driver having no coded
  resolution to derive from yet;
- the subsequent `S_FMT` on OUTPUT returns **EBUSY**.

PR #38 does it the other way round — `src/surface.c:87` sets OUTPUT, then :121
sets CAPTURE, both inside `RequestCreateSurfaces2()`, with a comment noting the
format must be set before any buffer exists. That ordering is what makes this
PR's HEVC work here, and I think it belongs in #44 regardless of which base
lands first.

## 2. The HEVC scaling matrix is never passed — streams with scaling lists decode wrong

`V4L2_CID_STATELESS_HEVC_SCALING_MATRIX` is never set, so any stream whose SPS
has `scaling_list_enabled_flag = 1` is decoded against flat matrices. The
failure is quiet: not a stall or a rejected control, but a decode that runs to
completion with the wrong quantisation.

In fairness to this PR, **neither tree ever passed it** — #38's `h265.c`
mentions `iqmatrix` three times, all in the declaration block of
`h265_set_controls()`, and then sets three controls, none of them a scaling
matrix; this PR removed the unused declarations. `picture.c` already copies the
client's `VAIQMatrixBufferHEVC` into the surface on both sides. Nothing read it.

Two details that may save someone the same detour:

- **No scan conversion is needed**, which is the opposite of what the bitstream
  syntax suggests. HEVC codes scaling lists in up-right diagonal order, but both
  APIs specify raster — `va_dec_hevc.h`: *"Matrix entries are in raster scan
  order which follows HEVC spec"*; the V4L2 control's kernel doc: *"expected in
  raster scan order"* for every member. ffmpeg's parser has already undone the
  scan (`scaling_list_data()` in `libavcodec/hevc/ps.c` stores each coefficient
  at its raster position; `vaapi_hevc.c` copies the arrays across unchanged —
  checked in 6.1 and 7.1). So it is a straight copy, and the 32x32 pair is
  matrixId 0 and 3 on both sides.
- **The obvious test vectors cannot catch this.** Anything encoded with x265's
  defaults has `scaling_list_enabled_flag = 0`, and cedrus writes its scaling
  SRAM only when that SPS flag is set — so a driver passing no matrix at all
  still scores bit-exact. Two vectors close it: `x265 --scaling-list default`
  (implicit HEVC default lists, non-flat from 8x8 up) and an explicit custom
  list file (non-flat at 4x4 as well, with DC coefficients differing from their
  own matrix — the default DCs are all 16, so the first vector is blind to those
  two fields). Both read `MISMATCH … ve+25` before the fix and bit-exact after;
  `ve+25` is the VE's interrupt count, i.e. the engine really decoded all 25
  frames both times.

The patch is ~40 lines against this branch's `c488d8df`, and it builds and runs
on that head. Happy to open it as a PR if that is easier to review.

## 3. `V4L2_HEVC_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT` is derived backwards

`src/h265.c:117`:

```c
if (picture->slice_parsing_fields.bits.deblocking_filter_override_enabled_flag ||
    !picture->slice_parsing_fields.bits.pps_disable_deblocking_filter_flag)
        pps->flags |= V4L2_HEVC_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT;
```

VA-API does not expose `deblocking_filter_control_present_flag`, so an inference
is unavoidable — but this one sets the flag whenever deblocking is *enabled*,
which is the common case, and so claims "control present" for streams whose PPS
codes it as 0. One of my vectors is exactly that
(`deblocking_filter_control_present` = 0, `override_enabled` = 0, `pps_disable`
= 0 → flag set).

Per 7.3.2.3.1 both `deblocking_filter_override_enabled_flag` and
`pps_deblocking_filter_disabled_flag` are only *coded* when
`deblocking_filter_control_present_flag` is 1, so either being set implies it,
and neither being set leaves it genuinely unknowable from VA-API:

```c
if (…override_enabled_flag || …pps_disable_deblocking_filter_flag)
```

That is never wrong, where the current form frequently is. I should say plainly
that I have **not** validated this one: it is inert on cedrus, which references
neither this flag nor `UNIFORM_SPACING`, so my bit-exactness gate cannot score
it either way. I found it only by dumping the controls the driver received. On
another driver it would not be inert.

(`V4L2_HEVC_PPS_FLAG_UNIFORM_SPACING` is never set either, and I do **not**
think that is a bug: VA-API exposes no `uniform_spacing_flag`, and it has the
application populate `column_width_minus1[]`/`row_height_minus1[]` even when
spacing is uniform. Leaving the flag clear and passing explicit sizes — what
this PR does — is the right fallback.)

## 4. Merge hazard on top of #38: an uninitialised `h264_start_code`

Not a bug in this PR — it has no start-code handling at all — but it is what a
merge of the two produces, and it cost me the most time.

In #38, `context->h264_start_code` decides whether an Annex-B start code is
prepended to each slice, and **it is assigned nowhere**: `h264_get_controls()`,
which would set it, is defined and never called. The value read is whatever the
heap held; H.264 had been decoding bit-exact purely because that happened to be
zero.

When it is not zero, a start code is prepended, and this PR's HEVC path then
reads the NAL header out of it:

```c
b = source_data + slice->slice_data_offset;
nal_unit_type = (b[0] >> H265_NAL_UNIT_TYPE_SHIFT) & H265_NAL_UNIT_TYPE_MASK;
```

`b[0]` is now the `0x00` of the start code, so `nal_unit_type` is 0 —
`TRAIL_N`, a *non-reference* picture — which cedrus passes straight to the
hardware in `VE_DEC_H265_DEC_NAL_HDR_NAL_UNIT_TYPE()`. The read is correct in
this PR's own tree, where nothing prepends anything.

cedrus accepts only `START_CODE_NONE`, for both codecs (`.max` and `.def` are
`NONE` for `V4L2_CID_STATELESS_H264_START_CODE` and the HEVC control alike).
Querying the per-codec `START_CODE` control is the correct general fix; I set
the flag explicitly to false, which is right for cedrus and not for everyone.

## What does work, for the record

On H713 / cedrus / 6.18.38 through stock ffmpeg, with the above applied:

```
h01-640x480-main            PASS bit-exact, ve+25
h02-1280x720-main           PASS bit-exact, ve+25   (WPP on)
h03-640x480-nowpp           PASS bit-exact, ve+25
h04-640x480-scaling         PASS bit-exact, ve+25   (default scaling lists)
h05-640x480-scaling-custom  PASS bit-exact, ve+25   (custom lists + DC)
```

H.264 is unregressed at 5/5 on the same driver.

One incidental finding: **entry point offsets are not needed**, at least via
ffmpeg. `num_entry_point_offsets` comes through as 0 even for WPP streams
(`entropy_coding_sync_enabled_flag = 1`), and h01/h02 are bit-exact without
`V4L2_CID_STATELESS_HEVC_ENTRY_POINT_OFFSETS` ever being filled. Entry points
parallelise WPP substreams; they are not required for correctness.

Not covered here: 10-bit, which is blocked in the kernel rather than in this
driver — `cedrus_video.c` exposes no 10-bit capture format at all, so nothing
can negotiate one.
