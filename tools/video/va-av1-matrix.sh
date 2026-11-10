#!/bin/bash
# FFmpeg VA-API AV1 against libdav1d, frame by frame. RUNS ON THE TARGET.
#
#   va-av1-matrix.sh clip.ivf [...]
#
# PASS = every frame's NV12 md5 equals libdav1d's on this board, AND the AV1
# core interrupted at least once per frame (a software fallback would pass).
#
# Both sides decode with -noautoscale and are compared in NV12, at each
# frame's own size. Comparing against a host-made .framemd5 was wrong for
# clips whose frame size changes: FFmpeg rescales every frame to the first
# frame's size, and the host's swscale (x86) rounds differently from the
# board's, so resize-* "failed" every rescaled frame while decoding
# bit-exact (2026-10-04).
#
# Over ssh ffmpeg needs -nostdin and </dev/null (it otherwise blocks reading
# the session's stdin, and a blocked read survives `timeout`), and -y (it
# otherwise refuses to overwrite and the old output is compared again).
export LIBVA_DRIVER_NAME=v4l2_request
irq() { awk '/1c0d000.av1/ { print $2 }' /proc/interrupts; }
md5s() { grep -v '^#' "$1" | awk -F, '{ print $NF }'; }
pass=0; fail=0; total=$#; k=0
for f in "$@"; do
	k=$((k + 1))
	rm -f /tmp/va.md5 /tmp/ref.md5
	timeout 300 ffmpeg -nostdin -y -v error -c:v libdav1d -i "$f" -noautoscale \
		-pix_fmt nv12 -f framemd5 /tmp/ref.md5 </dev/null 2>/dev/null
	a=$(irq); t0=$(date +%s)
	timeout 300 ffmpeg -nostdin -y -v error -hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$f" -noautoscale -vf hwdownload,format=nv12 -f framemd5 /tmp/va.md5 \
		</dev/null 2>/tmp/va.err
	rc=$?; d=$(( $(irq) - a ))
	n=$(grep -vc '^#' /tmp/va.md5 2>/dev/null); want=$(grep -vc '^#' /tmp/ref.md5 2>/dev/null)
	bad=$(diff <(md5s /tmp/va.md5) <(md5s /tmp/ref.md5) | grep -c '^[<>]')
	if [ $rc -eq 0 ] && [ "${want:-0}" -gt 0 ] && [ "$n" = "$want" ] && [ $bad -eq 0 ] && [ $d -ge $n ]; then
		pass=$((pass + 1)); r=PASS
	else
		fail=$((fail + 1)); r="FAIL rc=$rc frames=$n/$want diff_lines=$bad av1_irq=+$d"
	fi
	echo "[$k/$total] $r ${f##*/} (${n:-0} frames, $(( $(date +%s) - t0 ))s)"
done
echo "VA AV1 matrix: $pass pass, $fail fail"
