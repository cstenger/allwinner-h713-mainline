#!/bin/sh
# decd-all-preconditions.sh -- one run with EVERY known prerequisite correct at
# the same time, verified by readback before the operator is asked to look.
#
# WHY THIS EXISTS.  The 2026-08-31 recipe put full-colour 1280x720 NV12 on the
# panel.  Every run since has had at least one piece wrong, and each cost an
# operator look to discover:
#
#   2026-09-06 physaddr   selector on OSD (0x29000000); video never routed
#   2026-09-06 stride A/B ring slots 1-3 stale; composition dragged to 852x480
#   2026-09-06 ring-fill  composition still 852x480 from the earlier run
#   2026-09-08 Codex      selector on OSD, AFBD at 1920x1088 with IOVAs
#
# None of them was a fair test.  This script therefore CHECKS instead of hoping,
# prints a PASS/FAIL table, and REFUSES to hold for a visual test if anything
# fails.  A refusal is a successful run: it costs no operator attention.
#
# Composition at 0x05000000 is deliberately NOT written.  Measured 2026-09-08:
# on a normal boot all seventeen registers are already at the 1280x720 values.
# They only go to 852x480 if the SOURCE-COORDINATE client (/root/decd-client)
# runs, so this script uses decd-client.coord1080 and then verifies.
#
# ORDERING HAZARD: set IOMMU bypass BEFORE writing physical addresses.  A
# physical address presented to a translating IOMMU is an unmapped IOVA and
# faults master 2, which has blacked the panel until a power cycle.  The
# reverse order merely reads garbage for a moment.
#
# PRECONDITION, not checked here: MIPS must be alive (h713_disp init 0x34) and
# the DECD budget module loaded.  The script verifies both and aborts if not.

set -u

Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000
FRAME=${FRAME:-/root/decd-test-frame.nv12}
CLIENT=${CLIENT:-/root/decd-client.coord1080}
DWELL=${DWELL:-30}

Y_SLOTS="0x05600070 0x05600074 0x05600078 0x0560007c"
C_SLOTS="0x05600084 0x05600088 0x0560008c 0x05600090"
AFBD="0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"
COMP="0x050000f0 0x05000210 0x05000174 0x050001b4 0x05000224 0x05000274 0x05000278 0x050002b4 0x050002b8 0x05000444 0x05000544 0x05000804 0x0500080c 0x05000840 0x05000844 0x05000858 0x0500085c"
COMPV="0x63004040 0x63004040 0x00400040 0x00400040 0x02d00500 0x00400040 0x60020168 0x00400040 0x600202d0 0x02d00500 0x02d00500 0x002c0500 0x001402d0 0x02d10015 0x05000030 0x02d00015 0x05000030"

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
say() { echo "$*"; echo "precond: $*" > /dev/kmsg 2>/dev/null; }
lc() { echo "$1" | tr 'A-F' 'a-f'; }

FAIL=0
check() { # name actual expected
	if [ "$(lc "$2")" = "$(lc "$3")" ]; then
		printf '  PASS  %-28s %s\n' "$1" "$2"
	else
		printf '  FAIL  %-28s %s   expected %s\n' "$1" "$2" "$3"
		FAIL=$((FAIL + 1))
	fi
}

# ---------------------------------------------------------------- preflight
say "=== preflight ==="
CORE=$(rd 0x0306101c)
if [ "$CORE" != 0x00000001 ]; then
	echo "ABORT: MIPS core is $CORE, expected 0x00000001." >&2
	echo "  Run 'h713_disp init 0x34' at the U-Boot prompt, then boot the test" >&2
	echo "  FIT.  Do NOT re-release a quiesced core with direct MMIO." >&2
	exit 1
fi
if ! lsmod | grep -q decd; then
	echo "ABORT: no DECD module loaded.  Expected sunxi-decd-budget.ko." >&2
	exit 1
fi
say "core alive, DECD present"

key() { echo "SAVE_$(echo "$1" | tr -d 'x')"; }

# The snapshot MUST be taken after the client's PM_HINT has ungated the display
# block.  Taken before, every register reads 0x00000000 (gating, not state), and
# "restoring" those zeroes leaves the panel black instead of on the logo -- which
# looks exactly like a failed test.  snapshot() is therefore called after
# staging, and the selector is additionally floored to the known logo value.
snapshot() {
	for r in $AFBD 0x051c006c 0x05140508; do eval "$(key $r)=$(rd $r)"; done
	[ "$(rd 0x051c006c)" = 0x00000000 ] && SAVE_0051c006c=0x29000000
	SNAPPED=1
	say "snapshot: selector=$SAVE_0051c006c gain=$SAVE_005140508"
}

restore() {
	# The trap is armed before snapshot() runs, so an abort in between would
	# otherwise expand unset SAVE_ vars under set -u.  Nothing was written yet
	# in that window, so there is nothing to undo -- just park the logo route.
	if [ "${SNAPPED:-0}" != 1 ]; then
		say "--- aborted before snapshot; restoring logo selector only ---"
		wr 0x051c006c 0x29000000 2>/dev/null || true
		[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
		return
	fi
	say "--- restoring inherited logo path ---"
	for r in 0x051c006c $AFBD 0x05140508; do
		eval "v=\${$(key $r):-}"
		[ -n "$v" ] || continue
		wr "$r" "$v" 2>/dev/null || true
	done
	# Put the logo's OSD channel back before anything else, or the panel stays
	# blank after the run and looks like a failure.
	[ -z "${SAVE_OSD2:-}" ] || wr 0x05600140 "$SAVE_OSD2" 2>/dev/null || true
	wr 0x05600014 1 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	say "restored: selector=$(rd 0x051c006c) osd2=$(rd 0x05600140)"
}
trap restore EXIT INT TERM

# ---------------------------------------------------------------- configure
say "staging $FRAME via $CLIENT"
"$CLIENT" show "$FRAME" $(( (DWELL + 30) * 1000 )) >/dev/null 2>&1 &
PID=$!
sleep 4
snapshot                               # after PM_HINT, so values are real

wr 0x02010030 0x7C                     # bypass BEFORE addresses
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

# OSD_OFF=1 disables the OSD channel still showing the boot logo.
#
# Measured 2026-09-08 by diffing the FULL AFBD block (0x00-0x1FC) against the
# stock-playback capture.  The upper half had never been compared, because an
# earlier grep of '^056000' silently dropped every address from 0x05600100 up:
#
#   0x05600140  stock=0x83001900  live=0x03001901   ch2 ctrl, enable in bit 0
#   0x05600178  stock=0x781F6000  live=0x6C100000   ch2 buffer = the BOOT LOGO
#
# U-Boot prints "bootlogo.bmp published at 0x6c100000", so a second layer has
# been live under every test in this series, while stock playback has that exact
# channel disabled.  The structured banding may therefore be the LOGO composited
# under video geometry rather than our frame misread.  Clearing bit 0 separates
# the two: if the mess goes, it was the logo layer; if it stays, it is our path.
if [ "${OSD_OFF:-0}" = 1 ]; then
	SAVE_OSD2=$(rd 0x05600140)
	wr 0x05600140 "$(printf '0x%08X' $(( SAVE_OSD2 & ~1 )))"
	wr 0x05600014 1
	sleep 0.1
	say "OSD ch2 (logo) disabled: $SAVE_OSD2 -> $(rd 0x05600140)"
fi
sleep 0.2
wr 0x051c006c 0x39000000
sleep 0.3

# ---------------------------------------------------------------- verify
echo
say "=== precondition check ==="
check "MIPS core alive"        "$(rd 0x0306101c)" 0x00000001
check "IOMMU m2 bypass"        "$(rd 0x02010030)" 0x0000007C
check "selector = VIDEO"       "$(rd 0x051c006c)" 0x39000000
check "chroma gain"            "$(rd 0x05140508)" 0x144C0000
check "src ctrl/enable/fmt"    "$(rd 0x05600010)" 0x03000013
check "crop 1280x720"          "$(rd 0x05600020)" 0x02CF04FF
check "crop origin"            "$(rd 0x05600024)" 0x002C004F
check "picture 1280x720"       "$(rd 0x05600030)" 0x02D00500
check "picture 1280x720 (48)"  "$(rd 0x05600048)" 0x02D00500
check "chroma 1280x360"        "$(rd 0x0560004c)" 0x01680500
check "luma stride 1280"       "$(rd 0x05600040)" 0x00000500
check "chroma stride 1280"     "$(rd 0x05600044)" 0x00000500
for r in $Y_SLOTS; do check "Y slot $r" "$(rd $r)" $Y_PHYS; done
for r in $C_SLOTS; do check "C slot $r" "$(rd $r)" $C_PHYS; done

i=1
for r in $COMP; do
	v=$(echo $COMPV | cut -d' ' -f$i)
	check "comp $r" "$(rd $r)" "$v"
	i=$((i + 1))
done

# The frame must actually be in the memory we point the fetcher at.
W0=$(rd $Y_PHYS)
check "frame bytes at Y_PHYS" "$W0" 0x4B4B494A

echo
if [ "$FAIL" -ne 0 ]; then
	say "=== $FAIL PRECONDITION(S) FAILED -- NOT holding for a visual test ==="
	say "Nothing was shown to the operator.  Fix the failures above and rerun."
	exit 2
fi

# FMT_SWEEP=1 walks the format byte in 0x05600010[15:8] through all eight values
# the firmware can produce.  Derived 2026-09-08 by decoding the resolver jump
# table at MIPS 0x8b2078a4 (handlers at 0x8b1a321c..0x8b1a32f4):
#
#   VideoInfo code 0 -> fmt 0   (stock playback, and every run of ours)
#   codes 2,4,6      -> fmt 1,2,3
#   codes 8/11       -> fmt 4   (the only other value ever tried)
#   codes 9/12       -> fmt 5
#   code 15          -> fmt 6
#   code 14          -> fmt 7
#   codes 1,3,5,10,13-> error path
#
# Two of eight tested in three sessions.  This enumerates the rest in one
# operator window instead of one look per guess.
if [ "${FMT_SWEEP:-0}" = 1 ]; then
	say "=== FORMAT SWEEP: 8 phases x ${PHASE_S:-8}s, LOOK NOW ==="
	say "    watch for ANY phase that resolves into a real picture"
	f=0
	while [ $f -lt 8 ]; do
		wr 0x05600010 "$(printf '0x0300%02X13' $f)"
		wr 0x05600014 1
		say ">>> PHASE $((f + 1))/8  fmt=$f  ctrl=$(rd 0x05600010)"
		sleep "${PHASE_S:-8}"
		f=$((f + 1))
	done
	say "=== sweep done ==="
	exit 0
fi

# NV12_SEQ=1 replays the EXACT sequence from our own working KMS driver,
# patches/kernel/0065-drm-h713-afbd-scan-out-nv12-directly.patch, which put
# linear NV12 on this panel.  Two differences from everything we have run:
#
#   1. format byte 0x05600011 = 3 (NV12).  Row 0 is RGB888 -- so every run in
#      this series asked the engine to read NV12 as 4-byte-per-pixel RGB, which
#      is exactly the half-height/flat-bottom signature in test_79.
#   2. the config is published through AFBD_DIRTY at 0x0560006c, NOT the
#      0x05600014 latch every script here has used.  The patch's own comment
#      records this as the reason two earlier attempts failed: they set the
#      format byte, kept publishing the packed path, and the fetch stayed at
#      4 bytes/pixel.
#
# Driver order, preserved exactly: format, stride0, stride1, addr0, addr1, dirty.
if [ "${NV12_SEQ:-0}" = 1 ]; then
	say "--- replaying the 0065 NV12 driver sequence ---"
	busybox devmem 0x05600011 8 3          # AFBD_FORMAT  = NV12 (byte write)
	wr 0x05600040 0x00000500               # AFBD_PLANE_STRIDE0
	wr 0x05600044 0x00000500               # AFBD_PLANE_STRIDE1
	wr 0x05600070 $Y_PHYS                  # AFBD_PLANE_ADDR0
	wr 0x05600084 $C_PHYS                  # AFBD_PLANE_ADDR1
	wr 0x0560006c 1                        # AFBD_DIRTY -- the publish
	sleep 0.2
	say "ctrl=$(rd 0x05600010) fmt_byte=$(busybox devmem 0x05600011 8)"
	say "dirty=$(rd 0x0560006c) stride0=$(rd 0x05600040) addr0=$(rd 0x05600070)"
fi

say "=== ALL PRECONDITIONS PASS -- HOLDING ${DWELL}s, LOOK NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5; i=$((i + 5))
	say "  t=${i}s selector=$(rd 0x051c006c) Y0=$(rd 0x05600070) comp174=$(rd 0x05000174)"
done
say "=== done ==="
