#!/bin/sh
# VA-API decode gate for VP9 and AV1. RUNS ON THE TARGET.
#
# Decodes each clip with ffmpeg's VA-API hwaccel (through the v4l2-request
# driver) and with ffmpeg's software decoder, and compares every frame's MD5.
# A clip passes only if the frame counts match, every hash matches, and the
# decoder's interrupt count moved by at least the number of frames -- ffmpeg
# falls back to software without a word when a hwaccel refuses a stream, and
# a fallback hashes exactly like a pass (see passing-suites-that-cannot-fail).
#
#   usage: va-gate.sh clip [clip ...]      (.webm/.ivf/.mkv/.mp4; VP9 or AV1)
set -u
export LIBVA_DRIVER_NAME=${LIBVA_DRIVER_NAME:-v4l2_request}
OUT=${OUT:-/var/tmp/va-gate}
mkdir -p "$OUT"
irq() { awk -v p="$1" '$0 ~ p {print $2; exit}' /proc/interrupts; }
fail=0
for f in "$@"; do
	b=$(basename "$f"); b=${b%.*}
	codec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f")
	case $codec in
	vp9) line=1c0e000; sw=libvpx-vp9 ;;
	av1) line=1c0d000; sw=libdav1d ;;
	*) echo "$b: $codec is not VP9 or AV1"; fail=1; continue ;;
	esac
	ffmpeg -v error -c:v $sw -i "$f" -an -fps_mode passthrough -pix_fmt yuv420p -f framemd5 - 2>/dev/null |
		grep -v '^#' | awk -F', *' '{print $6}' > "$OUT/$b.sw.md5"
	a=$(irq $line)
	timeout "${TIMEOUT:-600}" ffmpeg -v error -hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$f" -vf 'hwdownload,format=nv12' -an -fps_mode passthrough -pix_fmt yuv420p -f framemd5 - \
		2> "$OUT/$b.hw.log" | grep -v '^#' | awk -F', *' '{print $6}' > "$OUT/$b.hw.md5"
	d=$(( $(irq $line) - a ))
	n=$(wc -l < "$OUT/$b.sw.md5"); got=$(wc -l < "$OUT/$b.hw.md5")
	same=$(paste -d' ' "$OUT/$b.sw.md5" "$OUT/$b.hw.md5" | awk '$1 == $2' | wc -l)
	first_bad=$(paste -d' ' "$OUT/$b.sw.md5" "$OUT/$b.hw.md5" | awk '$1 != $2 {print NR - 1; exit}')
	verdict=PASS
	[ "$n" -gt 0 ] && [ "$got" = "$n" ] && [ "$same" = "$n" ] || verdict=FAIL
	[ "$d" -ge "$n" ] || verdict=FAIL
	[ $verdict = PASS ] || fail=1
	printf '%-24s %s %s  frames exact %s/%s (got %s)  irq=+%s%s\n' "$b" "$verdict" "$codec" \
		"$same" "$n" "$got" "$d" "${first_bad:+  first mismatch: frame $first_bad}"
	[ $verdict = PASS ] || head -3 "$OUT/$b.hw.log" | sed 's/^/    /'
done
exit $fail
