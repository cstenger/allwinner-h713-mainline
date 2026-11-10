#!/bin/bash
# Does the decoder survive bad input? RUNS ON THE TARGET.
#
# The bit-exactness gates score OUTPUT for good input. This one scores
# SURVIVAL for bad input, which is a different property and the one that
# decides whether this stack can face a real file:
#
#   1. it must not hang            -- bounded by `timeout`, a kill is a failure
#   2. it must not take the kernel down
#   3. THE VIDEO ENGINE MUST STILL WORK AFTERWARDS
#
# (3) is the whole point. A cedrus `frame processing timed out!` wedges the VE
# for every client on this board -- GStreamer included -- so one malformed file
# can end video for the rest of the boot. Wrong output from a corrupt stream is
# not a defect; refusing to decode it is not a defect; a decoder that is dead
# for the NEXT stream is.
#
# So every case is followed by a recovery check: decode a known-good vector and
# require it bit-exact. That check is the verdict. A case that fails cleanly and
# recovers is a PASS however ugly its own exit status.
#
# ffmpeg parses headers in software, so several cases never reach the hardware
# at all -- that is a legitimate outcome, not a skipped test, and `ve+N` in the
# output says which cases actually exercised the engine.
#
#   usage: ./decode-robustness-test.sh [bad-stream-dir]
#          (default ./bad, as produced by make-bad-streams.sh)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
DECODE_RC=0
BAD=${1:-$DIR/bad}
CASE_TIMEOUT=${CASE_TIMEOUT:-30}

GOOD_HEVC=h01-640x480-main
# The Main10 canary. A malformed 10-bit stream must leave the 10-bit path
# usable, and h01 cannot show that: it never programs the second plane or the
# 10BIT_CONFIGURE registers, so it would report "recovered" while the path the
# bad stream actually damaged went unchecked.
GOOD_HEVC10=h07-640x480-main10
GOOD_H264=v03-1280x720-main
# m01 rather than a field-coded vector: this is the recovery canary, run after
# every malformed case, so it wants to be the fastest clean decode available.
GOOD_MPEG2=m01-352x288-progressive

HEVC_REF=${HEVC_REF:-$DIR/hevc-reference-md5.txt}
H264_REF=${H264_REF:-$DIR/reference-md5.txt}
MPEG2_REF=${MPEG2_REF:-$DIR/mpeg2-reference-md5.txt}
# Main10's baseline is the hardware's own output; no software md5 can match the
# truncated 8-bit plane a client receives. See hevc10-reference-md5.txt.
HEVC10_REF=${HEVC10_REF:-$DIR/hevc10-reference-md5.txt}

[ -d "$BAD" ] || { echo "FATAL: no bad-stream directory at $BAD"; exit 1; }

# This one does not fail silently -- it fails LOUDLY AND WRONGLY, which is
# worse. recovery_ok() compares the good vector's md5 against an empty string,
# never matches, and the baseline check declares "FATAL -- the good vector does
# not decode. Reboot and re-run." on a perfectly healthy engine. The documented
# response to that message is a power cycle, so a missing file costs a reboot
# and an investigation into a wedge that never happened.
for f in "$HEVC_REF" "$H264_REF" "$MPEG2_REF" "$HEVC10_REF"; do
	[ -s "$f" ] && continue
	echo "FATAL: no reference hashes at $f" >&2
	echo "" >&2
	echo "  recovery_ok() scores the good vector against these md5s. Without" >&2
	echo "  them every recovery check reads as WEDGED and the baseline aborts" >&2
	echo "  asking for a reboot -- on an engine that is fine." >&2
	echo "" >&2
	echo "  Fix: copy tools/video/reference-md5.txt," >&2
	echo "  tools/video/hevc-reference-md5.txt and" >&2
	echo "  tools/video/mpeg2-reference-md5.txt and" >&2
	echo "  tools/video/hevc10-reference-md5.txt from the repo to $DIR/." >&2
	exit 2
done

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}
kmsg_count() { dmesg | grep -ciE "$1" || true; }

want_hevc_md5() { grep " $GOOD_HEVC\$" "$HEVC_REF" | cut -d' ' -f1; }
want_h264_md5() { grep "^$GOOD_H264 WHOLE" "$H264_REF" | awk '{print $NF}'; }
want_mpeg2_md5() { grep "^$GOOD_MPEG2 WHOLE" "$MPEG2_REF" | awk '{print $NF}'; }
want_hevc10_md5() { grep " $GOOD_HEVC10\$" "$HEVC10_REF" | cut -d' ' -f1; }

# Same reasoning as the file check: an empty want here reads as WEDGED.
for m in "$(want_hevc_md5)" "$(want_h264_md5)" "$(want_mpeg2_md5)" "$(want_hevc10_md5)"; do
	[ -n "$m" ] || {
		echo "FATAL: reference files present but missing an entry for" >&2
		echo "  $GOOD_HEVC, $GOOD_H264 or $GOOD_MPEG2 -- recovery would read" >&2
		echo "  as WEDGED." >&2
		exit 2
	}
done

# DECODE_RC is set as a side effect on purpose. ${PIPESTATUS[0]} read after a
# FUNCTION CALL reports the function's own status -- bash resets PIPESTATUS for
# every simple command, and the function returns md5sum's status, which is 0
# whatever ffmpeg did. Reading it that way would have scored a `timeout` kill
# (124) as a clean decode, i.e. reported HUNG cases as passes: the exact
# failure this harness exists to catch.
decode_to_md5() {
	LIBVA_DRIVER_NAME=v4l2_request timeout "$CASE_TIMEOUT" \
		ffmpeg -hide_banner -v error -y \
		-hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$1" -vf 'hwdownload,format=nv12' \
		-f rawvideo -pix_fmt nv12 pipe:1 2>"$ERR" | md5sum | cut -d' ' -f1
	DECODE_RC=${PIPESTATUS[0]}
}

# The recovery check, and the reason the whole harness exists.
recovery_ok() {
	local got want
	case $1 in
	h) got=$(decode_to_md5 "$DIR/$GOOD_HEVC.h265"); want=$(want_hevc_md5) ;;
	t) got=$(decode_to_md5 "$DIR/$GOOD_HEVC10.h265"); want=$(want_hevc10_md5) ;;
	m) got=$(decode_to_md5 "$DIR/$GOOD_MPEG2.m2v"); want=$(want_mpeg2_md5) ;;
	*) got=$(decode_to_md5 "$DIR/$GOOD_H264.h264"); want=$(want_h264_md5) ;;
	esac
	[ "$got" = "$want" ]
}

ERR=$(mktemp)
trap 'rm -f "$ERR"' EXIT

echo "=== recovery baseline (if this fails, the VE is already wedged) ==="
for c in h t v m; do
	if recovery_ok $c; then
		echo "     $c: good vector decodes bit-exact — starting from a healthy engine"
	else
		echo "     $c: FATAL — the good vector does not decode. Reboot and re-run."
		exit 1
	fi
done

pass=0; fail=0
echo
echo "=== malformed input ==="
printf '%-34s %-10s %-8s %-6s %s\n' CASE OUTCOME ve RECOVER NOTE

for f in "$BAD"/*.h265 "$BAD"/*.h264 "$BAD"/*.m2v; do
	[ -r "$f" ] || continue
	name=$(basename "$f")
	case $name in
	*-h-*) codec=h ;;
	*-t-*) codec=t ;;   # Main10; recovers against the 10-bit canary
	*-m-*) codec=m ;;
	*) codec=v ;;
	esac

	# Two different timeouts exist and they mean different things: the
	# watchdog's "frame processing timed out!" is the one that resets the
	# engine and historically wedges it, while cedrus_h265.c's "timed out
	# waiting to skip bits" is a bounded wait inside slice setup that does
	# not reset anything. Counting them together would blur the very
	# distinction this test is about.
	wd0=$(kmsg_count "frame processing timed out")
	skip0=$(kmsg_count "timed out waiting to skip bits")
	oops0=$(kmsg_count "Oops|BUG:|Call trace|kernel panic")

	a=$(ve_irq)
	decode_to_md5 "$f" >/dev/null
	rc=$DECODE_RC
	ve=$(( $(ve_irq) - a ))

	if [ "$rc" -eq 124 ]; then
		outcome=HUNG
	elif [ "$rc" -eq 0 ]; then
		outcome=decoded
	else
		outcome="err($rc)"
	fi

	note=""
	[ "$(kmsg_count "frame processing timed out")" -ne "$wd0" ] && note="WATCHDOG TIMEOUT"
	if [ "$(kmsg_count "timed out waiting to skip bits")" -ne "$skip0" ]; then
		note="${note:+$note, }skip-bits timeout"
	fi
	oops_note=""
	if [ "$(kmsg_count "Oops|BUG:|Call trace|kernel panic")" -ne "$oops0" ]; then
		oops_note="KERNEL OOPS"
		note="${note:+$note, }KERNEL OOPS"
	fi

	if recovery_ok $codec; then
		rec=ok
	else
		rec=WEDGED
	fi

	# The verdict ignores the case's own exit status on purpose, AND it ignores
	# a watchdog timeout. Both were failures in the first version of this
	# harness and neither should be: the engine stalling on deliberately
	# corrupted slice data is the hardware behaving reasonably, and the driver
	# timing out, resetting and returning an error is the recovery path doing
	# its job. Measured on this board, a stall is followed by a bit-exact
	# decode every time. Only a hang, a kernel complaint, or a dead engine
	# afterwards is a failure.
	if [ "$rec" = ok ] && [ "$outcome" != HUNG ] && [ -z "$oops_note" ]; then
		pass=$((pass + 1))
	else
		fail=$((fail + 1))
	fi

	printf '%-34s %-10s ve+%-5s %-6s %s\n' "$name" "$outcome" "$ve" "$rec" "$note"

	# Once the engine is wedged every later result is a consequence of this
	# one, not an independent sample. Say so and stop.
	if [ "$rec" = WEDGED ]; then
		echo
		echo "STOPPING: the engine no longer decodes a known-good stream."
		echo "Everything after this point would measure the wedge, not the case."
		break
	fi
done

echo
echo "R1: $pass pass, $fail fail"
[ "$fail" -eq 0 ]
