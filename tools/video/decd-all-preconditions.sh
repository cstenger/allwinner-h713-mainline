#!/bin/sh
# decd-all-preconditions.sh -- one verified path to the panel, three sources.
#
# Verifies every precondition by readback and REFUSES to hold for a visual test
# unless all of them pass.  A refusal costs no operator attention; a photograph
# of a misconfigured run costs a look and teaches nothing.
#
#   MODE=static    a file staged into the scanout carveout by decd-client
#                  (bypass + physical addresses)          -- PROVEN, test_80
#   MODE=carveout  Cedrus decodes, frame 0 copied into the same carveout
#                  (bypass + physical addresses)          -- provenance test
#   MODE=live      Cedrus decodes, driver owns the ring, one Y/C pair per frame
#                  (IOMMU translation + IOVAs)            -- real playback
#
# WHY THIS EXISTS.  Every ad-hoc script written against this hardware has
# diverged from the verified sequence in some small way, and only a photograph
# caught it.  The tally so far: a stale selector, three dead ring slots, five
# unset geometry words, a snapshot taken while the block was clock-gated, a
# player that exited before the hold, and -- four times -- a missing commit
# latch.  All were visible in a register read taken beforehand.
#
# ==========================================================================
# THE TWO LATCHES.  Both are required and they do different jobs:
#
#   0x05600014   commits the SOURCE CONFIG    (seven geometry words + enable)
#   0x0560006c   publishes the PLANE ADDRESSES (two-plane YUV path)
#
# Discovering that 0x0560006c was the missing publish led to scripts built
# around it that dropped 0x05600014 entirely, so geometry and enable were
# written, read back correct, and never committed.  The fetcher then had no
# valid picture configuration, fetched nothing, and zeroes render as SOLID
# GREEN (Y=U=V=0 through BT.601 clamps R and B to 0 and gives G ~= 135).
#
# Solid green means "fetching nothing", not "wrong colour".  Treat it as a
# configuration failure and look for an uncommitted or unpublished register.
# ==========================================================================
#
# ORDER BELOW IS THE test_80 ORDER AND IS LOAD-BEARING.  Config is committed in
# format 0, the selector is routed, and only then does the format byte become 3
# and the plane addresses publish.
#
# Format byte: 0 = RGB888, 3 = NV12 (patch 0065, AFBD_FMT_NV12).  Stock playback
# runs format 0 because stock composites video into an RGB surface -- it is not
# evidence for our path.  The driver never programs this byte (it only traces
# it), so a manual 3 persists across frames.
#
# IOMMU ordering: set bypass/translation only while the source is DISABLED.  The
# source rests at base 0 with 1920x1088 geometry and scans low memory the
# instant it is enabled -- garbage under bypass, an AFBD-wedging L1-invalid
# fault under translation.

set -u

MODE=${MODE:-static}
FRAME=${FRAME:-/root/decd-test-frame.nv12}
STREAM=${STREAM:-/root/leota-720p.h264}
CLIENT=${CLIENT:-/root/decd-client.coord1080}
PLAYER=${PLAYER:-/root/decd-play}
DWELL=${DWELL:-30}
RING_MAX=${RING_MAX:-2000}
Y_PHYS=0x6c500000
C_PHYS=0x6c5E1000
CHROMA_OFF=0xE1000              # 1280*720; a real Y/C pair differs by this

Y_SLOTS="0x05600070 0x05600074 0x05600078 0x0560007c"
C_SLOTS="0x05600084 0x05600088 0x0560008c 0x05600090"
AFBD="0x05600010 0x05600020 0x05600024 0x05600030 0x05600040 0x05600044 0x05600048 0x0560004c"
COMP="0x050000f0 0x05000210 0x05000174 0x050001b4 0x05000224 0x05000274 0x05000278 0x050002b4 0x050002b8 0x05000444 0x05000544 0x05000804 0x0500080c 0x05000840 0x05000844 0x05000858 0x0500085c"
COMPV="0x63004040 0x63004040 0x00400040 0x00400040 0x02d00500 0x00400040 0x60020168 0x00400040 0x600202d0 0x02d00500 0x02d00500 0x002c0500 0x001402d0 0x02d10015 0x05000030 0x02d00015 0x05000030"

rd() { busybox devmem "$1" 32; }
wr() { busybox devmem "$1" 32 "$2"; }
rb() { busybox devmem "$1" 8; }
say() { echo "$*"; echo "precond: $*" > /dev/kmsg 2>/dev/null; }
lc() { echo "$1" | tr 'A-F' 'a-f'; }

FAIL=0
check() {
	if [ "$(lc "$2")" = "$(lc "$3")" ]; then
		printf '  PASS  %-28s %s\n' "$1" "$2"
	else
		printf '  FAIL  %-28s %s   expected %s\n' "$1" "$2" "$3"
		FAIL=$((FAIL + 1))
	fi
}
check_ne() {   # name value rejected
	if [ "$(lc "$2")" != "$(lc "$3")" ]; then
		printf '  PASS  %-28s %s\n' "$1" "$2"
	else
		printf '  FAIL  %-28s %s   must not be %s\n' "$1" "$2" "$3"
		FAIL=$((FAIL + 1))
	fi
}

# ---------------------------------------------------------------- preflight
case "$MODE" in
static|carveout|live) ;;
*) echo "ABORT: MODE must be static, carveout or live" >&2; exit 1 ;;
esac

say "=== preflight (MODE=$MODE) ==="
CORE=$(rd 0x0306101c)
if [ "$CORE" != 0x00000001 ]; then
	echo "ABORT: MIPS core is $CORE, expected 0x00000001." >&2
	echo "  Run 'h713_disp init 0x34' at the U-Boot prompt, then boot the test" >&2
	echo "  FIT.  Do NOT re-release a quiesced core with direct MMIO." >&2
	exit 1
fi
lsmod | grep -q decd || { echo "ABORT: no DECD module loaded." >&2; exit 1; }
case "$MODE" in
static)   [ -r "$FRAME" ]  || { echo "ABORT: no frame $FRAME" >&2; exit 1; } ;;
*)        [ -r "$STREAM" ] || { echo "ABORT: no stream $STREAM" >&2; exit 1; }
          [ -x "$PLAYER" ] || { echo "ABORT: no player $PLAYER" >&2; exit 1; } ;;
esac
say "core alive, DECD present"

key() { echo "SAVE_$(echo "$1" | tr -d 'x')"; }

# The snapshot MUST be taken after the source's PM hint has ungated the block.
# Taken before, every register reads 0x00000000 -- gating, not state -- and
# restoring those zeroes blanks the panel, which looks exactly like a failure.
snapshot() {
	for r in $AFBD 0x051c006c 0x05140508; do eval "$(key $r)=$(rd $r)"; done
	SAVE_002010030=$INHERITED_BYP
	[ "$(rd 0x051c006c)" = 0x00000000 ] && SAVE_0051c006c=0x29000000
	SNAPPED=1
	say "snapshot: selector=$SAVE_0051c006c bypass=$SAVE_002010030"
}

restore() {
	if [ "${SNAPPED:-0}" != 1 ]; then
		say "--- aborted before snapshot; parking the logo selector only ---"
		wr 0x051c006c 0x29000000 2>/dev/null || true
		[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
		return
	fi
	say "--- restoring inherited logo path ---"
	wr 0x051c006c "$SAVE_0051c006c" 2>/dev/null || true
	# Disable the source before moving the IOMMU back (ordering rule).
	wr 0x05600010 "$(printf '0x%08X' $(( SAVE_005600010 & 0xFFFFFFFC )))" 2>/dev/null || true
	wr 0x05600014 1 2>/dev/null || true
	wr 0x02010030 "$SAVE_002010030" 2>/dev/null || true
	for r in $AFBD 0x05140508; do
		eval "v=\${$(key $r):-}"
		[ -n "$v" ] && wr "$r" "$v" 2>/dev/null || true
	done
	wr 0x05600014 1 2>/dev/null || true
	wr 0x0560006c 1 2>/dev/null || true
	[ -z "${SAVE_RINGMAX:-}" ] || echo "$SAVE_RINGMAX" > /sys/module/sunxi_decd/parameters/ring_writes_max 2>/dev/null || true
	touch /tmp/precond-stop 2>/dev/null || true
	[ -z "${PID:-}" ] || kill "$PID" 2>/dev/null || true
	pkill -f "$(basename "$PLAYER") $STREAM" 2>/dev/null || true
	say "restored: selector=$(rd 0x051c006c) bypass=$(rd 0x02010030)"
}
trap restore EXIT INT TERM

SAVE_RINGMAX=$(cat /sys/module/sunxi_decd/parameters/ring_writes_max 2>/dev/null || echo "")
# The inherited IOMMU state must be captured BEFORE the DRIVER_ROUTE early flip.
# snapshot() runs after it, so it would record the flipped value and "restore" the
# board to whichever mode ran last -- state drift that makes a later result
# confusing for no benefit.
INHERITED_BYP=$(rd 0x02010030)

# ---------------------------------------------------------------- source
# DRIVER_ROUTE: the disable + IOMMU flip must happen BEFORE the source starts.
# The driver routes at submit time, so doing them afterwards clobbers the enable
# and forces a second 0x05600014 commit -- and committing while the format byte
# already reads 3 latches a 2-bytes-per-pixel interpretation.  That renders each
# display row from two source rows: the frame appears TWICE side by side and
# runs out at half height (test_81).  Commit in format 0 or not at all.
if [ "${DRIVER_ROUTE:-0}" = 1 ]; then
	case "$MODE" in
	live) EARLY_BYP=0x78 ;;
	*)    EARLY_BYP=0x7C ;;
	esac
	wr 0x05600010 "$(printf '0x%08X' $(( $(rd 0x05600010) & 0xFFFFFFFC )))"
	wr 0x05600014 1
	sleep 0.1
	wr 0x02010030 $EARLY_BYP
	say "DRIVER_ROUTE: source disabled, IOMMU -> $(rd 0x02010030), before submit"
fi

case "$MODE" in
static)
	say "staging $FRAME via $CLIENT"
	"$CLIENT" show "$FRAME" $(( (DWELL + 30) * 1000 )) >/dev/null 2>&1 &
	;;
carveout)
	# DECD_FREEZE keeps the process (and its PM hint) alive for the whole hold
	# without decoding anything new; DECD_CARVEOUT copies decoded frame 0 to
	# Y_PHYS.  A player that exits mid-hold gates the display block off.
	say "decoding $STREAM, frame 0 -> carveout $Y_PHYS"
	DECD_FREEZE=1 DECD_CARVEOUT=1 "$PLAYER" "$STREAM" $(( (DWELL + 30) * 30 )) \
		>/tmp/precond-player.log 2>&1 &
	;;
live)
	# LOOP the clip.  decd-play stops at END OF STREAM, not at max-frames, and
	# the fixture is only ~10 s (300 frames at 30 fps).  With a longer hold the
	# player exits partway, the harness sees "source process alive" fail,
	# restores, and puts ring_writes_max back to 1 -- which freezes the ring.
	# On the panel that is "video plays for a few seconds, then freezes", and it
	# is entirely self-inflicted: the picture was correct until the clip ended.
	# Re-running the player for the whole hold keeps PM and the ring alive.
	say "live playback from $STREAM (looped), driver owns the ring"
	# ring_writes_done is cumulative and read-only (0444), so a fixed cap is
	# already spent by earlier runs and the driver silently stops writing.
	# Budget RELATIVE to the current count.
	RW_DONE=$(cat /sys/module/sunxi_decd/parameters/ring_writes_done)
	echo $(( RW_DONE + RING_MAX )) > /sys/module/sunxi_decd/parameters/ring_writes_max
	say "ring budget: done=$RW_DONE max=$(cat /sys/module/sunxi_decd/parameters/ring_writes_max)"
	rm -f /tmp/precond-stop
	( while [ ! -f /tmp/precond-stop ]; do
		"$PLAYER" "$STREAM" $(( (DWELL + 10) * 30 )) >>/tmp/precond-player.log 2>&1
		[ -f /tmp/precond-stop ] && break
		sleep 0.2
	  done ) &
	;;
esac
PID=$!
sleep 4
kill -0 "$PID" 2>/dev/null || { echo "ABORT: source process died:" >&2; tail -5 /tmp/precond-player.log 2>/dev/null >&2; exit 1; }
snapshot

# ---------------------------------------------------------------- configure
# IOMMU first, while the source is still disabled.  Skipped under DRIVER_ROUTE:
# it was already done before the submit, and redoing it here would undo the
# driver's route.
if [ "${DRIVER_ROUTE:-0}" != 1 ]; then
wr 0x05600010 "$(printf '0x%08X' $(( SAVE_005600010 & 0xFFFFFFFC )))"
wr 0x05600014 1
sleep 0.1
fi
# Full 8-digit form: devmem reads back 0x0000007C, so a 0x7C literal fails the
# string compare.  The first run of this harness flagged exactly that.
case "$MODE" in
live) BYP=0x00000078 ;;   # Cedrus buffers are dma-mapped: the ring carries IOVAs
*)    BYP=0x0000007C ;;   # carveout/static: real physical addresses
esac
wr 0x02010030 $BYP

# Plane addresses: fixed physical for the carveout modes; in live mode the
# driver writes a fresh Y/C pair per frame and must not be overwritten.
if [ "$MODE" != live ]; then
	for r in $Y_SLOTS; do wr "$r" $Y_PHYS; done
	for r in $C_SLOTS; do wr "$r" $C_PHYS; done
fi

# DRIVER_ROUTE=1 writes NOTHING to the AFBD block: patch 0095 makes the driver
# program it instead -- hardware-verified 2026-09-08.  The trap it had to solve:
# the config commit at 0x05600014 RETIRES ON VSYNC, so back-to-back kernel writes
# never latch while shell recipes always did (they slept 100 ms).  The failure is
# invisible to a register dump.  (patch 0095 makes the driver
# program the geometry, enable, format byte and config commit from the submitted
# descriptor.  Only the display-side gain and selector are set here, because
# those live in the display engine, are not mapped by the driver, and are shared
# with the MIPS logo path.  The checks below are unchanged, so this proves the
# driver's own programming is sufficient rather than assuming it.
if [ "${DRIVER_ROUTE:-0}" = 1 ]; then
	say "DRIVER_ROUTE=1: AFBD block left entirely to the driver"
	# No enable and no commit here: the driver's route already set both, and a
	# second commit after the format byte is 3 latches 2 bytes/pixel.  Only the
	# display-engine registers are ours.
	wr 0x05140508 0x144C0000
	sleep 0.1
	wr 0x051c006c 0x39000000
else
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600030 0x02D00500
wr 0x05600048 0x02D00500
wr 0x0560004c 0x01680500
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000013
wr 0x05600014 1                        # COMMIT the source config
sleep 0.1
wr 0x051c006c 0x39000000               # route to video

busybox devmem 0x05600011 8 3          # format -> NV12
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
if [ "$MODE" != live ]; then
	wr 0x05600070 $Y_PHYS
	wr 0x05600084 $C_PHYS
fi
fi
# The plane-address PUBLISH runs in BOTH modes.  0x0560006c publishes plane
# addresses; 0x05600014 commits the source config.  Under DRIVER_ROUTE the
# driver owns the commit, but this harness still writes the four ring slots in
# static/carveout mode, so it must publish them -- leaving this inside the else
# branch meant the slots were written and never published, and the addresses in
# force stayed whatever the driver last published.
wr 0x0560006c 1
sleep 0.3

# ---------------------------------------------------------------- verify
echo
say "=== precondition check (MODE=$MODE) ==="
check "MIPS core alive"        "$(rd 0x0306101c)" 0x00000001
check "IOMMU master 2"         "$(rd 0x02010030)" $BYP
check "selector = VIDEO"       "$(rd 0x051c006c)" 0x39000000
check "chroma gain"            "$(rd 0x05140508)" 0x144C0000
check "src ctrl (fmt 3 + en)"  "$(rd 0x05600010)" 0x03000313
check "format byte = NV12"     "$(rb 0x05600011)" 0x03
check "crop 1280x720"          "$(rd 0x05600020)" 0x02CF04FF
check "crop origin"            "$(rd 0x05600024)" 0x002C004F
check "picture 1280x720"       "$(rd 0x05600030)" 0x02D00500
check "picture 1280x720 (48)"  "$(rd 0x05600048)" 0x02D00500
check "chroma 1280x360"        "$(rd 0x0560004c)" 0x01680500
check "luma stride 1280"       "$(rd 0x05600040)" 0x00000500
check "chroma stride 1280"     "$(rd 0x05600044)" 0x00000500

i=1
for r in $COMP; do
	check "comp $r" "$(rd $r)" "$(echo $COMPV | cut -d' ' -f$i)"
	i=$((i + 1))
done

if [ "$MODE" = live ]; then
	# Wait for the driver to (re)populate the ring before checking it.
	# patch 0096 blanks all four slots when the last client closes, which is
	# correct, but it races with the next run: the ring reads zero for a moment
	# at startup and the checks below then report a spurious "Y slot non-zero"
	# failure.  Observed 1 run in 5-6.  The old decd-visible-sequence.sh had a
	# wait_ring() helper for the same reason.
	_w=0
	while [ $_w -lt 40 ]; do
		[ "$(rd 0x05600070)" != 0x00000000 ] && break
		_w=$((_w + 1))
		sleep 0.1
	done
	[ $_w -gt 0 ] && say "ring armed after ${_w}00 ms"

	# The driver owns the ring: require every slot non-zero and every Y/C pair
	# separated by exactly the luma-plane size.  A zero slot means the driver
	# wrote a blank frame; a wrong delta means the pair is not a real frame.
	# The driver rewrites the ring ~60x/s, and each rd() is a separate devmem
	# process, so a Y/C pair can straddle an update and yield a nonsense (even
	# negative) delta.  Re-read until the pair is coherent -- C, Y, C with both
	# C reads equal -- rather than weakening the check.
	pair_delta() {   # y_reg c_reg -> prints delta, or "racy"
		_t=0
		while [ $_t -lt 8 ]; do
			_c1=$(rd "$2"); _y=$(rd "$1"); _c2=$(rd "$2")
			if [ "$_c1" = "$_c2" ]; then
				printf '0x%X\n' $(( _c1 - _y )); return 0
			fi
			_t=$((_t + 1))
		done
		echo racy
	}
	n=1
	for r in $Y_SLOTS; do
		y=$(rd $r); c=$(rd $(echo $C_SLOTS | cut -d' ' -f$n))
		check_ne "Y slot $n non-zero" "$y" 0x00000000
		# Must NOT still be the carveout address: that would mean the driver
		# never wrote the ring and we are checking stale values from a previous
		# run -- a false pass this harness hit on its first live dry-run.
		check_ne "Y slot $n driver-written" "$y" "$Y_PHYS"
		d=$(pair_delta "$r" "$(echo $C_SLOTS | cut -d' ' -f$n)")
		check "Y/C delta slot $n" "$d" "$CHROMA_OFF"
		n=$((n + 1))
	done
	B=$(cat /sys/module/sunxi_decd/parameters/ring_writes_done)
	sleep 1
	A=$(cat /sys/module/sunxi_decd/parameters/ring_writes_done)
	if [ "$A" -gt "$B" ]; then
		printf '  PASS  %-28s %s -> %s\n' "ring advancing" "$B" "$A"
	else
		printf '  FAIL  %-28s stuck at %s\n' "ring advancing" "$A"
		FAIL=$((FAIL + 1))
	fi
else
	for r in $Y_SLOTS; do check "Y slot $r" "$(rd $r)" $Y_PHYS; done
	for r in $C_SLOTS; do check "C slot $r" "$(rd $r)" $C_PHYS; done
	# The bytes must actually be at the address the fetcher is pointed at.
	check_ne "frame bytes at Y_PHYS" "$(rd $Y_PHYS)" 0x00000000
	check_ne "chroma bytes at C_PHYS" "$(rd $C_PHYS)" 0x00000000
fi

if kill -0 "$PID" 2>/dev/null; then
	printf '  PASS  %-28s pid %s\n' "source process alive" "$PID"
else
	printf '  FAIL  %-28s exited early (PM hint dropped)\n' "source process alive"
	FAIL=$((FAIL + 1))
fi

echo
if [ "$FAIL" -ne 0 ]; then
	say "=== $FAIL PRECONDITION(S) FAILED -- NOT holding for a visual test ==="
	say "Nothing was shown to the operator.  Fix the failures above and rerun."
	exit 2
fi

say "=== ALL PRECONDITIONS PASS -- HOLDING ${DWELL}s, LOOK NOW ==="
i=0
while [ $i -lt $DWELL ]; do
	sleep 5; i=$((i + 5))
	say "  t=${i}s Y0=$(rd 0x05600070) sel=$(rd 0x051c006c) core=$(rd 0x0306101c)"
done
say "=== done ==="
[ "$MODE" = static ] || { say "--- player ---"; tail -4 /tmp/precond-player.log; }
