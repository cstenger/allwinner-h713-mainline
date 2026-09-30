#!/bin/bash
# AV1 hardware decode gate. RUNS ON THE TARGET.
#
# Decodes each IVF stream on the AV1 core through v4l2slav1dec and compares
# every output frame's MD5 with a reference decoded on the host by libdav1d:
#
#   host$ ffmpeg -c:v libdav1d -i clip.ivf -pix_fmt yuv420p -f framemd5 clip.ivf.framemd5
#
# The .framemd5 file sits next to the stream. A decode only counts as hardware
# if the AV1 interrupt count moved by at least the number of frames -- a
# pipeline that silently fell back to software would otherwise pass (see
# passing-suites-that-cannot-fail) -- and a stream passes only if the frame
# COUNTS match as well as every hash.
#
#   usage: av1-gate.sh clip.ivf [clip.ivf ...]
set -u
OUT=${OUT:-/var/tmp/av1-gate}
mkdir -p "$OUT"
irq() { awk '/1c0d000/ {print $2; exit}' /proc/interrupts; }
fail=0
for f in "$@"; do
	b=$(basename "$f" .ivf)
	ref="$f.framemd5"
	[ -f "$ref" ] || { echo "$b: no reference $ref"; fail=1; continue; }
	wh=$(awk -F'[ :]+' '/^#dimensions 0/ {print $3; exit}' "$ref")
	grep -v '^#' "$ref" | awk -F', *' '{print $6}' > "$OUT/$b.ref.md5"
	n=$(wc -l < "$OUT/$b.ref.md5")
	a=$(irq)
	timeout 120 gst-launch-1.0 -q filesrc location="$f" ! ivfparse ! av1parse ! \
		v4l2slav1dec ! videoconvert ! video/x-raw,format=I420 ! \
		filesink location="$OUT/$b.hw.yuv" > "$OUT/$b.hw.log" 2>&1
	rc=$?
	d=$(( $(irq) - a ))
	ffmpeg -v error -f rawvideo -pix_fmt yuv420p -s "$wh" -i "$OUT/$b.hw.yuv" \
		-f framemd5 - 2>/dev/null | grep -v '^#' | awk -F', *' '{print $6}' > "$OUT/$b.hw.md5"
	got=$(wc -l < "$OUT/$b.hw.md5")
	same=$(paste -d' ' "$OUT/$b.ref.md5" "$OUT/$b.hw.md5" | awk '$1 == $2' | wc -l)
	first_bad=$(paste -d' ' "$OUT/$b.ref.md5" "$OUT/$b.hw.md5" | awk '$1 != $2 {print NR - 1; exit}')
	[ -n "${KEEP_YUV:-}" ] || rm -f "$OUT/$b.hw.yuv"
	verdict=PASS
	[ "$rc" = 0 ] || verdict=FAIL
	[ "${d:-0}" -ge "$n" ] || verdict=FAIL
	[ "$got" = "$n" ] && [ "$same" = "$n" ] || verdict=FAIL
	[ $verdict = PASS ] || fail=1
	printf '%-24s %s %s  frames exact %s/%s (got %s)  av1_irq=+%s rc=%s%s\n' \
		"$b" "$verdict" "$wh" "$same" "$n" "$got" "$d" "$rc" \
		"${first_bad:+  first mismatch: frame $first_bad}"
done
exit $fail
