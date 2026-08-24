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
#
# Streams are Annex-B elementary (.h264/.h265) because the target has no
# container demuxer in the decode path -- keep the test about the decoder.
#
# References are NV12, which is what cedrus emits, so a target-side capture can
# be compared byte-for-byte rather than eyeballed.
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

# h07 -- Main10. It decodes: the engine writes an 8-bit plane plus a separate
# 2-bit plane, and the 8-bit plane is a correct rendition (57 dB PSNR against
# this software reference). It is NOT scored by md5 for that reason -- the VE
# truncates where swscale dithers -- so it lives in hevc-10bit-test.sh rather
# than the H1 gate. 10 frames is plenty; this is a format question, not an
# endurance one.
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=640x480:rate=25" -frames:v 10 \
  -pix_fmt yuv420p10le -c:v libx265 -profile:v main10 \
  -x265-params "log-level=error:keyint=5" -f hevc h07-640x480-main10.h265
echo "==> h07-640x480-main10  (640x480, 10 frames, main10) $(stat -c%s h07-640x480-main10.h265) bytes"

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
