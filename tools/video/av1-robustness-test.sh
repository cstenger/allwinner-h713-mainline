#!/bin/sh
# AV1 robustness: damaged streams must not hang or poison the core. RUNS ON THE TARGET.
#
# For each damaged stream (tools/video/make-av1-bad-streams.py): decode it,
# which must END by itself within the timeout (any exit code is fine -- a
# damaged stream may fail); then decode a known-good clip, which must still be
# bit-exact with its interrupts. The core has been seen to stall until a power
# cycle, so the run STOPS at the first stream after which the good clip fails:
# driving a stuck core further proves nothing and risks a wedge.
#
#   usage: av1-robustness-test.sh good.ivf bad.ivf [bad.ivf ...]
set -u
good=$1; shift
here=$(cd "$(dirname "$0")" && pwd)
irq() { awk '/1c0d000/ {print $2; exit}' /proc/interrupts; }
fail=0
for f in "$@"; do
	b=$(basename "$f" .ivf)
	before=$(dmesg | wc -l); a=$(irq)
	timeout 60 gst-launch-1.0 -q filesrc location="$f" ! ivfparse ! av1parse ! \
		v4l2slav1dec ! fakesink > /tmp/rob.log 2>&1
	rc=$?
	d=$(( $(irq) - a ))
	msgs=$(dmesg | tail -n +$((before + 1)) | grep -oE "decode failed|core still busy|interrupt without a cause|cannot set up the frame|timed out|Page fault" | sort | uniq -c | tr -s ' ' | tr '\n' ',')
	health=$(OUT=/var/tmp/rob sh "$here/av1-gate.sh" "$good" | awk '{print $2}')
	[ "$rc" = 124 ] && ended=HUNG || ended="rc=$rc"
	printf '%-26s %s irq=+%s  kernel: %s  good clip after: %s\n' "$b" "$ended" "$d" "${msgs:-none}" "$health"
	if [ "$health" != PASS ] || [ "$rc" = 124 ]; then
		echo "STOPPED: the core is not healthy after $b"
		exit 1
	fi
done
exit $fail
