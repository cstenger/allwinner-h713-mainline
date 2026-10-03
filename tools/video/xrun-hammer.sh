#!/bin/sh
# Repeated forced audio underruns; stop at the first that leaves playback frozen.
# RUNS ON THE TARGET.
#
#   sh xrun-hammer.sh CLIP [AO] [N]      (AO=alsa by default; null is the control)
#
# The "GPU path freeze" of 2026-10-02 was this. An audio underrun mid-play,
# then mpv's ALSA recovery left the PCM PREPARED with a full buffer
# (avail 0) and never started it. mpv's threads then wait on each other in
# futexes, and video, paced by the audio clock, stops. One forced underrun
# recovers; the 32nd of a run froze. With --ao=null, 40 of 40 recover. Each
# underrun is a SIGSTOP of a few hundred ms to 2 s, varied so the resume
# lands at different points in a period.
# MPV/VO pick the player: the default is Debian's mpv on the GPU path;
# MPV=/usr/local/bin/mpv VO=drm is the patched direct path (patches/mpv).
CLIP=$1 AO=${2:-alsa} N=${3:-40}
MPV=${MPV:-/usr/bin/mpv} VO=${VO:-gpu}
case "$VO" in gpu*) CTX=--gpu-context=drm ;; *) CTX= ;; esac
irq() { awk '/1c0e000/ { print $2 }' /proc/interrupts; }
# shellcheck disable=SC2086
LIBVA_DRIVER_NAME=v4l2_request "$MPV" --no-config --vo=$VO $CTX --hwdec=vaapi \
	--ao=$AO --loop-file=inf --input-terminal=no -v --scale=bilinear --dscale=bilinear --cscale=bilinear \
	--dither-depth=no --deband=no "$CLIP" > /tmp/xh.log 2>&1 < /dev/null &
P=$!
sleep 6
i=0
while [ $i -lt $N ]; do
	i=$((i + 1))
	# vary the stall length so the resume lands at different points of a period
	d=$(awk -v s=$i 'BEGIN { srand(s); printf "%.2f", 0.2 + rand() * 1.8 }')
	kill -STOP $P; sleep $d; kill -CONT $P
	a=$(irq); sleep 3; b=$(irq)
	if [ $((b - a)) -lt 10 ]; then
		sleep 3; c=$(irq)
		echo "FROZE after underrun #$i (stop ${d}s): decode +$((b - a)) then +$((c - b)); alsa $(grep -h -m1 state /proc/asound/card*/pcm0p/sub0/status 2>/dev/null)"
		cat /proc/asound/card*/pcm0p/sub0/status 2>/dev/null | head -8
		for t in /proc/$P/task/*; do echo "  $(cat $t/comm) $(cat $t/wchan)"; done | sort | uniq -c
		tr '\r' '\n' < /tmp/xh.log | grep -av statusline | grep -av '^\s*$' | tail -6
		kill $P; exit 0
	fi
done
echo "ao=$AO mpv=$MPV vo=$VO: $N forced underruns, playback recovered every time"
# How often the stranded state actually arose and was rescued (patches/mpv 0005):
# zero here would mean the run never exercised the fix at all.
echo "rescued-by-0005: $(tr '\r' '\n' < /tmp/xh.log | grep -c 'full but never started')"
kill $P; wait $P 2>/dev/null
