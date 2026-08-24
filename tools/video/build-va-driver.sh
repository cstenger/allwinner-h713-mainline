#!/usr/bin/env bash
# Build and install the VA-API driver on the board, reproducibly. RUNS ON THE HOST.
#
# WHY THIS EXISTS. Hardware video decode on this board depends on a .so that
# was, until now, built by hand: clone a pull request, apply five patches,
# meson, ninja, copy it into /usr/lib/.../dri/. Nothing in the rootfs build
# produces it, so **a fresh flash silently loses hardware decode** and the way
# back lives in somebody's shell history. That is the last thing standing
# between "decode works" and "decode ships".
#
# THE BUILD HAS TO HAPPEN ON THE BOARD, and not for convenience: the driver's
# entry point is __vaDriverInit_<major>_<minor>, derived from the libva
# pkg-config version at compile time. A host build against libva 1.24 produces
# a library the board's 1.22 loader will not call -- it dlopens, finds no
# matching symbol, and falls back to software with no error that names the
# cause. This script verifies the symbol against the board's own libva rather
# than trusting that.
#
# The board has no git, so the patch series is applied HERE and the tree is
# shipped over as a tarball.
#
#   usage: tools/video/build-va-driver.sh [--install] [--test]
#          BOARD=192.168.4.1 tools/video/build-va-driver.sh --install --test
#
# Without --install it builds and verifies but leaves the running driver alone.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
SRC=${SRC:-$ROOT/local/upstream/va-driver-src}
PATCHES=$ROOT/patches/libva-v4l2-request
UPSTREAM=https://github.com/bootlin/libva-v4l2-request
PR=38
BASE=1c5f2cad21dff3b56d35355082867c24e4f191c6
DRI=/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so

install=0; test=0
for arg in "$@"; do
	case $arg in
	--install) install=1 ;;
	--test) test=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 1 ;;
	esac
done

# --- 1. the source tree, patched, on the host -------------------------------
if [ ! -d "$SRC/.git" ]; then
	echo "==> cloning $UPSTREAM (PR #$PR)"
	git clone -q "$UPSTREAM" "$SRC"
	git -C "$SRC" fetch -q origin "refs/pull/$PR/head:pr$PR"
fi

echo "==> checking out the pinned base and applying the series"
git -C "$SRC" checkout -q "pr$PR"
git -C "$SRC" reset -q --hard "$BASE"
git -C "$SRC" clean -qfd

# Applied in series order, and the series file is the authority -- a patch on
# disk that nobody listed is not part of the driver.
while read -r patch; do
	[ -n "$patch" ] || continue
	# Some of these carry no mail headers, so `git am` cannot author them;
	# apply and commit instead, which works for both shapes.
	git -C "$SRC" apply "$PATCHES/$patch"
	git -C "$SRC" add -A
	git -C "$SRC" -c user.name=build -c user.email=build@localhost \
		commit -q -m "$patch"
	echo "    $patch"
done < "$PATCHES/series"

# --- 2. build it on the board ----------------------------------------------
echo "==> shipping the tree to $BOARD and building there"
$SSH 'rm -rf /root/va-driver-build && mkdir -p /root/va-driver-build'
tar -C "$SRC" --exclude .git -cz . | $SSH 'tar -xz -C /root/va-driver-build'

# The board's clock can trail the host's after a power cycle, and meson refuses
# to configure a tree whose files are dated in the future ("Clock skew
# detected"). Restamping costs nothing and removes a confusing failure.
$SSH 'cd /root/va-driver-build && find . -exec touch {} + &&
      rm -rf build && meson setup build >/dev/null && ninja -C build' 2>&1 |
	tail -3

# --- 3. verify the entry point against the board's own libva ---------------
echo "==> verifying the entry-point symbol"
$SSH 'set -e
	cd /root/va-driver-build
	want=$(pkg-config --modversion libva | cut -d. -f1,2 | tr . _)
	if nm -D --defined-only build/src/v4l2_request_drv_video.so |
	   grep -q "__vaDriverInit_$want"; then
		echo "    __vaDriverInit_$want present, matching libva $(pkg-config --modversion libva)"
	else
		echo "    ERROR: built driver exports"
		nm -D --defined-only build/src/v4l2_request_drv_video.so |
			grep vaDriverInit || echo "      (no vaDriverInit symbol at all)"
		echo "    but this board needs __vaDriverInit_$want"
		exit 1
	fi'

if [ "$install" -eq 0 ]; then
	echo "==> built and verified; NOT installed (pass --install)"
	exit 0
fi

# --- 4. install, keeping the outgoing driver ------------------------------
stamp=$(date +%Y%m%d-%H%M%S)
echo "==> installing"
$SSH "set -e
	[ -f $DRI ] && cp $DRI $DRI.$stamp.bak && echo '    kept the outgoing driver at $DRI.$stamp.bak'
	cp /root/va-driver-build/build/src/v4l2_request_drv_video.so $DRI
	sync"

# Record WHAT was installed, so drift can be detected later. This project has
# already lost a session to a board running a cedrus module that predated two
# patches which had been in series for weeks, with nothing anywhere able to say
# so. A stamp turns that from an archaeology problem into one command.
echo "==> stamping the install"
series_id=$(cat "$PATCHES/series" | while read -r p; do
	[ -n "$p" ] && sha256sum "$PATCHES/$p"
done | sha256sum | cut -c1-16)
$SSH "cat > /etc/h713-video-stack <<EOF
# Written by tools/video/build-va-driver.sh -- do not edit by hand.
va_driver_series=$series_id
va_driver_installed=$stamp
va_driver_patches=$(wc -l < "$PATCHES/series")
EOF"
echo "    series id $series_id"

echo "==> vainfo says:"
$SSH "LIBVA_DRIVER_NAME=v4l2_request vainfo 2>/dev/null |
	grep -E 'vainfo: Driver|VAProfile' | sed 's/^/    /'"

if [ "$test" -eq 1 ]; then
	echo "==> gates"
	$SSH 'cd /root/video-test &&
	      ./hevc-decode-test.sh 2>&1 | tail -2 &&
	      ./va-decode-test.sh 2>&1 | tail -1 &&
	      ./hevc-10bit-test.sh 2>&1 | tail -1'
fi
