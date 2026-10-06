#!/usr/bin/env bash
# Letterbox Phase 4 geometry stress clip: one VP9 stream whose picture size
# changes every few frames, for MINUTES minutes. RUNS ON THE HOST.
#
#   make-geometry-stress.sh OUT.ivf [MINUTES] [FRAMES_PER_SEGMENT]
#                                   (defaults 10 and 6, at 30 fps)
#
# Each size is encoded once as a SEGMENT of key-frame-led VP9 (ffmpeg
# testsrc2 with the size and its index burnt in, so a frame shown at the
# wrong geometry is recognisable); the segments are then joined by
# ivf-concat.py in a shuffled order, a fresh shuffle per cycle, with a
# fixed seed. Every join is a key frame with a new size: the mid-stream
# case kmssink renegotiates, and so a geometry commit on the video plane.
# Consecutive segments never repeat a size, so every join IS a transition.
#
# The sizes cover what plane-up (stock v4l2slvp9dec ! kmssink) puts on the
# plane: kmssink fits each into 1280x720 itself.
#
#   size        kmssink's destination      what the window layer does
#   1280x720    1280x720 at (0,0)          native, letterbox registers restored
#   1280x536    1280x536 at (0,92)         unity, letterboxed
#   960x720     960x720 at (160,0)         unity, pillarboxed
#   640x360     1280x720 at (0,0)          2x
#   852x480     1278x720 at (1,0)          1.5x, odd x rounded to even
#   720x576     900x720 at (190,0)         1.25x
#   352x288     880x720 at (200,0)         2.5x
#   320x240     960x720 at (160,0)         3x
#   1024x576    1280x720 at (0,0)          1.25x, 576 not a multiple of 16
set -euo pipefail
OUT=${1:?OUT.ivf}
MIN=${2:-10}
SEG=${3:-6}
HERE=$(cd "$(dirname "$0")" && pwd)
SIZES=(1280x720 1280x536 960x720 640x360 852x480 720x576 352x288 320x240 1024x576)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

i=0
for s in "${SIZES[@]}"; do
	w=${s%x*} h=${s#*x}
	ffmpeg -v error -f lavfi -i "testsrc2=size=${s}:rate=30" -frames:v "$SEG" \
		-vf "drawtext=text='${i} ${s}':fontsize=$((h / 6)):fontcolor=white:box=1:boxcolor=black:x=(w-tw)/2:y=(h-th)/2" \
		-c:v libvpx-vp9 -g "$SEG" -crf 63 -b:v 0 -deadline realtime -cpu-used 8 \
		-pix_fmt yuv420p -f ivf "$TMP/seg$i.ivf"
	i=$((i + 1))
done

# Shuffled order, never the same size twice in a row.
n=$(( MIN * 60 * 30 / SEG ))
mapfile -t order < <(python3 - "$n" "${#SIZES[@]}" <<'PY'
import random, sys
n, k = int(sys.argv[1]), int(sys.argv[2])
r = random.Random(713)
out, last = [], None
while len(out) < n:
    cyc = list(range(k))
    r.shuffle(cyc)
    if cyc[0] == last:
        cyc[0], cyc[-1] = cyc[-1], cyc[0]
    out += cyc
    last = cyc[-1]
for x in out[:n]:
    print(x)
PY
)
args=()
for x in "${order[@]}"; do args+=("$TMP/seg$x.ivf"); done
python3 "$HERE/ivf-concat.py" --fps 30 "$OUT" "${args[@]}"
echo "$OUT: ${#order[@]} segments of $SEG frames, $((${#order[@]} - 1)) transitions, $MIN min at 30 fps"
