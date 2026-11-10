# Report for bootlin/libva-v4l2-request PR #44 — draft, not posted

Written 2026-08-22. This is a **draft of a comment to post on the upstream PR**,
kept in the repo so the claims can be checked before anything is published. It
is written to be read by someone who has never seen this project.

Everything in it was verified against the PRs' own trees at the heads below, not
recalled from our merged tree — and doing that changed two of the four items,
which is exactly why it was worth doing. See "What checking changed" at the end.

| | |
| --- | --- |
| PR #44 head | `c488d8df` "Added HEVC" |
| PR #38 head | `1c5f2cad` "Don't advertise broken profiles" (our base) |
| hardware | Allwinner H713 (sun50iw12), Cedrus VE, no IOMMU on the VE |
| kernel | 6.18.38, mainline `sunxi-cedrus` staging driver |
| userspace | stock ffmpeg 7.1.5, libva 1.22, no patches to either |
| our patches | <https://github.com/…/patches/libva-v4l2-request> (0001–0005) |

---

## Post this

**Subject: #44 cannot decode on cedrus without #38's format ordering — plus one
functional bug, one wrong flag derivation, and a merge hazard**

I ported this PR onto PR #38 to get HEVC working on an Allwinner H713 (Cedrus,
kernel 6.18.38, stock ffmpeg 7.1.5). It works: **HEVC now decodes bit-exact on
the video engine through unmodified ffmpeg**, five vectors, with GStreamer's
`v4l2slh265dec` scoring the same on the same streams as an oracle. Thank you for
the port — the reference-picture-set restructure in particular is the part that
carried the design risk, and it is correct.

Four things are worth reporting back.

### 1. On cedrus, #44 alone decodes nothing — H.264 or HEVC — because of format ordering

This one is structural, not a tuning issue, and it will hit anyone testing this
PR on a stateless V4L2 decoder.

`RequestCreateSurfaces2()` sets the **CAPTURE** format (`src/surface.c:103`),
and the **OUTPUT** (coded) format is only set later, in `RequestCreateContext()`
(`src/context.c:117`). Modern libva clients create surfaces before the context —
ffmpeg does — so the driver sees CAPTURE first.

The V4L2 stateless decoder interface requires the opposite order: the coded
format goes on OUTPUT first, and the CAPTURE format is *derived* from it
(`Documentation/userspace-api/media/v4l/dev-decoder.rst`, "Initialization").
cedrus enforces it in `cedrus_s_fmt_vid_out()`. What we measured:

- the CAPTURE format is clamped to **16x16**, because at that point the driver
  has no coded resolution to derive from;
- the later `S_FMT` on OUTPUT then returns **EBUSY**.

PR #38 does it the other way round — `src/surface.c:87` sets OUTPUT, then :121
sets CAPTURE, both inside `RequestCreateSurfaces2()`, with a comment saying the
format must be set before any buffer is created. That ordering is what makes
this PR's HEVC work here, and I think it belongs in #44 regardless of which base
lands first.

### 2. The HEVC scaling matrix is never passed — streams with scaling lists decode wrong

`V4L2_CID_STATELESS_HEVC_SCALING_MATRIX` is never set, so any stream whose SPS
has `scaling_list_enabled_flag = 1` is decoded against flat matrices. The output
is not garbage — it is a completed decode with the wrong quantisation, which is
harder to notice.

To be fair to this PR: **neither tree ever passed it.** #38's `h265.c` mentions
`iqmatrix` three times, all in the declaration block of `h265_set_controls()`,
and then sets three controls, none of which is a scaling matrix; #44's rewrite
removed the unused declarations. `picture.c` on both sides already copies the
client's `VAIQMatrixBufferHEVC` into the surface. Nothing read it.

Two details that may save someone the same detour:

- **No scan conversion is needed**, which is the opposite of what the bitstream
  syntax suggests. HEVC codes scaling lists in up-right diagonal order, but both
  APIs specify raster — `va_dec_hevc.h`: *"Matrix entries are in raster scan
  order which follows HEVC spec"*; the V4L2 control's kernel doc: *"expected in
  raster scan order"* for every member. ffmpeg's `scaling_list_data()`
  (`libavcodec/hevc/ps.c`) already stores each coefficient at its raster
  position and `vaapi_hevc.c` copies the arrays across unchanged (checked in 6.1
  and 7.1). So the driver's job is a straight copy, and the 32x32 pair is
  matrixId 0 and 3 on both sides.
- **The obvious test vectors cannot catch this.** Anything encoded with x265's
  defaults has `scaling_list_enabled_flag = 0`, and cedrus writes its scaling
  SRAM only when that SPS flag is set — so a driver that fills nothing at all
  still scores bit-exact. Two vectors close it: `x265 --scaling-list default`
  (implicit HEVC default lists, non-flat from 8x8 up) and an explicit custom
  list file (non-flat at 4x4 as well, with DC coefficients that differ from
  their own matrix — the default DCs are all 16, so the first vector is blind to
  those two fields). Both went `MISMATCH … ve+25` before the fix and bit-exact
  after; `ve+25` is the VE's interrupt count, i.e. the engine really decoded all
  25 frames both times.

Patch: [`0005-h265-pass-the-scaling-matrix.patch`](../../patches/libva-v4l2-request/0005-h265-pass-the-scaling-matrix.patch).
It is ~40 lines and I am happy to open it as a PR against this branch if useful.

### 3. `V4L2_HEVC_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT` is derived backwards

`src/h265.c:117`:

```c
if (picture->slice_parsing_fields.bits.deblocking_filter_override_enabled_flag ||
    !picture->slice_parsing_fields.bits.pps_disable_deblocking_filter_flag)
        pps->flags |= V4L2_HEVC_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT;
```

VA-API does not expose `deblocking_filter_control_present_flag`, so a derivation
is unavoidable — but this one sets the flag whenever deblocking is *enabled*,
which is the common case, and so reports "control present" for streams whose PPS
says 0. One of our vectors is exactly that (`deblocking_filter_control_present`
= 0, `override_enabled` = 0, `pps_disable` = 0 → flag set).

The spec makes a strictly-safe derivation available: both
`deblocking_filter_override_enabled_flag` and
`pps_deblocking_filter_disabled_flag` are only *present* in the PPS when
`deblocking_filter_control_present_flag` is 1, so either one being set implies
it, and neither being set leaves it genuinely unknowable from VA-API:

```c
if (…override_enabled_flag || …pps_disable_deblocking_filter_flag)
```

That is never wrong, where the current form frequently is. It happens to be
inert on cedrus, which references neither flag — I only found it by dumping the
controls the driver received. On another driver it would not be inert.

(`V4L2_HEVC_PPS_FLAG_UNIFORM_SPACING` is never set either, but I do **not**
think that is a bug: VA-API exposes no `uniform_spacing_flag`, and it says the
application populates `column_width_minus1[]`/`row_height_minus1[]` even when
spacing is uniform. Leaving the flag clear and passing the explicit sizes — what
this PR does — is the right fallback.)

### 4. Merge hazard on top of #38: an uninitialised `h264_start_code`

Not a #44 bug — #44 has no start-code handling at all — but it is what a merge
of the two produces, and it cost me the most time, so it is worth flagging.

In #38, `context->h264_start_code` decides whether an Annex-B start code is
prepended to each slice, and **it is assigned nowhere**: `h264_get_controls()`,
which would set it, is defined and never called. The value read is whatever the
heap held. H.264 had been decoding bit-exact purely because that happened to be
zero.

When it is not zero, a start code is prepended, and #44's HEVC path then reads
the NAL header from it:

```c
b = source_data + slice->slice_data_offset;
nal_unit_type = (b[0] >> H265_NAL_UNIT_TYPE_SHIFT) & H265_NAL_UNIT_TYPE_MASK;
```

`b[0]` is now the `0x00` of the start code, so `nal_unit_type` is 0 —
`TRAIL_N`, a *non-reference* picture — which cedrus passes straight to the
hardware in `VE_DEC_H265_DEC_NAL_HDR_NAL_UNIT_TYPE()`. The read itself is
correct in #44's own tree, where nothing prepends anything.

cedrus accepts only `START_CODE_NONE`, for both codecs (`.max` and `.def` are
`NONE` for `V4L2_CID_STATELESS_H264_START_CODE` and the HEVC control alike).
Querying the per-codec `START_CODE` control is the correct general fix; we set
the flag explicitly to false, which is right for cedrus and not for everyone.

### What does work, for the record

With the above, on H713/cedrus/6.18.38 through stock ffmpeg:

```
h01-640x480-main            PASS bit-exact, ve+25
h02-1280x720-main           PASS bit-exact, ve+25   (WPP on)
h03-640x480-nowpp           PASS bit-exact, ve+25
h04-640x480-scaling         PASS bit-exact, ve+25   (default scaling lists)
h05-640x480-scaling-custom  PASS bit-exact, ve+25   (custom lists + DC)
```

H.264 is unregressed at 5/5 on the same driver.

One incidental finding: **entry point offsets are not needed**, at least via
ffmpeg. `num_entry_point_offsets` is reported as 0 even for WPP streams
(`entropy_coding_sync_enabled_flag = 1`), and h01/h02 are bit-exact without
`V4L2_CID_STATELESS_HEVC_ENTRY_POINT_OFFSETS` ever being filled. They
parallelise WPP substreams; they are not required for correctness.

Not covered here: 10-bit. That is blocked in the kernel rather than in this
driver — `cedrus_video.c` exposes no 10-bit capture format at all, so nothing
can negotiate one.

---

## What checking changed (kept out of the posted text)

Two claims from our own commit messages did not survive being checked against
the upstream trees, and both would have been wrong to post:

1. **"#44 dropped the iqmatrix handling."** False. #38 never had it either — its
   `h265.c` declares `iqmatrix`/`iqmatrix_set` and never reads them. Corrected
   in patch 0005's message, the patches README and `docs/vaapi-scope.md`.
2. **"The coded pixelformat was hardcoded to `V4L2_PIX_FMT_H264_SLICE`."** True
   of *our* base (#38 sets it in `surface.c`), **not** of #44, whose
   `context.c:95-115` switches on the profile and sets `V4L2_PIX_FMT_HEVC_SLICE`
   for `VAProfileHEVCMain`. That bug is ours-plus-#38's, and reporting it to #44
   would have been simply incorrect. It is not in the posted text.

A third was softened: `UNIFORM_SPACING` "is never set" is true but is not a bug,
because VA-API exposes no such flag and supplies the explicit tile sizes anyway.

The remaining two — format ordering and the scaling matrix — were confirmed
directly in `c488d8df`.
