#!/bin/sh
# Event-driven HDMI-in on the panel, staged at runtime (HDMI panel-source
# design 10.26). Run on the board as root from the directory holding the
# bundle (h713-hdmi-v4l2.ko, 71-h713-hdmi-in.rules, h713-hdmi-ring.service,
# h713-hdmi-video.service). Everything goes under /run, so a reboot erases it;
# nothing is installed.
#
#   stage-hdmi-video.sh observe SECS   stage 1: load the bridge alone (no rule,
#                                      no units, no DRM), log every signal
#                                      transition for SECS, then unload.
#                                      No panel change.
#   ARMED=yes stage-hdmi-video.sh stage
#                                      stage 3: rule + units in /run, start the
#                                      bridge unit. The panel switches to HDMI
#                                      as soon as a signal locks.
#   stage-hdmi-video.sh status         signal, units, restarts, recent log
#   stage-hdmi-video.sh unstage        stop the units, remove the /run files
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
RUN=/run/h713-hdmi-video
ATTR=/sys/devices/platform/h713-hdmi-ring/signal

die() { echo "stage-hdmi-video: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run as root"
loaded() { lsmod | grep -q '^h713_hdmi_v4l2 '; }

case "${1:-}" in
observe)
	SECS=${2:?SECS}
	loaded && die "the bridge is already loaded"
	[ -f "$HERE/h713-hdmi-v4l2.ko" ] || die "no module in $HERE"
	dmesg -n 7 || true
	insmod "$HERE/h713-hdmi-v4l2.ko" completion=pair allow_480p=0
	trap 'rmmod h713_hdmi_v4l2 2>/dev/null || true' EXIT HUP INT TERM
	echo "signal now: $(cat $ATTR)"
	DEV=/dev/$(basename "$(dirname "$(grep -l '^h713-hdmi-in$' /sys/class/video4linux/*/name)")")
	echo "device $DEV"
	v4l2-ctl -d "$DEV" --get-input --list-dv-timings --get-dv-timings --get-fmt-video 2>&1 \
		| grep -vE '^\s*$' | head -40
	v4l2-ctl -d "$DEV" --query-dv-timings 2>&1 | head -12
	if [ "${COMPLIANCE:-}" = 1 ]; then
		v4l2-compliance -d "$DEV" 2>&1 | grep -E 'fail|warn|Total|DV_TIMINGS|EVENT' | head -40
	fi
	echo "watching for ${SECS}s; transitions (kernel time):"
	timeout "$SECS" udevadm monitor --kernel --property --subsystem-match=video4linux 2>/dev/null \
		| grep --line-buffered -E '^(KERNEL\[|H713_HDMI_)' || true
	echo "signal at end: $(cat $ATTR)"
	for p in sig_transitions sig_bad_guard; do
		printf '%s=%s ' "$p" "$(cat /sys/module/h713_hdmi_v4l2/parameters/$p)"
	done
	echo
	dmesg | grep 'h713-hdmi-v4l2: \(initial \)\?signal' | tail -40
	;;
stage)
	[ "${ARMED:-}" = yes ] || die "stage needs ARMED=yes (the panel switches on lock)"
	loaded && die "the bridge is already loaded"
	for f in h713-hdmi-v4l2.ko 71-h713-hdmi-in.rules h713-hdmi-ring.service h713-hdmi-video.service; do
		[ -f "$HERE/$f" ] || die "missing $f"
	done
	mkdir -p "$RUN" /run/udev/rules.d /run/systemd/system/h713-hdmi-ring.service.d
	cp "$HERE/h713-hdmi-v4l2.ko" "$RUN/"
	cp "$HERE/71-h713-hdmi-in.rules" /run/udev/rules.d/
	cp "$HERE/h713-hdmi-ring.service" "$HERE/h713-hdmi-video.service" /run/systemd/system/
	printf '[Service]\nEnvironment=H713_BRIDGE=%s/h713-hdmi-v4l2.ko\n' "$RUN" \
		> /run/systemd/system/h713-hdmi-ring.service.d/stage.conf
	udevadm control --reload
	systemctl daemon-reload
	systemctl start h713-hdmi-ring.service
	sleep 2
	"$0" status
	;;
status)
	echo "signal: $(cat $ATTR 2>/dev/null || echo 'bridge not loaded')"
	for u in h713-hdmi-ring.service h713-hdmi-video.service 'dev-h713\x2dhdmi\x2din.device'; do
		printf '%-34s %s\n' "$u" "$(systemctl show -p ActiveState,SubState,NRestarts --value "$u" | tr '\n' ' ')"
	done
	journalctl -b --no-pager -o short-monotonic -u h713-hdmi-video.service -n 8 | tail -8
	dmesg | grep 'h713-hdmi-v4l2: \(initial \)\?signal' | tail -8
	;;
unstage)
	systemctl stop h713-hdmi-video.service h713-hdmi-ring.service 2>/dev/null || true
	rm -f /run/udev/rules.d/71-h713-hdmi-in.rules \
		/run/systemd/system/h713-hdmi-ring.service \
		/run/systemd/system/h713-hdmi-video.service
	rm -rf /run/systemd/system/h713-hdmi-ring.service.d "$RUN"
	udevadm control --reload
	systemctl daemon-reload
	loaded && rmmod h713_hdmi_v4l2 || true
	echo "unstaged; bridge $(loaded && echo 'STILL LOADED' || echo unloaded)"
	;;
*)
	sed -n '2,20p' "$0"
	exit 2
	;;
esac
