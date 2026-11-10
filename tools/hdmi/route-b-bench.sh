#!/bin/sh
# Route B bench (HDMI panel-source design 10.25.4), run on the board as root.
#
# The V4L2 bridge (modules/hdmi-v4l2, completion=pair, cacheable ring) gives
# NV12; stock GStreamer puts it on the production KMS NV12 plane.
#
#   route-b-bench.sh check DIR          load, list formats, stream 300 NV12 frames
#                                       (one frame saved to DIR/frame0.nv12 first),
#                                       report rate and bridge counters, unload.
#                                       No panel change.
#   ARMED=yes route-b-bench.sh show SECS
#                                       v4l2src io-mode=dmabuf ! NV12 ! kmssink on
#                                       the video plane for SECS, rate printed,
#                                       then unload. Visual.
#
# Env: KO (default /root/route-b/h713-hdmi-v4l2.ko), COMPLETION (default pair),
# EXTRA (more module parameters, e.g. verify_full=0),
# PLANE (default 38, the NV12 video plane id kms-yuv-still reported on the
# production kernel).
set -eu
KO=${KO:-/root/route-b/h713-hdmi-v4l2.ko}
COMPLETION=${COMPLETION:-pair}
PLANE=${PLANE:-38}

die() { echo "route-b-bench: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run as root"
[ -f "$KO" ] || die "no module at $KO"
lsmod | grep -q '^h713_hdmi_v4l2 ' && die "the bridge is already loaded; rmmod it first"

load() {
	insmod "$KO" width=1280 height=720 completion="$COMPLETION" source_cached=1 ${EXTRA:-}
	trap 'rmmod h713_hdmi_v4l2 2>/dev/null || true' EXIT HUP INT TERM
	DEV=
	for d in /sys/class/video4linux/video*; do
		if grep -qx "h713-hdmi-in" "$d/name" 2>/dev/null; then DEV=/dev/$(basename "$d"); fi
	done
	[ -n "$DEV" ] || die "bridge device not found"
	dmesg | grep 'h713-hdmi-v4l2' | tail -3
	echo "device $DEV"
}

counters() {
	for p in frames_produced frames_delivered frames_overwritten frames_rejected; do
		printf '%s=%s ' "$p" "$(cat /sys/module/h713_hdmi_v4l2/parameters/$p)"
	done
	echo
}

case "${1:-}" in
check)
	OUT=${2:?DIR}
	mkdir -p "$OUT"
	load
	v4l2-ctl -d "$DEV" --list-formats
	v4l2-ctl -d "$DEV" --set-fmt-video=width=1280,height=720,pixelformat=NV12
	v4l2-ctl -d "$DEV" --get-fmt-video
	v4l2-ctl -d "$DEV" --stream-mmap=4 --stream-count=1 --stream-to="$OUT/frame0.nv12"
	t0=$(date +%s.%N)
	v4l2-ctl -d "$DEV" --stream-mmap=4 --stream-count=300 --stream-to=/dev/null 2>&1 | tail -2
	t1=$(date +%s.%N)
	ls -l "$OUT/frame0.nv12"
	awk -v a="$t0" -v b="$t1" 'BEGIN { printf "300 frames in %.2f s (%.1f fps)\n", b - a, 300 / (b - a) }'
	counters
	;;
show)
	[ "${ARMED:-}" = yes ] || die "show needs ARMED=yes (it changes the panel)"
	SECS=${2:?SECS}
	load
	timeout "$SECS" gst-launch-1.0 -e -q \
		v4l2src device="$DEV" io-mode=dmabuf \
		! video/x-raw,format=NV12,width=1280,height=720 \
		! fpsdisplaysink text-overlay=false silent=false sync=false \
		  video-sink="kmssink driver-name=sun50i-h713-afbd plane-id=$PLANE skip-vsync=true" 2>&1 \
		| grep -E 'rendered|dropped|ERROR|WARN' | tail -4 || true
	counters
	;;
*)
	sed -n '2,18p' "$0"
	exit 2
	;;
esac
dmesg | grep 'h713-hdmi-v4l2' | tail -2
