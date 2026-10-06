#!/usr/bin/env bash
# Letterbox Phase 3 gate clips: pictures SMALLER than their fit, one per
# codec the plane decodes, two with anamorphic SAR. RUNS ON THE HOST.
#
#   make-upscale-clips.sh OUTDIR [SECONDS]
#
# The picture is letterbox-card.c's card at the clip's own size (square
# pixels; a SAR clip stretches it like any anamorphic source), with a small
# white square moving along the centre line so every frame differs and the
# plane keeps flipping. Audio is the 0.3 sine every tone clip uses. Each
# clip gets a reference render of what the panel should show
# (letterbox-reference.py panel), using h713-play's own fit arithmetic.
#
#   clip                              fit        proc ratio
#   up-640x360-h264.mp4               1280x720   2x
#   up-852x480-hevc.mp4               1278x720   1.5x
#   up-352x288-vp9.mp4                880x720    2.5x, 200-px bars
#   up-720x576-sar16x15-h264.mp4      960x720    1.333 H / 1.25 V, 160-px bars
#   up-720x480-sar32x27-av1.mp4       1280x720   1.778 H / 1.5 V
set -euo pipefail
OUT=${1:?OUTDIR}
SECS=${2:-10}
HERE=$(cd "$(dirname "$0")" && pwd)
REF="$HERE/../display/letterbox-reference.py"
mkdir -p "$OUT"

clip() {	# name w h sar_n sar_d encoder-args...
	local name=$1 w=$2 h=$3 sn=$4 sd=$5; shift 5
	python3 "$REF" card "$OUT/$name.card.png" "$w" "$h"
	ffmpeg -hide_banner -loglevel error -y \
		-loop 1 -framerate 30 -i "$OUT/$name.card.png" \
		-f lavfi -i "color=white:s=16x16:r=30" \
		-f lavfi -i "aevalsrc=0.3*sin(2*PI*440*t):s=48000:c=stereo" \
		-filter_complex "[0][1]overlay=x='mod(t*120,W-16)':y=(H-16)/2:shortest=1,format=yuv420p,setsar=$sn/$sd[v]" \
		-map "[v]" -map 2:a -t "$SECS" "$@" -c:a aac -b:a 128k "$OUT/$name.mp4"
	# h713-play's fit: display size W*sn x H*sd, aspect-fit into 1280x720, even
	local dw=$((w * sn)) dh=$((h * sd)) fw fh
	if [ $((dw * 720)) -ge $((dh * 1280)) ]; then
		fw=1280 fh=$(( (1280 * dh / dw + 1) / 2 * 2 ))
	else
		fh=720 fw=$(( (720 * dw / dh + 1) / 2 * 2 ))
	fi
	python3 "$REF" panel "$OUT/$name.ref.png" "$w" "$h" "$fw" "$fh" \
		$(( (1280 - fw) / 2 / 2 * 2 )) $(( (720 - fh) / 2 ))
	rm -f "$OUT/$name.card.png"
	echo "$name.mp4: ${w}x${h} sar $sn:$sd -> ${fw}x${fh}"
}

clip up-640x360-h264          640 360  1  1 -c:v libx264 -profile:v high -g 30 -crf 20
clip up-852x480-hevc          852 480  1  1 -c:v libx265 -x265-params log-level=error:keyint=30 -crf 22 -tag:v hvc1
clip up-352x288-vp9           352 288  1  1 -c:v libvpx-vp9 -g 30 -crf 30 -b:v 0
clip up-720x576-sar16x15-h264 720 576 16 15 -c:v libx264 -profile:v high -g 30 -crf 20
clip up-720x480-sar32x27-av1  720 480 32 27 -c:v libsvtav1 -g 30 -crf 35 -preset 8
