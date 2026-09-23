#!/usr/bin/env bash
# Generate the H.264 test-vector ladder for H713 video-decode bring-up, plus a
# host-decoded reference frame set for each vector.
#
# The ladder exists because "the decoder produced output" and "the decoder
# produced the RIGHT output" are different claims, and this project has been
# burned by the gap before. Each step adds exactly one coding feature, so a
# failure names the feature that broke it instead of just failing.
#
#   v01  320x240   Constrained Baseline   I+P, CAVLC, no B      minimum viable
#   v02  1280x720  Constrained Baseline   I+P, CAVLC, no B      panel-native
#   v03  1280x720  Main                   + B-frames, CABAC     reference reorder
#   v04  1280x720  High                   + 8x8 transform       what real files use
#   v05  1920x1080 High                   real-world clip       integration test
#   h01  640x480   HEVC Main              8-bit                 HEVC minimum
#   h02  1280x720  HEVC Main              8-bit                 HEVC panel-native
#   m01  352x288   MPEG-2 Main            I+P, no B             MPEG-2 minimum
#   m02  720x576   MPEG-2 Main            + B-frames            DVD/PAL shape
#   m03  1280x720  MPEG-2 Main            progressive HD        HD progressive
#   m04  720x576   MPEG-2 Main            interlaced sequence   interlaced coding
#
# Streams are Annex-B elementary (.h264/.h265) because the target has no
# container demuxer in the decode path -- keep the test about the decoder.
# MPEG-2 is elementary (.m2v) for the same reason.
#
# References are NV12, which is what cedrus emits, so a target-side capture can
# be compared byte-for-byte rather than eyeballed.
#
# MPEG-2 IS THE EXCEPTION TO THAT LAST SENTENCE, and it matters. H.264, HEVC and
# VP8 all define exact integer reconstruction, so a host software decode is a
# correctness oracle and the target must match it bit-for-bit. MPEG-2 specifies
# an IDCT *accuracy requirement* instead, so a conformant hardware IDCT is
# allowed to differ from any particular software one -- about 72 dB PSNR here.
# The .nv12 written for an MPEG-2 vector is therefore a PSNR yardstick, NOT
# something to md5 against the target. The MPEG-2 regression baseline is the
# hardware's own pinned output in tools/video/mpeg2-reference-md5.txt; see
# mpeg2-decode-test.sh, which scores md5 against that and PSNR against this.
#
# One MPEG-2 vector cannot be generated at all: see the m05 note at the bottom.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT_DIR=${1:-$PROJECT_ROOT/local/video-test}
REAL_CLIP=${REAL_CLIP:-$PROJECT_ROOT/local/Madame Leota Complete Audio Loop - Edit.mp4}

command -v ffmpeg >/dev/null || { echo "error: ffmpeg not found on host" >&2; exit 1; }

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"

# Deterministic synthetic source: testsrc2 is reproducible frame-for-frame, so
# the reference YUV is a fixed artifact rather than something that drifts
# between runs. Motion matters -- a static scene never exercises inter
# prediction, which is most of what a decoder does.
gen() {
  local name=$1 w=$2 h=$3 frames=$4 profile=$5
  shift 5

  echo "==> $name  (${w}x${h}, $frames frames, $profile)"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=${w}x${h}:rate=30" -frames:v "$frames" \
    -pix_fmt yuv420p -c:v libx264 -profile:v "$profile" "$@" \
    -f h264 "$name.h264"

  # Host software decode -> NV12 reference. This is the ground truth the
  # target's output is scored against.
  ffmpeg -hide_banner -loglevel error -y \
    -i "$name.h264" -pix_fmt nv12 -f rawvideo "$name.nv12"

  printf '    stream %s bytes, reference %s bytes (%s frames of %d)\n' \
    "$(stat -c%s "$name.h264")" "$(stat -c%s "$name.nv12")" \
    "$(( $(stat -c%s "$name.nv12") / (w * h * 3 / 2) ))" "$frames"
}

# HEVC, same shape: deterministic source, Annex-B elementary stream, NV12
# reference decoded on the host. The VE decodes H.265 as well as H.264 -- both
# bit-exact -- and these are the vectors that established it.
#
# 10-bit is h07, below, and it DOES decode -- the comment that used to stand
# here ("Main10 does not decode ... zero frames") was wrong. cedrus writes an
# 8-bit plane plus a separate 2-bit plane; the 8-bit plane is a correct
# rendition. It is not scored by md5 because the engine truncates where swscale
# dithers. See docs/hevc-10bit-findings.md.
gen_hevc() {
  local name=$1 w=$2 h=$3 frames=$4 profile=$5 xtra=${6:-}
  shift 5; [ $# -gt 0 ] && shift
  # Extra x265 params are appended to the base set rather than passed as a
  # second -x265-params, which would silently override the first.
  local xp="log-level=error:keyint=10${xtra:+:$xtra}"

  echo "==> $name  (${w}x${h}, $frames frames, $profile)"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=${w}x${h}:rate=25" -frames:v "$frames" \
    -pix_fmt yuv420p -c:v libx265 -profile:v "$profile" \
    -x265-params "$xp" "$@" \
    -f hevc "$name.h265"

  ffmpeg -hide_banner -loglevel error -y \
    -i "$name.h265" -pix_fmt nv12 -f rawvideo "$name.nv12"

  printf '    stream %s bytes, reference %s bytes (%s frames of %d)\n' \
    "$(stat -c%s "$name.h265")" "$(stat -c%s "$name.nv12")" \
    "$(( $(stat -c%s "$name.nv12") / (w * h * 3 / 2) ))" "$frames"
}

# MPEG-2. Same deterministic source, same elementary-stream shape. -b:v and -g
# are pinned because the defaults have moved between ffmpeg releases and this
# has to regenerate byte-identically years from now.
#
# The .nv12 here is a PSNR yardstick, not an md5 reference -- see the header.
gen_mpeg2() {
  local name=$1 w=$2 h=$3 frames=$4
  shift 4

  echo "==> $name  (${w}x${h}, $frames frames, MPEG-2)"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=${w}x${h}:rate=25" -frames:v "$frames" \
    -pix_fmt yuv420p -c:v mpeg2video -b:v 5M -g 12 "$@" \
    -f mpeg2video "$name.m2v"

  ffmpeg -hide_banner -loglevel error -y \
    -i "$name.m2v" -pix_fmt nv12 -f rawvideo "$name.nv12"

  printf '    stream %s bytes, sw yardstick %s bytes (%s frames of %d)\n' \
    "$(stat -c%s "$name.m2v")" "$(stat -c%s "$name.nv12")" \
    "$(( $(stat -c%s "$name.nv12") / (w * h * 3 / 2) ))" "$frames"
}

# v01 -- the minimum. Constrained Baseline: no B-frames, no CABAC, no 8x8.
# If this does not decode, nothing else will, and the fault is fundamental.
gen v01-320x240-baseline 320 240 8 baseline \
  -x264-params "bframes=0:cabac=0:ref=1:weightp=0:8x8dct=0"

# v02 -- same coding tools at panel resolution. Separates "does not decode" from
# "does not decode at this size" (stride, buffer sizing, IOMMU mapping).
gen v02-1280x720-baseline 1280 720 60 baseline \
  -x264-params "bframes=0:cabac=0:ref=1:weightp=0:8x8dct=0"

# v03 -- adds B-frames and CABAC. Exercises reference list construction and
# output reordering, the part a stateless decoder's userspace gets wrong first.
gen v03-1280x720-main 1280 720 60 main \
  -x264-params "bframes=2:cabac=1:ref=3:8x8dct=0"

# v04 -- adds the 8x8 transform. This is what real-world High-profile files use.
gen v04-1280x720-high 1280 720 60 high \
  -x264-params "bframes=2:cabac=1:ref=3:8x8dct=1"

# h01/h02 -- HEVC Main, 8-bit. Both verified bit-exact against these references
# on the bench board (2026-08-16), through gst v4l2slh265dec with no driver
# changes, at ~550 fps for 720p.
gen_hevc h01-640x480-main   640 480 25 main
gen_hevc h02-1280x720-main 1280 720 25 main

# h03 -- the same source with WPP OFF, and the reason matters for the shim port.
# x265 enables wavefront parallel processing by DEFAULT (it prints
# `wpp(8 rows)` in its own tool line), so h01/h02 set
# entropy_coding_sync_enabled_flag and every slice carries entry point offsets.
# cedrus genuinely consumes those -- cedrus_h265.c copies them into a 4 KiB
# entry-points buffer and programs it -- so h01/h02 cannot decode without
# V4L2_CID_STATELESS_HEVC_ENTRY_POINT_OFFSETS being filled correctly.
#
# h03 removes that requirement, which makes it the simplest stream that can
# possibly decode and the right first milestone for porting src/h265.c: it
# separates "my control filling is wrong" from "I have not done entry points
# yet". Both are bit-exact through gst v4l2slh265dec today.
gen_hevc h03-640x480-nowpp  640 480 25 main wpp=0

# h04/h05 -- scaling lists, and the reason they exist is that h01-h03 cannot
# test them. All three have scaling_list_enabled_flag = 0, cedrus gates its
# write of V4L2_CID_STATELESS_HEVC_SCALING_MATRIX on that SPS flag, and so a
# decoder that never fills the control at all scores bit-exact on every one of
# them. That is how the shim shipped without it.
#
#   h04  --scaling-list default: the SPS enables scaling lists but carries no
#        data, so the HEVC default matrices (Table 7-5/7-6) apply. They are
#        non-flat from 8x8 up, which is enough to catch a matrix that is not
#        passed -- but every default DC coefficient is 16 and the 4x4 lists are
#        flat 16, so h04 alone cannot see a bug in those two fields.
#   h05  explicit custom lists from scaling-list-custom.txt, non-flat at every
#        size with DC values that differ from their own matrix. Covers what h04
#        is blind to, and exercises sps_scaling_list_data_present_flag = 1.
gen_hevc h04-640x480-scaling 640 480 25 main "scaling-list=default"
gen_hevc h05-640x480-scaling-custom 640 480 25 main \
  "scaling-list=$PROJECT_ROOT/tools/video/scaling-list-custom.txt"

# h06 -- lossless, i.e. transquant_bypass_enabled_flag = 1, a coding tool no
# other vector here uses. In lossless coding the transform and quantisation are
# skipped entirely for a CU, which is a different path through the VE than
# anything h01-h05 exercises. Named as an untested gap in the readiness review
# and closed here; TILES remain uncovered because x265 cannot produce them (it
# does WPP and slices only) and no tiling HEVC encoder is installed.
gen_hevc h06-640x480-lossless 640 480 25 main "lossless=1"

# h10 -- THE PITCH-ALIGNMENT GUARD, and the only vector here that is not a
# multiple of 32 wide. 656 is deliberately a multiple of 16 but NOT of 32,
# because that is exactly the distinction that can regress.
#
# The engine rounds VE_PRIMARY_FB_LINE_STRIDE_CHROMA -- which cedrus programs as
# bytesperline / 2 -- up to 16 in its own units, so the chroma stride it uses is
# ALIGN(bytesperline, 32). At a pitch that is 16- but not 32-aligned it writes
# chroma at the pitch and reads reference chroma a step wider: intra frames stay
# correct, every inter frame corrupts in chroma, and LUMA IS NEVER WRONG. A gate
# scoring luma, or only the first frame, cannot see it -- which is how it
# survived until 2026-09-23 with every vector in this file 640, 1280 or 1920
# wide. Patch 0125 and docs/reference/hevc-unaligned-chroma-2026-09-23.md.
#
# Keep this vector. Without it nothing stops the 32 in cedrus_video.c going
# back to 16, and the failure it guards against is invisible to every other
# check in the tree.
gen_hevc h10-656x480-unaligned 656 480 25 main

# h07 -- Main10. It decodes, and with the 2-bit side plane read back it is
# bit-exact 10 bit (hevc-10bit-verify.py). The 8-bit plane alone -- which is all
# a client can currently ask for -- is a correct 8-bit rendition, 57 dB against
# this software reference. It is NOT scored by md5 for that reason, so it lives
# in hevc-10bit-test.sh rather than the H1 gate. 10 frames is plenty; this is a
# format question, not an endurance one.
gen_hevc10() {
  local name=$1 w=$2 h=$3
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=${w}x${h}:rate=25" -frames:v 10 \
    -pix_fmt yuv420p10le -c:v libx265 -profile:v main10 \
    -x265-params "log-level=error:keyint=5" -f hevc "$name.h265"
  echo "==> $name  (${w}x${h}, 10 frames, main10) $(stat -c%s "$name.h265") bytes"
}

gen_hevc10 h07-640x480-main10 640 480

# h08 -- Main10 at a second resolution, so a layout result cannot come from one
# geometry. 720 is not a multiple of 32 and 480 is, which already differ.
gen_hevc10 h08-1280x720-main10 1280 720

# h09 -- THE ONE THAT CAN FAIL. 482 is 8 mod 16, so the coded height (488, a
# multiple of 8) and the capture canvas height (496, a multiple of 16) differ.
# The 2-bit chroma rows begin after coded_h luma rows, and reading them at the
# canvas height gives bit-exact luma with chroma 81.6% correct at maxerr 3 --
# 62.5 dB, which passes any PSNR threshold loose enough to be safe. h07 and h08
# cannot see that bug. Keep this vector: without it the 10-bit gate is decorative.
# 642 also makes DIV_ROUND_UP(width, 4) differ from width / 4.
gen_hevc10 h09-642x482-main10 642 482

# m01 -- the MPEG-2 minimum. I+P only, so a failure here is fundamental rather
# than a reordering or interlacing bug.
gen_mpeg2 m01-352x288-progressive 352 288 25 -bf 0

# m02 -- adds B-frames at DVD/PAL resolution, which is the shape almost all real
# MPEG-2 arrives in. Replaces the uncommitted real-world clip the earlier
# MPEG-2 work scored against.
gen_mpeg2 m02-720x576-progressive 720 576 50 -bf 2

# m03 -- progressive HD. Separates "MPEG-2 is broken" from "MPEG-2 is broken at
# this size", the same job v02 does for H.264.
gen_mpeg2 m03-1280x720-progressive 1280 720 50 -bf 2

# m04 -- interlaced SEQUENCE (progressive_sequence = 0) still coded as frame
# pictures, with interlaced ME and DCT. This is the coding mode, not the picture
# structure; m05 below is the one that changes picture_structure.
gen_mpeg2 m04-720x576-interlaced 720 576 50 -bf 2 -vf interlace -flags +ilme+ildct

# m05 -- FIELD PICTURES, and it is a committed binary rather than a generated
# one, deliberately.
#
# ffmpeg's mpeg2video encoder cannot emit them. Tested directly: +ilme+ildct,
# -vf interlace, -field_order tt, -alternate_scan and tinterlace=4, alone and in
# combination, all produce picture_structure = FRAME. The flags change
# progressive_sequence and the DCT, never the picture structure. (-top is
# rejected outright by ffmpeg 9: "not an encoding option".)
#
# That matters because field-coded MPEG-2 is exactly what kernel patch 0123
# exists for -- half-height PICCODEDSIZE and the held capture buffer -- so a
# ladder without it cannot fail when that patch regresses. The vector therefore
# ships as a file: tools/video/vectors/m05-720x576-field.m2v, 31 frames coded as
# 62 pictures (31 TOP + 31 BOTTOM), progressive_sequence = 0.
if [ -f "$PROJECT_ROOT/tools/video/vectors/m05-720x576-field.m2v" ]; then
  cp "$PROJECT_ROOT/tools/video/vectors/m05-720x576-field.m2v" m05-720x576-field.m2v
  ffmpeg -hide_banner -loglevel error -y \
    -i m05-720x576-field.m2v -pix_fmt nv12 -f rawvideo m05-720x576-field.nv12
  printf '==> m05-720x576-field  (committed binary, cannot be generated)\n'
  printf '    stream %s bytes, sw yardstick %s bytes\n' \
    "$(stat -c%s m05-720x576-field.m2v)" "$(stat -c%s m05-720x576-field.nv12)"
else
  echo "==> m05 MISSING: tools/video/vectors/m05-720x576-field.m2v not in the repo"
  echo "    Field-coded MPEG-2 (kernel patch 0123) is UNCOVERED without it."
fi

# m06 -- m05 with its damaged tail removed, and the reason it has to exist is
# that m05 cannot be scored by the VA-API-based suites.
#
# m05's last frame is damaged and carries no sequence_end_code. libva patch 0012
# reports that as a decode error and ffmpeg DROPS the frame, so the VA path emits
# 30 frames where GStreamer emits 31. Both are right and their first 30 frames
# are bit-identical (verified on hardware), but the whole-file md5s differ, so
# one vector cannot have one baseline across both paths.
#
# Rather than carry two baselines for one stream, cut m05 at the last clean
# frame boundary and terminate it properly. m06 decodes to the same 30 frames on
# both paths, which is what soak/concurrency/robustness need, while m05 stays in
# the M2 gate as the damaged-tail case. Byte surgery on a committed binary, so
# it is deterministic.
if [ -f m05-720x576-field.m2v ]; then
  python3 - <<'PY'
d = open('m05-720x576-field.m2v', 'rb').read()
codes, i = [], 0
while True:
    i = d.find(b'\x00\x00\x01', i)
    if i < 0 or i + 4 > len(d): break
    codes.append((i, d[i+3]))
    i += 3
pics = [off for off, sc in codes if sc == 0x00]
# 62 field pictures = 31 frames; keep 60 = 30 frames, dropping the damaged one.
idx = codes.index((pics[60], 0x00))
# Do not leave a dangling GOP/sequence/extension header at EOF.
while idx > 0 and codes[idx-1][1] in {0xB8, 0xB3, 0xB5, 0xB2}:
    idx -= 1
out = bytearray(d[:codes[idx][0]])
out += b'\x00\x00\x01\xb7'          # sequence_end_code -- m05 lacks one
open('m06-720x576-field-clean.m2v', 'wb').write(bytes(out))
print(f"==> m06-720x576-field-clean  (derived from m05: 30 of 31 frames, cleanly ended)")
print(f"    stream {len(out)} bytes")
PY
  ffmpeg -hide_banner -loglevel error -y \
    -i m06-720x576-field-clean.m2v -pix_fmt nv12 -f rawvideo m06-720x576-field-clean.nv12
  printf '    sw yardstick %s bytes\n' "$(stat -c%s m06-720x576-field-clean.nv12)"
fi

# v05 -- the real clip, first 60 frames, as the integration test. Not synthetic,
# so no exact reference; scored by eye on the panel and by PSNR against a host
# software decode of the same stream.
if [ -f "$REAL_CLIP" ]; then
  echo "==> v05-1920x1080-high  (real clip, first 60 frames)"
  ffmpeg -hide_banner -loglevel error -y -i "$REAL_CLIP" \
    -frames:v 60 -c:v copy -bsf:v h264_mp4toannexb -f h264 v05-1920x1080-high.h264
  ffmpeg -hide_banner -loglevel error -y -i v05-1920x1080-high.h264 \
    -pix_fmt nv12 -f rawvideo v05-1920x1080-high.nv12
  printf '    stream %s bytes, reference %s bytes\n' \
    "$(stat -c%s v05-1920x1080-high.h264)" "$(stat -c%s v05-1920x1080-high.nv12)"
else
  echo "==> v05 skipped: real clip not found at $REAL_CLIP"
fi

echo
echo "Test vectors in $OUT_DIR:"
ls -la "$OUT_DIR"
