#!/bin/bash
# VP9 hardware decode gate. RUNS ON THE TARGET.
#
# Decodes each stream twice -- on the VE through v4l2slvp9dec, and in software
# through libvpx (vp9dec) -- and compares them with ffmpeg's PSNR. A decode
# only counts as hardware if the VE interrupt count moved by at least the
# number of frames: a pipeline that silently fell back to software would
# otherwise pass with infinite PSNR (see passing-suites-that-cannot-fail).
#
#   usage: vp9-gate.sh file.webm [file.webm ...]
set -u
OUT=${OUT:-/var/tmp/vp9-gate}
mkdir -p "$OUT"
irq() { awk '/cedrus|1c0e000/ {print $2; exit}' /proc/interrupts; }
dims() { ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$1"; }
nframes() { ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$1"; }
fail=0
for f in "$@"; do
	b=$(basename "$f" .webm)
	wh=$(dims "$f"); n=$(nframes "$f")
	a=$(irq)
	timeout 60 gst-launch-1.0 -q filesrc location="$f" ! matroskademux ! vp9parse ! \
		v4l2slvp9dec ! videoconvert ! video/x-raw,format=I420 ! \
		filesink location="$OUT/$b.hw.yuv" > "$OUT/$b.hw.log" 2>&1
	rc=$?
	d=$(( $(irq) - a ))
	timeout 60 gst-launch-1.0 -q filesrc location="$f" ! matroskademux ! vp9parse ! \
		vp9dec ! videoconvert ! video/x-raw,format=I420 ! \
		filesink location="$OUT/$b.sw.yuv" > "$OUT/$b.sw.log" 2>&1
	hw_sz=$(stat -c%s "$OUT/$b.hw.yuv" 2>/dev/null || echo 0)
	sw_sz=$(stat -c%s "$OUT/$b.sw.yuv")
	psnr=$(ffmpeg -hide_banner -f rawvideo -pix_fmt yuv420p -s "$wh" -i "$OUT/$b.hw.yuv" \
		-f rawvideo -pix_fmt yuv420p -s "$wh" -i "$OUT/$b.sw.yuv" \
		-lavfi psnr="stats_file=$OUT/$b.psnr" -f null - 2>&1 | grep -o 'average:[^ ]*')
	worst=$(awk '{for(i=1;i<=NF;i++) if ($i ~ /^psnr_avg:/) {split($i,a,":"); v=a[2]; if (v=="inf") v=999; if (min==""||v<min) {min=v; fr=$1}}} END {print min, fr}' "$OUT/$b.psnr" 2>/dev/null)
	# Raw frames are large (1080p: 3 MB each, twice); keep only the scores.
	[ -n "${KEEP_YUV:-}" ] || rm -f "$OUT/$b.hw.yuv" "$OUT/$b.sw.yuv"
	verdict=PASS
	[ "$rc" = 0 ] || verdict=FAIL
	[ "$d" -ge "$n" ] || verdict=FAIL
	[ "$hw_sz" = "$sw_sz" ] || verdict=FAIL
	case "$psnr" in *inf*) ;; *) verdict=FAIL ;; esac
	[ $verdict = PASS ] || fail=1
	printf '%-22s %s %4s frames  ve_irq=+%-4s rc=%s bytes hw/sw=%s/%s  %s  worst(psnr,frame)=%s\n' \
		"$b" "$verdict" "$n" "$d" "$rc" "$hw_sz" "$sw_sz" "$psnr" "$worst"
done
exit $fail
