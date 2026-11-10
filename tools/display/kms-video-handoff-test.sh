#!/bin/sh
# Test an explicit fullscreen handoff from the KMS RGB channel to AFBD source 0.
#
# The earlier kms-video-plane-test.sh left the KMS RGB channel fetching while
# source 0 was selected.  The selector visibly displaced the console, but the
# verified NV12 frame rendered as garbage.  This test answers the next, narrower
# question: does the same source render correctly when the RGB channel is first
# disabled and committed?
#
# The transition is deliberately exclusive in both directions:
#
#   RGB on, video off -> RGB off -> video on -> select video
#   select video      -> video off -> RGB on  -> select RGB
#
# Every register written here is saved and restored on normal exit, error,
# SIGINT, or SIGTERM.  The test is specific to the known 0077 KMS experiment
# state and refuses to run if that state has drifted.
#
# The first hardware run used the default one-slot mode and remained garbage.
# RING_ALL=yes adds the state the comparison then proved was missing: all four
# Y/C slots plus the dirty latch, matching a successful DECD-managed static
# submission. Keeping the switch explicit preserves the first run as a
# reproducible negative control.
#
# Usage: ARMED=yes [RING_ALL=yes] kms-video-handoff-test.sh [DWELL_SECONDS]

set -eu

DEVMEM="busybox devmem"
DWELL=${1:-10}
FRAME=${FRAME:-/root/kmstest/f60.nv12}
VIDEO_INFO=${VIDEO_INFO:-/root/kmstest/f60.videoinfo}
MEM_WRITE=${MEM_WRITE:-/root/kmstest/mem-write}
RING_ALL=${RING_ALL:-no}

Y_PHYS=0x6C500000
C_PHYS=0x6C5E1000
INFO_PHYS=0x4D941000
FRAME_SIZE=1382400
FRAME_SHA256=70bddcf8d5c05caf4c6abd0d29399b7467f47caea470c80f7d3998831379cfec
INFO_SIZE=4096
INFO_SHA256=3c225757336feee622d2c25c2d3e320a6282f16b99381f7601bc7377be0fff6b

fail()
{
	echo "REFUSING: $*" >&2
	exit 1
}

[ "${ARMED:-}" = yes ] || fail "set ARMED=yes only after the observer is watching"
case "$RING_ALL" in
yes|no) ;;
*) fail "RING_ALL must be 'yes' or 'no', not '$RING_ALL'" ;;
esac

rd()
{
	$DEVMEM "$1" 32
}

wr()
{
	$DEVMEM "$1" 32 "$2" >/dev/null || return 1
	readback=$(rd "$1")
	case "$readback" in
	"$2"|"0x${2#0x}") ;;
	*)	echo "write verification failed: $1 <- $2, read $readback" >&2
		return 1 ;;
	esac
}

# READY is a self-clearing commit latch, so a readback of zero is success.
wr_latch()
{
	$DEVMEM "$1" 32 0x00000001 >/dev/null
}

require_consumed()
{
	addr=$1
	label=$2
	sleep 0.05
	ready=$(rd "$addr")
	[ "$ready" = 0x00000000 ] || fail "$label commit was not consumed: $ready"
}

DT=/proc/device-tree/soc
DISP_ST=$(tr -d '\0' < "$DT/display@5600000/status" 2>/dev/null || echo missing)
DEC_ST=$(tr -d '\0' < "$DT/dec@5600000/status" 2>/dev/null || echo missing)
[ "$DISP_ST" = okay ] || fail "display@5600000 is '$DISP_ST', expected okay"
[ "$DEC_ST" = disabled ] || fail "dec@5600000 is '$DEC_ST', expected disabled"
[ -e /dev/dri/card0 ] || fail "no DRM device; did the AFBD KMS driver bind?"
[ -x "$MEM_WRITE" ] || fail "missing executable mmap writer: $MEM_WRITE"
[ -f "$FRAME" ] || fail "missing staged NV12 frame: $FRAME"

frame_size=$(wc -c < "$FRAME" | tr -d ' ')
[ "$frame_size" = "$FRAME_SIZE" ] ||
	fail "$FRAME is $frame_size bytes, expected $FRAME_SIZE"
frame_hash=$(sha256sum "$FRAME" | awk '{print $1}')
[ "$frame_hash" = "$FRAME_SHA256" ] ||
	fail "$FRAME hash is $frame_hash, expected $FRAME_SHA256"
if [ "$RING_ALL" = yes ]; then
	[ -f "$VIDEO_INFO" ] || fail "missing staged VideoInfo page: $VIDEO_INFO"
	info_size=$(wc -c < "$VIDEO_INFO" | tr -d ' ')
	[ "$info_size" = "$INFO_SIZE" ] ||
		fail "$VIDEO_INFO is $info_size bytes, expected $INFO_SIZE"
	info_hash=$(sha256sum "$VIDEO_INFO" | awk '{print $1}')
	[ "$info_hash" = "$INFO_SHA256" ] ||
		fail "$VIDEO_INFO hash is $info_hash, expected $INFO_SHA256"
fi

SAVE_051C006C=$(rd 0x051c006c)
SAVE_05140508=$(rd 0x05140508)
SAVE_05600010=$(rd 0x05600010)
SAVE_05600014=$(rd 0x05600014)
SAVE_05600020=$(rd 0x05600020)
SAVE_05600024=$(rd 0x05600024)
SAVE_05600040=$(rd 0x05600040)
SAVE_05600044=$(rd 0x05600044)
SAVE_05600070=$(rd 0x05600070)
SAVE_05600084=$(rd 0x05600084)
if [ "$RING_ALL" = yes ]; then
	SAVE_05600060=$(rd 0x05600060)
	SAVE_05600064=$(rd 0x05600064)
	SAVE_05600068=$(rd 0x05600068)
	SAVE_0560006C=$(rd 0x0560006c)
	SAVE_05600074=$(rd 0x05600074)
	SAVE_05600078=$(rd 0x05600078)
	SAVE_0560007C=$(rd 0x0560007c)
	SAVE_05600080=$(rd 0x05600080)
	SAVE_05600088=$(rd 0x05600088)
	SAVE_0560008C=$(rd 0x0560008c)
	SAVE_05600090=$(rd 0x05600090)
	SAVE_05600094=$(rd 0x05600094)
	SAVE_05600098=$(rd 0x05600098)
	SAVE_0560009C=$(rd 0x0560009c)
	SAVE_056000A0=$(rd 0x056000a0)
	SAVE_056000A4=$(rd 0x056000a4)
	SAVE_056000A8=$(rd 0x056000a8)
fi
SAVE_05600140=$(rd 0x05600140)
SAVE_05600144=$(rd 0x05600144)
SAVE_05600178=$(rd 0x05600178)

# These exact values were read after the negative coexistence test restored.
# Failing closed avoids racing an outstanding KMS or source-0 commit, or
# applying the known channel-disable encoding to an unknown configuration.
[ "$SAVE_051C006C" = 0x29000000 ] ||
	fail "selector is $SAVE_051C006C, expected the KMS route 0x29000000"
[ "$SAVE_05600010" = 0x03000010 ] ||
	fail "video control is $SAVE_05600010, expected disabled 0x03000010"
[ "$SAVE_05600014" = 0x00000000 ] ||
	fail "video commit is already pending: $SAVE_05600014"
[ "$SAVE_05600140" = 0x03001901 ] ||
	fail "KMS control is $SAVE_05600140, expected active 0x03001901"
[ "$SAVE_05600144" = 0x00000000 ] ||
	fail "KMS commit is already pending: $SAVE_05600144"
if [ "$RING_ALL" = yes ]; then
	[ "$SAVE_05600060" = 0x00000001 ] ||
		fail "DECD gate is $SAVE_05600060, expected enabled 0x00000001"
	[ "$SAVE_05600064" = 0x00000000 ] ||
		fail "field/repeat state is $SAVE_05600064, expected zero"
	[ "$SAVE_05600068" = 0x00000122 ] ||
		fail "ring mux is $SAVE_05600068, expected 0x00000122"
	for empty in "$SAVE_0560006C" "$SAVE_05600070" "$SAVE_05600074" \
		"$SAVE_05600078" "$SAVE_0560007C" "$SAVE_05600080" \
		"$SAVE_05600084" "$SAVE_05600088" "$SAVE_0560008C" \
		"$SAVE_05600090" "$SAVE_05600094" "$SAVE_05600098" \
		"$SAVE_0560009C" "$SAVE_056000A0" "$SAVE_056000A4" \
		"$SAVE_056000A8"; do
		[ "$empty" = 0x00000000 ] ||
			fail "source ring is not in the expected all-zero idle state"
	done
fi

RESTORED=0
restore()
{
	[ "$RESTORED" = 0 ] || return
	RESTORED=1
	echo "restoring exclusive KMS scanout"

	# Stop source 0 while its valid bases are still installed, then return its
	# descriptor to the exact state found before the test.
	wr 0x05600010 "$SAVE_05600010" || true
	wr_latch 0x05600014 || true
	sleep 0.05
	wr 0x05600020 "$SAVE_05600020" || true
	wr 0x05600024 "$SAVE_05600024" || true
	wr 0x05600040 "$SAVE_05600040" || true
	wr 0x05600044 "$SAVE_05600044" || true
	wr 0x05600070 "$SAVE_05600070" || true
	wr 0x05600084 "$SAVE_05600084" || true
	if [ "$RING_ALL" = yes ]; then
		wr 0x05600074 "$SAVE_05600074" || true
		wr 0x05600078 "$SAVE_05600078" || true
		wr 0x0560007c "$SAVE_0560007C" || true
		wr 0x05600080 "$SAVE_05600080" || true
		wr 0x05600088 "$SAVE_05600088" || true
		wr 0x0560008c "$SAVE_0560008C" || true
		wr 0x05600090 "$SAVE_05600090" || true
		wr 0x05600094 "$SAVE_05600094" || true
		wr 0x05600098 "$SAVE_05600098" || true
		wr 0x0560009c "$SAVE_0560009C" || true
		wr 0x056000a0 "$SAVE_056000A0" || true
		wr 0x056000a4 "$SAVE_056000A4" || true
		wr 0x056000a8 "$SAVE_056000A8" || true
		wr 0x0560006c "$SAVE_0560006C" || true
	fi
	wr 0x05140508 "$SAVE_05140508" || true

	# Re-enable and commit RGB before routing the panel back to it.  Source 0
	# is already disabled, so the two fetch paths are never active together.
	wr 0x05600140 "$SAVE_05600140" || true
	wr_latch 0x05600144 || true
	sleep 0.05
	wr 0x051c006c "$SAVE_051C006C" || true
	sleep 0.05

	echo "restore state: video_ctrl=$(rd 0x05600010) video_ready=$(rd 0x05600014)" \
	     "kms_ctrl=$(rd 0x05600140) kms_ready=$(rd 0x05600144)" \
	     "kms_src=$(rd 0x05600178) selector=$(rd 0x051c006c)"
}

trap 'restore' EXIT
trap 'restore; exit 130' INT TERM

echo "pre-test: video_ctrl=$SAVE_05600010 video_ready=$SAVE_05600014" \
	"kms_ctrl=$SAVE_05600140 kms_ready=$SAVE_05600144" \
	"kms_src=$SAVE_05600178 selector=$SAVE_051C006C ring_all=$RING_ALL"

# Re-stage the byte-verified frame without touching any live scanout buffer.
"$MEM_WRITE" "$FRAME" "$Y_PHYS"
if [ "$RING_ALL" = yes ]; then
	# This is the final reserved-page form produced by DECD after it copies the
	# userspace payload and patches the two embedded physical pointers.
	"$MEM_WRITE" "$VIDEO_INFO" "$INFO_PHYS"
fi

echo "WATCH THE PANEL: exclusive video handoff for ${DWELL}s, then KMS returns"

# 0x83001900 is the hardware-validated disabled encoding for serviced OSD
# channel 1.  Its READY latch was previously observed to clear immediately.
wr 0x05600140 0x83001900
wr_latch 0x05600144
require_consumed 0x05600144 "KMS disable"

# Exact source-0 recipe that rendered frame 60 correctly in the DECD-owned
# environment, now with no concurrent RGB fetch.
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
wr 0x05600070 "$Y_PHYS"
wr 0x05600084 "$C_PHYS"
if [ "$RING_ALL" = yes ]; then
	# The frame manager fills one ring slot per service and marks the ring dirty
	# after slot 3. A repeated static frame therefore has the same Y/C and
	# VideoInfo addresses in every slot. Aux and field bytes are zero for this
	# linear frame.
	wr 0x05600074 "$Y_PHYS"
	wr 0x05600078 "$Y_PHYS"
	wr 0x0560007c "$Y_PHYS"
	wr 0x05600080 0x00000000
	wr 0x05600088 "$C_PHYS"
	wr 0x0560008c "$C_PHYS"
	wr 0x05600090 "$C_PHYS"
	wr 0x05600094 0x00000000
	wr 0x05600098 "$INFO_PHYS"
	wr 0x0560009c "$INFO_PHYS"
	wr 0x056000a0 "$INFO_PHYS"
	wr 0x056000a4 "$INFO_PHYS"
	wr 0x056000a8 0x00000000
	wr 0x0560006c 0x00000001
fi
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000013
wr_latch 0x05600014
require_consumed 0x05600014 "video enable"
wr 0x051c006c 0x39000000

echo "during test: video_ctrl=$(rd 0x05600010) video_ready=$(rd 0x05600014)" \
	"kms_ctrl=$(rd 0x05600140) kms_ready=$(rd 0x05600144)" \
	"y_ring=$(rd 0x05600070)/$(rd 0x05600074)/$(rd 0x05600078)/$(rd 0x0560007c)" \
	"dirty=$(rd 0x0560006c) selector=$(rd 0x051c006c)"

sleep "$DWELL"

restore
trap - EXIT INT TERM
exit 0
