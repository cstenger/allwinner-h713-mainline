#!/bin/sh
# Light the AFBD video plane while the KMS driver owns the block.
#
# This is the question patch 0065 was really asking, with the state it was
# missing. 0065 programmed plane addresses and strides into a source it never
# enabled, never sized, never gave a chroma gain, and never routed -- so nothing
# appeared and the conclusion was drawn that these registers are not in the
# scanout path. They are; they belong to a *separate* video plane, and the
# 2026-08-31 work found the rest of the sequence.
#
# Everything proven so far about that plane was measured with U-Boot's adopted
# logo on the other channel. What is untested is whether it can be lit while the
# KMS driver owns the AFBD block -- whether its bind-time reset or its atomic
# commits stomp the plane. That is the load-bearing unknown for merging DECD's
# capability into sun50i-h713-afbd as a second DRM plane, so it is worth
# answering by register poke before writing any driver code.
#
# There is no DECD here, so nothing submits frames: the plane is pointed at a
# static NV12 image placed in the adopted scanout carveout beforehand, e.g.
#
#   dd if=frame60.nv12 of=/dev/mem bs=4096 seek=$((0x6c500000 / 4096)) \
#      conv=notrunc
#
# /dev/mem can reach that region because it is no-map; CONFIG_STRICT_DEVMEM
# blocks system RAM but not reserved carveouts.
#
# Usage:  ARMED=yes kms-video-plane-test.sh [DWELL_SECONDS]

set -eu

DEVMEM="busybox devmem"
DWELL=${1:-10}

# Y at 0x6c500000, C one full luma plane later. Same base DECD_CARVEOUT uses,
# clear of the 2.7 MB logo at 0x6c100000.
Y_PHYS=0x6C500000
C_PHYS=0x6C5E1000

fail()
{
	echo "REFUSING: $*" >&2
	exit 1
}

[ "${ARMED:-}" = yes ] || fail "set ARMED=yes after the observer is watching"

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

# Self-clearing commit latch: reading back 0 is success, so readback
# verification is invalid here. The caller checks consumption separately.
wr_latch()
{
	$DEVMEM "$1" 32 "$2" >/dev/null || return 1
}

# This is the inverse of the DECD wrapper's check, and it matters: the whole
# point is that KMS owns the block for this test.
DT=/proc/device-tree/soc
DISP_ST=$(tr -d '\0' < "$DT/display@5600000/status" 2>/dev/null || echo missing)
DEC_ST=$(tr -d '\0' < "$DT/dec@5600000/status" 2>/dev/null || echo missing)
[ "$DISP_ST" = okay ] || fail "display@5600000 is '$DISP_ST', expected okay"
[ "$DEC_ST" = disabled ] || fail "dec@5600000 is '$DEC_ST', expected disabled"

[ -e /dev/dri/card0 ] || fail "no DRM device; did the AFBD driver bind?"

SAVE_051C006C=$(rd 0x051c006c)
SAVE_05140508=$(rd 0x05140508)
SAVE_05600010=$(rd 0x05600010)
SAVE_05600020=$(rd 0x05600020)
SAVE_05600024=$(rd 0x05600024)
SAVE_05600040=$(rd 0x05600040)
SAVE_05600044=$(rd 0x05600044)
SAVE_05600070=$(rd 0x05600070)
SAVE_05600084=$(rd 0x05600084)

RESTORED=0
restore()
{
	[ "$RESTORED" = 0 ] || return
	RESTORED=1
	echo "restoring the KMS route"
	wr 0x051c006c "$SAVE_051C006C" || true
	wr 0x05600010 "$SAVE_05600010" || true
	wr 0x05600020 "$SAVE_05600020" || true
	wr 0x05600024 "$SAVE_05600024" || true
	wr 0x05600040 "$SAVE_05600040" || true
	wr 0x05600044 "$SAVE_05600044" || true
	wr 0x05600070 "$SAVE_05600070" || true
	wr 0x05600084 "$SAVE_05600084" || true
	wr_latch 0x05600014 0x00000001 || true
	wr 0x05140508 "$SAVE_05140508" || true
	sleep 0.1
	echo "restore state: ctrl=$(rd 0x05600010) ready=$(rd 0x05600014)" \
	     "gain=$(rd 0x05140508) selector=$(rd 0x051c006c)"
}

trap 'restore' EXIT
trap 'restore; exit 130' INT TERM

echo "pre-test: ctrl=$SAVE_05600010 geom=$SAVE_05600020/$SAVE_05600024" \
     "stride=$SAVE_05600040/$SAVE_05600044 ybase=$SAVE_05600070" \
     "gain=$SAVE_05140508 selector=$SAVE_051C006C"

echo "WATCH THE PANEL: video plane for ${DWELL}s, then the KMS route back"

# Exact state that produced the photographed correct 1280x720 colour frame,
# with the plane addresses pointed at the carveout instead of a decoder buffer.
wr 0x05600020 0x02CF04FF
wr 0x05600024 0x002C004F
wr 0x05600040 0x00000500
wr 0x05600044 0x00000500
wr 0x05600070 "$Y_PHYS"
wr 0x05600084 "$C_PHYS"
wr 0x05140508 0x144C0000
wr 0x05600010 0x03000013
wr_latch 0x05600014 0x00000001
sleep 0.05
READY=$(rd 0x05600014)
[ "$READY" = 0x00000000 ] || echo "NOTE: source commit not consumed: $READY" >&2
wr 0x051c006c 0x39000000

sleep "$DWELL"

echo "during test: ctrl=$(rd 0x05600010) ybase=$(rd 0x05600070)" \
     "selector=$(rd 0x051c006c)"
restore
trap - EXIT INT TERM
exit 0
