#!/bin/sh
# decd-enable-test.sh -- does enabling AFBD source 0 route DECD to the panel?
#
# TARGET-SIDE. Run on the board, on the patch-0068 boot (DECD exclusive owner,
# KMS absent, shared display reset withheld). Serial console only.
#
# THE QUESTION
#
# ge2d_dev.ko's own writeback accessors (__afbd_is_ch_en, __afbd_get_pixel_fmt,
# __afbd_get_pic_size) treat the 0x05600000 window as THREE sources:
#
#   id 0  0x05600010  enable = bits 1:0   fmt 15:8   size 0x05600030
#   id 1  0x05600100  enable = bit 0      fmt 15:8   size 0x05600134
#   id 2  0x05600140  enable = bit 0      fmt 15:8   size 0x05600174
#
# Ids 1/2 are the RGB OSD channels. Id 0 is the video source, and it is exactly
# the register set DECD programs. On 2026-08-26 a live read found source 0
# provisioned (1280x720 at 0x030, uncompressed bit 4 set) with DECD's own enable
# and mux already set by U-Boot -- and its enable bits 1:0 CLEAR. Neither stock
# decd.ko nor ge2d_dev.ko writes them, and neither does our port.
#
# WHY THE SEQUENCE MATTERS
#
# The 2026-08-25 mixer layer-0 test was run with DECD idle, so it had nothing to
# composite and could not have shown anything either way. This script refuses to
# touch the enable until it has PROVEN frames are flowing, so a null here means
# something. That check is the point of the script; do not skip it.
#
# WHAT IT WRITES
#
# Only 0x05600010, only bits 1:0, read-modify-write, restored on every exit
# path including Ctrl-C. That register is NOT the one the panel is scanning
# from (that is 0x05600140), which is what makes this materially safer than the
# mixer probe. --hide-osd additionally clears 0x05600140 bit 0 and is opt-in:
# it blanks the panel until restored.
#
# Usage:
#   decd-enable-test.sh FRAME.nv12 [--dwell SEC] [--hide-osd]

set -u

FRAME=""
DWELL=15
HIDE_OSD=0
CLIENT=${CLIENT:-./decd-client}

while [ $# -gt 0 ]; do
	case "$1" in
	--dwell)    DWELL="$2"; shift 2 ;;
	--hide-osd) HIDE_OSD=1; shift ;;
	-h|--help)  sed -n '2,36p' "$0"; exit 0 ;;
	*)          FRAME="$1"; shift ;;
	esac
done

[ -n "$FRAME" ] || { echo "usage: $0 FRAME.nv12 [--dwell SEC] [--hide-osd]" >&2; exit 2; }
[ -f "$FRAME" ] || { echo "no such frame: $FRAME" >&2; exit 2; }

DEVMEM="busybox devmem"

SRC0_CTRL=0x05600010
CH1_CTRL=0x05600140

# addr:label, dumped as a set so every observation is comparable
REGS="0x05600000:afbd_global \
0x05600010:src0_ctrl \
0x05600020:src0_wh \
0x05600024:src0_blk \
0x05600030:src0_picsize \
0x05600040:src0_stride0 \
0x05600044:src0_stride1 \
0x05600060:decd_enable \
0x05600068:decd_mux \
0x0560006c:decd_dirty \
0x05600070:decd_y \
0x05600084:decd_c \
0x05600100:ch0_ctrl \
0x05600140:ch1_ctrl \
0x05600144:ch1_ready \
0x05600170:ch1_stride \
0x05600178:ch1_src \
0x0525c004:mixer_en"

rd() { $DEVMEM "$1"; }
wr() { $DEVMEM "$1" 32 "$2"; }

dump() {
	echo "--- registers: $1 ---"
	for e in $REGS; do
		a=${e%%:*}; n=${e##*:}
		printf '  %-14s %s = %s\n' "$n" "$a" "$(rd "$a")"
	done
}

# --- preconditions -----------------------------------------------------------

echo "=== preconditions ==="
# NOT a /dev/dri check: panfrost registers a DRM node too, so card0 exists on
# the 0068 boot as well. The thing that actually matters is which driver owns
# 0x05600000 and SPI 110, and the device tree answers that directly.
DT=/proc/device-tree/soc
DISP_ST=$(tr -d '\0' < $DT/display@5600000/status 2>/dev/null)
DEC_ST=$(tr -d '\0' < $DT/dec@5600000/status 2>/dev/null)
if [ "$DISP_ST" != disabled ]; then
	echo "REFUSING: display@5600000 status='$DISP_ST', expected 'disabled'." >&2
	echo "This is not the 0068 boot. KMS and DECD cannot both own" >&2
	echo "0x05600000 and SPI 110. Boot h713-kernel-decd-test.fit." >&2
	exit 1
fi
[ "$DEC_ST" = okay ] || { echo "REFUSING: dec@5600000 status='$DEC_ST'" >&2; exit 1; }
echo "  DT: display@5600000=disabled, dec@5600000=okay"

# The FIT carries kernel+DTB only; modules come from the rootfs, where
# /lib/modules holds the PRODUCTION build. That one requires the reset property
# 0068 deletes, so it fails to probe with -ENOENT and leaves no /dev/decd.
# Fix: rmmod sunxi_decd; insmod /root/sunxi-decd-test.ko
if [ ! -c /dev/decd ]; then
	echo "no /dev/decd." >&2
	if lsmod | grep -q '^sunxi_decd'; then
		echo "sunxi_decd IS loaded but did not probe -- almost certainly the" >&2
		echo "production module from /lib/modules. Swap it:" >&2
		echo "  rmmod sunxi_decd && insmod /root/sunxi-decd-test.ko" >&2
	fi
	exit 1
fi
[ -c /dev/scanout-dmabuf ] || { echo "no /dev/scanout-dmabuf" >&2; exit 1; }
[ -x "$CLIENT" ] || { echo "no decd-client at $CLIENT (set CLIENT=)" >&2; exit 1; }
echo "  /dev/decd, /dev/scanout-dmabuf, $CLIENT present; no KMS device. OK"

ORIG_SRC0=$(rd $SRC0_CTRL)
ORIG_CH1=$(rd $CH1_CTRL)
echo "  saved src0_ctrl=$ORIG_SRC0  ch1_ctrl=$ORIG_CH1"

CLIENT_PID=""
restore() {
	echo
	echo "=== restore ==="
	[ -n "$CLIENT_PID" ] && kill "$CLIENT_PID" 2>/dev/null
	wr $SRC0_CTRL "$ORIG_SRC0"
	[ "$HIDE_OSD" = 1 ] && wr $CH1_CTRL "$ORIG_CH1"
	echo "  src0_ctrl restored to $(rd $SRC0_CTRL) (was $ORIG_SRC0)"
	echo "  ch1_ctrl  now         $(rd $CH1_CTRL) (was $ORIG_CH1)"
	dump "after restore"
	echo
	echo "Reboot before drawing conclusions from any later run."
}
trap 'restore; exit 130' INT TERM

dump "baseline, before any frame"

# --- start the frame flow ----------------------------------------------------

echo
echo "=== submitting frames ==="
# repeat=1 makes the hardware re-fetch this frame every vsync for the dwell,
# so the register state below is a steady state, not a one-shot.
"$CLIENT" show "$FRAME" $(( (DWELL * 5 + 30) * 1000 )) &
CLIENT_PID=$!
sleep 3

# --- PROVE frames are flowing before touching anything -----------------------

echo
echo "=== proving the queue is live (this gates the rest) ==="
# The driver registers its IRQ as DECD_NAME = "decd", which is the last field
# of the /proc/interrupts line. Sum only the per-CPU count columns.
irq_count() {
	awk '$NF=="decd" {s=0; for(i=2;i<=NF;i++) if ($i ~ /^[0-9]+$/) s+=$i; print s; found=1}
	     END {if (!found) print "NONE"}' /proc/interrupts
}
IRQ_A=$(irq_count)
sleep 2
IRQ_B=$(irq_count)
Y=$(rd 0x05600070); C=$(rd 0x05600084)

if [ "$IRQ_A" = NONE ] || [ "$IRQ_B" = NONE ]; then
	echo "  DECD irq: no line named 'decd' in /proc/interrupts" >&2
	echo
	echo "STOP: the driver's IRQ is not registered, so the queue cannot be" >&2
	echo "running. Check that sunxi-decd.ko bound to dec@5600000." >&2
	restore
	exit 1
fi

# The hwirq number (110) also matches ^[0-9]+$ and is summed, but it is the same
# constant in both samples, so it cancels in the delta.
RATE=$(( (IRQ_B - IRQ_A) / 2 ))
echo "  DECD irq: $IRQ_A -> $IRQ_B over 2 s  (~${RATE}/s, expect ~60)"
echo "  queued Y=$Y  C=$C"

LIVE=1
[ "$RATE" -lt 30 ] && LIVE=0
case "$Y" in 0x00000000|0) LIVE=0 ;; esac
if [ "$LIVE" = 0 ]; then
	echo
	echo "STOP: frames are NOT flowing (irq ~${RATE}/s, Y=$Y)." >&2
	echo "Enabling source 0 now would repeat the 2026-08-25 mixer mistake:" >&2
	echo "a null with nothing to composite proves nothing. Fix the queue first." >&2
	restore
	exit 1
fi
echo "  queue is live. Proceeding."

# geometry: DECD should have rewritten source 0 for THIS frame (1280x720).
WH=$(rd 0x05600020)
echo "  src0_wh=$WH (expect 0x02CF04FF for 1280x720; 0x043F077F means DECD did"
echo "     not reconfigure and the source still carries stock's 1920x1088)"

if [ "$HIDE_OSD" = 1 ]; then
	echo
	echo "=== hiding the OSD channel (--hide-osd) ==="
	NEW_CH1=$(printf '0x%08x' $(( ORIG_CH1 & ~1 )))
	wr $CH1_CTRL "$NEW_CH1"
	echo "  ch1_ctrl $ORIG_CH1 -> $(rd $CH1_CTRL); panel should go black now"
	sleep 3
fi

# --- the sweep ---------------------------------------------------------------

echo
echo "=== sweeping source 0 enable, bits 1:0 of $SRC0_CTRL ==="
echo "WATCH THE PANEL. Each step holds ${DWELL}s."
BASE=$(( ORIG_SRC0 & ~3 ))
for V in 1 2 3; do
	NEW=$(printf '0x%08x' $(( BASE | V )))
	echo
	echo "--- enable = $V   ($SRC0_CTRL <- $NEW) ---"
	wr $SRC0_CTRL "$NEW"
	RB=$(rd $SRC0_CTRL)
	echo "  readback $RB $([ "$RB" = "$NEW" ] && echo '(took)' || echo '(DID NOT TAKE)')"
	sleep "$DWELL"
	dump "enable=$V, after ${DWELL}s"
done

restore
echo
echo "=== what to report ==="
echo "For each enable value: did the panel change at all, and if so, to what?"
echo "A readback that does not take is itself the result -- it would mean the"
echo "bits are gated, not merely unset."
