#!/bin/bash
# Headless H.265 scale/rotate check -- RUNS ON THE BOARD.
#
# Same four-quadrant method as the H.264 rotation check: decode a card whose
# quadrants are constant luma and sample the centre of each output quadrant, so
# the result is a number rather than a look at the panel.
#
# The card is built once with:
#   ffmpeg -f lavfi -i color=black:size=64x32 -f lavfi -i color=white:size=64x32 \
#          -f lavfi -i color=red:size=64x32   -f lavfi -i color=blue:size=64x32 \
#          -filter_complex "[0:v][1:v]hstack[t];[2:v][3:v]hstack[b];[t][b]vstack,format=yuv420p" \
#          -frames:v 1 -c:v libx265 -crf 12 -f hevc quad128x64.h265
#
# As of 2026-09-16 this FAILS on everything except rotate=0, because enabling
# the H.265 secondary output hangs the VE -- see
# docs/reference/h265-sdrt-field-layout-2026-09-16.md.  rotate=0 passing proves
# nothing: cedrus_transforming() is false there, so the path under test never
# runs.
cd /mnt/media-data
export LIBVA_DRIVER_NAME=v4l2_request
run() {  # $1=rotation $2=compose WxH $3=expected "TL TR BL BR"
  rm -f /tmp/hr.nv12
  err=$(CEDRUS_ROTATE=$1 CEDRUS_COMPOSE=$2 CEDRUS_DUMP=/tmp/hr.nv12 \
        LD_PRELOAD=./compose-probe.so \
        ffmpeg -hide_banner -loglevel error -hwaccel vaapi \
               -hwaccel_output_format vaapi -f hevc -i quad128x64.h265 \
               -frames:v 1 -f null - 2>&1 | grep compose-probe | head -1)
  echo "rot=$1 compose=$2 | $err"
  python3 - "$2" "$3" "$err" <<'PY'
import sys, re
compose, expect, err = sys.argv[1], sys.argv[2], sys.argv[3]
w, h = (int(x) for x in compose.split('x'))
m = re.search(r'stride=(\d+)', err)
stride = int(m.group(1)) if m else w
try:
    d = open('/tmp/hr.nv12','rb').read()
except FileNotFoundError:
    print('    NO DUMP'); raise SystemExit
pts = [(w//4, h//4), (3*w//4, h//4), (w//4, 3*h//4), (3*w//4, 3*h//4)]
got = [d[y*stride + x] for x, y in pts]
want = [int(v) for v in expect.split()]
ok = all(abs(g-e) <= 2 for g, e in zip(got, want))
print("    sampled %s  expected %s  -> %s" % (got, want, "PASS" if ok else "FAIL"))
PY
}
run 0   128x64 "16 235 81 41"
run 90  64x128 "81 16 41 235"
run 180 128x64 "41 81 235 16"
run 270 64x128 "235 41 16 81"
