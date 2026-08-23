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
BAD=${1:-$DIR/bad}
CASE_TIMEOUT=${CASE_TIMEOUT:-30}

GOOD_HEVC=h01-640x480-main
GOOD_H264=v03-1280x720-main

[ -d "$BAD" ] || { echo "FATAL: no bad-stream directory at $BAD"; exit 1; }

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}
kmsg_count() { dmesg | grep -ciE "$1" || true; }

want_hevc_md5() { grep " $GOOD_HEVC\$" "$DIR/hevc-reference-md5.txt" | cut -d' ' -f1; }
want_h264_md5() { grep "^$GOOD_H264 WHOLE" "$DIR/reference-md5.txt" | awk '{print $NF}'; }

decode_to_md5() {
	LIBVA_DRIVER_NAME=v4l2_request timeout "$CASE_TIMEOUT" \
		ffmpeg -hide_banner -v error -y \
		-hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$1" -vf 'hwdownload,format=nv12' \
		-f rawvideo -pix_fmt nv12 pipe:1 2>"$ERR" | md5sum | cut -d' ' -f1
}

# The recovery check, and the reason the whole harness exists.
recovery_ok() {
	local got want
	case $1 in
	h) got=$(decode_to_md5 "$DIR/$GOOD_HEVC.h265"); want=$(want_hevc_md5) ;;
	*) got=$(decode_to_md5 "$DIR/$GOOD_H264.h264"); want=$(want_h264_md5) ;;
	esac
	[ "$got" = "$want" ]
}

ERR=$(mktemp)
trap 'rm -f "$ERR"' EXIT

echo "=== recovery baseline (if this fails, the VE is already wedged) ==="
for c in h v; do
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

for f in "$BAD"/*.h265 "$BAD"/*.h264; do
	[ -r "$f" ] || continue
	name=$(basename "$f")
	case $name in *-h-*) codec=h ;; *) codec=v ;; esac

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
	rc=${PIPESTATUS[0]}
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
	if [ "$(kmsg_count "Oops|BUG:|Call trace|kernel panic")" -ne "$oops0" ]; then
		note="${note:+$note, }KERNEL OOPS"
	fi

	if recovery_ok $codec; then
		rec=ok
	else
		rec=WEDGED
	fi

	# The verdict ignores the case's own exit status on purpose: only a hang,
	# a kernel complaint, or a dead engine afterwards is a failure.
	if [ "$rec" = ok ] && [ "$outcome" != HUNG ] && [ -z "$note" ]; then
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
