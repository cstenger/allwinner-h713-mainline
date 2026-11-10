#!/bin/sh
# Soak one clip through tools/video/h713-play: continuous playback, A/V sync
# near the start and near the end (drift), and CPU / GPU / temperature in
# between. RUNS ON THE TARGET.
#
#   sh plane-soak.sh CLIP [MINUTES]          (MINUTES defaults to 10)
#
# CLIP should be an av-sync clip long enough for the soak
# (tools/video/make-avsync-clip.sh OUTDIR 630 all). Prints `SOAK key=value`
# lines and one `SOAK SUMMARY` line. Why each number is there:
#   route=      h713-play's decision; a soak of the wrong route proves nothing.
#   rendered/position  frames shown against stream time: 30 fps means
#               rendered ~= position * 30.
#   sync0/sync1 av-sync-probe's median offset early and late in the same
#               playback; their difference is drift (audio vs the system
#               clock the pipeline runs on).
#   cpu/player  whole-board and player CPU, averaged only between the two
#               probe windows (the probe's own load is excluded).
#   gpu_irq     GPU interrupts over the same window: the plane routes should
#               leave it at 0.
#   pcm         the playback PCM's state at every sample; anything but
#               RUNNING means audio stopped.
CLIP=${1:?usage: plane-soak.sh CLIP [MINUTES]}
MIN=${2:-10}
PROBE=${PROBE:-/root/av-sync-probe}
PLAY=${PLAY:-/root/h713-play}
DUR=$((MIN * 60))
[ -r "$CLIP" ] || { echo "SOAK ERROR: no clip $CLIP"; exit 2; }

cpu() { head -1 /proc/stat; }
gpu() { awk '/panfrost/ { s += $2 + $3 + $4 + $5 } END { print s + 0 }' /proc/interrupts; }
ptime() { awk '{ print $14 + $15 }' "/proc/$1/stat" 2>/dev/null || echo 0; }
temp() { cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | sort -n | tail -1; }
pcm() { grep -h '^state' /proc/asound/card*/pcm*p/sub0/status 2>/dev/null | awk '{ print $2 }' | head -1; }
busy() { printf '%s\n%s\n' "$1" "$2" | awk '{ idle[NR] = $5 + $6; t = 0; for (i = 2; i <= NF; i++) t += $i; tot[NR] = t }
	END { printf "%.1f", 100 * (1 - (idle[2] - idle[1]) / (tot[2] - tot[1])) }'; }

"$PLAY" "$CLIP" > /tmp/soak-play.log 2>&1 &
P=$!
sleep 5
route=$(head -1 /tmp/soak-play.log | grep -oE 'plane-[a-z]+|gpu' | head -1)
echo "SOAK clip=${CLIP##*/} route=${route:-?} minutes=$MIN pid=$P"

sync0=$("$PROBE" 25 | sed -n 's/.*median \([^ ]*\) ms.*/\1/p')
[ -n "$sync0" ] || sync0=none

# The measured window: from after the first probe to before the second.
c0=$(cpu); g0=$(gpu); p0=$(ptime $P); hz=$(getconf CLK_TCK); t0=$(date +%s)
maxt=$(temp); states=""
end=$((DUR - 40))
while [ $(( $(date +%s) - t0 + 30 )) -lt "$end" ]; do
	kill -0 $P 2>/dev/null || break
	sleep 10
	t=$(temp); [ "$t" -gt "$maxt" ] && maxt=$t
	s=$(pcm); case " $states " in *" $s "*) ;; *) states="$states $s" ;; esac
done
c1=$(cpu); g1=$(gpu); p1=$(ptime $P); t1=$(date +%s)
secs=$((t1 - t0))

sync1=$("$PROBE" 25 | sed -n 's/.*median \([^ ]*\) ms.*/\1/p')
[ -n "$sync1" ] || sync1=none

kill -INT $P 2>/dev/null
wait $P 2>/dev/null
res=$(grep 'gst-plane-play:\|Exiting' /tmp/soak-play.log | tail -1)
drift=none
[ "$sync0" != none ] && [ "$sync1" != none ] &&
	drift=$(awk -v a="$sync0" -v b="$sync1" 'BEGIN { printf "%+.1f", b - a }')
player=$(awk -v d=$((p1 - p0)) -v hz="$hz" -v s="$secs" 'BEGIN { printf "%.1f", 100 * d / hz / s }')

echo "SOAK window=${secs}s cpu_all=$(busy "$c0" "$c1")% player=${player}% gpu_irq=$((g1 - g0)) max_temp=$((maxt / 1000))C pcm=${states# }"
echo "SOAK result: $res"
echo "SOAK SUMMARY ${CLIP##*/} route=${route:-?} sync0=${sync0}ms sync1=${sync1}ms drift=${drift}ms cpu_all=$(busy "$c0" "$c1")% player=${player}% gpu_irq=$((g1 - g0)) max_temp=$((maxt / 1000))C pcm=${states# } | $res"
