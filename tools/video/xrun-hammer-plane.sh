#!/bin/sh
# Repeated forced audio underruns on WP4's plane player; stop at the first
# that leaves playback frozen. RUNS ON THE TARGET.
#
#   sh xrun-hammer-plane.sh CLIP [N]
#   GST_PLANE_PLAY_AUDIOSINK="alsasink device=pipewire" sh xrun-hammer-plane.sh CLIP 40
#
# The gst-plane-play counterpart of xrun-hammer.sh (mpv). Each underrun is a
# SIGSTOP of the player for 0.2-2 s, varied so the resume lands at different
# points in a period: the audio sink starves, its PipeWire stream (or the
# pipewire ALSA plugin) reports the underrun, and the sink's recovery runs.
# Playback counts as alive when decoder interrupts keep rising after the
# resume. The clip should be H.264/HEVC 1080p (plane-ve) and long enough for
# N rounds (~5 s each).
CLIP=${1:?usage: xrun-hammer-plane.sh CLIP [N]}
N=${2:-40}
PLAYER=${PLAYER:-/usr/local/bin/gst-plane-play}
export LIBVA_DRIVER_NAME=v4l2_request GST_VA_ALL_DRIVERS=1
export V4L2_REQUEST_SCALE=1280x720 V4L2_REQUEST_CROP=1920x1080

irq() { awk '/cedrus|1c0e000/ { s += $2 + $3 + $4 + $5 } END { print s + 0 }' /proc/interrupts; }

[ -r "$CLIP" ] || { echo "no clip $CLIP"; exit 2; }
"$PLAYER" "$CLIP" h264 vah264dec 1280x720 > /tmp/xrun-plane.log 2>&1 &
P=$!
sleep 6

# Prove the baseline first: a player that never started looks like a freeze.
a0=$(irq); sleep 2; b0=$(irq)
if ! kill -0 $P 2>/dev/null || [ "$b0" -le "$a0" ]; then
	echo "baseline: not decoding before any underrun (irq $a0 -> $b0)"
	cat /tmp/xrun-plane.log | tail -5
	kill -INT $P 2>/dev/null
	exit 2
fi
echo "baseline: decoding (irq +$((b0 - a0)) in 2 s), sink: ${GST_PLANE_PLAY_AUDIOSINK:-pipewiresink}"

i=1
while [ $i -le "$N" ]; do
	d=$(awk -v i=$i 'BEGIN { srand(i); printf "%.2f", 0.2 + rand() * 1.8 }')
	kill -STOP $P; sleep "$d"; kill -CONT $P
	a=$(irq); sleep 3; b=$(irq)
	if [ "$b" -le "$a" ]; then
		sleep 3; c=$(irq)
		if [ "$c" -le "$a" ]; then
			echo "FROZE after underrun #$i (stop ${d}s): irq $a -> $c"
			grep -h "^state\|avail\|delay" /proc/asound/card*/pcm*p/sub0/status
			tail -5 /tmp/xrun-plane.log
			kill -INT $P 2>/dev/null; sleep 1; kill -9 $P 2>/dev/null
			exit 1
		fi
	fi
	i=$((i + 1))
done
kill -INT $P
wait $P 2>/dev/null
echo "survived $N/$N forced underruns: $(grep 'gst-plane-play:' /tmp/xrun-plane.log)"
