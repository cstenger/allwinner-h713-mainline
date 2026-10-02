#!/bin/sh
# Every VA-API decode path, in one memory mode, scored. RUNS ON THE TARGET.
#
# WHY IT EXISTS. The VA driver has two ways to provide capture memory
# (libva-v4l2-request 0018): DMA-BUF heap buffers owned by the surfaces, the
# default, and the queue's own MMAP buffers, the fallback. A change to either
# has to be scored in both, across every codec, and the per-codec gates were
# written at different times with different habits -- one writes 186 MB of raw
# 1080p to /var/tmp and fails as a MISMATCH when the root filesystem fills
# (it did, 2026-10-01). This runs them all the same way: hashes streamed to
# md5sum, nothing large on disk, and a verdict per line.
#
#   usage: va-regress.sh dmabuf|mmap
#
# What each line checks, and against what:
#   va-gate   AV1 + VP9 per-frame MD5 vs libdav1d/libvpx, interrupts >= frames.
#             v10-odd-350x286 is the one width that is not 64-aligned: the VP9
#             engine reads references at a pitch it derives from the width
#             (kernel 0154), and every other vector here hid that, 2026-10-02.
#   10-bit    AV1 Main 10-bit per-frame vs libdav1d (P010 readback)
#   h264      whole-stream MD5 vs the host reference (reference-md5.txt)
#   hevc      the H1 gate (hevc-decode-test.sh)
#   mpeg2     whole-stream MD5 vs GStreamer v4l2slmpeg2dec, the established
#             oracle (cedrus MPEG-2 is not bit-exact against ffmpeg's IDCT)
#   loop      mpv --loop-file=5 must never fall back to software (0009's case)
#   reinit    mid-stream resolution changes (decode-reinit-test.sh); expected
#             to FAIL with mmap, where the queues cannot be renegotiated
#   conc      three concurrent clients (decode-concurrency-test.sh)
#
# Paths are the board's layout; override with AV1_DIR, VP9_DIR, TEST_DIR,
# VA_GATE (tools/video/va-gate.sh as installed).
m=${1:-}
case $m in dmabuf|mmap) ;; *) echo "usage: $0 dmabuf|mmap" >&2; exit 2 ;; esac
export LIBVA_DRIVER_NAME=v4l2_request V4L2_REQUEST_CAPTURE_MEMORY=$m
AV1_DIR=${AV1_DIR:-/root/av1}
VP9_DIR=${VP9_DIR:-/var/tmp}
TEST_DIR=${TEST_DIR:-/root/video-test}
VA_GATE=${VA_GATE:-/root/va-gate.sh}
T=/var/tmp/va-regress-$m
rm -rf "$T"; mkdir -p "$T"
irq() { awk -v p="$1" '$0 ~ p {print $2; exit}' /proc/interrupts; }
fails=0
say() {
	echo "$m $*"
	case "$*" in *FAIL*) fails=$((fails + 1)) ;; esac
}

cd "$AV1_DIR" || exit 1
OUT=$T/gate sh "$VA_GATE" A.ivf B.ivf C.ivf D.ivf E.ivf \
	"$VP9_DIR/v04-720p-default.webm" "$VP9_DIR/v11-1080p-mandel.webm" \
	"$VP9_DIR/v10-odd-350x286.webm" > "$T/gate.log" 2>&1
n=$(grep -c PASS "$T/gate.log")
[ "$n" = 8 ] && v=PASS || v=FAIL
say "va-gate: $v $n/8 $(grep FAIL "$T/gate.log" | cut -c1-40)"

for c in hbd720 hbd720-long; do
	ffmpeg -v error -c:v libdav1d -i $c.ivf -fps_mode passthrough -pix_fmt p010le -f framemd5 - |
		grep -v '^#' | awk -F', *' '{print $6}' > "$T/sw"
	ffmpeg -v error -hwaccel vaapi -hwaccel_output_format vaapi -i $c.ivf \
		-vf hwdownload,format=p010le -fps_mode passthrough -f framemd5 - 2>/dev/null |
		grep -v '^#' | awk -F', *' '{print $6}' > "$T/hw"
	n=$(wc -l < "$T/sw"); s=$(paste -d' ' "$T/sw" "$T/hw" | awk '$1 == $2' | wc -l)
	[ "$n" -gt 0 ] && [ "$s" = "$n" ] && v=PASS || v=FAIL
	say "10-bit $c: $v $s/$n"
done

cd "$TEST_DIR" || exit 1
for v in v01-320x240-baseline v02-1280x720-baseline v03-1280x720-main v04-1280x720-high v05-1920x1080-high; do
	want=$(awk -v v=$v '$1 == v && $2 == "WHOLE" {print $NF}' reference-md5.txt)
	a=$(irq 1c0e000)
	got=$(ffmpeg -v error -hwaccel vaapi -hwaccel_output_format vaapi -i ./$v.h264 \
		-vf hwdownload,format=nv12 -f rawvideo -pix_fmt nv12 - 2>/dev/null | md5sum | cut -d' ' -f1)
	[ -n "$want" ] && [ "$got" = "$want" ] && r=PASS || r=FAIL
	say "h264 $v: $r ve+$(( $(irq 1c0e000) - a ))"
done

OUT=$T/hevc ./hevc-decode-test.sh > "$T/hevc.log" 2>&1
grep -q '^H1: .* 0 fail' "$T/hevc.log" && r=PASS || r=FAIL
say "hevc: $r $(grep '^H1:' "$T/hevc.log")"
rm -rf "$T/hevc"

for v in m01-352x288-progressive m02-720x576-progressive m03-1280x720-progressive \
	 m04-720x576-interlaced m06-720x576-field-clean; do
	g=$(gst-launch-1.0 -q filesrc location=$v.m2v ! mpegvideoparse ! v4l2slmpeg2dec ! \
		videoconvert ! video/x-raw,format=I420 ! fdsink fd=1 2>/dev/null | md5sum | cut -d' ' -f1)
	h=$(ffmpeg -v error -hwaccel vaapi -hwaccel_output_format vaapi -i $v.m2v \
		-vf hwdownload,format=nv12 -fps_mode passthrough -pix_fmt yuv420p -f rawvideo - \
		2>/dev/null | md5sum | cut -d' ' -f1)
	[ "$g" = "$h" ] && r=PASS || r=FAIL
	say "mpeg2 $v: $r"
done

# Raw elementary streams cannot be seeked by lavf, so loop through MP4.
ffmpeg -v error -y -framerate 25 -i h02-1280x720-main.h265 -c copy "$T/h02.mp4"
ffmpeg -v error -y -framerate 30 -i v04-1280x720-high.h264 -c copy "$T/v04.mp4"
for f in "$AV1_DIR/hbd720.ivf" "$VP9_DIR/v04-720p-default.webm" "$T/h02.mp4" "$T/v04.mp4"; do
	a=$(( $(irq 1c0d000) + $(irq 1c0e000) ))
	out=$(timeout 300 mpv --no-config --vo=null --ao=null --hwdec=vaapi-copy --untimed \
		--loop-file=5 --msg-level=all=v "$f" 2>&1)
	hw=$(echo "$out" | grep -c 'Using hardware decoding')
	sw=$(echo "$out" | grep -c 'Using software decoding')
	[ "$hw" -ge 1 ] && [ "$sw" = 0 ] && r=PASS || r=FAIL
	say "loop $(basename "$f"): $r sw=$sw irq+$(( $(irq 1c0d000) + $(irq 1c0e000) - a ))"
done

OUT=$T/reinit ./decode-reinit-test.sh > "$T/reinit.log" 2>&1
res=$(grep '^RI1:' "$T/reinit.log")
if [ $m = dmabuf ]; then
	echo "$res" | grep -q ' 0 fail' && r=PASS || r=FAIL
else
	# The negative control: MMAP cannot renegotiate, every vector must fail.
	echo "$res" | grep -q '^RI1: 0 pass' && r="PASS (expected failures)" || r=FAIL
fi
say "reinit: $r $res"

./decode-concurrency-test.sh 5 3 > "$T/conc.log" 2>&1
grep -q '^C1: .* 0 fail' "$T/conc.log" && r=PASS || r=FAIL
say "conc: $r $(grep '^C1:' "$T/conc.log")"

echo "$m: $fails failing line(s)"
rm -rf "$T"
[ "$fails" = 0 ]
