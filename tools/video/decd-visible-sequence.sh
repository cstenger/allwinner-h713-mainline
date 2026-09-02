#!/bin/sh
# decd-visible-sequence.sh -- show NV12 frames or decoded H.264 through the
# proven H713 DECD route, then restore the inherited logo path.
#
# TARGET-SIDE, ROOT, DIAGNOSTIC ONLY.  This is for the patch-0068 DECD-exclusive
# boot. Static tests require the MIPS display firmware alive; decoded --play can
# explicitly use the safer parked-MIPS state. It deliberately writes shared
# display MMIO and refuses to run unless the DT proves KMS is disabled and DECD
# is the owner. The script snapshots every value it changes and restores them
# on normal exit, error, SIGINT, and SIGTERM.
#
# A visual test must be announced before it starts.  The explicit ARMED=yes
# gate prevents an accidental invocation from blanking the logo without an
# observer ready:
#
#   ARMED=yes CLIENT=/root/decd-client.coord1080 \
#     decd-visible-sequence.sh /root/decd-test-frame.nv12
#
# Alternating-frame cadence test (hardware-confirmed 2026-08-31):
#
#   ARMED=yes decd-visible-sequence.sh \
#     /root/decd-red.nv12 /root/decd-green.nv12 \
#     /root/decd-red.nv12 /root/decd-green.nv12
#
# Production-cadence diagnostic, using decd-client's two-buffer stream mode:
#
#   ARMED=yes CLIENT=/root/decd-client.stream \
#     decd-visible-sequence.sh --stream \
#     /root/decd-red.nv12 /root/decd-green.nv12 5 30
#
# Zero-copy Cedrus dma-buf playback (150 frames is about five seconds for the
# 29.97-fps fixture):
#
#   ARMED=yes PLAYER=/root/decd-play \
#     decd-visible-sequence.sh --play /root/leota-720p.h264 150
#
# Real Cedrus playback is also supported with the display MIPS deliberately
# parked, because the Linux DECD IRQ handler owns the four-slot Y/C address
# ring.  This avoids the observed live-MIPS + Cedrus/DECD hard lock and needs a
# separate opt-in:
#
#   ARMED=yes ALLOW_STOPPED_MIPS=yes PLAYER=/root/decd-play \
#     decd-visible-sequence.sh --play /root/leota-720p.h264 60
#
# DWELL_MS controls how long each submitted frame remains before the next one;
# default 800.  Do not invoke DECD PM-off or unload sunxi_decd afterwards: both
# can reset or clock-gate display hardware shared with the adopted logo path.

set -eu

CLIENT=${CLIENT:-/root/decd-client.coord1080}
PLAYER=${PLAYER:-/root/decd-play}
DWELL_MS=${DWELL_MS:-800}
TIMEOUT_S=$((DWELL_MS / 1000 + 3))
DEVMEM="busybox devmem"

fail()
{
	echo "REFUSING: $*" >&2
	exit 1
}

[ "${ARMED:-}" = yes ] || fail "set ARMED=yes after the observer is watching"
[ "$#" -gt 0 ] || fail "usage: decd-visible-sequence.sh FRAME.nv12 [...] | --stream A B SEC FPS | --play FILE.h264 [MAX_FRAMES]"

MODE=sequence
STREAM_A=""
STREAM_B=""
STREAM_SECONDS=""
STREAM_FPS=""
PLAY_FILE=""
PLAY_MAX_FRAMES=0
if [ "$1" = --stream ]; then
	[ "$#" -eq 5 ] || fail "--stream requires: FRAME-A FRAME-B SECONDS FPS"
	MODE=stream
	STREAM_A=$2
	STREAM_B=$3
	STREAM_SECONDS=$4
	STREAM_FPS=$5
	shift 5
	set -- "$STREAM_A" "$STREAM_B"
elif [ "$1" = --play ]; then
	[ "$#" -eq 2 ] || [ "$#" -eq 3 ] || fail "--play requires: FILE.h264 [MAX_FRAMES]"
	MODE=play
	PLAY_FILE=$2
	[ "$#" -eq 2 ] || PLAY_MAX_FRAMES=$3
	shift "$#"
	set -- "$PLAY_FILE"
fi

if [ "$MODE" = play ]; then
	[ -x "$PLAYER" ] || fail "player is not executable: $PLAYER"
else
	[ -x "$CLIENT" ] || fail "client is not executable: $CLIENT"
fi
[ -c /dev/decd ] || fail "/dev/decd is absent"
[ -c /dev/scanout-dmabuf ] || fail "/dev/scanout-dmabuf is absent"

for frame in "$@"; do
	[ -f "$frame" ] || fail "frame does not exist: $frame"
done

rd()
{
	$DEVMEM "$1" 32
}

wr()
{
	addr=$1
	value=$2
	$DEVMEM "$addr" 32 "$value" >/dev/null || return 1
	readback=$(rd "$addr")
	case "$readback" in
	"$value"|"0x${value#0x}"|"0x${value#0X}") ;;
	*)	echo "write verification failed: $addr <- $value, read $readback" >&2
		return 1 ;;
	esac
}

# Write a self-clearing commit latch.  Readback verification is invalid here:
# the hardware consumes the bit, so reading back 0 is success, not failure --
# and it is the caller's explicit "was it consumed?" check that verifies it.
# The restore path always tolerated this with `|| true`; the apply path did not,
# and aborted the run the moment DECD started consuming the latch promptly.
wr_latch()
{
	$DEVMEM "$1" 32 "$2" >/dev/null || return 1
}

# Sum only the per-CPU count columns.  The line is
#   330:   0  0  0  0   GICv2  142  Level  decd
# and the old version summed every numeric field, which swept up the GIC hwirq
# number 142 as if it were a count -- so a freshly booted board reported
# "DECD IRQ: 142" with nothing having happened.  The delta was still right, but
# the absolute numbers were not, and "did this boot start clean?" is exactly
# what you want this for.  Counts stop at the first non-numeric field.
# Wait for DECD to arm its Y ring, i.e. for a real frame address to exist.
#
# Enabling the video source before that puts GARBAGE ON THE PANEL: the source
# rests at base 0 with an inherited 1920x1088 / stride-1920 geometry, so until a
# frame programs it, it scans the bottom of physical memory.  Under bypass that
# is merely ugly; under IOMMU translation the identical scan is an L1-invalid
# fault that wedges AFBD for the boot.  Either way, never enable this source
# speculatively.
#
# Any of the four ring slots counts -- waiting on slot 0 alone is a guess about
# which slot the first frame lands in.
wait_ring()
{
	i=0
	while [ "$i" -lt 400 ]; do
		for a in 0x05600070 0x05600074 0x05600078 0x0560007c; do
			[ "$(rd $a)" = 0x00000000 ] || return 0
		done
		i=$((i + 1))
		sleep 0.05
	done
	return 1
}

irq_count()
{
	awk '$NF=="decd" {s=0; for(i=2;i<=NF;i++) {if ($i !~ /^[0-9]+$/) break; s+=$i}
	                  print s; found=1}
	     END {if (!found) print "NONE"}' /proc/interrupts
}

MIPS=$(rd 0x0306101c)
if [ "$MIPS" != 0x00000001 ]; then
	[ "$MODE" = play ] && [ "${ALLOW_STOPPED_MIPS:-}" = yes ] &&
		[ "$MIPS" = 0x00000000 ] ||
		fail "MIPS status is $MIPS; stopped-MIPS --play requires ALLOW_STOPPED_MIPS=yes"
	echo "display MIPS deliberately stopped; Linux DECD IRQ owns playback ring"
fi

DT=/proc/device-tree/soc
DISP_ST=$(tr -d '\0' < "$DT/display@5600000/status" 2>/dev/null || true)
DEC_ST=$(tr -d '\0' < "$DT/dec@5600000/status" 2>/dev/null || true)
[ "$DISP_ST" = disabled ] || fail "display@5600000 is '$DISP_ST', expected disabled"
[ "$DEC_ST" = okay ] || fail "dec@5600000 is '$DEC_ST', expected okay"

# Snapshot the complete set this diagnostic owns.  Use the actual inherited
# values rather than assuming the known logo state so an error cannot restore
# stale constants from another boot.
SAVE_051C006C=$(rd 0x051c006c)
SAVE_05140508=$(rd 0x05140508)
SAVE_05600010=$(rd 0x05600010)
SAVE_05600020=$(rd 0x05600020)
SAVE_05600024=$(rd 0x05600024)
SAVE_05600040=$(rd 0x05600040)
SAVE_05600044=$(rd 0x05600044)

CLIENT_PID=""
RESTORED=0

restore()
{
	[ "$RESTORED" = 0 ] || return
	RESTORED=1
	echo "restoring inherited display path"
	[ -z "$CLIENT_PID" ] || kill "$CLIENT_PID" 2>/dev/null || true
	# Remove the visible route before changing its source layout.
	wr 0x051c006c "$SAVE_051C006C" || true
	wr 0x05600010 "$SAVE_05600010" || true
	wr 0x05600020 "$SAVE_05600020" || true
	wr 0x05600024 "$SAVE_05600024" || true
	wr 0x05600040 "$SAVE_05600040" || true
	wr 0x05600044 "$SAVE_05600044" || true
	wr_latch 0x05600014 0x00000001 || true
	wr 0x05140508 "$SAVE_05140508" || true
	sleep 0.1
	echo "restore state: ctrl=$(rd 0x05600010) ready=$(rd 0x05600014)" \
	     "gain=$(rd 0x05140508) selector=$(rd 0x051c006c)"
}

trap 'restore' EXIT
trap 'restore; exit 130' INT TERM

apply_visible_route()
{
	# Exact state that produced the photographed correct 1280x720 colour frame.
	wr 0x05600020 0x02CF04FF
	wr 0x05600024 0x002C004F
	wr 0x05600040 0x00000500
	wr 0x05600044 0x00000500
	wr 0x05140508 0x144C0000
	wr 0x05600010 0x03000013
	wr_latch 0x05600014 0x00000001
	sleep 0.05
	READY=$(rd 0x05600014)
	[ "$READY" = 0x00000000 ] || {
		echo "source commit was not consumed: $READY" >&2
		return 1
	}
	wr 0x051c006c 0x39000000
}

IRQ_BEFORE=$(irq_count)
if [ "$MODE" = stream ]; then
	echo "WATCH THE PANEL: ${STREAM_SECONDS}s at ${STREAM_FPS} fps, then logo restore"
	"$CLIENT" stream "$STREAM_A" "$STREAM_B" \
		"$STREAM_SECONDS" "$STREAM_FPS" &
	CLIENT_PID=$!
	# The 30-fps preflight proved the firmware changes only the queued Y/C
	# addresses during streaming.  Geometry and source enable stay unchanged, so
	# one route application after the first submit is sufficient.
	sleep 0.2
	apply_visible_route
	wait "$CLIENT_PID"
	CLIENT_PID=""
elif [ "$MODE" = play ]; then
	echo "WATCH THE PANEL: decoded $PLAY_FILE, max $PLAY_MAX_FRAMES frames, then logo restore"
	# Same shape as the stream branch, and this exact ordering is what the
	# hardware-proven 2026-09-01 runs used.
	#
	# DEAD END, recorded so it is not re-derived: this was briefly reordered to
	# apply the route *before* starting the player, on the theory that a fast
	# first submit could race the route rewrite -- patch 0075 flips IOMMU master
	# 2 from bypass to translation inside that submit, and a master-2 fault
	# wedges AFBD for the boot.  The reordered version faulted identically, so
	# there is no race.  The real precondition is that the bypass->translation
	# flip must happen while the video source is still DISABLED, which is a
	# property of which *session* spends the flip, not of ordering inside this
	# script.  Spend it with a nonvisible player run first; see
	# docs/reference/iommu-runtime-flip-ordering-2026-09-01.md.
	"$PLAYER" "$PLAY_FILE" "$PLAY_MAX_FRAMES" &
	CLIENT_PID=$!
	# Was a fixed 200 ms, which enabled the source long before the first frame
	# and showed a burst of garbage -- for a --freeze-at run, nearly two
	# seconds of it.  Wait for a real frame address instead.
	if wait_ring; then
		apply_visible_route
	else
		echo "DECD never armed its Y ring; leaving the logo route alone" >&2
	fi
	wait "$CLIENT_PID"
	CLIENT_PID=""
else
	echo "WATCH THE PANEL: $# frame(s), ${DWELL_MS} ms each, then logo restore"
	for frame in "$@"; do
		echo "submitting $frame"
		env DECD_FMT=0 timeout "${TIMEOUT_S}s" "$CLIENT" show "$frame" "$DWELL_MS" &
		CLIENT_PID=$!
		# FRAME_SUBMIT returns before the firmware worker has settled.  The
		# measured 150 ms delay keeps our route write after the submit without
		# wasting most of the observation dwell.
		sleep 0.15
		apply_visible_route
		wait "$CLIENT_PID"
		CLIENT_PID=""
	done
fi

IRQ_AFTER=$(irq_count)
echo "DECD IRQ: $IRQ_BEFORE -> $IRQ_AFTER"
restore
trap - EXIT INT TERM
exit 0
