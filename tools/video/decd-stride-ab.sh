#!/bin/sh
# decd-stride-ab.sh -- settle the shear with two coherent configurations in one
# operator window.
#
# Measured 2026-09-06 (decd-geom-measure.sh): during every visible run the
# source block is INCOHERENT.  apply_visible_route writes four of the seven
# geometry words to 1280x720 and leaves three at the inherited 852x480:
#
#   0x05600020 = 0x02CF04FF   crop      1280 x 720   <- written
#   0x05600040 = 0x00000500   luma pitch      1280   <- written
#   0x05600044 = 0x00000500   chroma pitch    1280   <- written
#   0x05600030 = 0x01E00354   picture    852 x 480   <- NOT written
#   0x05600048 = 0x01E00354              852 x 480   <- NOT written
#   0x0560004c = 0x00F00354   chroma     852 x 240   <- NOT written
#
# Also measured: the submit rewrites NOTHING (state before == state after), so
# the long-held "firmware rewrites the geometry on submit" is wrong for this
# client.  The 852x480 is simply inherited logo state.
#
# Two coherent configurations exist and only one can be right:
#
#   A  everything 1280x720.  Needs a scaler to fit the 852x480 window.  This is
#      what 7f5146a set by hand; its "shear gone" reading came from a nearly
#      flat frame and cannot discriminate.
#
#   B  crop 852x480 with pitch 1280.  Reads an 852x480 sub-rectangle out of the
#      720p frame and needs NO scaler -- and our path has none, because we own
#      the fetcher, not the pipeline.  Never tested: the one stride sweep that
#      ran was voided by the incoherent block.
#
# B is the minimal change from inherited: strides to 1280, nothing else.
# Prediction if B is right: a sharp, correctly coloured image showing the
# TOP-LEFT 852x480 CROP of the frame -- not the whole picture, and not sheared.
#
# Addresses are programmed PHYSICALLY under IOMMU bypass so translation is not a
# variable.  Bypass is set BEFORE the addresses: a physical address presented to
# a translating IOMMU is an unmapped IOVA and faults master 2, which has blacked
# the panel until a power cycle.  The reverse order merely reads garbage.

set -u

Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000
FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client.coord1080}
PHASE=${PHASE:-20}

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "stride-ab: $*" > /dev/kmsg 2>/dev/null; }

GEOM="0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"
ROUTE="0x051c006c 0x05140508"

# Save/restore key.  NOTE: tr -d 'x' on 0x051c006c gives 0051c006c, not
# 051c006c -- hardcoding the shorter name left the variable unset, and under
# set -u that aborted restore() on its first line, so the geometry loop never
# ran and the panel stayed on the video route.  Always derive the name.
key() { echo "SAVE_$(echo "$1" | tr -d 'x')"; }

for r in $GEOM $ROUTE; do eval "$(key $r)=$(rd $r)"; done

restore() {
	say "--- restoring inherited logo path ---"
	# Remove the visible route first, then the layout it was pointing at.
	for r in 0x051c006c $GEOM 0x05140508; do
		eval "v=\$$(key $r)"
		wr "$r" "$v" 2>/dev/null || true
	done
	wr 0x05600014 1 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: selector=$(rd 0x051c006c) 0x30=$(rd 0x05600030) pitch=$(rd 0x05600040)"
}
trap restore EXIT INT TERM

say "core=$(rd 0x0306101c) bypass=$(rd 0x02010030)"
say "staging $FRAME"
"$CLIENT" show "$FRAME" $(( (PHASE*2 + 30) * 1000 )) &
PID=$!
sleep 4

# bypass first, then physical addresses (ordering note above)
wr 0x02010030 0x7C
wr 0x05600070 $Y_PHYS
wr 0x05600084 $C_PHYS
wr 0x05140508 0x144C0000
say "addresses: Y=$(rd 0x05600070) C=$(rd 0x05600084) bypass=$(rd 0x02010030)"

apply() {
	wr 0x05600020 "$1"; wr 0x05600024 "$2"
	wr 0x05600030 "$3"; wr 0x05600048 "$3"; wr 0x0560004c "$4"
	wr 0x05600040 0x00000500
	wr 0x05600044 0x00000500
	wr 0x05600010 0x03000013
	wr 0x05600014 1
	sleep 0.1
	wr 0x051c006c 0x39000000
}

say ""
say "################ PHASE A: everything 1280x720 (needs a scaler) ################"
apply 0x02CF04FF 0x002C004F 0x02D00500 0x01680500
say "0x20=$(rd 0x05600020) 0x30=$(rd 0x05600030) 0x4c=$(rd 0x0560004c) pitch=$(rd 0x05600040)"
say "HOLDING ${PHASE}s -- LOOK NOW (phase A)"
i=0; while [ $i -lt $PHASE ]; do sleep 5; i=$((i+5)); say "  A t=${i}s"; done

say ""
say "################ PHASE B: crop 852x480, pitch 1280 (no scaler) ################"
apply 0x01DF0353 0x001D0035 0x01E00354 0x00F00354
say "0x20=$(rd 0x05600020) 0x30=$(rd 0x05600030) 0x4c=$(rd 0x0560004c) pitch=$(rd 0x05600040)"
say "HOLDING ${PHASE}s -- LOOK NOW (phase B)"
i=0; while [ $i -lt $PHASE ]; do sleep 5; i=$((i+5)); say "  B t=${i}s"; done

say "=== both phases done ==="
