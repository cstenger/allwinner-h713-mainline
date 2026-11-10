#!/bin/sh
# decd-block-capture.sh -- dump the whole AFBD block WHILE our video config is
# applied, so it can be diffed against the stock-Android-playback capture.
#
# No operator required.  The panel shows whatever it shows; we only want the
# registers.  This is the measurement that should have come before the last
# three visual tests.
#
# Reference: docs/reference/stock-android-playback-2026-08-28.txt, captured
# while stock was correctly displaying decoded video.  Its geometry words match
# ours exactly (0x03000013 / 0x02CF04FF / 0x02D00500 / strides 0x500), so any
# remaining difference in this block is a real candidate for the corruption.

set -u

Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000
FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client.coord1080}

Y_SLOTS="0x05600070 0x05600074 0x05600078 0x0560007c"
C_SLOTS="0x05600084 0x05600088 0x0560008c 0x05600090"
GEOM="0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"
ROUTE="0x051c006c 0x05140508"

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }

key() { echo "SAVE_$(echo "$1" | tr -d 'x')"; }
for r in $GEOM $ROUTE; do eval "$(key $r)=$(rd $r)"; done

restore() {
	for r in 0x051c006c $GEOM 0x05140508; do
		eval "v=\$$(key $r)"
		wr "$r" "$v" 2>/dev/null || true
	done
	wr 0x05600014 1 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	echo "restored: selector=$(rd 0x051c006c) pitch=$(rd 0x05600040)" >&2
}
trap restore EXIT INT TERM

"$CLIENT" show "$FRAME" 40000 >/dev/null 2>&1 &
PID=$!
sleep 4

wr 0x02010030 0x7C
for r in $Y_SLOTS; do wr "$r" $Y_PHYS; done
for r in $C_SLOTS; do wr "$r" $C_PHYS; done
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600030 0x02D00500
wr 0x05600048 0x02D00500
wr 0x0560004c 0x01680500
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000013
wr 0x05600014 1
sleep 0.2
wr 0x051c006c 0x39000000
sleep 1

echo "=== AFBD 0x05600000..0x056001ff (LIVE, video config applied) ==="
a=0
while [ $a -lt 512 ]; do
	printf '%08x %s\n' $((0x05600000 + a)) "$(rd $((0x05600000 + a)))"
	a=$((a + 4))
done
