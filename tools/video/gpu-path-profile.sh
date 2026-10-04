#!/bin/sh
# Profile stock mpv on the GPU path with perf. RUNS ON THE TARGET.
#
# WHY. The GPU path costs ~16% whole-board CPU against ~8% for the plane
# routes, ~5 points of it video, nearly all in mpv's own GL path (32% of one
# core against 15%), and no stock mpv knob moves it (docs/gpu-fallback-plan.md,
# WP2 follow-up). The candidates are the EGL dma-buf import of each decoded
# surface, Mesa/Panfrost CPU per draw and flush, and the GBM page flip. Only a
# profile tells them apart.
#
# WHAT. Plays CLIP with the same mpv command line as gpu-path-measure.sh (stock
# /usr/bin/mpv, vo=gpu, the "cheap" settings), lets it settle, then records the
# whole board (-a) for SECONDS: PipeWire, the kernel's DRM/Panfrost/dma-buf
# work and the VA driver count too, not only mpv. cpu-clock sampling, because
# the H713 DT has no PMU node; dwarf call graphs, because Debian's arm64
# userspace has no frame pointers. 99 Hz by default: dwarf copies ~8 KB of
# stack per sample, and the board has 932 MB of RAM for /dev/shm and perf.
#
# Needs the display: nothing else may hold DRM master (a running plane-route
# soak does), or mpv cannot open its DRM context.
#
#   sh gpu-path-profile.sh CLIP [SECONDS] [LABEL]      (SECONDS defaults to 30)
#   AUDIO=no sh gpu-path-profile.sh ...                (--ao=null)
#
# Writes /dev/shm/prof-LABEL.data (never the rootfs: it is ~95% full) and
# prints a by-DSO and a by-thread summary, which need no debug symbols.
CLIP=${1:?usage: gpu-path-profile.sh CLIP [SECONDS] [LABEL]}
SECS=${2:-30}
LABEL=${3:-$(basename "$CLIP" | sed 's/\.[^.]*$//')}
PERF=${PERF:-/usr/local/bin/perf}
MPV=${MPV:-/usr/bin/mpv}
OUT=/dev/shm/prof-$LABEL.data
LOG=/tmp/prof-mpv-$LABEL.log
MPV_OPTS=${MPV_OPTS:---scale=bilinear --dscale=bilinear --cscale=bilinear --dither-depth=no --deband=no --correct-downscaling=no --linear-downscaling=no --sigmoid-upscaling=no --hdr-compute-peak=no}
AO=
[ "${AUDIO:-yes}" = no ] && AO=--ao=null

[ -r "$CLIP" ] || { echo "PROF ERROR: no clip $CLIP"; exit 2; }
[ -x "$PERF" ] || { echo "PROF ERROR: no perf at $PERF (tools/build/build-perf.sh --install)"; exit 2; }

# shellcheck disable=SC2086
LIBVA_DRIVER_NAME=v4l2_request "$MPV" --no-config --vo=gpu --gpu-context=drm \
	--hwdec=vaapi --loop-file=inf --input-terminal=no $AO $MPV_OPTS \
	"$CLIP" > "$LOG" 2>&1 < /dev/null &
MPID=$!
sleep 5
kill -0 $MPID 2>/dev/null || { echo "PROF ERROR: mpv exited; see $LOG"; tail -5 "$LOG"; exit 1; }
grep -q 'Using hardware decoding' "$LOG" ||
	echo "PROF WARNING: mpv does not report hardware decoding; this would profile software decode"

echo "PROF clip=${CLIP##*/} label=$LABEL secs=$SECS audio=${AUDIO:-yes} mpv_pid=$MPID"
# Timed with SIGTERM, not a `-- sleep N` workload (launched over ssh, perf
# never saw that child exit and polled for 10+ minutes) and not SIGINT (a
# background job of a non-interactive shell starts with SIGINT ignored).
"$PERF" record -q -B -a -e cpu-clock -F ${FREQ:-99} --call-graph dwarf,8192 \
	-o "$OUT" > /tmp/prof-perf-$LABEL.log 2>&1 &
PPID_=$!
# Frequency changes. No CONFIG_CPU_FREQ_STAT on this kernel, but every change
# is one work item for the sugov:0 kthread, so its voluntary context switches
# count them.
sw() { awk '/^voluntary_ctxt_switches/ { print $2 }' /proc/$(pgrep -x sugov:0 | head -1)/status 2>/dev/null || echo 0; }
TR0=$(sw)
sleep "$SECS"
TR1=$(sw)
# -B skips the build-id pass over the data at the end: on this CPU it ran for
# minutes. Reports on this board read build ids from the files themselves.
# perf has also needed a second SIGTERM before; send one if it lingers.
kill -TERM $PPID_
i=0; while kill -0 $PPID_ 2>/dev/null && [ $i -lt 30 ]; do sleep 1; i=$((i + 1)); done
kill -TERM $PPID_ 2>/dev/null; wait $PPID_
kill $MPID 2>/dev/null; wait $MPID 2>/dev/null

echo "PROF data=$OUT ($(du -h "$OUT" | cut -f1)) sugov_wakeups=$((TR1 - TR0)) in ${SECS}s"
echo "=== by DSO, all CPUs (idle is the swapper/kernel idle loop) ==="
"$PERF" report --no-inline -i "$OUT" --no-children --sort dso --stdio 2>/dev/null |
	grep -E '^ +[0-9]' | head -20
echo "=== by thread ==="
"$PERF" report --no-inline -i "$OUT" --no-children --sort comm --stdio 2>/dev/null |
	grep -E '^ +[0-9]' | head -15
