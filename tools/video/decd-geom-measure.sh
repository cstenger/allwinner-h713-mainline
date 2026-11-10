#!/bin/sh
# decd-geom-measure.sh -- read the seven source-geometry words DURING a live
# submit, with no operator and no photograph.
#
# Why this exists: every geometry reading taken so far was taken *after* the
# sequence script's EXIT trap had already restored the inherited 852x480 logo
# state, so it could only ever show 852x480.  The question is what the block
# holds while a frame is actually being fetched.
#
# The 2026-08-30 finding (geom-restore-test.sh) is that a submit rewrites
# 0x05600030 and 0x0560004c to 852x480 while 0x05600020 and the strides stay at
# 1280x720 -- an incoherent block, which is exactly a stride shear.  That was
# attributed to the client passing source-pixel dimensions in a canonical
# 1920x1080 VideoInfo space, and decd-client.coord1080 is the corrected build.
#
# So this measures, in one run:
#   1. inherited state          (before anything)
#   2. after the client submits (does the submit rewrite 0x30/0x4c?)
#   3. after the route is applied (does apply_visible_route fix them?)
#
# It is READ-ONLY apart from the route it deliberately applies, and it restores.
# No visual judgement is required, so it costs nothing to run.

set -u

CLIENT=${CLIENT:-/root/decd-client.coord1080}
FRAME=${FRAME:-/root/decd-test-frame.nv12}

GEOM="0x05600010 0x05600020 0x05600024 0x05600030 0x05600034 0x05600040 0x05600044 0x05600048 0x0560004c"
ROUTE="0x051c006c 0x05140508"
RING="0x05600070 0x05600084 0x05600098"

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }

# decode a packed hi:lo 16-bit pair as "HI x LO" so mismatches are obvious
dec() {
	v=$(rd "$1")
	n=$((v))
	hi=$((n >> 16)); lo=$((n & 0xFFFF))
	printf '  %-12s %s   (%d x %d)\n' "$1" "$v" "$lo" "$hi"
}

dump() {
	echo "--- $1 ---"
	for r in $GEOM; do dec "$r"; done
	for r in $ROUTE $RING; do printf '  %-12s %s\n' "$r" "$(rd $r)"; done
}

echo "=== decd geometry measurement $(date) ==="
echo "client: $CLIENT   frame: $FRAME"
echo "core 0x0306101c = $(rd 0x0306101c)   bypass 0x02010030 = $(rd 0x02010030)"

# snapshot for restore
for r in $GEOM $ROUTE; do
	eval "SAVE_$(echo $r | tr -d 'x')=$(rd $r)"
done

restore() {
	echo "--- restoring ---"
	for r in $ROUTE $GEOM; do
		eval "v=\$SAVE_$(echo $r | tr -d 'x')"
		wr "$r" "$v" 2>/dev/null || true
	done
	wr 0x05600014 1 2>/dev/null || true
	echo "restored: selector=$(rd 0x051c006c) 0x30=$(rd 0x05600030) stride=$(rd 0x05600040)"
}
trap restore EXIT INT TERM

dump "1. inherited (before any submit)"

echo
echo "starting $CLIENT (20s dwell) ..."
"$CLIENT" show "$FRAME" 20000 &
PID=$!
sleep 4

dump "2. after submit -- did the submit rewrite 0x30 / 0x4c?"

echo
echo "applying the visible route (the five words the script sets)"
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000013
wr 0x05600014 1
sleep 0.1

dump "3. after apply_visible_route -- is the block coherent at 1280x720?"

echo
echo "NOTE: 0x05600030 and 0x0560004c are NOT written by apply_visible_route."
echo "      Stock playback capture has 0x0560004c = 0x02D00500 (1280x720)."

kill $PID 2>/dev/null || true
wait $PID 2>/dev/null || true
