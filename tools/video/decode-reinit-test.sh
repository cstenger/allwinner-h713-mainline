#!/bin/bash
# Does the decoder survive a mid-stream resolution change? RUNS ON THE TARGET.
#
# Every vector before this one is a single resolution from first frame to last,
# which is not what real files do. Adaptive streams, broadcast splices and
# concatenated recordings all change resolution mid-stream, and the decoder is
# expected to tear its state down and rebuild it without losing the picture or
# the engine.
#
# It is also the case most likely to break THIS shim specifically. PR #38 sets
# the coded format once, behind a flag its own comment calls a HACK:
#
#     // we declare SET_FORMAT_OF_OUTPUT_ONCE to ensure v4l2_set_format only
#     // gets called once (in the first RequestCreateSurfaces2 call ...)
#
# A second resolution needs that format set again. If the flag prevents it, the
# engine keeps decoding at the old geometry and the output is wrong -- or the
# capture buffers are the wrong size and it is worse than wrong.
#
# HOW IT IS SCORED. Per frame, both arms computed HERE with the same ffmpeg:
# framemd5 of the software decode against framemd5 of the VA-API decode, with
# -noautoscale. Without that flag ffmpeg scales every frame to the FIRST
# resolution, so the comparison silently runs through swscale (which is not
# stable across ffmpeg versions) and a fault can only be reported for the
# stream as a whole. With it, each segment is hashed at its own size and the
# first bad frame is named. Frame counts must match, and the VE must take at
# least one interrupt per frame: a decoder that falls back to software after
# the first segment hashes exactly like a pass for that segment
# (passing-suites-that-cannot-fail).
#
# PASSING since 2026-10-01 (libva-v4l2-request 0018/0019, kernel 0151): the
# VA driver releases and renegotiates its queues while old surfaces live on.
# That needs DMABUF capture; with V4L2_REQUEST_CAPTURE_MEMORY=mmap every
# vector is expected to fail at its first change, which is a useful negative
# control. AV1 is not here: libavcodec 7.1 never asks for new surfaces on an
# AV1 size change (docs/hevc-resolution-change.md).
#
# r01 BEFORE r02. r02 (H.264) once wedged the board with a work-in-progress
# fix installed -- ssh answers, no command completes, only a power cycle
# recovers -- while r01 fails safely. Pass vector names to pick:
#
#   ./decode-reinit-test.sh r01-resolution-change
#
#   usage: ./decode-reinit-test.sh [vector ...]

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-/var/tmp/reinit}

mkdir -p "$OUT"

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}
pass=0; fail=0

# vector:extension:frames
SPECS="r01-resolution-change:h265:75 vp9-rc:ivf:210 r02-resolution-change:h264:150"
if [ $# -gt 0 ]; then
	want="$*"; picked=""
	for spec in $SPECS; do
		case " $want " in *" ${spec%%:*} "*) picked="$picked $spec" ;; esac
	done
	SPECS=$picked
fi

# size and md5 of every frame, one per line, at each frame's own resolution
framemd5() {
	grep -v '^#' | awk -F', *' '{ print $5, $6 }'
}

for spec in $SPECS; do
	v=$(echo "$spec" | cut -d: -f1); ext=$(echo "$spec" | cut -d: -f2)
	frames=$(echo "$spec" | cut -d: -f3)
	[ -r "$DIR/$v.$ext" ] || { echo "  $v: no stream, skipped"; continue; }

	echo "=== $v ($frames frames) ==="

	# The software decode, computed here rather than trusted from a file.
	ffmpeg -hide_banner -v error -i "$DIR/$v.$ext" -noautoscale \
		-fps_mode passthrough -pix_fmt yuv420p -f framemd5 - 2>/dev/null |
		framemd5 > "$OUT/sw"
	sw_frames=$(wc -l < "$OUT/sw")
	echo "     sw  $sw_frames frames, sizes: $(awk '{print $1}' "$OUT/sw" | uniq | tr '\n' ' ')"

	if [ "$sw_frames" -ne "$frames" ]; then
		echo "     sw  FAIL — expected $frames frames; the vector or ffmpeg is not what this test assumes"
		fail=$((fail + 1)); continue
	fi

	a=$(ve_irq)
	LIBVA_DRIVER_NAME=v4l2_request timeout 180 \
		ffmpeg -hide_banner -v error \
		-hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$DIR/$v.$ext" -noautoscale -vf 'hwdownload,format=nv12' \
		-fps_mode passthrough -pix_fmt yuv420p -f framemd5 - \
		2>"$OUT/va.err" | framemd5 > "$OUT/va"
	va_ve=$(( $(ve_irq) - a ))
	va_frames=$(wc -l < "$OUT/va")
	same=$(paste -d' ' "$OUT/sw" "$OUT/va" | awk '$1 == $3 && $2 == $4' | wc -l)
	first_bad=$(paste -d' ' "$OUT/sw" "$OUT/va" |
		awk '$1 != $3 || $2 != $4 { print NR - 1; exit }')

	if [ "$same" -eq "$frames" ] && [ "$va_frames" -eq "$frames" ] &&
	   [ "$va_ve" -ge "$frames" ]; then
		echo "     va  PASS — $same/$frames frames identical to software, ve+$va_ve"
		pass=$((pass + 1))
	else
		echo "     va  FAIL — $same/$frames identical, $va_frames frames out, ve+$va_ve (want >= $frames)${first_bad:+, first bad frame $first_bad}"
		grep -v 'Capture memory' "$OUT/va.err" | head -2 | sed 's/^/            /'
		fail=$((fail + 1))
	fi
	grep 'Renegotiating' "$OUT/va.err" | sed 's/^v4l2-request: /     /'

	# The engine must still be usable afterwards -- a reinit that leaves it
	# wedged would be a worse failure than a wrong picture.
	a=$(ve_irq)
	LIBVA_DRIVER_NAME=v4l2_request timeout 60 \
		ffmpeg -hide_banner -v error -y -hwaccel vaapi \
		-hwaccel_output_format vaapi -i "$DIR/h01-640x480-main.h265" \
		-vf 'hwdownload,format=nv12' -f rawvideo -pix_fmt nv12 pipe:1 \
		2>/dev/null | md5sum | cut -d' ' -f1 > "$OUT/after"
	if [ "$(cat "$OUT/after")" = "$(grep ' h01-640x480-main$' "$DIR/hevc-reference-md5.txt" | cut -d' ' -f1)" ] &&
	   [ "$(( $(ve_irq) - a ))" -gt 0 ]; then
		echo "     engine still healthy afterwards"
	else
		echo "     ENGINE WEDGED after the reinit"
		fail=$((fail + 1))
	fi
	rm -f "$OUT/sw" "$OUT/va" "$OUT/va.err" "$OUT/after"
done

echo
echo "RI1: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
