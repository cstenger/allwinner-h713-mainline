#!/bin/sh
# decd-cedrus-play.sh -- real Cedrus-decoded video to the panel, MIPS alive.
#
# Follows the static NV12 result of 2026-09-08
# (docs/reference/nv12-scanout-solved-2026-09-08.md) with two changes forced by
# measurement, not assumption:
#
#  1. IOMMU master 2 must TRANSLATE (0x78), not bypass.  Cedrus buffers are
#     dma-mapped, so the ring receives IOVAs -- measured 0xFA200000/0xFA2E1000,
#     differing by 0xE1000 = 1280*720, a real Y/C pair.  Under bypass those are
#     read as physical addresses and are not DRAM.
#     The static test used physical carveout addresses, which is why it wanted
#     bypass; this is the opposite case.
#
#  2. ring_writes_max must allow one sync per frame.  With the budget module at
#     1, only the first frame ever reaches the fetcher.  20 writes with the MIPS
#     alive did NOT lock the SoC, so the historical hard-lock does not bite at
#     this depth; the cap here is bounded rather than unlimited so a runaway
#     cannot sit at 60 Hz indefinitely.
#
# ORDERING RULES, both from hard-won hazard notes:
#   - flip 0x7c->0x78 only while the DECD video source is DISABLED, because the
#     source rests at base 0 with 1920x1088 geometry and scans low memory the
#     instant it is enabled: garbage under bypass, an AFBD-wedging L1-invalid
#     fault under translation.
#   - never enable that source with no frame behind it.  So the player starts
#     FIRST and the route is applied after the first submits have armed the ring
#     -- the same shape decd-visible-sequence.sh uses for its --play branch.
#
# The driver already publishes correctly: dec_reg_set_dirty() writes
# workaround+12 = 0x0560006c.  It does NOT program the format byte -- that is
# only traced (dec_debug_trace_frame) -- so we set 0x05600011 = 3 ourselves and
# it persists across frames.

set -u

STREAM=${STREAM:-/root/leota-720p.h264}
FRAMES=${FRAMES:-150}
RING_MAX=${RING_MAX:-2000}
PLAYER=${PLAYER:-/root/decd-play}

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "cedrus: $*" > /dev/kmsg 2>/dev/null; }

CORE=$(rd 0x0306101c)
[ "$CORE" = 0x00000001 ] || { echo "ABORT: MIPS core is $CORE, expected 1" >&2; exit 1; }
lsmod | grep -q decd || { echo "ABORT: no DECD module" >&2; exit 1; }
[ -r "$STREAM" ] || { echo "ABORT: no stream $STREAM" >&2; exit 1; }

SAVE_CTRL=$(rd 0x05600010)
SAVE_GAIN=$(rd 0x05140508)
SAVE_SEL=$(rd 0x051c006c)
SAVE_BYP=$(rd 0x02010030)
SAVE_S40=$(rd 0x05600040)
SAVE_S44=$(rd 0x05600044)
GEOM="0x05600020 0x05600024 0x05600030 0x05600048 0x0560004c"
for r in $GEOM; do eval "G_$(echo $r|tr -d 'x')=$(rd $r)"; done
SAVE_MAX=$(cat /sys/module/sunxi_decd/parameters/ring_writes_max)
[ "$SAVE_SEL" = 0x00000000 ] && SAVE_SEL=0x29000000

restore() {
	say "--- restoring ---"
	wr 0x051c006c "$SAVE_SEL" 2>/dev/null || true
	# Disable the source before moving the IOMMU back (ordering rule).
	wr 0x05600010 "$(printf '0x%08X' $(( SAVE_CTRL & 0xFFFFFFFC )))" 2>/dev/null || true
	wr 0x0560006c 1 2>/dev/null || true
	wr 0x02010030 "$SAVE_BYP" 2>/dev/null || true
	wr 0x05600010 "$SAVE_CTRL" 2>/dev/null || true
	for r in $GEOM; do eval "v=\$G_$(echo $r|tr -d 'x')"; wr "$r" "$v" 2>/dev/null || true; done
	wr 0x05600040 "$SAVE_S40" 2>/dev/null || true
	wr 0x05600044 "$SAVE_S44" 2>/dev/null || true
	wr 0x05140508 "$SAVE_GAIN" 2>/dev/null || true
	wr 0x0560006c 1 2>/dev/null || true
	echo "$SAVE_MAX" > /sys/module/sunxi_decd/parameters/ring_writes_max 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: selector=$(rd 0x051c006c) bypass=$(rd 0x02010030) ringmax=$SAVE_MAX"
}
trap restore EXIT INT TERM

say "=== Cedrus playback, MIPS alive ==="
say "stream=$STREAM frames=$FRAMES ring_max=$RING_MAX"
say "before: bypass=$SAVE_BYP ctrl=$SAVE_CTRL sel=$SAVE_SEL"

# 1. source OFF, then flip the IOMMU to translation (never the other order)
wr 0x05600010 "$(printf '0x%08X' $(( SAVE_CTRL & 0xFFFFFFFC )))"
wr 0x0560006c 1
sleep 0.1
wr 0x02010030 0x78
say "source disabled, IOMMU master 2 -> $(rd 0x02010030) (translating)"

echo "$RING_MAX" > /sys/module/sunxi_decd/parameters/ring_writes_max

# 2. player FIRST, so the ring is armed before the source is enabled
say "starting player ..."
"$PLAYER" "$STREAM" "$FRAMES" > /tmp/cedrus-play.log 2>&1 &
PID=$!
sleep 1

say "ring after first submits: Y0=$(rd 0x05600070) C0=$(rd 0x05600084)"

# TWO LATCHES, DIFFERENT JOBS -- the bug that cost four green frames:
#   0x05600014  commits the SOURCE CONFIG (geometry + enable)
#   0x0560006c  publishes the PLANE ADDRESSES (two-plane YUV path)
# Both are required.  On discovering 0x0560006c was the missing publish, the
# first versions of these Cedrus scripts were built around it and dropped
# 0x05600014 entirely -- so the geometry and enable were written, read back
# correctly, and never committed.  The fetcher had no valid picture config,
# fetched nothing, and zeroes render as solid green.
# Order below mirrors the working test_80 run exactly: commit the config in
# format 0, then switch the format byte to 3, set the plane addresses, publish.
# 3. now the route: format NV12, FULL geometry, strides, gain, enable, publish.
#
# All SEVEN geometry words, not just the strides.  The first version of this
# script carried the strides over from the static recipe and left the other five
# behind; measured live during playback they were all zero, and a 0x0 picture
# fetches nothing.  All-zero data renders as SOLID GREEN -- Y=0,U=0,V=0 through
# BT.601 clamps R and B to 0 and computes G ~= 135 -- which is exactly what the
# panel showed.  Solid green here means "fetching nothing", not "wrong colour".
busybox devmem 0x05600011 8 3
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600030 0x02D00500
wr 0x05600048 0x02D00500
wr 0x0560004c 0x01680500
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000013
wr 0x05600014 1          # commit source config
sleep 0.1
busybox devmem 0x05600011 8 3   # now NV12
# Plane addresses are NOT written here: the driver owns the ring during
# playback and writes a fresh Y/C pair per frame.  Overwriting them with fixed
# values would pin one frame.  Publish so the format switch takes effect.
wr 0x0560006c 1          # publish plane addresses
sleep 0.1
wr 0x051c006c 0x39000000

say "ctrl=$(rd 0x05600010) fmt=$(busybox devmem 0x05600011 8) sel=$(rd 0x051c006c)"
say "=== PLAYING -- LOOK NOW ==="

i=0
while kill -0 "$PID" 2>/dev/null; do
	sleep 1
	i=$((i + 1))
	say "  t=${i}s Y0=$(rd 0x05600070) done=$(cat /sys/module/sunxi_decd/parameters/ring_writes_done) core=$(rd 0x0306101c)"
	[ $i -gt 40 ] && break
done
wait "$PID" 2>/dev/null
PID=""
say "--- player output ---"
tail -6 /tmp/cedrus-play.log
say "=== done ==="
