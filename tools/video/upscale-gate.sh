#!/bin/bash
# Letterbox Phase 3 gate: do sub-panel clips play MAGNIFIED on the video plane
# through stock kmssink, GPU idle? RUNS ON THE TARGET, as root.
#
#   upscale-gate.sh [--lead S] [--gap S] CLIP...
#
# For each clip, h713-play picks the route and plays it (stock
# v4l2sl*dec ! kmssink for plane-up). While it plays this records:
#   * the route h713-play printed;
#   * the video plane's DRM state at 4 s and 6 s (debugfs): crtc, fb id,
#     crtc-pos (the destination kmssink asked for), src-pos. The fb id must
#     CHANGE between the two -- a parked plane can still look right;
#   * interrupt deltas: panfrost-job (must be 0, or the clip silently went
#     to the GPU), the decoders (1c0e000.video-codec = cedrus: H.264, HEVC
#     and VP9; 1c0d000.av1 = the AV1 core), h713-afbd (the plane's vsyncs)
#     and the IOMMU (faults);
#   * new kernel messages (refused commits, IOMMU faults);
#   * a scanout grab at 5 s (/root/scanout-grab). It reads the FRAMEBUFFER,
#     i.e. the source picture before proc: it proves the buffer is right and
#     at the source size, NOT the magnification -- only the glass shows that.
#   * gst-plane-play's rendered / dropped counts.
#
# OPERATOR: one "ready" runs everything. The first clip starts after --lead
# seconds (default 30); the console shows for --gap seconds between clips
# (default 5); the console coming back for good is the cue to stop. Compare
# each clip against its .ref.png from make-upscale-clips.sh.
set -u
LEAD=30 GAP=5
while [ $# -gt 0 ]; do
	case $1 in
	--lead) LEAD=$2; shift 2 ;;
	--gap) GAP=$2; shift 2 ;;
	*) break ;;
	esac
done
HERE=$(cd "$(dirname "$0")" && pwd)
PLAY=${PLAY:-$HERE/h713-play}
OUT=${OUT:-/tmp/upscale-gate}
mkdir -p "$OUT"
T0=$(date +%s.%N)
ts() { awk -v t0="$T0" -v t="$(date +%s.%N)" 'BEGIN { printf "%7.2f", t - t0 }'; }

irq() {	# sum of all CPUs' counts for the interrupt named $1
	awk -v n="$1" '$NF == n { s = 0; for (i = 2; i <= NF; i++) if ($i ~ /^[0-9]+$/) s += $i; print s; f = 1 }
		END { if (!f) print 0 }' /proc/interrupts
}

plane_state() {	# crtc fb crtc-pos src-pos of the plane named video-0
	cat /sys/kernel/debug/dri/*/state 2>/dev/null | awk '
		/^plane\[/ { p = ($0 ~ /video-0/) }
		p && /crtc=/ { sub(/.*crtc=/, ""); c = $0 }
		p && /fb=/ && !/fb=.*format/ { sub(/.*fb=/, ""); f = $0 }
		p && /crtc-pos=/ { sub(/.*crtc-pos=/, ""); cp = $0 }
		p && /src-pos=/ { sub(/.*src-pos=/, ""); sp = $0 }
		END { printf "crtc=%s fb=%s dst=%s src=%s", c, f, cp, sp }'
}

echo "[$(ts)] upscale gate: ${#@} clips; first starts in ${LEAD}s"
sleep "$LEAD"
for clip in "$@"; do
	b=$(basename "$clip" .mp4)
	d0=$(dmesg | wc -l)
	g0=$(irq panfrost-job) v0=$(irq 1c0e000.video-codec) a0=$(irq 1c0d000.av1)
	f0=$(irq h713-afbd) m0=$(irq 2010000.iommu)
	echo "[$(ts)] === $b ==="
	"$PLAY" "$clip" > "$OUT/$b.log" 2>&1 < /dev/null &
	pid=$!
	sleep 4; s4=$(plane_state)
	sleep 1; grab=$(/root/scanout-grab "$OUT/$b.ppm" 2>&1 | tail -1)
	sleep 1; s6=$(plane_state)
	wait "$pid"; rc=$?
	g=$(( $(irq panfrost-job) - g0 )) v=$(( $(irq 1c0e000.video-codec) - v0 ))
	a=$(( $(irq 1c0d000.av1) - a0 )) f=$(( $(irq h713-afbd) - f0 ))
	m=$(( $(irq 2010000.iommu) - m0 ))
	new=$(dmesg | tail -n +$((d0 + 1)))
	fb4=$(printf '%s' "$s4" | sed 's/.*fb=\([^ ]*\).*/\1/')
	fb6=$(printf '%s' "$s6" | sed 's/.*fb=\([^ ]*\).*/\1/')
	echo "  route: $(grep -m1 '^h713-play:' "$OUT/$b.log" | sed 's/^h713-play: //')"
	echo "  plane @4s: $s4"
	echo "  plane @6s: $s6   fb $([ "$fb4" != "$fb6" ] && echo CHANGES || echo 'DOES NOT CHANGE')"
	echo "  irqs: gpu $g, cedrus $v, av1 $a, afbd $f, iommu $m"
	echo "  grab: $grab"
	echo "  player: $(grep -iE 'rendered|dropped|error' "$OUT/$b.log" | tr '\n' ' ') (exit $rc)"
	if [ -n "$new" ]; then echo "  KERNEL:"; printf '%s\n' "$new" | sed 's/^/    /'; else echo "  kernel: quiet"; fi
	sleep "$GAP"
done
echo "[$(ts)] upscale gate done"
