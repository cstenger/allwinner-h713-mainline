#!/bin/sh
# decd-static-via-iova.sh -- isolate ONE variable: translation vs bypass.
#
# Known good (2026-09-08): the static test frame renders correctly with
#   IOMMU master 2 in BYPASS (0x7C) and PHYSICAL addresses written by hand.
#
# Failing: real Cedrus playback with
#   IOMMU master 2 TRANSLATING (0x78) and IOVAs written by the driver.
#
# Everything else has been measured identical between the two: geometry, format
# byte 3, strides, chroma gain, selector, source enable, all four ring slots
# holding real non-zero Y/C pairs, config stable across the whole run, and ZERO
# IOMMU faults (INT_STA, L1, L2 and the faulting-VA register all read 0).
# dec@5600000 declares iommus = <&mmu_aw 2 0> -- a single master port, so the
# VE's "needs both ports" quirk does not apply.
#
# So this runs the KNOWN-GOOD STATIC FRAME through the IOVA path: same file,
# same client, same geometry -- but translation on, and the driver's own ring
# writes (ring_writes_max raised) instead of hand-written physical addresses.
#
#   picture appears -> translation is FINE; the fault is Cedrus-specific
#                      (buffer contents, cache visibility, or submit timing)
#   solid green     -> translation is the fault; master 2 resolves to zeroes
#                      without faulting, and the static/bypass result is the
#                      only path that works
#
# Solid green means "fetching zeroes", not "wrong colour": Y=0,U=0,V=0 through
# BT.601 clamps R and B to 0 and gives G ~= 135.

set -u

FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client.coord1080}
DWELL=${DWELL:-25}
RING_MAX=${RING_MAX:-2000}

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "iova-test: $*" > /dev/kmsg 2>/dev/null; }

[ "$(rd 0x0306101c)" = 0x00000001 ] || { echo "ABORT: MIPS not alive" >&2; exit 1; }

SAVE_CTRL=$(rd 0x05600010); SAVE_GAIN=$(rd 0x05140508)
SAVE_SEL=$(rd 0x051c006c);  SAVE_BYP=$(rd 0x02010030)
SAVE_MAX=$(cat /sys/module/sunxi_decd/parameters/ring_writes_max)
[ "$SAVE_SEL" = 0x00000000 ] && SAVE_SEL=0x29000000
GEOM="0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"
for r in $GEOM; do eval "G_$(echo $r|tr -d 'x')=$(rd $r)"; done

restore() {
	say "--- restoring ---"
	wr 0x051c006c "$SAVE_SEL" 2>/dev/null || true
	wr 0x05600010 "$(printf '0x%08X' $(( SAVE_CTRL & 0xFFFFFFFC )))" 2>/dev/null || true
	wr 0x0560006c 1 2>/dev/null || true
	wr 0x02010030 "$SAVE_BYP" 2>/dev/null || true
	wr 0x05600010 "$SAVE_CTRL" 2>/dev/null || true
	for r in $GEOM; do eval "v=\$G_$(echo $r|tr -d 'x')"; wr "$r" "$v" 2>/dev/null || true; done
	wr 0x05140508 "$SAVE_GAIN" 2>/dev/null || true
	wr 0x0560006c 1 2>/dev/null || true
	echo "$SAVE_MAX" > /sys/module/sunxi_decd/parameters/ring_writes_max 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: sel=$(rd 0x051c006c) bypass=$(rd 0x02010030)"
}
trap restore EXIT INT TERM

# source OFF before moving the IOMMU (ordering rule)
wr 0x05600010 "$(printf '0x%08X' $(( SAVE_CTRL & 0xFFFFFFFC )))"
wr 0x0560006c 1
sleep 0.1
wr 0x02010030 0x78
echo "$RING_MAX" > /sys/module/sunxi_decd/parameters/ring_writes_max
say "source off, master 2 -> $(rd 0x02010030) (translating), ring_max=$RING_MAX"

say "staging $FRAME (driver will dma-map it -> IOVA)"
"$CLIENT" show "$FRAME" $(( (DWELL + 25) * 1000 )) >/dev/null 2>&1 &
PID=$!
sleep 3

say "ring after submit: Y0=$(rd 0x05600070) C0=$(rd 0x05600084)"

busybox devmem 0x05600011 8 3
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600030 0x02D00500
wr 0x05600048 0x02D00500
wr 0x0560004c 0x01680500
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000313
wr 0x0560006c 1
sleep 0.1
wr 0x051c006c 0x39000000

say "ctrl=$(rd 0x05600010) fmt=$(busybox devmem 0x05600011 8) sel=$(rd 0x051c006c)"
say "IOMMU faults: INT_STA=$(rd 0x02010108) L1=$(rd 0x02010180) L2=$(rd 0x02010184)"
say "=== HOLDING ${DWELL}s -- LOOK NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5; i=$((i+5))
	say "  t=${i}s Y0=$(rd 0x05600070) faults=$(rd 0x02010108) core=$(rd 0x0306101c)"
done
say "=== done ==="
