#!/bin/bash
# Letterbox Phase 4 geometry stress: play a clip whose picture size changes
# every few frames (make-geometry-stress.sh) on the video plane, then prove
# the plane still works. RUNS ON THE TARGET, as root. Headless: nothing here
# needs the operator; the glass is not part of the pass.
#
#   geometry-stress.sh STRESS.ivf [CONTROL_CLIP]
#
# PASS needs all of:
#   route        h713-play chose plane-up (a GPU route proves nothing);
#   commits      geometry commits (the driver's "video picture ... shown"
#                debug line, drm.debug=0x4 for the run) >= the clip's
#                transitions minus 1% -- kmssink may drop a frame at a join,
#                but a run with few commits did not stress anything;
#   refused      0 refused commits in kmssink's log (a refusal makes it give
#                up scaling for the rest of the run);
#   iommu        0 IOMMU interrupts (a fetch past a buffer faults);
#   kernel       no READY/completion timeouts, "not expressible", faults
#                or warnings from the display driver;
#   gpu          0 GPU interrupts;
#   frames       at most LOSS_MAX (default 4) frames lost per transition.
#                The decoder alone (v4l2slvp9dec ! fakesink sync=true) loses
#                none; the driver's geometry commit costs one extra vsync
#                (kms-geometry-flip: 33.5 ms against 16.7). The rest is
#                GStreamer renegotiating while kmssink holds the shown
#                buffer: 2.5 frames per transition in the first 1-minute run
#                (2026-10-05). A regression shows as a jump, not a drift;
#   alive        afterwards a native CONTROL_CLIP plays with the video
#                plane's fb id changing between two samples, the video
#                source enabled in hardware (0x05600010 bits 1:0 = 3; idle
#                reads ...10) and the display's vsync interrupts counting --
#                DRM accounting alone can look right on a parked plane.
#
# Prints `STRESS key=value` lines and one `STRESS RESULT PASS|FAIL` line.
set -u
CLIP=${1:?usage: geometry-stress.sh STRESS.ivf [CONTROL_CLIP]}
CTRL=${2:-/root/video-test/vp9-rc-30.ivf}
HERE=$(cd "$(dirname "$0")" && pwd)
PLAY=${PLAY:-$HERE/h713-play}
MMIO=${MMIO:-/root/mmio-read}
OUT=${OUT:-/tmp/geometry-stress}
LOSS_MAX=${LOSS_MAX:-4}
mkdir -p "$OUT"

irq() {
	awk -v n="$1" '$NF == n { s = 0; for (i = 2; i <= NF; i++) if ($i ~ /^[0-9]+$/) s += $i; print s; f = 1 }
		END { if (!f) print 0 }' /proc/interrupts
}
video_fb() {
	cat /sys/kernel/debug/dri/*/state 2>/dev/null | awk '
		/^plane\[/ { p = ($0 ~ /video-0/) }
		p && /fb=/ && !/format/ { sub(/.*fb=/, ""); print; exit }'
}
src_ctrl() { "$MMIO" 5600010 1 2>/dev/null | awk 'NR == 1 { print $2 }'; }

frames=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$CLIP")
trans=$(ffprobe -v error -skip_frame nokey -show_entries frame=width,height -of csv=p=0 "$CLIP" | uniq | wc -l)
trans=$((trans - 1))
echo "STRESS clip=${CLIP##*/} frames=$frames transitions=$trans"

fail=0
check() { # name ok-expression message
	if eval "$2"; then echo "STRESS $1 ok: $3"; else echo "STRESS $1 FAIL: $3"; fail=1; fi
}

dmesg -C
echo 0x4 > /sys/module/drm/parameters/debug
dmesg -w > "$OUT/dmesg.log" 2>&1 &
dpid=$!
g0=$(irq panfrost-job) m0=$(irq 2010000.iommu) f0=$(irq h713-afbd) v0=$(irq 1c0e000.video-codec)
t0=$(date +%s)
GST_DEBUG=kmssink:3 "$PLAY" --route=plane "$CLIP" > "$OUT/play.log" 2>&1 < /dev/null
rc=$?
t1=$(date +%s)
g=$(( $(irq panfrost-job) - g0 )) m=$(( $(irq 2010000.iommu) - m0 ))
f=$(( $(irq h713-afbd) - f0 )) v=$(( $(irq 1c0e000.video-codec) - v0 ))
sleep 1
echo 0 > /sys/module/drm/parameters/debug
kill $dpid 2>/dev/null; wait $dpid 2>/dev/null

route=$(grep -m1 -oE 'plane-[a-z]+|: gpu' "$OUT/play.log")
commits=$(grep -c 'h713_lb_program\] video picture' "$OUT/dmesg.log")
refused=$(sed 's/\x1b\[[0-9;]*m//g' "$OUT/play.log" | grep -ciE 'Failed to (set|draw)|setplane.*fail|Invalid argument|Numerical result')
rendered=$(sed -n 's/.*rendered \([0-9]*\),.*/\1/p' "$OUT/play.log")
dropped=$(sed -n 's/.*dropped \([0-9]*\),.*/\1/p' "$OUT/play.log")
bad=$(grep -E 'sun50i-h713-afbd|iommu' "$OUT/dmesg.log" | grep -vE 'h713_lb_program\]|\[drm:drm_' | grep -iE 'warn|err|fault|did not|not expressible|timeout' )

echo "STRESS play exit=$rc seconds=$((t1 - t0)) rendered=${rendered:-?} dropped=${dropped:-?}"
echo "STRESS irqs gpu=$g iommu=$m afbd=$f cedrus=$v"
check route '[ "$route" = plane-up ]' "route=${route:-none}"
check commits '[ "$commits" -ge $(( trans - trans / 100 )) ]' "$commits geometry commits for $trans transitions"
check refused '[ "$refused" = 0 ]' "$refused refused commits in kmssink's log"
check iommu '[ "$m" = 0 ]' "$m IOMMU interrupts"
check gpu '[ "$g" = 0 ]' "$g GPU interrupts"
check kernel '[ -z "$bad" ]' "$(printf '%s' "$bad" | wc -l) display/IOMMU complaints"
[ -n "$bad" ] && printf '%s\n' "$bad" | head -20 | sed 's/^/STRESS   /'
lost=$(( frames - ${rendered:-0} ))
per=$(awk -v l=$lost -v t=$trans 'BEGIN { printf "%.2f", t ? l / t : l }')
check frames 'awk -v p=$per -v m=$LOSS_MAX "BEGIN { exit !(p <= m) }"' "rendered ${rendered:-0} of $frames: $per lost per transition (max $LOSS_MAX)"

# Alive afterwards: a control clip must flip the plane and move the ring.
"$PLAY" --route=plane "$CTRL" > "$OUT/control.log" 2>&1 < /dev/null &
cp=$!
sleep 3; fb1=$(video_fb) f1=$(irq h713-afbd) sc=$(src_ctrl)
sleep 1; fb2=$(video_fb) f2=$(irq h713-afbd)
wait $cp; crc=$?
check alive '[ $crc = 0 ] && [ -n "$fb1" ] && [ "$fb1" != "$fb2" ] && [ $(( sc & 3 )) = 3 ] && [ $(( f2 - f1 )) -gt 30 ]' \
	"control ${CTRL##*/}: exit $crc, fb $fb1 -> $fb2, source ctrl $sc, $(( f2 - f1 )) vsyncs in 1 s"

[ $fail = 0 ] && echo "STRESS RESULT PASS" || echo "STRESS RESULT FAIL"
exit $fail
