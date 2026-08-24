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
# HOW IT IS SCORED, and why there is no stored reference. ffmpeg's rawvideo
# output must have one frame size, so it scales every later resolution back to
# the first -- which drags swscale into the comparison, and swscale is NOT
# stable across ffmpeg versions. A host-generated md5 (ffmpeg 9.0.1) does not
# reproduce on the board (7.1.5), and the first version of this test duly
# reported "HARNESS IS WRONG" for both vectors, which was correct.
#
# So both arms are computed HERE, on the board, with the same ffmpeg, and
# compared to each other. The criterion is unchanged in substance -- hardware
# output must equal software output -- and it no longer depends on two machines
# agreeing about a scaler that has nothing to do with the decoder.
#
# ITERATE ON THE HEVC VECTOR. r02 (H.264) can wedge the board outright with a
# work-in-progress fix installed -- ssh answers, no command completes, and only
# a power cycle recovers -- while r01 fails safely. Pass vector names to pick:
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

# vector:extension:frames:width:height -- the geometry is the FIRST
# resolution in the stream, because ffmpeg's rawvideo output must have one
# frame size and scales every later resolution back to that one. Assuming
# 640x480 for every vector made r02 (which starts at 1280x720) count 450
# frames instead of 150 and fail as a harness error.
SPECS="r01-resolution-change:h265:75:640:480 r02-resolution-change:h264:150:1280:720"
if [ $# -gt 0 ]; then
	want="$*"; picked=""
	for spec in $SPECS; do
		case " $want " in *" ${spec%%:*} "*) picked="$picked $spec" ;; esac
	done
	SPECS=$picked
fi

for spec in $SPECS; do
	v=$(echo "$spec" | cut -d: -f1); ext=$(echo "$spec" | cut -d: -f2)
	frames=$(echo "$spec" | cut -d: -f3)
	fw=$(echo "$spec" | cut -d: -f4); fh=$(echo "$spec" | cut -d: -f5)
	fsize=$(( fw * fh * 3 / 2 ))
	[ -r "$DIR/$v.$ext" ] || { echo "  $v: no stream, skipped"; continue; }

	echo "=== $v ($frames frames, first resolution ${fw}x${fh}) ==="

	# The software decode, computed here rather than trusted from a file.
	ffmpeg -hide_banner -v error -y -i "$DIR/$v.$ext" \
		-pix_fmt nv12 -f rawvideo "$OUT/sw" 2>/dev/null
	sw_md5=$(md5sum "$OUT/sw" | cut -d' ' -f1)
	sw_frames=$(( $(stat -c%s "$OUT/sw") / fsize ))
	echo "     sw  $sw_frames frames, md5 $sw_md5"

	if [ "$sw_frames" -ne "$frames" ]; then
		echo "     sw  FAIL — expected $frames frames; the vector or ffmpeg is not what this test assumes"
		fail=$((fail + 1)); continue
	fi

	a=$(ve_irq)
	LIBVA_DRIVER_NAME=v4l2_request timeout 180 \
		ffmpeg -hide_banner -v error -y \
		-hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$DIR/$v.$ext" -vf 'hwdownload,format=nv12' \
		-f rawvideo -pix_fmt nv12 "$OUT/va" 2>"$OUT/va.err"
	va_ve=$(( $(ve_irq) - a ))
	va_md5=$(md5sum "$OUT/va" 2>/dev/null | cut -d' ' -f1)
	va_frames=$(( $(stat -c%s "$OUT/va" 2>/dev/null || echo 0) / fsize ))

	if [ "$va_ve" -eq 0 ]; then
		echo "     va  FAIL — ve+0, every frame decoded on the CPU"
		head -2 "$OUT/va.err" | sed 's/^/            /'
		fail=$((fail + 1))
	elif [ "$va_md5" = "$sw_md5" ]; then
		echo "     va  PASS — identical to software across the resolution changes, ve+$va_ve"
		pass=$((pass + 1))
	else
		echo "     va  MISMATCH ve+$va_ve (expected ve+$frames), $va_frames frames vs $sw_frames"
		head -2 "$OUT/va.err" | sed 's/^/            /'
		fail=$((fail + 1))
	fi

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
