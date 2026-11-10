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
#   usage: av1-gate.sh clip.{ivf,mp4,mkv} [...]   (reference: clip.ext.framemd5)
set -u
OUT=${OUT:-/var/tmp/av1-gate}
mkdir -p "$OUT"
irq() { awk '/1c0d000/ {print $2; exit}' /proc/interrupts; }
# Driver complaints so far; a clip that provokes one fails even if it hashes.
kerr() { dmesg | grep -cE 'decode failed|core still busy|interrupt without a cause|cannot set up the frame|timed out|iommu.*fault'; }
demux() { case "$1" in *.ivf) echo ivfparse ;; *.mp4) echo qtdemux ;; *) echo matroskademux ;; esac; }
# GStreamer pads each I420 row to a multiple of 4 bytes; ffmpeg's rawvideo
# wants them tight. Only widths that are not a multiple of 8 need it.
depad() {
	if [ $(($1 % 8)) = 0 ]; then cat; else python3 -c '
import sys
w, h = int(sys.argv[1]), int(sys.argv[2])
cw, ch = (w + 1) // 2, (h + 1) // 2
ys, cs = (w + 3) & ~3, (cw + 3) & ~3
i, o = sys.stdin.buffer, sys.stdout.buffer
while True:
    f = i.read(ys * h + 2 * cs * ch)
    if len(f) < ys * h + 2 * cs * ch:
        break
    for r in range(h):
        o.write(f[r * ys:r * ys + w])
    for p in range(2):
        b = ys * h + p * cs * ch
        for r in range(ch):
            o.write(f[b + r * cs:b + r * cs + cw])
' "$1" "$2"; fi
}
fail=0
for f in "$@"; do
	b=$(basename "$f"); b=${b%.*}
	ref="$f.framemd5"
	[ -f "$ref" ] || { echo "$b: no reference $ref"; fail=1; continue; }
	wh=$(awk -F'[ :]+' '/^#dimensions 0/ {print $3; exit}' "$ref")
	grep -v '^#' "$ref" | awk -F', *' '{print $6}' > "$OUT/$b.ref.md5"
	n=$(wc -l < "$OUT/$b.ref.md5")
	a=$(irq)
	e0=$(kerr)
	# Hash in a stream: a long clip's raw frames do not fit on the board.
	# KEEP_YUV=1 also keeps them (short clips only).
	{ timeout "${TIMEOUT:-600}" gst-launch-1.0 -q filesrc location="$f" ! $(demux "$f") ! av1parse ! \
		v4l2slav1dec ! videoconvert ! video/x-raw,format=I420 ! \
		fdsink fd=1 2> "$OUT/$b.hw.log"; echo $? > "$OUT/$b.rc"; } |
		depad "${wh%x*}" "${wh#*x}" |
		{ if [ -n "${KEEP_YUV:-}" ]; then tee "$OUT/$b.hw.yuv"; else cat; fi; } |
		ffmpeg -v error -f rawvideo -pix_fmt yuv420p -s "$wh" -i - \
		-f framemd5 - 2>/dev/null | grep -v '^#' | awk -F', *' '{print $6}' > "$OUT/$b.hw.md5"
	rc=$(cat "$OUT/$b.rc")
	d=$(( $(irq) - a ))
	ke=$(( $(kerr) - e0 ))
	got=$(wc -l < "$OUT/$b.hw.md5")
	same=$(paste -d' ' "$OUT/$b.ref.md5" "$OUT/$b.hw.md5" | awk '$1 == $2' | wc -l)
	first_bad=$(paste -d' ' "$OUT/$b.ref.md5" "$OUT/$b.hw.md5" | awk '$1 != $2 {print NR - 1; exit}')
	verdict=PASS
	[ "$rc" = 0 ] || verdict=FAIL
	[ "${d:-0}" -ge "$n" ] || verdict=FAIL
	[ "$ke" = 0 ] || verdict=FAIL
	[ "$got" = "$n" ] && [ "$same" = "$n" ] || verdict=FAIL
	[ $verdict = PASS ] || fail=1
	printf '%-24s %s %s  frames exact %s/%s (got %s)  av1_irq=+%s kerr=+%s rc=%s%s\n' \
		"$b" "$verdict" "$wh" "$same" "$n" "$got" "$d" "$ke" "$rc" \
		"${first_bad:+  first mismatch: frame $first_bad}"
done
exit $fail
