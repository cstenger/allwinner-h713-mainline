#!/bin/sh
# decd-ring-fill.sh -- program ALL FOUR ring slots, not just slot 0.
#
# MEASURED 2026-09-06, and it explains the corruption outright:
#
#   Y slot 0 = 0x6C500000   real frame
#   Y slot 1 = 0xFFC00000   stale IOVA -- not DRAM under bypass
#   Y slot 2 = 0xFFC00000   stale
#   Y slot 3 = 0xFFC00000   stale
#
# The fetcher cycles all four slots, so three frames in four come from an
# address that is not memory.  That is the green noise, and it is why the
# "details changed" between two photographs of the same static frame: the ring
# was rotating through three garbage slots and one real one.
#
# CAUSAL LINK WORTH KEEPING: the DECD hard-lock workaround is ring_writes_max=1
# (see the 2026-09-04 handoff -- the driver's 60 Hz vsync handler rewriting all
# four slots every frame is what locks the SoC with the MIPS alive).  Writing
# the ring exactly once means exactly ONE slot gets a real address.  The fix for
# the lock is the cause of the corruption.  wait_ring() never caught it because
# it only checks whether ANY slot is non-zero.
#
# Addresses are physical under IOMMU bypass.  Bypass is set BEFORE the
# addresses: a physical address presented to a translating IOMMU is an unmapped
# IOVA and faults master 2, which has blacked the panel until a power cycle.
#
# Geometry is the coherent 1280x720 set.  NOTE: test_76 showed the source
# geometry words do NOT control the displayed footprint -- that is owned by the
# MIPS window layer -- so this is for internal coherence, not for sizing.

set -u

Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000
FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client.coord1080}
DWELL=${DWELL:-25}

Y_SLOTS="0x05600070 0x05600074 0x05600078 0x0560007c"
C_SLOTS="0x05600084 0x05600088 0x0560008c 0x05600090"
GEOM="0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"
ROUTE="0x051c006c 0x05140508"

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "ringfill: $*" > /dev/kmsg 2>/dev/null; }

key() { echo "SAVE_$(echo "$1" | tr -d 'x')"; }
for r in $GEOM $ROUTE $Y_SLOTS $C_SLOTS; do eval "$(key $r)=$(rd $r)"; done

restore() {
	say "--- restoring inherited logo path ---"
	for r in 0x051c006c $GEOM 0x05140508; do
		eval "v=\$$(key $r)"
		wr "$r" "$v" 2>/dev/null || true
	done
	wr 0x05600014 1 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: selector=$(rd 0x051c006c) pitch=$(rd 0x05600040)"
}
trap restore EXIT INT TERM

say "core=$(rd 0x0306101c) bypass=$(rd 0x02010030)"
say "staging $FRAME"
"$CLIENT" show "$FRAME" $(( (DWELL + 25) * 1000 )) &
PID=$!
sleep 4

say "--- ring BEFORE ---"
for r in $Y_SLOTS; do say "  Y $r = $(rd $r)"; done
for r in $C_SLOTS; do say "  C $r = $(rd $r)"; done

# bypass first, then addresses (ordering note above)
wr 0x02010030 0x7C
for r in $Y_SLOTS; do wr "$r" $Y_PHYS; done
for r in $C_SLOTS; do wr "$r" $C_PHYS; done

say "--- ring AFTER ---"
for r in $Y_SLOTS; do say "  Y $r = $(rd $r)"; done
for r in $C_SLOTS; do say "  C $r = $(rd $r)"; done

# coherent geometry + chroma gain + enable + commit, then route
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
sleep 0.1
wr 0x051c006c 0x39000000

say "geom 0x20=$(rd 0x05600020) 0x30=$(rd 0x05600030) pitch=$(rd 0x05600040)"
say "gain=$(rd 0x05140508) selector=$(rd 0x051c006c)"
say ""
say "=== HOLDING ${DWELL}s -- LOOK NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5; i=$((i+5))
	say "  t=${i}s  Y0=$(rd 0x05600070) Y1=$(rd 0x05600074) Y2=$(rd 0x05600078) Y3=$(rd 0x0560007c)"
done
say "=== done ==="
