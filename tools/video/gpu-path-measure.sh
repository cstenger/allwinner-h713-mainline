#!/bin/sh
# Measure one clip through stock mpv on the GPU path. RUNS ON THE TARGET.
# WP2 of docs/gpu-fallback-plan.md; the host driver is gpu-path-run.sh.
#
#   sh gpu-path-measure.sh CLIP [LABEL]
#   VO=gpu-next DUR=60 MPV_OPTS='--scale=bilinear' sh gpu-path-measure.sh clip.mp4
#
# Prints a block of `WP2 key=value` lines and one `WP2 SUMMARY` line. Each
# number is there because a passing run can hide its absence:
#
#   hwdec=      mpv's own hwdec-current. "no" means software decode, and the
#               GPU numbers then describe a different workload.
#   dec_irq=    decoder interrupts (cedrus or the AV1 core). Zero means no frame
#               reached hardware, whatever hwdec= claims.
#   vodrop/decdrop/delayed  mpv's counters (frame-drop-count is the VO's drops
#               in mpv 0.40; decoder-frame-drop-count the decoder's). vodrop is
#               what the eye sees.
#   gpu_busy=   fragment-engine busy share from Panfrost's own counters, and
#   gpu_real=   cycles/ns, the GPU's REAL clock (clk_summary lied until 0152).
#   flips=      distinct plane states in a 20-sample burst ~50 ms apart (a
#               frozen picture shows 1). Replaced fb_changes=, which aliased.
#   fb_changes= how many of the plane-state samples showed a new framebuffer on
#               the plane with a CRTC. A frozen picture shows 0; "mpv says it
#               played" is not "the panel changed" (see vo=drm, 2026-09-03).
set -u
CLIP=$1
LABEL=${2:-$(basename "$CLIP")}
VO=${VO:-gpu}
DUR=${DUR:-60}
MPV=${MPV:-/usr/bin/mpv}
HWDEC=${HWDEC:-vaapi}
MPV_OPTS=${MPV_OPTS:-}
GPU=/sys/bus/platform/devices/1800000.gpu
DF=/sys/class/devfreq/1800000.gpu
LOG=/tmp/gpu-path-mpv.log
STATE=/tmp/gpu-path-planes.txt

[ -r "$CLIP" ] || { echo "WP2 FATAL no clip $CLIP"; exit 1; }

irqsum() {
	awk -v p="$1" 'NR == 1 { ncpu = NF; next }
	               $0 ~ p { for (i = 2; i <= ncpu + 1; i++) s += $i }
	               END { print s + 0 }' /proc/interrupts
}
cpustat() { awk '/^cpu /{ print $2+$3+$4+$6+$7+$8, $5 }' /proc/stat; }
zone() {
	for z in /sys/class/thermal/thermal_zone*; do
		[ "$(cat "$z/type")" = "$1" ] && cat "$z/temp"
	done
}
# Panfrost per-client counters: "cycles ns" for the client with work.
gpusample() {
	for fd in /proc/$1/fdinfo/*; do
		grep -q 'drm-driver:.*panfrost' "$fd" 2>/dev/null || continue
		c=$(awk '/drm-cycles-fragment/{print $2}' "$fd")
		n=$(awk '/drm-engine-fragment/{print $2}' "$fd")
		[ "${c:-0}" != 0 ] && { echo "$c $n"; return; }
	done
	echo "0 0"
}
# The fb id on every plane that has a CRTC, as one token per plane.
planes() {
	awk '/^plane\[/ { p = $1 } /crtc=crtc/ { c = 1 } /crtc=\(null\)/ { c = 0 }
	     /^\t*fb=/ { if (c && $1 != "fb=0") printf "%s%s ", p, $1 }
	     END { print "" }' /sys/kernel/debug/dri/5600000.display/state 2>/dev/null
}

echo 1 > "$GPU/profiling"
DEC0=$(irqsum 'video-codec|1c0d000|av1')
GIRQ0=$(irqsum 'panfrost-job')
set -- $(cpustat); CB0=$1 CI0=$2
T0=$(date +%s)

# --gpu-context only for the GPU VOs: the patched direct-path build
# (/usr/local/bin/mpv, vo=drm) has no DRM GPU context and exits on the option.
# LOOP=1 loops the clip for DUR seconds (the 10-minute direct-vs-GPU runs);
# stopping it at DUR is then the plan, not a sign of a slow player.
case "$VO" in gpu*) CTX=--gpu-context=drm ;; *) CTX= ;; esac
if [ -n "${LOOP:-}" ]; then LEN=--loop-file=inf; else LEN=--end=$DUR; fi

# shellcheck disable=SC2086
LIBVA_DRIVER_NAME=v4l2_request "$MPV" --no-config --vo="$VO" $CTX \
	--hwdec="$HWDEC" $LEN --input-terminal=no --really-quiet=no \
	--term-status-msg='STAT vodrop=${frame-drop-count} decdrop=${decoder-frame-drop-count} delayed=${vo-delayed-frame-count} avsync=${avsync} pos=${=time-pos} hwdec=${hwdec-current} src=${video-params/w}x${video-params/h} fmt=${video-params/hw-pixelformat} fps=${container-fps} est=${estimated-vf-fps}' \
	$MPV_OPTS "$CLIP" > "$LOG" 2>&1 < /dev/null &
MPID=$!

# Settle, then sample through the steady state.
sleep 5
G0=$(gpusample $MPID)
: > "$STATE"
TMAXG=0 TMAXC=0 KHZ=""
i=0
while kill -0 $MPID 2>/dev/null && [ $i -lt $((DUR - 10)) ]; do
	planes >> "$STATE"
	g=$(zone gpu-thermal); c=$(zone cpu-thermal)
	[ "${g:-0}" -gt "$TMAXG" ] && TMAXG=$g
	[ "${c:-0}" -gt "$TMAXC" ] && TMAXC=$c
	KHZ="$KHZ $(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
	MCPU=$(awk '{ print $14 + $15 }' /proc/$MPID/stat 2>/dev/null || echo "$MCPU")
	G1=$(gpusample $MPID)
	sleep 1
	i=$((i + 1))
done
# Flip check. The 1 s samples above alias: mpv cycles three buffers at 30 fps,
# so a once-a-second sample lands on the same one every time and a moving
# picture reads as frozen (2026-10-02: 1/50 on a clip that played fine). A
# burst faster than the frame rate cannot alias that way. Only meaningful
# while the player is still running, so it is taken here, before the wait.
FLIPS=na
if kill -0 $MPID 2>/dev/null; then
	: > "$STATE.burst"
	for b in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
		planes >> "$STATE.burst"
		sleep 0.04
	done
	FLIPS=$(sort -u "$STATE.burst" | wc -l)
fi

# Bounded: a player that cannot present (e.g. "Mapping hardware decoded surface
# failed") stops advancing and never reaches --end, and an unbounded wait here
# once held the panel and the whole run for 17 minutes on a 60 s clip.
HUNG=0
LIMIT=$((DUR + 20)); [ -n "${LOOP:-}" ] && LIMIT=$DUR
while kill -0 $MPID 2>/dev/null && [ $(($(date +%s) - T0)) -lt $LIMIT ]; do
	sleep 1
done
if [ -n "${LOOP:-}" ] && kill -0 $MPID 2>/dev/null; then
	kill $MPID
elif kill -0 $MPID 2>/dev/null; then
	HUNG=1
	# Evidence before the kill: where every thread is waiting, the kernel
	# stacks of the blocked ones, and what mpv last said.
	for t in /proc/$MPID/task/*; do
		echo "WP2 hung-thread $(cat $t/comm) state=$(cut -d' ' -f3 $t/stat) wchan=$(cat $t/wchan)"
		case "$(cut -d' ' -f3 $t/stat)" in D) sed 's/^/WP2 hung-stack   /' $t/stack 2>/dev/null ;; esac
	done
	tr '\r' '\n' < "$LOG" | grep -av '^STAT' | grep -av '^[[:space:]]*$' | tail -8 | sed 's/^/WP2 hung-log /'
	tr '\r' '\n' < "$LOG" | grep -a '^STAT' | tail -1 | sed 's/^/WP2 hung-last /'
	dmesg | tail -5 | sed 's/^/WP2 hung-dmesg /'
	kill $MPID; sleep 2; kill -9 $MPID 2>/dev/null
fi
wait $MPID
RC=$?
# "HUNG" is usually not a deadlock: a renderer slower than real time that has
# stopped dropping frames (gpu-next upscaling 852x480 ran at 0.3x, 2026-10-02).
# speed= (position reached / wall time) says which. mpv start-up is inside the
# wall time, so a real-time 60 s run reads ~0.94; well below 0.9 is not real time.
[ $HUNG = 1 ] && RC=SLOW-OR-HUNG
T1=$(date +%s)
echo 0 > "$GPU/profiling"

DEC=$(( $(irqsum 'video-codec|1c0d000|av1') - DEC0 ))
GIRQ=$(( $(irqsum 'panfrost-job') - GIRQ0 ))
set -- $(cpustat); CB=$(( $1 - CB0 )) CI=$(( $2 - CI0 ))
SECS=$((T1 - T0))
CLK=$(getconf CLK_TCK)
set -- $G0 $G1
GBUSY=$(awk -v n0="$2" -v n1="$4" -v s="$i" 'BEGIN { if (s > 0) printf "%.0f", (n1 - n0) / (s * 1e7); else print "na" }')
GREAL=$(awk -v c0="$1" -v n0="$2" -v c1="$3" -v n1="$4" 'BEGIN { if (n1 > n0) printf "%.0f", (c1 - c0) * 1000 / (n1 - n0); else print "na" }')
# Cumulative ms in each OPP since boot (MHz:ms); diff two runs for a delta.
TIS=$(awk 'NR > 2 { gsub(/\*/, ""); printf "%s:%s ", $1 / 1000000, $NF }' "$DF/trans_stat")
STAT=$(tr '\r' '\n' < "$LOG" | grep -a '^STAT' | tail -1)
FB=$(awk '{ print }' "$STATE" | sort | uniq | wc -l)
NS=$(wc -l < "$STATE")
KHZ=$(echo $KHZ | tr ' ' '\n' | sort -n | uniq -c | awk '{ printf "%d@%d ", $1, $2 / 1000 }')
ERR=$(grep -aiE 'error|failed|fallback|unsupported' "$LOG" | grep -av '^STAT' | sort -u | head -3 | tr '\n' '|')

echo "WP2 label=$LABEL vo=$VO opts='$MPV_OPTS' rc=$RC secs=$SECS"
echo "WP2 mpv: ${STAT#STAT }"
echo "WP2 dec_irq=$DEC gpu_irq_s=$((GIRQ / (SECS > 0 ? SECS : 1))) gpu_busy=${GBUSY}% gpu_real=${GREAL}MHz opp_ms_cumulative=[$TIS]"
echo "WP2 cpu_all=$(awk -v b=$CB -v i=$CI 'BEGIN { printf "%.0f", 100 * b / (b + i) }')% mpv_cpu=$(awk -v t="${MCPU:-0}" -v k=$CLK -v s=$SECS 'BEGIN { printf "%.0f", 100 * t / k / s }')%(of-one-core) cpu_khz=[$KHZ] tmax_gpu=$TMAXG tmax_cpu=$TMAXC"
echo "WP2 planes: samples=$NS distinct_states=$FB flips_in_burst=$FLIPS/20 last=[$(tail -1 "$STATE")]"
[ -n "$ERR" ] && echo "WP2 mpv-msgs: $ERR"
set -- ${STAT#STAT }
POS=$(echo "$STAT" | sed -n 's/.* pos=\([0-9.]*\).*/\1/p')
SPEED=$(awk -v p="${POS:-0}" -v s="$SECS" 'BEGIN { if (s > 0) printf "%.2f", p / s; else print "na" }')
echo "WP2 SUMMARY $LABEL vo=$VO rc=$RC speed=$SPEED $* dec_irq=$DEC gpu_busy=${GBUSY}% gpu_real=${GREAL} flips=$FLIPS/20 tmax_gpu=$TMAXG"
