#!/bin/sh
# Check gst-seek-test output against a software reference. RUNS ON THE TARGET.
#
#   usage: gst-seek-check.sh seek.log clip.framemd5 fps irq-pattern irq-before
#
# Every frame the decoder delivered after every seek must hash to the
# reference frame with the same timestamp; a run that delivered no frames, or
# moved the decoder's interrupt count by fewer than it delivered, fails.
set -u
log=$1; ref=$2; fps=$3; pat=$4; before=$5
after=$(awk -v p="$pat" '$0 ~ p {print $2; exit}' /proc/interrupts)
grep -v '^#' "$ref" | awk -F', *' '{print $6}' > /tmp/seek.ref
awk -v fps="$fps" 'NR == FNR { ref[FNR - 1] = $1; next }
	$2 == "frame" { n++; first = !got[$1]++; i = int($3 * fps / 1e9 + 0.5);
		# the first frame after a seek may be the one straddling the target,
		# its timestamp clipped forward to the segment start
		if (ref[i] == $4 || (first && i > 0 && ref[i - 1] == $4)) ok++; else { bad++; if (bad <= 5) print "  MISMATCH", $1, "frame", i } }
	/TIMEOUT|REFUSED/ { print "  " $0; bad++ }
	/^seek/ && $2 == "frame" && !seen[$1]++ { seeks++; land = land " " i }
	END { printf "frames %d exact %d bad %d seeks %d (landed on:%s)\n", n, ok, bad, seeks, land;
	      exit !(n > 0 && bad == 0 && seeks > 0) }' /tmp/seek.ref "$log"
rc=$?
n=$(grep -c ' frame ' "$log")
d=$((after - before))
echo "irq +$d for $n delivered frames"
[ "$d" -ge "$n" ] || rc=1
[ $rc = 0 ] && echo PASS || echo FAIL
exit $rc
