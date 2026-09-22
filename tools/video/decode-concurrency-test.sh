#!/bin/bash
# Do concurrent clients get correct output? RUNS ON THE TARGET.
#
# cedrus is ONE m2m device. Everything else in this project's video testing has
# opened it alone, which is not how a real system uses it -- a player and a
# thumbnailer, or two players, will have requests in flight at the same time,
# and the kernel is expected to interleave their jobs on a single engine.
#
# Two things can go wrong and neither shows up in a single-client test:
#
#   * jobs interleave but state does not -- one client's picture parameters or
#     reference buffers leak into another's frame, so BOTH decode "successfully"
#     and at least one is wrong;
#   * a device-wide action taken for one client (a reset, in particular) breaks
#     a job belonging to another. Patch 0040 pulses the engine reset in
#     stop_streaming, and the patch's own comment flags exactly this risk.
#
# So the check is bit-exactness of every concurrent client, not just liveness.
# Vectors differ per client on purpose: identical streams would hide a mix-up
# between them, which is the most likely form of the first failure.
#
#   usage: ./decode-concurrency-test.sh [rounds] [clients]      (default 5 3)

set -u

DIR=$(cd "$(dirname "$0")" && pwd)
ROUNDS=${1:-5}
CLIENTS=${2:-3}
OUT=${OUT:-/var/tmp/conc}
HEVC_REF=${HEVC_REF:-$DIR/hevc-reference-md5.txt}
H264_REF=${H264_REF:-$DIR/reference-md5.txt}

mkdir -p "$OUT"

# Without the references every round scores MISMATCH -- the comparison below is
# against an empty string -- so the run "fails", but for the wrong reason and
# with no hint that the cause is a missing file rather than a cross-client
# corruption. That is a whole session spent chasing the harness. Worse, the two
# sides are equal when BOTH are empty, so a round in which no client wrote an
# md5 at all would score as a pass. Fail up front instead.
for f in "$HEVC_REF" "$H264_REF"; do
	[ -s "$f" ] && continue
	echo "FATAL: no reference hashes at $f" >&2
	echo "" >&2
	echo "  This test scores each client's output against a known md5; without" >&2
	echo "  the references it cannot tell a clean run from a corrupted one." >&2
	echo "" >&2
	echo "  Fix: copy tools/video/reference-md5.txt and" >&2
	echo "  tools/video/hevc-reference-md5.txt from the repo to $DIR/." >&2
	exit 2
done

# One HEVC and two H.264, so a mix-up crosses a codec boundary as well as a
# stream boundary -- the coarsest possible thing to get wrong.
POOL=("h01-640x480-main:h265" "v03-1280x720-main:h264" "v01-320x240-baseline:h264"
      "h03-640x480-nowpp:h265" "v02-1280x720-baseline:h264")

ve_irq() {
	awk '/video-codec/ { for (i = 2; i <= 5; i++) s += $i } END { print s + 0 }' \
		/proc/interrupts
}
kmsg_count() { dmesg | grep -ciE "$1" || true; }

want_md5() {
	case $1 in
	h0*) grep " $1\$" "$HEVC_REF" | cut -d' ' -f1 ;;
	*)   grep "^$1 WHOLE" "$H264_REF" | awk '{print $NF}' ;;
	esac
}

# A present-but-incomplete reference file is the same blind spot one vector at
# a time, and the pool is fixed, so check the whole pool before doing any work.
for entry in "${POOL[@]}"; do
	v=${entry%%:*}
	[ -n "$(want_md5 "$v")" ] || {
		echo "FATAL: no reference md5 for $v -- refusing to score it blind" >&2
		exit 2
	}
done

# `timeout` is not belt-and-braces here. Three concurrent clients can leave a
# decoder stuck in D state inside v4l2_m2m_cancel_job(), where it ignores
# SIGKILL, and `wait` on such a child never returns -- the first run of this
# harness hung for eleven minutes and had to be ended by rebooting the board.
decode() {
	LIBVA_DRIVER_NAME=v4l2_request timeout "${CLIENT_TIMEOUT:-90}" \
		ffmpeg -hide_banner -v error -y \
		-hwaccel vaapi -hwaccel_output_format vaapi \
		-i "$DIR/$1.$2" -vf 'hwdownload,format=nv12' \
		-f rawvideo -pix_fmt nv12 pipe:1 2>"$OUT/$1.err" \
		| md5sum | cut -d' ' -f1 > "$OUT/$1.md5"
}

wd0=$(kmsg_count "frame processing timed out")
oops0=$(kmsg_count "Oops|BUG:|Call trace|kernel panic")
ve0=$(ve_irq)
pass=0; fail=0

echo "=== $CLIENTS concurrent clients x $ROUNDS rounds ==="

for r in $(seq 1 "$ROUNDS"); do
	picked=()
	for i in $(seq 0 $((CLIENTS - 1))); do
		picked+=("${POOL[$(( (r + i) % ${#POOL[@]} ))]}")
	done

	a=$(ve_irq)
	t0=$(date +%s%N)
	for entry in "${picked[@]}"; do
		decode "${entry%%:*}" "${entry##*:}" &
	done
	wait
	t1=$(date +%s%N)
	ve=$(( $(ve_irq) - a ))

	line=""
	for entry in "${picked[@]}"; do
		v=${entry%%:*}
		got=$(cat "$OUT/$v.md5" 2>/dev/null)
		if [ "$got" = "$(want_md5 "$v")" ]; then
			pass=$((pass + 1)); line="$line $v=ok"
		else
			fail=$((fail + 1)); line="$line $v=MISMATCH"
			head -1 "$OUT/$v.err" 2>/dev/null | sed 's/^/          /'
		fi
	done

	printf '  round %-2s %5s ms  ve+%-5s %s\n' "$r" "$(( (t1 - t0) / 1000000 ))" "$ve" "$line"
done

wd1=$(kmsg_count "frame processing timed out")
oops1=$(kmsg_count "Oops|BUG:|Call trace|kernel panic")

echo
echo "  frames on VE $(( $(ve_irq) - ve0 ))"
echo "  watchdog timeouts $wd0 -> $wd1"
echo "  oops/BUG          $oops0 -> $oops1"
rm -f "$OUT"/*.md5 "$OUT"/*.err
echo "C1: $pass pass, $fail fail"
[ "$fail" -eq 0 ] && [ "$wd1" -eq "$wd0" ] && [ "$oops1" -eq "$oops0" ]
