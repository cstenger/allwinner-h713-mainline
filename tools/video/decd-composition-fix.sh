#!/bin/sh
# decd-composition-fix.sh -- correct the firmware-owned composition block, not
# just the AFBD fetcher.
#
# MEASURED 2026-09-06.  Our AFBD state is byte-identical to the 2026-08-31
# known-good capture that put full-colour NV12 on the panel:
#
#   0x05600020 0x02cf04ff   0x05600030 0x02d00500   0x05600040 0x00000500
#   0x0560004c 0x01680500   0x05600060 0x00000001   0x05600070 0x6c500000
#
# ...and the picture is still green noise.  The difference is DOWNSTREAM: all
# seventeen composition registers at 0x05000000 are at the 852x480 values.
# 0x05000174 = 0x002B002B is the scaler ratio (43/64) configured for an
# 852-wide source, while AFBD fetches 1280x720 at stride 1280.  The composition
# stage and the fetcher disagree, and composition is what drives the panel.
# That is also why changing AFBD geometry never moved the footprint.
#
# How it got that way: the SOURCE-COORDINATE client (/root/decd-client) drives
# the whole block to 852x480 -- see frame-composition-block-capture-2026-08-31.
# Only a corrected-client frame the firmware actually SERVICES reverses it, and
# the firmware has serviced none since, because the driver's ring writer is
# frozen at ring_writes_done == ring_writes_max.
#
# Raising ring_writes_max would let the firmware fix it properly, but the 60 Hz
# ring rewrite is exactly what hard-locks the SoC with the MIPS alive, so this
# writes the registers directly instead.  All seventeen were verified writable
# and non-reverting (stuck=17 reverted=0).
#
# Target values are from the known-good capture's 1280x720 column.

set -u

Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000
FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client.coord1080}
DWELL=${DWELL:-25}

Y_SLOTS="0x05600070 0x05600074 0x05600078 0x0560007c"
C_SLOTS="0x05600084 0x05600088 0x0560008c 0x05600090"
AFBD="0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"
COMP="0x050000f0 0x05000210 0x05000174 0x050001b4 0x05000224 0x05000274 0x05000278 0x050002b4 0x050002b8 0x05000444 0x05000544 0x05000804 0x0500080c 0x05000840 0x05000844 0x05000858 0x0500085c"
COMPV="0x63004040 0x63004040 0x00400040 0x00400040 0x02d00500 0x00400040 0x60020168 0x00400040 0x600202d0 0x02d00500 0x02d00500 0x002c0500 0x001402d0 0x02d10015 0x05000030 0x02d00015 0x05000030"
ROUTE="0x051c006c 0x05140508"

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "compfix: $*" > /dev/kmsg 2>/dev/null; }

key() { echo "SAVE_$(echo "$1" | tr -d 'x')"; }
for r in $AFBD $ROUTE $COMP; do eval "$(key $r)=$(rd $r)"; done

restore() {
	say "--- restoring inherited logo path ---"
	for r in 0x051c006c $AFBD 0x05140508 $COMP; do
		eval "v=\$$(key $r)"
		wr "$r" "$v" 2>/dev/null || true
	done
	wr 0x05600014 1 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: selector=$(rd 0x051c006c) comp174=$(rd 0x05000174)"
}
trap restore EXIT INT TERM

say "core=$(rd 0x0306101c) bypass=$(rd 0x02010030)"
say "staging $FRAME"
"$CLIENT" show "$FRAME" $(( (DWELL + 25) * 1000 )) &
PID=$!
sleep 4

# --- AFBD: the known-good 2026-08-31 state, all four ring slots ---
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
sleep 0.1

# --- composition: the 1280x720 column ---
i=1
for r in $COMP; do
	v=$(echo $COMPV | cut -d' ' -f$i)
	wr "$r" "$v"
	i=$((i + 1))
done
sleep 0.1

wr 0x051c006c 0x39000000

say "afbd  0x20=$(rd 0x05600020) 0x30=$(rd 0x05600030) pitch=$(rd 0x05600040) Y=$(rd 0x05600070)"
say "comp  0x174=$(rd 0x05000174) 0x224=$(rd 0x05000224) 0x844=$(rd 0x05000844)"
say "route selector=$(rd 0x051c006c) gain=$(rd 0x05140508)"
say ""
say "=== HOLDING ${DWELL}s -- LOOK NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5; i=$((i+5))
	say "  t=${i}s comp174=$(rd 0x05000174) Y0=$(rd 0x05600070)"
done
say "=== done ==="
