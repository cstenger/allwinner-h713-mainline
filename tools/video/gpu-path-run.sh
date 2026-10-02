#!/usr/bin/env bash
# WP2 driver: run gpu-path-measure.sh on the board over the capture media set.
# RUNS ON THE HOST. docs/gpu-fallback-plan.md, WP2.
#
#   tools/video/gpu-path-run.sh [CLIP-GLOB...]
#   VOS="gpu gpu-next" DUR=60 tools/video/gpu-path-run.sh '0[1-6]*' 1b-h264-1280x720.mp4
#   MPV_OPTS='--scale=bilinear --dscale=bilinear --dither=no' ...  the "cheap" settings
#
# Each clip is copied into the board's /tmp (tmpfs: the root filesystem is 92%
# full and the media partition holds 52 MB) and deleted after its runs, so only
# one clip is resident at a time. Results append to $OUT (one block per run,
# plus the WP2 SUMMARY lines) and are echoed.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
BOARD=${BOARD:-192.168.4.1}
MEDIA=${MEDIA:-$ROOT/local/h713-lab/stock-capture-20261001/media}
VOS=${VOS:-gpu gpu-next}
DUR=${DUR:-60}
MPV_OPTS=${MPV_OPTS:-}
OUT=${OUT:-$ROOT/local/h713-lab/wp2-$(date +%Y%m%d)/results.txt}
SSH=(ssh -F /dev/null -o ConnectTimeout=8 "root@$BOARD")

# The plan's set: 1080p per codec, 4K, small sources, the rot90 set, native 720p.
DEFAULT=(01-h264-1080.mp4 02-hevc-1080.mp4 04-vp9-1080.webm 05-av1-1080.mp4
         06-av110-1080.mp4 52-h264-2160.mp4 11-h264-852x480.mp4
         13-h264-352x288.mp4 30-h264-720-rot90.mp4 31-hevc-720-rot90.mp4
         32-vp9-720-rot90.mp4 33-av1-720-rot90.mp4 1b-h264-1280x720.mp4)

clips=()
if [ $# -eq 0 ]; then
	clips=("${DEFAULT[@]}")
else
	shopt -s nullglob
	for g in "$@"; do
		for f in "$MEDIA"/$g; do clips+=("$(basename "$f")"); done
	done
fi
[ ${#clips[@]} -gt 0 ] || { echo "no clips matched" >&2; exit 1; }

mkdir -p "$(dirname "$OUT")"
scp -q -F /dev/null "$ROOT/tools/video/gpu-path-measure.sh" "root@$BOARD:/root/"
{
	echo "# $(date -Is) kernel=$("${SSH[@]}" 'uname -v') vos='$VOS' dur=$DUR opts='$MPV_OPTS'"
} >> "$OUT"

for c in "${clips[@]}"; do
	[ -s "$MEDIA/$c" ] || { echo "missing $MEDIA/$c" >&2; continue; }
	scp -q -F /dev/null "$MEDIA/$c" "root@$BOARD:/tmp/$c"
	for vo in $VOS; do
		# A short pause between runs. It does not equalise temperature: each
		# run records tmax_* and its CPU frequencies, so read those rather
		# than assuming later runs started as cool as earlier ones.
		"${SSH[@]}" "VO=$vo DUR=$DUR MPV=${MPV:-/usr/bin/mpv} LOOP=${LOOP:-} MPV_OPTS='$MPV_OPTS' sh /root/gpu-path-measure.sh /tmp/$c $c" |
			tee -a "$OUT"
		sleep 10
	done
	"${SSH[@]}" "rm -f /tmp/$c"
done
echo "results: $OUT"
grep 'WP2 SUMMARY' "$OUT" | tail -n $(( ${#clips[@]} * $(wc -w <<< "$VOS") ))
