#!/bin/bash
# Does the VE come back after a decode timeout? RUNS ON THE TARGET.
#
# The stall comes from a MALFORMED STREAM, not from fault injection, and that
# is the second design of this test rather than the first. Patch 0058 tried to
# starve the VLD by programming four times the bit length; the engine decoded
# all 25 frames anyway (ve+25, with the injection message in dmesg proving the
# knob fired), so VE_DEC_H265_BITS_LEN is an upper bound and not a promise the
# hardware waits on. What DOES stall it reliably is real damage to the slice
# payload -- bad/b03-h-bitflip-payload.h265 fires the watchdog every time.
# Better test anyway: it is the failure a real file causes.
#
# THE EXPERIMENT IS AN A/B INSIDE ONE BOOT. Both arms run against the same
# hardware state, the same CMA layout and the same stream; the only difference
# is sunxi_cedrus.watchdog_full_reset, flipped through sysfs between them. That
# is the design that made patch 0040's result worth believing, and it is what
# lets the broken behaviour be shown on demand instead of quoted from a log.
#
# ORDER IS NOT ARBITRARY: the fixed arm runs FIRST. The broken arm is expected
# to leave the engine dead, and anything measured after that would be measuring
# the wedge rather than the arm.
#
# The third step is diagnostic rather than pass/fail: once wedged, does
# reloading the module bring the engine back? If it does, the stall lives in
# driver state; if it does not, it is in the hardware, and only a reset
# sequence can clear it. Either answer is worth having written down.

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
VECTOR=${VECTOR:-h01-640x480-main}
PARAM=/sys/module/sunxi_cedrus/parameters
STALLER=${STALLER:-$DIR/bad/b03-h-bitflip-payload.h265}

[ -r "$STALLER" ] || {
	echo "FATAL: no stalling stream at $STALLER (run make-bad-streams.sh)."
	exit 1
}
[ -w "$PARAM/watchdog_full_reset" ] || {
	echo "FATAL: no watchdog_full_reset knob. This needs patch 0057."
	exit 1
}

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}
wd_count() { dmesg | grep -c "frame processing timed out" || true; }
want_md5() { grep " $VECTOR\$" "$DIR/hevc-reference-md5.txt" | cut -d' ' -f1; }

decode() {
	LIBVA_DRIVER_NAME=v4l2_request timeout 30 \
		ffmpeg -hide_banner -v error -y \
		-hwaccel vaapi -hwaccel_output_format vaapi \
		-i "${1:-$DIR/$VECTOR.h265}" -vf 'hwdownload,format=nv12' \
		-f rawvideo -pix_fmt nv12 pipe:1 2>/dev/null | md5sum | cut -d' ' -f1
}

good_decode() { [ "$(decode)" = "$(want_md5)" ]; }

arm() {
	local label=$1 setting=$2 wd0 wd1 ve0

	echo "=== arm $label: watchdog_full_reset=$setting ==="
	echo "$setting" > "$PARAM/watchdog_full_reset"

	if ! good_decode; then
		echo "     SKIPPED — the engine is already not decoding before this arm"
		return 2
	fi
	echo "     pre-check: good vector bit-exact"

	wd0=$(wd_count); ve0=$(ve_irq)
	decode "$STALLER" >/dev/null
	wd1=$(wd_count)

	if [ "$wd1" -eq "$wd0" ]; then
		echo "     INCONCLUSIVE — no watchdog timeout fired (ve+$(( $(ve_irq) - ve0 )))."
		echo "     $(basename "$STALLER") did not stall the engine this time."
		return 3
	fi
	echo "     stalling stream -> watchdog fired ($wd0 -> $wd1), ve+$(( $(ve_irq) - ve0 ))"

	if good_decode; then
		echo "     RECOVERED — the very next decode is bit-exact"
		return 0
	fi
	echo "     WEDGED — the engine no longer decodes a known-good stream"
	return 1
}

echo "kernel $(uname -r), good vector $VECTOR, staller $(basename "$STALLER")"
echo

arm FIXED Y; fixed=$?
echo

arm BROKEN N; broken=$?
echo

if [ "$broken" -eq 1 ]; then
	echo "=== diagnostic: is the wedge in the driver or in the hardware? ==="
	if rmmod sunxi_cedrus 2>/dev/null && modprobe sunxi_cedrus 2>/dev/null; then
		sleep 2
		if good_decode; then
			echo "     a module reload restores decoding — the stall was driver state"
		else
			echo "     a module reload does NOT restore decoding — the engine itself"
			echo "     is stuck, and only a full reset sequence can clear it"
		fi
	else
		echo "     could not reload the module (in use?); skipped"
	fi
	echo
fi

echo "=== result ==="
case "$fixed:$broken" in
0:1) echo "W1: PASS — recovery works with the fix and fails without it, same boot"
     echo "     Restore the default before leaving: echo Y > $PARAM/watchdog_full_reset"
     exit 0 ;;
0:0) echo "W1: BOTH ARMS RECOVERED — the second reset line changes nothing observable"
     echo "     here. On this hardware the engine comes back from a decode timeout"
     echo "     with or without it, so patch 0057 fixes no symptom this test can see." ;;
*)   echo "W1: FAIL — the fixed arm did not recover (code $fixed); broken arm code $broken" ;;
esac
exit 1
