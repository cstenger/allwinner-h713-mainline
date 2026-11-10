#!/bin/sh
# AV1 mid-stream resolution change. RUNS ON THE TARGET.
#
# The stream is several clips of different sizes joined by
# tools/video/ivf-concat.py, so each join carries a new sequence header. The
# reference is the MD5 of the clips' libdav1d output (I420) concatenated:
#
#   host$ for c in a b c; do ffmpeg -c:v libdav1d -i $c.ivf -pix_fmt yuv420p -f rawvideo -; done | md5sum
#
# kept next to the stream as clip.ivf.md5. A per-frame hash cannot be used:
# the frame size changes under it. Hardware is proven by the interrupt count.
#
#   usage: av1-reschange-test.sh clip.ivf frames
set -u
f=$1; n=$2
irq() { awk '/1c0d000/ {print $2; exit}' /proc/interrupts; }
kerr() { dmesg | grep -cE 'decode failed|core still busy|interrupt without a cause|cannot set up the frame|timed out|iommu.*fault'; }
want=$(cut -d' ' -f1 "$f.md5")
a=$(irq); e0=$(kerr)
md5=$(timeout 300 gst-launch-1.0 -q filesrc location="$f" ! ivfparse ! av1parse ! \
	v4l2slav1dec ! videoconvert ! video/x-raw,format=I420 ! fdsink fd=1 2>/tmp/av1-reschange.log |
	md5sum | cut -d' ' -f1)
d=$(( $(irq) - a )); ke=$(( $(kerr) - e0 ))
verdict=PASS
[ "$md5" = "$want" ] || verdict=FAIL
[ "$d" -ge "$n" ] || verdict=FAIL
[ "$ke" = 0 ] || verdict=FAIL
echo "$(basename "$f") $verdict  md5 $md5 (want $want)  av1_irq=+$d (frames $n) kerr=+$ke"
[ $verdict = PASS ]
