#!/bin/bash
# H1 — does HEVC decode on the VE, bit-exact? RUNS ON THE TARGET.
#
# The yardstick for the HEVC work in docs/vaapi-scope.md, and the gate the
# libva-v4l2-request h265 port will be scored against once it exists. Like
# va-decode-test.sh it runs with NO DISPLAY INVOLVED: the display path is a
# separate risk, and a failure with both in play lands in neither half cleanly.
#
# Two arms, and which ones run is the point:
#
#   gst   GStreamer v4l2slh265dec. This ALREADY WORKS -- it is the reference
#         implementation of the same eight controls cedrus registers, against
#         this exact kernel, and it is what established HEVC on this hardware.
#         It is the oracle, not the subject.
#   va    libva-v4l2-request through stock ffmpeg. NOT YET IMPLEMENTED; skipped
#         with a clear line until src/h265.c is ported. This is the subject.
#
# WHY THE SOFTWARE CONTROL RUNS FIRST, same reasoning as the H.264 gate:
# ffmpeg's CPU decoder writing the same rawvideo through the same filter chain
# must reproduce the reference md5. If it does not, the harness is wrong (pixel
# format, frame count, cropping) and every hardware result below is unreadable.
#
# FORCING NV12 IS LOAD-BEARING, not decoration. Unforced, v4l2slh265dec
# negotiates the 32x32-tiled ST12 format, which is correct output that can
# never match a linear reference -- it reads as a decode bug and is not one.
#
# THE VECTORS, and why there are three:
#
#   h01/h02  x265 defaults, which means WPP IS ON (`wpp(8 rows)` in its own
#            tool line). entropy_coding_sync_enabled_flag is set, every slice
#            carries entry point offsets, and cedrus genuinely consumes them --
#            cedrus_h265.c copies them into a 4 KiB entry-points buffer and
#            programs it. So these two REQUIRE
#            V4L2_CID_STATELESS_HEVC_ENTRY_POINT_OFFSETS.
#   h03      the same source with wpp=0. No entry point offsets, so it is the
#            simplest thing that can possibly decode, and it is the right first
#            milestone for the shim port -- it decomposes "my control filling is
#            wrong" from "I have not implemented entry points yet".
#   h04/h05  scaling lists. h01-h03 all have scaling_list_enabled_flag = 0, and
#            cedrus gates its scaling-matrix write on that SPS flag, so those
#            three vectors CANNOT SEE whether the matrix is passed at all --
#            which is exactly how the shim shipped without passing it. h04 uses
#            the implicit HEVC default lists (non-flat from 8x8 up, every DC
#            coefficient 16); h05 carries explicit custom lists that are
#            non-flat at 4x4 too and whose DC values differ from their matrix,
#            so it also covers the two fields h04 is blind to.
#
#   usage: ./hevc-decode-test.sh [vector-name ...]      (default: all five)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
# NOT /tmp: it is a 467 MB tmpfs on this image and 720p25 raw NV12 is 34 MB a
# vector. ENOSPC leaves a truncated file with a perfectly valid md5, which
# scores as MISMATCH and reads as a decode bug.
OUT=${OUT:-/var/tmp/hevc-out}
REF="$DIR/hevc-reference-md5.txt"
mkdir -p "$OUT"

[ -r "$REF" ] || { echo "FATAL: no reference md5 file at $REF"; exit 1; }

VECTORS=${*:-"h01-640x480-main h02-1280x720-main h03-640x480-nowpp \
	h04-640x480-scaling h05-640x480-scaling-custom"}

# Sum the per-CPU columns of the video-codec interrupt line. A rise of exactly
# one per frame is positive proof the VE did the work -- stronger than "we
# asked it to", because a silent fallback to software would leave it flat.
ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}

want_md5() { grep " $1\$" "$REF" | cut -d' ' -f1; }

pass=0; fail=0; skip=0

echo "=== software control (the yardstick, not the subject) ==="
for v in $VECTORS; do
	[ -r "$DIR/$v.h265" ] || { echo "  $v: no stream, skipped"; continue; }
	ffmpeg -hide_banner -loglevel error -y -i "$DIR/$v.h265" \
		-pix_fmt nv12 -f rawvideo "$OUT/$v.sw" 2>/dev/null
	got=$(md5sum "$OUT/$v.sw" | cut -d' ' -f1)
	if [ "$got" = "$(want_md5 "$v")" ]; then
		printf '     %-24s PASS (sw) — harness sound\n' "$v"
	else
		printf '     %-24s FAIL (sw) — HARNESS IS WRONG, stop reading here\n' "$v"
		fail=$((fail + 1))
	fi
	rm -f "$OUT/$v.sw"
done

echo
echo "=== gst v4l2slh265dec (the oracle: already known good) ==="
for v in $VECTORS; do
	[ -r "$DIR/$v.h265" ] || continue
	v0=$(ve_irq)
	gst-launch-1.0 -q filesrc location="$DIR/$v.h265" ! h265parse ! v4l2slh265dec \
		! video/x-raw,format=NV12 ! filesink location="$OUT/$v.gst" >/dev/null 2>&1
	v1=$(ve_irq)
	got=$(md5sum "$OUT/$v.gst" 2>/dev/null | cut -d' ' -f1)
	if [ "$got" = "$(want_md5 "$v")" ]; then
		printf '     %-24s PASS (hw) bit-exact, ve+%d\n' "$v" "$((v1 - v0))"
		pass=$((pass + 1))
	else
		printf '     %-24s MISMATCH (hw) ve+%d\n' "$v" "$((v1 - v0))"
		fail=$((fail + 1))
	fi
	rm -f "$OUT/$v.gst"
done

echo
echo "=== libva-v4l2-request through stock ffmpeg (the subject) ==="
if LIBVA_DRIVER_NAME=v4l2_request vainfo 2>/dev/null | grep -qiE 'HEVC|H265'; then
	for v in $VECTORS; do
		[ -r "$DIR/$v.h265" ] || continue
		v0=$(ve_irq)
		# -hwaccel_output_format vaapi is LOAD-BEARING. Without it ffmpeg
		# silently falls back to software when hwaccel init fails, and
		# software decode reproduces the reference md5 by definition --
		# so the run reports PASS having never touched the VE. That
		# happened on the first PR#44 run and only ve+0 gave it away.
		LIBVA_DRIVER_NAME=v4l2_request ffmpeg -hide_banner -v error -y \
			-hwaccel vaapi -hwaccel_output_format vaapi \
			-i "$DIR/$v.h265" -vf 'hwdownload,format=nv12' \
			-f rawvideo -pix_fmt nv12 "$OUT/$v.va" 2>"$OUT/$v.err"
		v1=$(ve_irq)
		ve=$((v1 - v0))
		got=$(md5sum "$OUT/$v.va" 2>/dev/null | cut -d' ' -f1)
		if [ "$ve" -eq 0 ]; then
			# Bit-exact with a flat VE counter is a software decode
			# wearing a hardware result's clothes. Never a pass.
			printf '     %-24s FAIL (va) SOFTWARE FALLBACK — ve+0, no frame reached the engine\n' "$v"
			head -1 "$OUT/$v.err" 2>/dev/null | sed 's/^/          /'
			fail=$((fail + 1))
		elif [ "$got" = "$(want_md5 "$v")" ]; then
			printf '     %-24s PASS (va) bit-exact, ve+%d\n' "$v" "$ve"
			pass=$((pass + 1))
		else
			printf '     %-24s MISMATCH (va) ve+%d\n' "$v" "$ve"
			head -1 "$OUT/$v.err" 2>/dev/null | sed 's/^/          /'
			fail=$((fail + 1))
		fi
		rm -f "$OUT/$v.err"
		rm -f "$OUT/$v.va"
	done
else
	echo "     SKIPPED — the shim advertises no HEVC profile yet."
	echo "     That is expected until src/h265.c is ported; see docs/vaapi-scope.md."
	skip=$((skip + 1))
fi

echo
echo "H1: $pass pass, $fail fail, $skip arm(s) skipped"
[ "$fail" -eq 0 ]
