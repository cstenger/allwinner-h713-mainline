#!/usr/bin/env bash
# Is the board running what this repo says it should? RUNS ON THE HOST.
#
# THE FAILURE THIS EXISTS FOR, because it has already happened here: the board
# was found decoding with a sunxi-cedrus.ko that predated two patches which had
# been in patches/kernel/series for weeks. Everything looked right -- the gates
# passed, the kernel version matched, the module loaded -- and a whole line of
# reasoning was built on a binary that was not the source. Nothing anywhere
# could have said so.
#
# cedrus, the VA driver and mpv are the three pieces that do NOT arrive by
# flashing a kernel FIT: the module lives in the rootfs, the .so is built on the
# board, and mpv is cross-built in a container. All three can silently fall
# behind the tree. This compares what is installed with what the series files
# currently describe, and says which.
#
# Exit status is 0 only when all three match, so it can gate a test run.
#
#   usage: tools/video/check-video-stack.sh
#          BOARD=192.168.4.1 tools/video/check-video-stack.sh
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# shellcheck source=../../config/paths.sh
source "$ROOT/config/paths.sh"
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
drift=0

echo "=== kernel module (sunxi-cedrus) ==="

# ASK THE BUILD which tree this configuration produces rather than guessing.
# The first version of this script took the newest tree under build/ and
# promptly reported drift on a correct board, because the newest tree was a
# debug probe. build.sh hashes the series, the defconfig and the fragments into
# the directory name, so `kernel-tree` is the only answer that cannot drift
# from what a build would actually use.
#
# KERNEL_CONFIG matters and is stated, not assumed: the shipping kernel carries
# the sysrq fragment, and a different fragment set is a different tree.
KERNEL_CONFIG=${KERNEL_CONFIG:-sysrq}
export KERNEL_CONFIG
tree=$(cd "$ROOT" && tools/build/build.sh kernel-tree 2>/dev/null)
echo "    config: KERNEL_CONFIG=$KERNEL_CONFIG"
ko=$(find "$tree" -name sunxi-cedrus.ko -print -quit 2>/dev/null)

if [ -z "${ko:-}" ]; then
	echo "    no module built for this configuration -- expected it under"
	echo "    ${tree:-<build.sh could not name a tree>}"
	echo "    fix: KERNEL_CONFIG=$KERNEL_CONFIG tools/build/build.sh kernel"
	drift=1
else
	host_md5=$(md5sum "$ko" | cut -d' ' -f1)
	board_md5=$($SSH 'md5sum $(modinfo -n sunxi_cedrus 2>/dev/null) 2>/dev/null | cut -d" " -f1')
	echo "    host  $(basename "$tree" | cut -c1-30)  $host_md5"
	echo "    board $board_md5"
	if [ "$host_md5" = "$board_md5" ]; then
		echo "    MATCH"
	else
		echo "    DRIFT — the board is not running this build."
		echo "    fix: tools/install-kernel-module.sh $tree sunxi-cedrus"
		drift=1
	fi

	# A module with no parameters at all is the specific shape of the
	# original failure, so name it rather than leaving it to be noticed.
	params=$($SSH 'ls /sys/module/sunxi_cedrus/parameters/ 2>/dev/null | tr "\n" " "')
	echo "    parameters: ${params:-<none>}"
fi

echo
echo "=== VA-API driver (libva-v4l2-request) ==="

series_id=$(while read -r p; do
	[ -n "$p" ] && sha256sum "$ROOT/patches/libva-v4l2-request/$p"
done < "$ROOT/patches/libva-v4l2-request/series" | sha256sum | cut -c1-16)

board_id=$($SSH 'sed -n "s/^va_driver_series=//p" /etc/h713-video-stack 2>/dev/null')
board_when=$($SSH 'sed -n "s/^va_driver_installed=//p" /etc/h713-video-stack 2>/dev/null')

echo "    series now  $series_id ($(grep -c . "$ROOT/patches/libva-v4l2-request/series") patches)"
if [ -z "$board_id" ]; then
	echo "    board       <unstamped>"
	echo "    DRIFT — the installed driver predates stamping, so it cannot be"
	echo "    identified. Reinstall to establish provenance:"
	echo "    fix: tools/video/build-va-driver.sh --install --test"
	drift=1
elif [ "$board_id" = "$series_id" ]; then
	echo "    board       $board_id (installed $board_when)"
	echo "    MATCH"
else
	echo "    board       $board_id (installed $board_when)"
	echo "    DRIFT — the installed driver was built from a different series."
	echo "    fix: tools/video/build-va-driver.sh --install --test"
	drift=1
fi

echo
echo "=== mpv (stock) and audio (PipeWire) ==="

# The direct DRM-PRIME path (patches/mpv, /usr/local/bin/mpv) was RETIRED on
# 2026-10-02: playback is stock Debian mpv on the GPU path (docs/gpu-fallback-
# plan.md, WP2 decision), with audio through PipeWire as the user "media"
# (docs/audio-underrun-deadlock.md). The patched build is kept on the board as
# /usr/local/bin/mpv-direct for the HDMI-in preview tooling only. Check that
# what a plain `mpv` runs is the stock binary and that its audio reaches
# PipeWire: a PATH shadow, or a missing PIPEWIRE_RUNTIME_DIR, silently puts
# playback back on mpv's ALSA output and its underrun deadlock.
mpv_path=$($SSH 'command -v mpv 2>/dev/null')
pw_dir=$($SSH 'echo "$PIPEWIRE_RUNTIME_DIR"')
pw_state=$($SSH 'systemctl --machine=media@.host --user is-active pipewire wireplumber 2>/dev/null | tr "\n" " "')
ao=$($SSH 'mpv --no-config --vo=null -v --length=0.3 av://lavfi:sine=duration=0.3 2>&1 | grep -aoE "AO: \[[a-z]+\]" | head -1')
echo "    mpv         ${mpv_path:-<none>}"
echo "    PipeWire    dir=${pw_dir:-<unset>} services: ${pw_state:-<none>}"
echo "    mpv audio   ${ao:-<not determined>}"
if [ "$mpv_path" != "/usr/bin/mpv" ]; then
	echo "    DRIFT — plain mpv is not the stock build (a retired direct-path"
	echo "    binary back on PATH?). fix: rename it, e.g. to /usr/local/bin/mpv-direct"
	drift=1
fi
if [ "$pw_state" != "active active " ]; then
	echo "    DRIFT — PipeWire is not running as user media."
	echo "    fix: loginctl enable-linger media (see tools/rootfs/customize.sh)"
	drift=1
fi
case "$ao" in
	*pipewire*) ;;
	"") echo "    DRIFT — mpv opened no audio output for a generated tone."
	    drift=1 ;;
	*) echo "    DRIFT — mpv chose $ao, not PipeWire: playback is on mpv's ALSA output."
	   drift=1 ;;
esac

echo
echo "=== what the driver actually offers ==="
$SSH 'LIBVA_DRIVER_NAME=v4l2_request vainfo 2>/dev/null |
	grep -E "VAProfile" | sed "s/^/    /"' || echo "    vainfo failed"

echo
if [ "$drift" -eq 0 ]; then
	echo "STACK: in sync with the tree"
else
	echo "STACK: DRIFT — results from this board describe something other than this tree"
fi
exit "$drift"
