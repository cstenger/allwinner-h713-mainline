#!/bin/sh
# decd-cedrus-carveout.sh -- a REAL Cedrus-decoded frame on the panel, via the
# known-good bypass+physical path.
#
# Established 2026-09-08, in this order:
#   - the static test frame renders correctly with master 2 in BYPASS and
#     PHYSICAL addresses (docs/reference/nv12-scanout-solved-2026-09-08.md)
#   - real Cedrus playback under TRANSLATION renders solid green
#   - the SAME static frame under TRANSLATION also renders solid green
#
# The last one is the isolation: translation is the fault, not Cedrus. Master 2
# resolves to zeroes and raises NO fault -- INT_STA, L1, L2 and the faulting-VA
# register all read 0 for 25 s. So "zero IOMMU faults" does NOT prove the IOVAs
# are mapped, which is what commit f410ebf concluded; it is equally consistent
# with silent zeroes.
#
# decd-play's own comment names the mechanism: DECD has no scatter-gather.
# dec_dma_map() keeps only sg_dma_address(sgt->sgl) and the hardware scans from
# that one base, so an IOVA is "an address valid only in someone else's address
# space".
#
# DECD_CARVEOUT=1 makes decd-play copy decoded frame 0 into the scanout carveout
# at 0x6c500000 and submit that instead -- the same physical address the working
# static recipe uses. Frame 0 only; this proves provenance, it is not playback.
#
# PM LIFETIME: the player MUST stay alive for the whole hold.  The first run of
# this script used FRAMES=30 -- one second -- then held for 25 s with the player
# dead.  On exit it drops its PM hint, and DECD PM-off can reset or clock-gate
# display hardware shared with the logo path, so the block was gated long before
# anyone looked.  DECD_FREEZE=1 resubmits one buffer, so a large FRAMES count
# keeps the process (and PM) alive without decoding anything new.
#
# Solid green means "fetching zeroes", not "wrong colour": Y=0,U=0,V=0 through
# BT.601 clamps R and B to 0 and gives G ~= 135.

set -u

STREAM=${STREAM:-/root/leota-720p.h264}
FRAMES=${FRAMES:-900}   # must outlast DWELL: the player exiting drops PM
DWELL=${DWELL:-25}
Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "carveout: $*" > /dev/kmsg 2>/dev/null; }

[ "$(rd 0x0306101c)" = 0x00000001 ] || { echo "ABORT: MIPS not alive" >&2; exit 1; }

SAVE_CTRL=$(rd 0x05600010); SAVE_GAIN=$(rd 0x05140508)
SAVE_SEL=$(rd 0x051c006c);  SAVE_BYP=$(rd 0x02010030)
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
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: sel=$(rd 0x051c006c) bypass=$(rd 0x02010030)"
}
trap restore EXIT INT TERM

# source OFF before moving the IOMMU, then BYPASS (physical addressing)
wr 0x05600010 "$(printf '0x%08X' $(( SAVE_CTRL & 0xFFFFFFFC )))"
wr 0x0560006c 1
sleep 0.1
wr 0x02010030 0x7C
say "source off, master 2 -> $(rd 0x02010030) (bypass, physical)"

say "decoding $STREAM, copying frame 0 into the carveout at $Y_PHYS"
DECD_FREEZE=1 DECD_CARVEOUT=1 /root/decd-play "$STREAM" "$FRAMES" > /tmp/carveout.log 2>&1 &
PID=$!
sleep 4

say "carveout first words: $(rd $Y_PHYS) $(rd $(printf '0x%X' $((Y_PHYS + 4))))"

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
# the proven static recipe, verbatim
busybox devmem 0x05600011 8 3
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600030 0x02D00500
wr 0x05600048 0x02D00500
wr 0x0560004c 0x01680500
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
for r in 0x05600070 0x05600074 0x05600078 0x0560007c; do wr "$r" $Y_PHYS; done
for r in 0x05600084 0x05600088 0x0560008c 0x05600090; do wr "$r" $C_PHYS; done
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000013
wr 0x05600014 1          # commit source config
sleep 0.1
busybox devmem 0x05600011 8 3   # now NV12
wr 0x05600070 $Y_PHYS
wr 0x05600084 $C_PHYS
wr 0x0560006c 1          # publish plane addresses
sleep 0.1
wr 0x051c006c 0x39000000

say "ctrl=$(rd 0x05600010) fmt=$(busybox devmem 0x05600011 8) Y0=$(rd 0x05600070) sel=$(rd 0x051c006c)"
say "=== HOLDING ${DWELL}s -- LOOK NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5; i=$((i+5))
	say "  t=${i}s Y0=$(rd 0x05600070) core=$(rd 0x0306101c)"
done
say "--- player ---"
tail -5 /tmp/carveout.log
say "=== done ==="
