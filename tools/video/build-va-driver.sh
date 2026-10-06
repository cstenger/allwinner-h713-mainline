#!/usr/bin/env bash
# Build and install the VA-API driver on the board, reproducibly. RUNS ON THE HOST.
#
# The driver is megi's libva-v4l2_request (https://xff.cz/git/libva-v4l2_request/)
# at a pinned commit, plus patches/libva-v4l2_request/. It replaced bootlin's
# PR #38 on 2026-10-03; that build is tools/video/build-va-driver-bootlin.sh.
#
# WHY THIS EXISTS. Hardware video decode on this board depends on a .so that
# was, until now, built by hand: clone a pull request, apply the patch series,
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
#          tools/video/build-va-driver.sh --tree-tar FILE
#
# Without --install it builds and verifies but leaves the running driver alone.
# --tree-tar only writes the patched tree (no .git) to FILE, with an
# h713-va-driver.stamp of the series id, and never touches a board: it is how
# tools/rootfs/build.sh gets the source it compiles inside the image.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
# Not local/upstream/va-driver-src: that is the retired bootlin tree, and this
# script resets its tree hard.
SRC=${SRC:-$ROOT/local/upstream/va-driver-megi-src}
PATCHES=$ROOT/patches/libva-v4l2_request
UPSTREAM=https://xff.cz/git/libva-v4l2_request/
BASE=cac6ece0e23ac1f944dd3af266680aff0c3184df
DRI=/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so

install=0; test=0; tree_tar=
while [ $# -gt 0 ]; do
	case $1 in
	--install) install=1 ;;
	--test) test=1 ;;
	--tree-tar) tree_tar=${2:?--tree-tar needs a FILE}; shift ;;
	*) echo "unknown argument: $1" >&2; exit 1 ;;
	esac
	shift
done

# The identity of the patch series, stamped into /etc/h713-video-stack by both
# the board install and the rootfs build.
series_id() {
	while read -r p; do
		[ -n "$p" ] && sha256sum "$PATCHES/$p"
	done < "$PATCHES/series" | sha256sum | cut -c1-16
}

# --- 1. the source tree, patched, on the host -------------------------------
if [ ! -d "$SRC/.git" ]; then
	echo "==> cloning $UPSTREAM"
	git clone -q "$UPSTREAM" "$SRC"
fi

echo "==> checking out the pinned base and applying the series"
git -C "$SRC" checkout -q --detach "$BASE"
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

if [ -n "$tree_tar" ]; then
	printf 'va_driver_series=%s\nva_driver_patches=%s\nva_driver_base=%s\n' \
		"$(series_id)" "$(grep -c . "$PATCHES/series")" "$BASE" > "$SRC/h713-va-driver.stamp"
	tar -C "$SRC" --exclude .git -czf "$tree_tar" .
	rm -f "$SRC/h713-va-driver.stamp"
	echo "==> patched tree written to $tree_tar"
	exit 0
fi

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
series_id=$(series_id)
# Append after stripping our own keys, NOT '>' over the whole file: build-mpv.sh
# stamps the same file with mpv_* keys, and truncating here silently erased them.
$SSH "touch /etc/h713-video-stack
	grep -q '^# Written by' /etc/h713-video-stack ||
		sed -i '1i # Written by tools/video/build-*.sh -- do not edit by hand.' \
			/etc/h713-video-stack
	sed -i '/^va_driver_/d' /etc/h713-video-stack
	cat >> /etc/h713-video-stack <<EOF
va_driver_series=$series_id
va_driver_installed=$stamp
va_driver_patches=$(grep -c . "$PATCHES/series")
EOF"
echo "    series id $series_id"

echo "==> vainfo says:"
$SSH "LIBVA_DRIVER_NAME=v4l2_request vainfo 2>/dev/null |
	grep -E 'vainfo: Driver|VAProfile' | sed 's/^/    /'"

if [ "$test" -eq 1 ]; then
	echo "==> gates"
	# The whole regression suite against the INSTALLED driver: every codec,
	# AV1 8/10-bit, seek loops, resolution changes, concurrency (~6 min).
	$SSH 'sh /root/va-regress.sh dmabuf 2>&1 | tail -22'
fi
