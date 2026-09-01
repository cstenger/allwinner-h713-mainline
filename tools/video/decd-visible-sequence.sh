#!/bin/sh
# decd-visible-sequence.sh -- show one or more NV12 frames through the proven
# H713 DECD route, then restore the inherited logo path.
#
# TARGET-SIDE, ROOT, DIAGNOSTIC ONLY.  This is for the patch-0068 DECD-exclusive
# boot with the MIPS display firmware alive.  It deliberately writes shared
# display MMIO and refuses to run unless the DT proves KMS is disabled and DECD
# is the owner.  The script snapshots every value it changes and restores them
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
# DWELL_MS controls how long each submitted frame remains before the next one;
# default 800.  Do not invoke DECD PM-off or unload sunxi_decd afterwards: both
# can reset or clock-gate display hardware shared with the adopted logo path.

set -eu

CLIENT=${CLIENT:-/root/decd-client.coord1080}
DWELL_MS=${DWELL_MS:-800}
TIMEOUT_S=$((DWELL_MS / 1000 + 3))
DEVMEM="busybox devmem"

fail()
{
	echo "REFUSING: $*" >&2
	exit 1
}

[ "${ARMED:-}" = yes ] || fail "set ARMED=yes after the observer is watching"
[ "$#" -gt 0 ] || fail "usage: decd-visible-sequence.sh FRAME.nv12 [...]"
[ -x "$CLIENT" ] || fail "client is not executable: $CLIENT"
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

irq_count()
{
	awk '$NF=="decd" {s=0; for(i=2;i<=NF;i++) if ($i ~ /^[0-9]+$/) s+=$i; print s; found=1}
	     END {if (!found) print "NONE"}' /proc/interrupts
}

MIPS=$(rd 0x0306101c)
[ "$MIPS" = 0x00000001 ] || fail "MIPS status is $MIPS, expected 0x00000001"

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
	wr 0x05600014 0x00000001 || true
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
	wr 0x05600014 0x00000001
	sleep 0.05
	READY=$(rd 0x05600014)
	[ "$READY" = 0x00000000 ] || {
		echo "source commit was not consumed: $READY" >&2
		return 1
	}
	wr 0x051c006c 0x39000000
}

IRQ_BEFORE=$(irq_count)
echo "WATCH THE PANEL: $# frame(s), ${DWELL_MS} ms each, then logo restore"

for frame in "$@"; do
	echo "submitting $frame"
	env DECD_FMT=0 timeout "${TIMEOUT_S}s" "$CLIENT" show "$frame" "$DWELL_MS" &
	CLIENT_PID=$!
	# FRAME_SUBMIT returns before the firmware worker has settled.  The measured
	# 150 ms delay keeps our route write after the submit without wasting most of
	# the observation dwell.
	sleep 0.15
	apply_visible_route
	wait "$CLIENT_PID"
	CLIENT_PID=""
done

IRQ_AFTER=$(irq_count)
echo "DECD IRQ: $IRQ_BEFORE -> $IRQ_AFTER"
restore
trap - EXIT INT TERM
exit 0
