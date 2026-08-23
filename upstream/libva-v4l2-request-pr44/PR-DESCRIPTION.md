<!--
Use this if you open a PULL REQUEST (as well as, or instead of, the comment in
PR-COMMENT.md). Target the PR #44 branch, NOT master -- the change assumes its
HEVC port is present. Title first, then everything below the `---` is the body.
-->

**Title:** `h265: pass the scaling matrix`

---

Builds on #44. `V4L2_CID_STATELESS_HEVC_SCALING_MATRIX` is never set, so a
stream whose SPS has `scaling_list_enabled_flag = 1` is decoded against flat
matrices. The failure is quiet — not a stall or a rejected control, but a decode
that runs to completion with the wrong quantisation.

`picture.c` already copies the client's `VAIQMatrixBufferHEVC` into
`surface_object->params.h265.iqmatrix` and sets `iqmatrix_set`. Nothing read it.
(Neither tree ever did: #38's `h265.c` mentions `iqmatrix` only in a declaration
block it never uses, and #44 removed the dead declarations.)

**No scan conversion is needed**, which is the opposite of what the bitstream
syntax suggests. HEVC codes scaling lists in up-right diagonal order, but both
APIs specify raster — `va_dec_hevc.h` says *"Matrix entries are in raster scan
order which follows HEVC spec"* and the V4L2 control's kernel doc says
*"expected in raster scan order"* for every member. ffmpeg's parser has already
undone the scan (`scaling_list_data()` in `libavcodec/hevc/ps.c`;
`vaapi_hevc.c` copies across unchanged — checked in 6.1 and 7.1). The 32x32 pair
is matrixId 0 and 3 on both sides.

The control is set only when the client actually sent a matrix, as `mpeg2.c`
already does for its quantiser matrices.

### Testing

Allwinner H713 (Cedrus, kernel 6.18.38), unmodified ffmpeg 7.1.5, libva 1.22,
on this PR rebased onto #38 for its format ordering. Two x265 vectors at
640x480, 25 frames — `--scaling-list default` (implicit HEVC default lists) and
a custom list file (non-flat at 4x4, DC coefficients differing from their own
matrix):

| vector | before | after |
| --- | --- | --- |
| default lists | MISMATCH, ve+25 | **bit-exact**, ve+25 |
| custom lists + DC | MISMATCH, ve+25 | **bit-exact**, ve+25 |

`ve+25` is the video engine's interrupt count: all 25 frames really decoded on
the hardware in both runs. GStreamer's `v4l2slh265dec` was bit-exact on both
throughout, so the kernel side was never at fault. Three non-scaling-list HEVC
vectors and a five-step H.264 ladder are unregressed.

Worth knowing for anyone adding a test: a stream encoded with x265's defaults
has `scaling_list_enabled_flag = 0`, and cedrus writes its scaling SRAM only
when that flag is set — so a driver that passes no matrix at all still scores
bit-exact. The gap is invisible without a vector that enables scaling lists.
