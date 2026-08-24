#!/bin/bash
# Does ONE long-lived process leak across many decode sessions? RUNS ON THE TARGET.
#
# WHAT THE SOAK CANNOT SEE. soak-decode.sh starts a fresh ffmpeg for every
# iteration, so the kernel reclaims everything that process held whether the
# shim released it or not. Thousands of clean iterations therefore say nothing
# about whether the driver leaks VA surfaces, V4L2 buffers, mmaps or file
# descriptors per decode session. A media server or a long-running player is
# exactly the case that would find out.
#
# So this runs ONE process over a long stream -- the same vector concatenated
# sixty times, which is what a player looping a file does -- and watches that process's own footprint rather than
# the system's. It covers the per-frame and per-surface leak classes: surfaces
# recycled through the DPB, buffers requeued, requests opened and closed once
# per picture, thousands of times inside a single context.
#
# THE FIRST VERSION USED A RESOLUTION-CHANGING STREAM to force context churn as
# well, and reported PASS on a run whose VE interrupt count was ZERO: the shim
# cannot handle a mid-stream resolution change (see decode-reinit-test.sh), so
# ffmpeg fell back to software and the harness measured a CPU decoder's memory
# behaviour. Hence the ve check below -- the same rule every other gate here
# applies, which this one was missing.
#
# WHAT IS MEASURED, and why each one:
#
#   RSS       userspace growth: VA surfaces or mapped buffers never unmapped
#   FDs       the shim opens a request FD per surface; leaking those exhausts
#             the process limit long before memory runs out
#   maps      a leak that lands in mmap rather than the heap moves this and
#             not RSS
#   CmaFree   kernel-side buffers the driver allocated and did not return
#
# A slope is the signal, not a value: any decoder's footprint rises while it
# warms up. What matters is whether it is still rising at the end.
#
#   usage: ./decode-leak-test.sh [stream]     (default leak-stream.h265)
#
# Concatenated rather than -stream_loop: ffmpeg cannot seek a raw elementary
# stream, so looping it fails with "Operation not permitted" before a single
# frame is decoded.

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
STREAM=${1:-$DIR/leak-stream.h265}
SAMPLE=${SAMPLE:-5}

[ -r "$STREAM" ] || { echo "FATAL: no stream at $STREAM"; exit 1; }

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}
cma_free() { awk '/CmaFree/ { print $2 }' /proc/meminfo; }

echo "=== one process, $(basename "$STREAM"), $(stat -c%s "$STREAM") bytes ==="

ve0=$(ve_irq)
LIBVA_DRIVER_NAME=v4l2_request ffmpeg -hide_banner -v error -y \
	-hwaccel vaapi -hwaccel_output_format vaapi \
	-i "$STREAM" -vf 'hwdownload,format=nv12' -f null - &
pid=$!

printf '%6s %10s %6s %6s %10s\n' TIME RSS_kB FDS MAPS CMA_kB
first_rss=""; last_rss=""; first_fds=""; last_fds=""; n=0; samples=0

while kill -0 "$pid" 2>/dev/null; do
	rss=$(awk '/VmRSS/ { print $2 }' "/proc/$pid/status" 2>/dev/null)
	fds=$(ls "/proc/$pid/fd" 2>/dev/null | wc -l)
	maps=$(wc -l < "/proc/$pid/maps" 2>/dev/null || echo 0)
	[ -n "$rss" ] || break
	printf '%6s %10s %6s %6s %10s\n' "${n}s" "$rss" "$fds" "$maps" "$(cma_free)"
	# Skip the first sample: a decoder that has not yet allocated its DPB is
	# not a baseline, it is a process that has barely started.
	if [ "$n" -ge "$SAMPLE" ]; then
		[ -n "$first_rss" ] || { first_rss=$rss; first_fds=$fds; }
		last_rss=$rss; last_fds=$fds
		samples=$((samples + 1))
	fi
	n=$((n + SAMPLE))
	sleep "$SAMPLE"
done
wait "$pid" 2>/dev/null
rc=$?

frames=$(( $(ve_irq) - ve0 ))
echo
echo "  exit $rc, frames on the engine: $frames"

# THREE samples minimum, not two. With two, "first" and "last" can be the same
# reading and the delta is zero by construction -- which is how an earlier run
# of this reported PASS on a single sample. A slope needs points.
if [ "$samples" -lt 3 ]; then
	echo "  INCONCLUSIVE — only $samples usable sample(s); a slope needs at least 3."
	echo "  Use a longer stream: a leak becomes visible through repetition."
	exit 1
fi

d_rss=$((last_rss - first_rss))
d_fds=$((last_fds - first_fds))
echo "  RSS  ${first_rss} -> ${last_rss} kB  (delta ${d_rss} kB over $samples samples)"
echo "  FDs  ${first_fds} -> ${last_fds}      (delta ${d_fds})"

fail=0
# The rule every other gate here applies, and the one this harness was missing:
# a flat interrupt counter means the CPU did the work and nothing below this
# line describes the hardware path at all.
if [ "$frames" -eq 0 ]; then
	echo "  FAIL — ve+0: the decode never reached the engine, so this run"
	echo "         measured a software decoder and says nothing about the shim"
	fail=1
fi
# 8 MB over the run is roughly 200 kB per session; a real
# per-session leak of surfaces or buffers is far larger than that, and normal
# allocator behaviour is far smaller.
[ "$d_rss" -gt 8192 ] && { echo "  FAIL — RSS still climbing; that is a per-session leak"; fail=1; }
[ "$d_fds" -gt 8 ] && { echo "  FAIL — file descriptors accumulating"; fail=1; }
[ "$rc" -ne 0 ] && { echo "  FAIL — the decode itself did not succeed"; fail=1; }

echo
[ "$fail" -eq 0 ] && echo "L1: PASS — flat across the run" || echo "L1: FAIL"
exit "$fail"
