#!/usr/bin/env bash
# Letterbox Phase 4: what does the panel show while the video plane changes
# geometry? RUNS ON THE HOST; one operator "ready" runs everything.
#
#   geometry-flash-test.sh prep     copy + build kms-geometry-flip on the board
#   geometry-flash-test.sh plan     print the sequence and its timings, run nothing
#   geometry-flash-test.sh run      LEAD_S countdown, then every window back to back
#
# Each window is kms-geometry-flip: grey cards with white frames, cycling
# native -> scope 1280x536 -> 852x480 centred -> 640x360 at 2x -> 352x288 at
# 2.5x, HOLD frames (1 s at 60 Hz) each, CYCLES times. The decoder is not
# involved; every transition is one geometry commit, which the driver
# performs with the video source off for exactly one panel frame (33.5 ms
# commit against 16.7 for a flip, measured 2026-10-05).
#
# MODE=user (run 1, kernel 0164): the cover is written from userspace
#   W1  --cover none    the driver as it was
#   W2  --cover top     border overlay covers the panel (top = 720) before
#                       the commit
#   W3  --cover left    the same with left = 1280
#   RESULT 2026-10-06: W1-W3 identical. The green is the first frame AFTER
#   the source is re-enabled, inside the new picture window with the new
#   bars around it; the overlay latches on vsync, so a cover written before
#   the commit is replaced before it can show. -> kernel 0165.
#
# MODE=kernel (default, kernel 0165): the driver covers that frame itself;
# its transition_cover parameter picks the encoding per window
#   W1  transition_cover=0   positive control: green expected, as before
#   W2  transition_cover=1   top border 720 lines
#   W3  transition_cover=2   left border 1280
#
# Both modes then play, with the cover the kernel default leaves (1):
#   W4  vp9-rc-30.ivf   a decoded stream: 640x360 -> 1280x720 -> 352x288 -> 640x360
#                       (2 s, 2 s, 1 s, 2 s) through h713-play / stock kmssink
#   W5  r01             HEVC 640x480 -> 320x240 -> 640x480, 1 s each
#
# Between windows the console shows for GAP_S seconds; the console coming
# back for good is the cue to stop recording.
#
# WHAT TO LOOK FOR, per window: at each change of card, a flash -- green,
# black, or none -- and anything else (a frame of the wrong size, garbage,
# a white frame in the wrong place). Slow motion helps: the off interval is
# one 16.7 ms panel frame.
set -euo pipefail
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=20 -o BatchMode=yes root@$BOARD"
HERE=$(cd "$(dirname "$0")" && pwd)
LEAD_S=${LEAD_S:-30}
GAP_S=${GAP_S:-5}
CYCLES=${CYCLES:-3}
HOLD=${HOLD:-60}
VT=/root/video-test
MODE=${MODE:-kernel}
PARAM=/sys/module/sun50i_h713_afbd/parameters/transition_cover

case ${1:-} in
prep)
	scp -q "$HERE/kms-geometry-flip.c" "root@$BOARD:/root/"
	$SSH 'cc -O2 -Wall -o /root/kms-geometry-flip /root/kms-geometry-flip.c $(pkg-config --cflags --libs libdrm)'
	$SSH "ls $VT/vp9-rc-30.ivf $VT/r01-resolution-change.h265 /root/h713-play >/dev/null"
	[ "$MODE" = user ] || $SSH "cat $PARAM"
	echo "prep ok"
	;;
plan)
	w=$(( CYCLES * 5 * HOLD / 60 ))
	echo "lead ${LEAD_S}s"
	echo "W1 cover none  ~${w}s, $(( CYCLES * 5 - 1 )) transitions"
	echo "gap ${GAP_S}s; W2 cover top ~${w}s; gap; W3 cover left ~${w}s; gap"
	echo "W4 vp9-rc-30 7s (3 transitions); gap; W5 r01 3s (2 transitions); console = stop"
	echo "total ~$(( LEAD_S + 3 * w + 10 + 4 * GAP_S ))s"
	;;
run)
	if [ "$MODE" = user ]; then
		w1="--cover none" w2="--cover top" w3="--cover left" p1=: p2=: p3=: p4=:
	else
		w1="" w2="" w3=""
		p1="echo 0 > $PARAM" p2="echo 1 > $PARAM" p3="echo 2 > $PARAM" p4="echo 1 > $PARAM"
	fi
	# Detached on the board, so a dropped ssh cannot strand the plane.
	$SSH "cat > /tmp/geomflash.sh" <<EOF
#!/bin/sh
exec > /tmp/geomflash.log 2>&1
dmesg -C
sleep $LEAD_S
$p1; echo "W1 \$(date +%T.%N) $MODE"; /root/kms-geometry-flip $w1 $CYCLES $HOLD | tail -1
sleep $GAP_S
$p2; echo "W2 \$(date +%T.%N)"; /root/kms-geometry-flip $w2 $CYCLES $HOLD | tail -1
sleep $GAP_S
$p3; echo "W3 \$(date +%T.%N)"; /root/kms-geometry-flip $w3 $CYCLES $HOLD | tail -1
sleep $GAP_S
$p4
echo "W4 \$(date +%T.%N)"; /root/h713-play --route=plane $VT/vp9-rc-30.ivf | tail -2
sleep $GAP_S
echo "W5 \$(date +%T.%N)"; /root/h713-play --route=plane $VT/r01-resolution-change.h265 | tail -2
echo "END \$(date +%T.%N)"
dmesg | grep -iE 'warn|fault|did not|not expressible' || echo "kernel quiet"
/root/mmio-read 5200000 2
EOF
	$SSH 'chmod +x /tmp/geomflash.sh; setsid -f /tmp/geomflash.sh < /dev/null'
	echo "started: first window in ${LEAD_S}s. Waiting for the end..."
	# Bounded: a sequence that never prints END is a failure, not a wait.
	limit=$(( LEAD_S + 3 * CYCLES * 5 * HOLD / 60 + 4 * GAP_S + 90 ))
	t=0
	until $SSH 'grep -q "^END" /tmp/geomflash.log 2>/dev/null'; do
		sleep 5; t=$((t + 5))
		[ $t -lt $limit ] || { echo "no END after ${limit}s:"; $SSH 'cat /tmp/geomflash.log'; exit 1; }
	done
	sleep 2
	$SSH 'cat /tmp/geomflash.log'
	;;
*)
	sed -n '2,30p' "$0"
	exit 2
	;;
esac
