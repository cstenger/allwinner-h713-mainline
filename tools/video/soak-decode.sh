#!/bin/bash
# Hardware decode under sustained load, for hours. RUNS ON THE TARGET.
#
# The gate (hevc-decode-test.sh, va-decode-test.sh) proves the decoder is
# CORRECT. It cannot say the decoder is DURABLE: every vector is 25-60 frames
# and the whole run is over in a minute. This is the other half -- the same
# bit-exactness check, made continuously for hours, so that anything which only
# appears with time or repetition has somewhere to show up:
#
#   * output drifting after N iterations (would be silent corruption)
#   * a leak in CMA, in the kernel's free memory, or in buffer accounting
#   * the VE timing out once under repetition and never recovering
#   * throughput decaying as the board heats up
#
# WHY BIT-EXACTNESS EVERY ITERATION, not just liveness: a soak that only checks
# "did it exit 0" would have passed all the way through the scaling-list bug
# fixed in libva patch 0005 -- 25 frames decoded on the engine, to the wrong
# answer, exit status 0. Correctness has to be re-asserted, not assumed.
#
# NO DISPLAY IS INVOLVED, deliberately. The display path is a separate risk with
# its own history (docs/vaapi-scope.md); mixing them means a failure lands in
# neither half cleanly. This soak is about the video engine and the shim.
#
# NOTHING IS WRITTEN TO DISK per iteration. Decoded frames go down a pipe to
# md5sum -- 11.5 MB a vector at 640x480 and 82 MB at 720p60 would be hours of
# pointless eMMC wear, and /tmp is a tmpfs that would hit ENOSPC and produce a
# truncated file with a perfectly valid md5 (which scores as MISMATCH and reads
# as a decode bug).
#
#   usage: ./soak-decode.sh [seconds]          (default 7200 = 2 hours)
#          DURATION=600 ./soak-decode.sh       same thing
#          VECTORS="h01-640x480-main" ./soak-decode.sh 300
#
# Run it detached so an ssh drop does not kill it:
#   setsid nohup ./soak-decode.sh 7200 > /var/log/soak-decode.log 2>&1 &

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
DURATION=${1:-${DURATION:-7200}}
HEARTBEAT=${HEARTBEAT:-120}

HEVC_REF="$DIR/hevc-reference-md5.txt"
H264_REF="$DIR/reference-md5.txt"

HEVC_VECTORS="h01-640x480-main h02-1280x720-main h03-640x480-nowpp
	      h04-640x480-scaling h05-640x480-scaling-custom"
H264_VECTORS="v01-320x240-baseline v02-1280x720-baseline v03-1280x720-main
	      v04-1280x720-high v05-1920x1080-high"
VECTORS=${VECTORS:-"$HEVC_VECTORS $H264_VECTORS"}

# Sum the per-CPU columns of the video-codec interrupt line. A rise of exactly
# one per frame is positive proof the VE did the work; a FLAT counter across an
# iteration that still produced the right md5 means a silent software fallback,
# which is a failure however good the output looks.
ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}

meminfo() { awk -v k="$1:" '$1 == k { print $2 }' /proc/meminfo; }

# RAW CmaFree IS NOT A LEAK INDICATOR, and reading it as one wastes a session.
# CMA hosts movable allocations, so the page cache lives there quite legally and
# is handed back under pressure. Measured on this board: CmaFree fell 42,908 kB
# -> 7,156 kB across a 100-second soak and looked exactly like a leak, then
# returned to 115,704 kB the moment caches were dropped -- HIGHER than the
# "baseline", which was itself mostly cache. So the before/after pair that
# actually means something is taken after reclaim; the heartbeat value is kept
# only as a coarse liveness signal and labelled to say so.
cma_settled() { sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null; sleep 1; meminfo CmaFree; }

# Count the kernel's own complaints since boot. These are the events that would
# otherwise be invisible from userspace -- a decode can return success while the
# driver has logged a timeout and reset the engine underneath it.
dmesg_count() { dmesg | grep -ciE "$1" || true; }

# The two reference files are shaped differently and neither format is
# negotiable here -- they are what the existing gates already score against, and
# a soak that invented its own baseline would not be measuring the same claim.
# hevc-reference-md5.txt is `<md5>  <vector>`; reference-md5.txt is per-frame
# lines plus one `<vector> WHOLE <frames> <md5>` summary.
want_md5() {
	case $1 in
	h0*) grep " $1\$" "$HEVC_REF" | cut -d' ' -f1 ;;
	*)   grep "^$1 WHOLE" "$H264_REF" | awk '{print $NF}' ;;
	esac
}

stream_of() {
	case $1 in
	h0*) echo "$DIR/$1.h265" ;;
	*)   echo "$DIR/$1.h264" ;;
	esac
}

# One decode through the production path: stock ffmpeg, VA-API, our shim.
# -hwaccel_output_format vaapi is LOAD-BEARING -- without it ffmpeg silently
# falls back to software when hwaccel init fails, and software decode
# reproduces the reference md5 by definition, so the run would report PASS
# having never touched the VE.
decode_md5() {
	LIBVA_DRIVER_NAME=v4l2_request ffmpeg -hide_banner -v error -y \
		-hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$1" -vf 'hwdownload,format=nv12' \
		-f rawvideo -pix_fmt nv12 pipe:1 2>"$ERR" | md5sum | cut -d' ' -f1
}

ERR=$(mktemp)
trap 'rm -f "$ERR"' EXIT

for v in $VECTORS; do
	[ -r "$(stream_of "$v")" ] || { echo "FATAL: no stream for $v"; exit 1; }
	[ -n "$(want_md5 "$v")" ] || { echo "FATAL: no reference md5 for $v"; exit 1; }
done

start=$(date +%s)
deadline=$((start + DURATION))
ve0=$(ve_irq)
to0=$(dmesg_count "frame processing timed out")
to_start=$to0
oops0=$(dmesg_count "Oops|BUG:|Call trace|kernel panic")
cma0=$(cma_settled)
mem0=$(meminfo MemAvailable)

iter=0; pass=0; fail=0; fallback=0
declare -A first_ms   # per-vector wall time of the first iteration, for drift

echo "SOAK-DECODE start $(date -Is) duration=${DURATION}s vectors=$(echo $VECTORS | wc -w)"
echo "SOAK-DECODE baseline ve=$ve0 timeouts=$to0 oops=$oops0 cma=${cma0}kB memavail=${mem0}kB"
echo "SOAK-DECODE kernel=$(uname -r) maxfreq=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq 2>/dev/null)"

next_beat=$((start + HEARTBEAT))

while [ "$(date +%s)" -lt "$deadline" ]; do
	for v in $VECTORS; do
		[ "$(date +%s)" -lt "$deadline" ] || break

		a=$(ve_irq)
		t0=$(date +%s%N)
		got=$(decode_md5 "$(stream_of "$v")")
		t1=$(date +%s%N)
		b=$(ve_irq)

		ms=$(( (t1 - t0) / 1000000 ))
		ve=$((b - a))
		iter=$((iter + 1))

		if [ "$ve" -eq 0 ]; then
			fallback=$((fallback + 1)); fail=$((fail + 1))
			echo "SOAK-FAIL iter=$iter $v SOFTWARE FALLBACK ve+0 t=$(( $(date +%s) - start ))s"
			head -2 "$ERR" | sed 's/^/          /'
		elif [ "$got" != "$(want_md5 "$v")" ]; then
			fail=$((fail + 1))
			echo "SOAK-FAIL iter=$iter $v MISMATCH got=$got want=$(want_md5 "$v") ve+$ve t=$(( $(date +%s) - start ))s"
			head -2 "$ERR" | sed 's/^/          /'
		else
			pass=$((pass + 1))
			[ -n "${first_ms[$v]:-}" ] || first_ms[$v]=$ms
		fi

		# A timeout is worth reporting the moment it happens, not at the end:
		# it wedges the engine for every client on this board, so everything
		# after it is a consequence rather than an independent sample.
		to=$(dmesg_count "frame processing timed out")
		if [ "$to" -ne "$to0" ]; then
			echo "SOAK-EVENT iter=$iter VE TIMEOUT (dmesg count $to0 -> $to) t=$(( $(date +%s) - start ))s"
			to0=$to
		fi

		now=$(date +%s)
		if [ "$now" -ge "$next_beat" ]; then
			drift=""
			[ -n "${first_ms[$v]:-}" ] && drift=" ${v}_ms=$ms(first=${first_ms[$v]})"
			echo "SOAK t=$((now - start))s iter=$iter pass=$pass fail=$fail" \
			     "ve_delta=$(( $(ve_irq) - ve0 )) cma_raw=$(meminfo CmaFree)kB" \
			     "memavail=$(meminfo MemAvailable)kB" \
			     "temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)" \
			     "khz=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null)$drift"
			next_beat=$((now + HEARTBEAT))
		fi
	done
done

end=$(date +%s)

# Let the last decode finish being reclaimed before the closing measurement.
# Without this the final MemAvailable is taken while ffmpeg's teardown is still
# in flight and under-reports by tens of megabytes: a 2-hour run closed at
# -50,476 kB and read like a slow leak, then measured within 0.1% of its
# baseline a few minutes later. The leak numbers are the point of the soak, so
# they should not be the least settled thing in it.
sleep 10
oops1=$(dmesg_count "Oops|BUG:|Call trace|kernel panic")
cma1=$(cma_settled)
mem1=$(meminfo MemAvailable)

echo
echo "SOAK-DECODE DONE $(date -Is) t=$((end - start))s"
echo "  iterations   $iter  ($pass pass, $fail fail, $fallback software fallbacks)"
echo "  frames on VE $(( $(ve_irq) - ve0 ))"
# Print the DELTA, not the absolute count. The first version printed the raw
# dmesg tally, so a run that inherited six timeouts from an earlier test and
# added none of its own reported "timeouts 6" -- which reads as six failures in
# this run and is the opposite of the truth.
echo "  timeouts     +$(( $(dmesg_count "frame processing timed out") - to_start ))  (was $to_start at start)"
echo "  oops/BUG     $oops0 -> $oops1"
echo "  CmaFree      ${cma0}kB -> ${cma1}kB   (delta $((cma1 - cma0))kB, both after reclaim)"
echo "  MemAvailable ${mem0}kB -> ${mem1}kB   (delta $((mem1 - mem0))kB)"
[ "$fail" -eq 0 ] && [ "$oops1" -eq "$oops0" ]
