#!/bin/sh
# Loop stock mpv vo=gpu (cheap) on a clip; when decode interrupts stop for 3 s
# while mpv lives, dump evidence to /var/tmp/stall/ and stop. RUNS ON TARGET.
#
# Every freeze seen so far (2026-10-02, 3 of ~40 runs) happened under
# gpu-path-measure.sh, which also turns on Panfrost profiling and reads fdinfo
# and the DRM debugfs state every second; 25 min of plain playback did not
# freeze. PROFILE=1 and POKE=1 add those two back, one at a time, so the
# trigger can be separated from the playback path.
CLIP=$1; MAX=${MAX:-1500}
GPU=/sys/bus/platform/devices/1800000.gpu
O=/var/tmp/stall; rm -rf $O; mkdir -p $O
irq() { awk -v p="$1" '$0 ~ p { s = 0; for (i = 2; i <= 5; i++) s += $i; print s }' /proc/interrupts; }
LIBVA_DRIVER_NAME=v4l2_request /usr/bin/mpv --no-config --vo=gpu --gpu-context=drm --hwdec=vaapi \
	--loop-file=inf --input-terminal=no -v --scale=bilinear --dscale=bilinear --cscale=bilinear \
	--dither-depth=no --deband=no --correct-downscaling=no --linear-downscaling=no \
	--sigmoid-upscaling=no --hdr-compute-peak=no "$CLIP" > $O/mpv.log 2>&1 < /dev/null &
P=$!; T0=$(date +%s); prev=-1; still=0
[ -n "${PROFILE:-}" ] && echo 1 > $GPU/profiling
echo "profile=${PROFILE:-0} poke=${POKE:-0}" > $O/config
while kill -0 $P 2>/dev/null && [ $(($(date +%s) - T0)) -lt $MAX ]; do
	sleep 1
	if [ -n "${POKE:-}" ]; then
		cat /proc/$P/fdinfo/* > /dev/null 2>&1
		cat /sys/kernel/debug/dri/5600000.display/state > /dev/null 2>&1
	fi
	d=$(irq 1c0e000); g=$(irq panfrost-job)
	if [ "$d" = "$prev" ]; then still=$((still + 1)); else still=0; fi
	prev=$d
	echo "$(($(date +%s) - T0)) dec=$d gpu=$g still=$still" >> $O/trace
	if [ $still -ge 3 ]; then
		echo "STALL at t=$(($(date +%s) - T0))" > $O/verdict
		for t in /proc/$P/task/*; do
			echo "== $(cat $t/comm) state=$(cut -d' ' -f3 $t/stat) wchan=$(cat $t/wchan)"; cat $t/stack
		done > $O/threads
		cat /sys/kernel/debug/dma_buf/bufinfo > $O/bufinfo 2>&1
		cat /sys/kernel/debug/dri/5600000.display/state > $O/drmstate 2>&1
		for i in 1 2 3 4 5; do sleep 1; echo "post dec=$(irq 1c0e000) gpu=$(irq panfrost-job)" >> $O/trace; done
		dmesg | tail -30 > $O/dmesg
		kill $P; echo 0 > $GPU/profiling; exit 0
	fi
done
echo "NO STALL in $(($(date +%s) - T0)) s" > $O/verdict; kill $P 2>/dev/null
echo 0 > $GPU/profiling
