#!/bin/bash
# Does 10-bit HEVC decode on the VE? RUNS ON THE TARGET.
#
# SEPARATE FROM THE H1 GATE ON PURPOSE, because bit-exactness against a software
# decode is the wrong criterion for the 8-bit arms below, and mixing the two
# would corrupt a gate whose whole value is that md5 either matches or does not.
#
# WHAT THE ENGINE ACTUALLY PRODUCES. Main10 decodes into Allwinner's own layout:
# an 8-bit plane plus a separate packed 2-bit plane. BOTH ARE WRITTEN, and the
# pair reconstructs to bit-exact 10 bit -- 100% of samples, maxerr 0, on three
# geometries. No V4L2 fourcc describes the pair, so what reaches a client today
# is the 8-bit plane alone: the high 8 bits of each sample.
#
# CORRECTION, 2026-09-23. This header used to say the VE "truncates the low two
# bits", and arms 1 and 2 were built on it. The engine discards nothing -- the
# low bits are in the side plane, and were all along. What survives the
# correction is the narrower statement in arm 1, which is still true of the
# 8-bit plane read in isolation and is still why that arm cannot be exact.
#
# So this scores three things, and only the third can see a 10-bit defect:
#
#   1. PSNR of the 8-bit plane against an 8-bit software decode must clear
#      PSNR_MIN (default 50 dB). Measured on this board it is ~57 dB luma;
#      anything near 30 would mean the picture is wrong rather than merely
#      rounded differently. It cannot be exact, because the 8-bit plane is a
#      truncation of each 10-bit sample where swscale rounds and dithers.
#      That ~57 dB is against an 8-BIT reference. The same plane scored against
#      a 10-BIT reference gives 59.11 dB. Do not mix the two numbers.
#   2. THE SHIM AND THE ORACLE MUST AGREE BIT-EXACTLY. Both take the same
#      8-bit plane out of the same engine, so any difference between them is a
#      real defect in one of them -- and this comparison needs no reference at
#      all, which makes it sharper than 1.
#   3. THE 10-BIT ARM: hevc-10bit-verify.py reconstructs the full sample from
#      both planes and demands exactness. ARMS 1 AND 2 ARE BLIND TO THE SIDE
#      PLANE -- they would pass unchanged if it were zeroed, filled with
#      garbage, or read at the wrong row offset, because neither one ever looks
#      at it. Until 2026-09-23 this script had no such arm at all, which made it
#      an 8-bit test wearing a 10-bit name.
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
PROBE=${PROBE:-/root/probe-full.so}

mkdir -p "$OUT"
[ -r "$DIR/$VECTOR.h265" ] || { echo "FATAL: no stream at $DIR/$VECTOR.h265"; exit 1; }

# Geometry comes from the vector name. It used to be hardcoded 640x480 in two
# places while the script still accepted a vector argument, so asking for h08
# (1280x720) or h09 (642x482) compared buffers at the wrong size, computed the
# frame count from the wrong divisor, and printed a confident dB figure for it.
# Refuse rather than guess.
if [[ $VECTOR =~ -([0-9]+)x([0-9]+)- ]]; then
	W=${BASH_REMATCH[1]}
	H=${BASH_REMATCH[2]}
else
	echo "FATAL: cannot read a WxH geometry out of '$VECTOR'" >&2
	echo "" >&2
	echo "  Every size below is derived from the vector name. Guessing a" >&2
	echo "  default here is what the 640x480 hardcoding used to do, and it" >&2
	echo "  reported wrong-size comparisons as dB numbers." >&2
	echo "" >&2
	echo "  Fix: name the vector <prefix>-<W>x<H>-<suffix>, as h07/h08/h09 are." >&2
	exit 2
fi

# Arm 3 needs the LD_PRELOAD dumper, because the side plane lies past the
# sizeimage a client sees and nothing else can read it back. A missing probe
# must not silently drop the arm: that would restore precisely the defect this
# script was rewritten to remove.
if [ ! -r "$PROBE" ]; then
	echo "FATAL: no capture probe at $PROBE" >&2
	echo "" >&2
	echo "  Arm 3 is the only check here that can see a 10-bit defect. Skipping" >&2
	echo "  it would leave two arms that pass whatever the side plane contains," >&2
	echo "  and this script would again be an 8-bit test named for 10 bits." >&2
	echo "" >&2
	echo "  Fix: build it from tools/video/cedrus-compose-probe.c --" >&2
	echo "    cc -shared -fPIC -O2 -Wall -Wextra -Werror \\" >&2
	echo "       -o $PROBE cedrus-compose-probe.c -ldl" >&2
	exit 2
fi

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}

# Returns "y u v". SCORING LUMA ALONE IS WHAT HID A REAL BUG: at 642x482 the
# VE's inter-frame chroma is grossly wrong (MSE ~3900 against a software decode,
# ~12 dB) while luma stays bit-exact, so `PSNR y:` alone reported 56.39 dB and
# called it a pass. Measured 2026-09-23 on both Main10 and 8-bit Main, so it is
# a geometry defect, not a 10-bit one. The caller thresholds the WORST plane.
psnr_of() {
	ffmpeg -hide_banner -f rawvideo -pix_fmt nv12 -s "${W}x${H}" -i "$1" \
		-f rawvideo -pix_fmt nv12 -s "${W}x${H}" -i "$2" \
		-lavfi '[0:v][1:v]psnr' -f null - 2>&1 |
		sed -n 's/.*PSNR y:\([0-9.]*\) u:\([0-9.]*\) v:\([0-9.]*\).*/\1 \2 \3/p' | tail -1
}

# Worst of the three, or empty if the parse failed. Empty must stay empty: the
# verdict loop treats it as a failure, which is the correct reading of "the
# comparison could not be made".
worst_plane() {
	[ -n "$1" ] || return 0
	awk -v s="$1" 'BEGIN { split(s, p, " "); m = p[1];
		for (i = 2; i <= 3; i++) if (p[i] < m) m = p[i]; print m }'
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
sw_frame=$(( W * H * 3 / 2 ))
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
# GStreamer emits ONE OF TWO LAYOUTS, and which one depends on alignment. Both
# were measured on this board 2026-09-23; neither is the tight WxH frame the
# old code assumed when it took the first sw_frame bytes.
#
#   PASSTHROUGH (h07 640x480, h08 1280x720) -- the capture canvas is 16-aligned
#   on both axes, so when the picture is already 16-aligned it IS the canvas.
#   The V4L2 buffer goes through whole, trailing 2-bit side plane included:
#   h07 is 576000 = 640*480*1.5 + 160*480*1.5.
#
#   COPIED (h09 642x482) -- the picture is smaller than the 656x496 canvas, so
#   GStreamer copies it into a frame of its own with a 4-BYTE-aligned stride and
#   drops the side plane: 465612 = 644*482*1.5, exactly. Stride 656 and 642 do
#   not even divide the file.
#
# Recognise both exactly and refuse anything else. Guessing between them is how
# a sheared frame gets reported as a confident dB number.
# Pitch is 32-aligned, height 16-aligned. The 32 is not cosmetic: a pitch that
# is 16- but not 32-aligned makes the engine read reference chroma at a wider
# stride than it wrote, corrupting every inter frame.
# See docs/reference/hevc-unaligned-chroma-2026-09-23.md.
CANVAS_W=$(( (W + 31) / 32 * 32 ))
CANVAS_H=$(( (H + 15) / 16 * 16 ))
PITCH2=$(( ((CANVAS_W + 3) / 4 + 31) / 32 * 32 ))
PASSTHRU=$(( CANVAS_W * CANVAS_H * 3 / 2 + PITCH2 * CANVAS_H * 3 / 2 ))
GST_W=$(( (W + 3) / 4 * 4 ))
COPIED=$(( GST_W * H * 3 / 2 ))
if [ "$hw_frame" -eq "$PASSTHRU" ]; then
	PITCH=$CANVAS_W
	CBASE=$(( CANVAS_W * CANVAS_H ))
elif [ "$hw_frame" -eq "$COPIED" ]; then
	PITCH=$GST_W
	CBASE=$(( GST_W * H ))
else
	echo "     FAIL: frame is $hw_frame bytes, which is neither the passthrough"
	echo "           layout ($PASSTHRU) nor the copied one ($COPIED)."
	echo "           The layout is not one of the two we have measured, so every"
	echo "           comparison below would be against a misread buffer."
	exit 1
fi
python3 - "$OUT/gst.raw" "$OUT/gst" "$hw_frame" "$W" "$H" "$PITCH" "$CBASE" <<'PY'
import sys
src, dst, hw, w, h, pitch, cbase = sys.argv[1], sys.argv[2], *(int(v) for v in sys.argv[3:])
data = open(src, 'rb').read()
with open(dst, 'wb') as f:
    for i in range(len(data) // hw):
        frame = data[i * hw:(i + 1) * hw]
        for y in range(h):                       # luma: w of every pitch-byte row
            f.write(frame[y * pitch:y * pitch + w])
        for y in range(h // 2):                  # 8-bit chroma, interleaved
            f.write(frame[cbase + y * pitch:cbase + y * pitch + w])
PY
gst_planes=$(psnr_of "$OUT/gst" "$OUT/sw")
gst_psnr=$(worst_plane "$gst_planes")
printf '     ve+%-4s frame %s bytes, PSNR y/u/v %s dB\n' \
	"$gst_ve" "$hw_frame" "${gst_planes:-none}"

echo
echo "=== libva-v4l2-request through stock ffmpeg (the subject) ==="
v0=$(ve_irq)
LIBVA_DRIVER_NAME=v4l2_request ffmpeg -hide_banner -v error -y \
	-hwaccel vaapi -hwaccel_output_format vaapi \
	-i "$DIR/$VECTOR.h265" -vf 'hwdownload,format=nv12' \
	-f rawvideo -pix_fmt nv12 "$OUT/va" 2>"$OUT/va.err"
va_ve=$(( $(ve_irq) - v0 ))
va_planes=$(psnr_of "$OUT/va" "$OUT/sw")
va_psnr=$(worst_plane "$va_planes")
printf '     ve+%-4s %s bytes, PSNR y/u/v %s dB\n' \
	"$va_ve" "$(stat -c%s "$OUT/va" 2>/dev/null || echo 0)" "${va_planes:-none}"

if [ "$va_ve" -eq 0 ]; then
	echo "     FAIL — ve+0, every frame was decoded on the CPU"
	head -2 "$OUT/va.err" | sed 's/^/          /'
	fail=$((fail + 1))
fi

echo
echo "=== 10-bit exactness, both planes (arm 3) ==="
# Deliberately the full default vector set, NOT "$VECTOR". Arms 1 and 2 ask
# whether the client-visible 8-bit path is right for one stream; this one asks
# whether the 8+2 layout is read correctly, and that question needs the geometry
# spread. h09 (642x482) is the only vector whose coded height (488) and canvas
# height (496) differ, so it is the only one that can catch the side plane being
# read at the wrong row offset -- a bug that leaves luma bit-exact and chroma at
# 62.5 dB, which every PSNR threshold loose enough to be safe will pass. Letting
# a vector argument narrow this arm would quietly drop the one test that fails.
if python3 "$DIR/hevc-10bit-verify.py" --probe "$PROBE"; then
	verify_ok=1
else
	verify_ok=0
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
		echo "     $arm: PASS — worst plane $p dB against software (>= $PSNR_MIN)"
	else
		echo "     $arm: FAIL — worst plane $p dB is below $PSNR_MIN, that is a"
		echo "          wrong picture. Check y/u/v above: luma alone can be"
		echo "          bit-exact while chroma is broken."
		fail=$((fail + 1))
	fi
done

# Reference-free, and sharper than the PSNR arms above.
if cmp -s "$OUT/gst" "$OUT/va"; then
	echo "     shim vs oracle: PASS — byte-for-byte identical"
else
	echo "     shim vs oracle: FAIL — they disagree, so one of them is wrong"
	fail=$((fail + 1))
fi

# The only arm that reads the side plane. Everything above passes without it.
if [ "$verify_ok" -eq 1 ]; then
	echo "     10-bit exactness: PASS — every sample of every plane, all vectors"
else
	echo "     10-bit exactness: FAIL — the 10-bit reconstruction is not exact"
	fail=$((fail + 1))
fi

# Only on success. This used to run unconditionally, which was survivable while
# every arm here was a PSNR number -- but arm 3 can now fail on a layout defect,
# and diagnosing one means looking at the buffers that produced it. A gate built
# to fail must not delete its own evidence.
if [ "$fail" -eq 0 ]; then
	rm -f "$OUT/sw" "$OUT/gst" "$OUT/gst.raw" "$OUT/va" "$OUT/va.err"
else
	echo
	echo "     buffers kept in $OUT/ for diagnosis"
fi
echo
echo "T1: $([ "$fail" -eq 0 ] && echo PASS || echo "$fail failure(s)")"
[ "$fail" -eq 0 ]
