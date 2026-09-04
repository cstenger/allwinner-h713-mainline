#!/bin/bash
# Does 10-bit HEVC decode on the VE? RUNS ON THE TARGET.
#
# SEPARATE FROM THE H1 GATE ON PURPOSE, because bit-exactness is the wrong
# criterion here and mixing the two would corrupt a gate whose whole value is
# that md5 either matches or does not.
#
# The engine decodes Main10 into Allwinner's own layout: an 8-bit plane plus a
# separate 2-bit plane. No V4L2 fourcc describes that pair, so what reaches a
# client is the 8-bit plane -- a correct 8-bit rendition of a 10-bit stream.
# Comparing it to a software decode cannot be bit-exact: the VE truncates the
# low two bits where swscale rounds and dithers. Two correct answers that
# differ in the last bit.
#
# So this scores two things instead, and the second is the strict one:
#
#   1. PSNR against a software decode must clear PSNR_MIN (default 50 dB).
#      Measured on this board it is ~57 dB luma; anything near 30 would mean
#      the picture is wrong rather than merely rounded differently.
#   2. THE SHIM AND THE ORACLE MUST AGREE BIT-EXACTLY. Both take the same
#      8-bit plane out of the same engine, so any difference between them is a
#      real defect in one of them -- and this comparison needs no reference at
#      all, which makes it the sharper of the two.
#
# ve+N is reported for the same reason as everywhere else: a correct-looking
# result with a flat interrupt counter is a software fallback wearing a
# hardware result's clothes. That is exactly how this started -- the shim
# advertised Main10, ffmpeg accepted it, and every frame was decoded on the
# CPU because the kernel refused a bit-depth increase after buffers existed.
#
#   usage: ./hevc-10bit-test.sh [vector]        (default h07-640x480-main10)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
VECTOR=${1:-h07-640x480-main10}
PSNR_MIN=${PSNR_MIN:-50}
OUT=${OUT:-/var/tmp/hevc10}

mkdir -p "$OUT"
[ -r "$DIR/$VECTOR.h265" ] || { echo "FATAL: no stream at $DIR/$VECTOR.h265"; exit 1; }

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}

psnr_of() {
	ffmpeg -hide_banner -f rawvideo -pix_fmt nv12 -s 640x480 -i "$1" \
		-f rawvideo -pix_fmt nv12 -s 640x480 -i "$2" \
		-lavfi '[0:v][1:v]psnr' -f null - 2>&1 |
		sed -n 's/.*PSNR y:\([0-9.]*\).*/\1/p' | tail -1
}

fail=0

echo "=== software reference ==="
ffmpeg -hide_banner -v error -y -i "$DIR/$VECTOR.h265" \
	-pix_fmt nv12 -f rawvideo "$OUT/sw" 2>/dev/null
echo "     $(stat -c%s "$OUT/sw") bytes"

echo
echo "=== GStreamer v4l2slh265dec (the oracle) ==="
v0=$(ve_irq)
gst-launch-1.0 -q filesrc location="$DIR/$VECTOR.h265" ! h265parse ! v4l2slh265dec \
	! video/x-raw,format=NV12 ! filesink location="$OUT/gst.raw" >/dev/null 2>&1
gst_ve=$(( $(ve_irq) - v0 ))
# Strip the 2-bit plane the engine appends, which the driver includes in
# sizeimage and GStreamer faithfully writes out.
sw_frame=$(( 640 * 480 * 3 / 2 ))
# Both sizes have to be established BEFORE the arithmetic. This division used to
# be written inline, so an empty or missing gst.raw made the assignment fail
# silently under `set -u` (there is no `set -e` here) and the script died on the
# next line with "hw_frame: unbound variable" -- a shell error reported as a
# driver failure, which is exactly what a gate must never do.
gst_bytes=$(stat -c%s "$OUT/gst.raw" 2>/dev/null || echo 0)
sw_bytes=$(stat -c%s "$OUT/sw" 2>/dev/null || echo 0)
if [ "$sw_bytes" -lt "$sw_frame" ]; then
	echo "     FAIL: software reference is $sw_bytes bytes, under one frame."
	echo "           ffmpeg could not decode the vector; nothing here is about the VE."
	exit 1
fi
sw_frames=$(( sw_bytes / sw_frame ))
if [ "$gst_bytes" -eq 0 ]; then
	echo "     FAIL: v4l2slh265dec produced no output (ve+$gst_ve)."
	echo "           The oracle did not run, so the bit-exact comparison below"
	echo "           cannot be made. Treat this as the failure, not as a skip."
	exit 1
fi
hw_frame=$(( gst_bytes / sw_frames ))
python3 - "$OUT/gst.raw" "$OUT/gst" "$hw_frame" "$sw_frame" <<'PY'
import sys
src, dst, hw, sw = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
data = open(src, 'rb').read()
with open(dst, 'wb') as f:
    for i in range(len(data) // hw):
        f.write(data[i * hw:i * hw + sw])
PY
gst_psnr=$(psnr_of "$OUT/gst" "$OUT/sw")
printf '     ve+%-4s frame %s bytes (%s + 2-bit plane), PSNR y %s dB\n' \
	"$gst_ve" "$hw_frame" "$sw_frame" "$gst_psnr"

echo
echo "=== libva-v4l2-request through stock ffmpeg (the subject) ==="
v0=$(ve_irq)
LIBVA_DRIVER_NAME=v4l2_request ffmpeg -hide_banner -v error -y \
	-hwaccel vaapi -hwaccel_output_format vaapi \
	-i "$DIR/$VECTOR.h265" -vf 'hwdownload,format=nv12' \
	-f rawvideo -pix_fmt nv12 "$OUT/va" 2>"$OUT/va.err"
va_ve=$(( $(ve_irq) - v0 ))
va_psnr=$(psnr_of "$OUT/va" "$OUT/sw")
printf '     ve+%-4s %s bytes, PSNR y %s dB\n' "$va_ve" "$(stat -c%s "$OUT/va" 2>/dev/null || echo 0)" "$va_psnr"

if [ "$va_ve" -eq 0 ]; then
	echo "     FAIL — ve+0, every frame was decoded on the CPU"
	head -2 "$OUT/va.err" | sed 's/^/          /'
	fail=$((fail + 1))
fi

echo
echo "=== verdicts ==="
for arm in gst va; do
	p=$(eval echo \$${arm}_psnr)
	if [ -z "$p" ]; then
		echo "     $arm: FAIL — no PSNR (decode produced nothing usable)"
		fail=$((fail + 1))
	# awk, not bc: bc is not installed on this rootfs, and `bc || echo 0`
	# fails CLOSED -- every threshold check returned 0 and reported a 57 dB
	# picture as wrong. A comparison that cannot run must be an error, not a
	# verdict.
	elif [ "$(awk -v a="$p" -v b="$PSNR_MIN" 'BEGIN { print (a >= b) ? 1 : 0 }')" = "1" ]; then
		echo "     $arm: PASS — $p dB against the software decode (>= $PSNR_MIN)"
	else
		echo "     $arm: FAIL — $p dB is below $PSNR_MIN, that is a wrong picture"
		fail=$((fail + 1))
	fi
done

# The strict one, and it needs no reference.
if cmp -s "$OUT/gst" "$OUT/va"; then
	echo "     shim vs oracle: PASS — byte-for-byte identical"
else
	echo "     shim vs oracle: FAIL — they disagree, so one of them is wrong"
	fail=$((fail + 1))
fi

rm -f "$OUT/sw" "$OUT/gst" "$OUT/gst.raw" "$OUT/va" "$OUT/va.err"
echo
echo "T1: $([ "$fail" -eq 0 ] && echo PASS || echo "$fail failure(s)")"
[ "$fail" -eq 0 ]
