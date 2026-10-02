#!/usr/bin/env bash
# WP2 driver for gst-path-measure.sh: CLIP:DECODER pairs. RUNS ON THE HOST.
#   tools/video/gst-path-run.sh 1b-h264-1280x720.mp4:v4l2slh264dec 05-av1-1080.mp4:vaav1dec
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
BOARD=${BOARD:-192.168.4.1}
MEDIA=${MEDIA:-$ROOT/local/h713-lab/stock-capture-20261001/media}
DUR=${DUR:-30}
OUT=${OUT:-$ROOT/local/h713-lab/wp2-$(date +%Y%m%d)/gst-results.txt}
SSH=(ssh -F /dev/null -o ConnectTimeout=8 "root@$BOARD")
mkdir -p "$(dirname "$OUT")"
scp -q -F /dev/null "$ROOT/tools/video/gst-path-measure.sh" "root@$BOARD:/root/"
echo "# $(date -Is) kernel=$("${SSH[@]}" 'uname -v') dur=$DUR" >> "$OUT"
for pair in "$@"; do
	c=${pair%%:*} d=${pair#*:}
	"${SSH[@]}" "test -s /tmp/$c" || scp -q -F /dev/null "$MEDIA/$c" "root@$BOARD:/tmp/$c"
	"${SSH[@]}" "sh /root/gst-path-measure.sh /tmp/$c $d $DUR" | tee -a "$OUT"
	sleep 5
done
"${SSH[@]}" 'rm -f /tmp/*.mp4 /tmp/*.webm'
grep 'GST SUMMARY' "$OUT" | tail -n $#
