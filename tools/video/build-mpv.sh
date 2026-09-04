#!/usr/bin/env bash
# Build and install the patched mpv for the board, reproducibly. RUNS ON THE HOST.
#
# WHY THIS EXISTS. The direct DRM-PRIME video path is a downstream mpv patch
# (patches/mpv/). Without this script the only artifact is one unversioned
# binary in /root on the board, reproducible solely by hand-following a README --
# the same failure mode build-va-driver.sh was written to end for the VA driver,
# where a fresh flash silently loses hardware decode.
#
# WHY IT DOES NOT BUILD ON THE BOARD, unlike build-va-driver.sh. The board's
# rootfs is 2.7 GB at ~97% full and it has no internet, so it can neither hold an
# mpv build tree nor install the ~10 build dependencies. That was measured, not
# assumed: freeing 126 MB of stale kernel images was nowhere near enough.
#
# WHAT WE GIVE UP, AND HOW WE BUY IT BACK. Building off-target loses the
# guarantee that the result links against the board's own libraries. Two gates
# replace it:
#   * the built binary must be an aarch64 ELF containing the patch's marker
#     string -- a series that failed to apply would otherwise install a stock
#     mpv and look like success until someone read the logs;
#   * after installing, `ldd` runs ON THE BOARD and any "not found" is fatal.
#     mpv links libdisplay-info.so.2, which happened to be present; nothing
#     guarantees the next dependency will be.
#
# INSTALLS TO /usr/local/bin, not /usr/bin. Debian owns /usr/bin/mpv, so
# overwriting it means the next apt upgrade quietly reverts the video path.
# /usr/local/bin precedes /usr/bin in the board's PATH.
#
#   usage: tools/video/build-mpv.sh [--install] [--test] [--rebuild-rootfs]
#          BOARD=192.168.4.1 tools/video/build-mpv.sh --install --test
#
# Without --install it builds and verifies but leaves the running mpv alone.
# The ~1.1 GB arm64 rootfs is cached and reused; --rebuild-rootfs forces it,
# which is what you want after changing DEPS below.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
SRC=${SRC:-$ROOT/local/upstream/mpv-src}
WORK=${WORK:-$ROOT/local/upstream/mpv-arm64}
PATCHES=$ROOT/patches/mpv
UPSTREAM=https://github.com/mpv-player/mpv.git
TAG=v0.40.0
BASE=e48ac7ce08462f5e33af6ef9deeac6fa87eef01e
DEST=/usr/local/bin/mpv
SUITE=trixie

# From mpv's own meson.build, not guessed -- an earlier guess omitted
# libavfilter, libplacebo and libass and cost three round trips. libdisplay-info
# is required by -Ddrm=enabled alongside libdrm (meson.build:934) and is the
# easiest of the set to miss.
DEPS=build-essential,meson,ninja-build,pkg-config,ca-certificates,\
libavcodec-dev,libavfilter-dev,libavformat-dev,libavutil-dev,\
libswresample-dev,libswscale-dev,libplacebo-dev,libass-dev,\
libasound2-dev,libva-dev,libdrm-dev,libdisplay-info-dev

MARKER='Using direct DRM PRIME video-plane scanout'

install=0; test=0; rebuild=0
for arg in "$@"; do
	case $arg in
	--install) install=1 ;;
	--test) test=1 ;;
	--rebuild-rootfs) rebuild=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 1 ;;
	esac
done

# `--test` on its own gates WHAT IS ON THE BOARD, and skips the build entirely.
# Otherwise checking a gate cost a 20-minute emulated rebuild, which is enough
# friction that the gate stops being run.
build=1
[ "$test" -eq 1 ] && [ "$install" -eq 0 ] && build=0

if [ "$build" -eq 1 ]; then

# --- 0. host prerequisites --------------------------------------------------
# Each of these cost a debugging round when absent, so name them precisely.
echo "==> checking host prerequisites"
fatal=0
command -v mmdebstrap >/dev/null || { echo "    missing: mmdebstrap"; fatal=1; }
[ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] || {
	echo "    missing: binfmt qemu-aarch64 (install qemu-user-static + binfmt support)"; fatal=1; }
# The F flag preloads the interpreter into the kernel, which is what lets an
# aarch64 chroot run without copying a qemu binary into it.
if [ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] &&
   ! grep -q 'flags:.*F' /proc/sys/fs/binfmt_misc/qemu-aarch64; then
	echo "    binfmt qemu-aarch64 lacks the F flag; the chroot will need qemu copied in"
fi
# This one is the whole reason the first four attempts failed: without the
# keyring INSTALLED (a cached .pkg.tar.zst is not enough) apt rejects every
# Debian repository as unsigned, and no --keyring value fixes it.
[ -e /usr/share/keyrings/debian-archive-keyring.gpg ] || {
	echo "    missing: /usr/share/keyrings/debian-archive-keyring.gpg"
	echo "      sudo pacman -U $ROOT/build/cache/debian-archive-keyring/debian-archive-keyring-*.pkg.tar.zst"
	echo "      (or your distro's debian-archive-keyring package)"
	fatal=1; }
unshare -r true 2>/dev/null || { echo "    missing: unprivileged user namespaces"; fatal=1; }
[ "$fatal" -eq 0 ] || exit 1
echo "    ok"

# --- 1. the source tree, patched --------------------------------------------
if [ ! -d "$SRC/.git" ]; then
	echo "==> cloning $UPSTREAM ($TAG)"
	git clone -q --branch "$TAG" "$UPSTREAM" "$SRC"
fi

echo "==> checking out the pinned commit and applying the series"
git -C "$SRC" reset -q --hard "$BASE"
git -C "$SRC" clean -qfd
# The series file is the authority: a patch on disk that nobody listed is not
# part of this build.
while read -r patch; do
	[ -n "$patch" ] || continue
	git -C "$SRC" apply "$PATCHES/$patch"
	git -C "$SRC" add -A
	git -C "$SRC" -c user.name=build -c user.email=build@localhost \
		commit -q -m "$patch"
	echo "    $patch"
done < "$PATCHES/series"

# --- 2. the arm64 build environment ----------------------------------------
mkdir -p "$WORK"
TARBALL=$WORK/rootfs.tar
if [ "$rebuild" -eq 1 ] || [ ! -f "$TARBALL" ]; then
	echo "==> building the arm64 $SUITE rootfs (~1.1 GB, a few minutes)"
	rm -f "$TARBALL"
	# --skip=check/qemu: arch-test is a Debian package with no Arch equivalent,
	# and binfmt was already verified above.
	# Output must be a TARBALL: writing a directory tree under $HOME fails with
	# "Permission denied" in --mode=unshare.
	mmdebstrap --mode=unshare --architecture=arm64 --variant=apt \
		--skip=check/qemu --include="$DEPS" "$SUITE" "$TARBALL"
else
	echo "==> reusing cached rootfs ($TARBALL); --rebuild-rootfs to refresh"
fi

echo "==> unpacking the rootfs and staging the source"
RFS=$WORK/root
rm -rf "$RFS"; mkdir -p "$RFS"
# Extract inside a user namespace so the archive's root-owned files map to us.
unshare -r tar -xf "$TARBALL" -C "$RFS" 2>/dev/null || true
[ -d "$RFS/usr/lib/aarch64-linux-gnu" ] || { echo "    rootfs looks wrong"; exit 1; }
rm -rf "$RFS/build-mpv"
cp -a "$SRC" "$RFS/build-mpv"
rm -rf "$RFS/build-mpv/.git"

cat > "$RFS/do-build.sh" <<'EOS'
#!/bin/bash
set -e
cd /build-mpv
meson setup build --buildtype=release -Dauto_features=disabled \
	-Dalsa=enabled -Ddrm=enabled -Dgl=disabled -Dlibmpv=false \
	-Dvaapi=enabled -Dvaapi-drm=enabled
ninja -C build mpv
EOS
chmod +x "$RFS/do-build.sh"

# NOTE: apt does NOT work inside this emulated chroot -- it fails with
# "Sub-process http returned an error code (112)". To add a dependency, put it
# in DEPS above and re-run with --rebuild-rootfs. Do not try to apt-get here.
echo "==> building mpv under emulation (slow; ~230 compile steps)"
unshare -r --mount --pid --fork chroot "$RFS" /bin/bash -c \
	'mount -t proc proc /proc 2>/dev/null; /do-build.sh' 2>&1 | tail -3

BIN=$RFS/build-mpv/build/mpv

# --- 3. verify the artifact -------------------------------------------------
echo "==> verifying the built binary"
[ -f "$BIN" ] || { echo "    ERROR: no binary produced"; exit 1; }
# Process substitution, NOT a pipe. `producer | grep -q` makes grep exit at the
# first match, the producer takes SIGPIPE, and `set -o pipefail` reports the
# whole pipeline as failed -- so a correct binary is rejected. This cost one
# full container build to find.
grep -q 'ARM aarch64' < <(file "$BIN") || {
	echo "    ERROR: not an aarch64 binary"; exit 1; }
grep -qF "$MARKER" < <(strings -a "$BIN") || {
	echo "    ERROR: built mpv has no direct-path marker."
	echo "    The series applied but the feature is absent -- treat this as a"
	echo "    failed build, not a working mpv."
	exit 1; }
echo "    aarch64 ELF with the direct DRM PRIME path present"

if [ "$install" -eq 0 ]; then
	echo "==> built and verified; NOT installed (pass --install)"
	exit 0
fi

fi  # build

if [ "$install" -eq 1 ]; then

# --- 4. install, keeping whatever was there --------------------------------
stamp=$(date +%Y%m%d-%H%M%S)
echo "==> installing to $BOARD:$DEST"
scp -q "$BIN" "root@$BOARD:/tmp/mpv-staged.$stamp"
# An 'a && b' chain, not an if, would abort under set -e on a board that has no
# mpv yet -- the first install is exactly when you least want a spurious failure.
$SSH "set -e
	if [ -f $DEST ]; then
		cp $DEST $DEST.$stamp.bak
		echo '    kept the outgoing binary at $DEST.$stamp.bak'
	fi
	install -m 0755 /tmp/mpv-staged.$stamp $DEST
	rm -f /tmp/mpv-staged.$stamp
	sync
	echo \"    which mpv -> \$(command -v mpv)\""

# --- 5. the gate that replaces building on target --------------------------
# Building off-target cannot guarantee the result links against the board's
# libraries, so check it directly rather than hoping. mpv links
# libdisplay-info.so.2 today only because something else in the image pulls it
# in; nothing promises the next dependency will be there.
echo "==> checking runtime links on the board"
$SSH "set -e
	missing=\$(ldd $DEST 2>/dev/null | grep 'not found' || true)
	if [ -n \"\$missing\" ]; then
		echo '    ERROR: unresolved libraries on the board:'
		echo \"\$missing\" | sed 's/^/      /'
		exit 1
	fi
	echo \"    all \$(ldd $DEST | wc -l) libraries resolve\""

echo "==> stamping the install"
series_id=$(while read -r p; do
	[ -n "$p" ] && sha256sum "$PATCHES/$p"
done < "$PATCHES/series" | sha256sum | cut -c1-16)
$SSH "touch /etc/h713-video-stack
	sed -i '/^mpv_/d' /etc/h713-video-stack
	cat >> /etc/h713-video-stack <<EOF
mpv_series=$series_id
mpv_installed=$stamp
mpv_base=$BASE
mpv_patches=$(grep -c . "$PATCHES/series")
EOF"
echo "    series id $series_id"

fi  # install

# --- 6. optional: prove the direct path on hardware ------------------------
if [ "$test" -eq 1 ]; then
	echo "==> testing the direct path"
	$SSH 'set -e
		# Pick a plain 720p clip on purpose. The first *.h264 alphabetically is
		# r02-resolution-change, which is a decoder torture case -- a failure
		# there would say nothing about whether the display path works.
		for c in /root/leota-720p.h264 \
			 /root/video-test/v02-1280x720-baseline.h264 \
			 /root/video-test/*.h264; do
			[ -f "$c" ] && clip=$c && break
		done
		[ -n "${clip:-}" ] || { echo "    no test clip on the board"; exit 1; }
		echo "    clip: $clip"
		# Loop, so the player is still running when the plane is sampled. The
		# previous version played 5 seconds and then read only the mpv log.
		cat > /tmp/mpv-direct-test.sh <<EOF
export LIBVA_DRIVER_NAME=v4l2_request
exec mpv --no-config --no-audio --vo=drm --hwdec=vaapi --loop-file=inf \
    --msg-level=all=v "$clip"
EOF
		dmesg_mark=$(dmesg | wc -l)
		setsid bash /tmp/mpv-direct-test.sh </dev/null >/tmp/mpv-direct-test.log 2>&1 &
		sleep 12

		# WHAT THE KERNEL SEES, not what mpv claims. mpv prints the direct-path
		# message when it SELECTS the path, not when a frame reaches the screen.
		# A version of this driver dropped every PRIME frame in flip_page() and
		# never programmed the plane: mpv logged the direct path, every atomic
		# commit succeeded, audio played, and the panel was black -- and the
		# log-only gate below reported PASS. Read the plane instead.
		plane=$(sed -n "s/.*Using [a-z]* plane \([0-9]*\) as drmprime plane.*/\1/p" \
			/tmp/mpv-direct-test.log | head -1)
		state=$(ls /sys/kernel/debug/dri/*/state 2>/dev/null | head -1)
		if [ -n "$plane" ] && [ -n "$state" ]; then
			blk1=$(grep -A2 "^plane\[$plane\]:" "$state" | head -3)
			pcrtc=$(echo "$blk1" | sed -n "s/.*crtc=//p" | head -1)
			pfb1=$(echo "$blk1" | sed -n "s/.*fb=//p" | head -1)
			sleep 3
			pfb2=$(grep -A2 "^plane\[$plane\]:" "$state" | head -3 |
				sed -n "s/.*fb=//p" | head -1)
		fi
		holes=$(grep -c "Hole in swapchain?" /tmp/mpv-direct-test.log || true)
		fails=$(grep -c "hardware accelerator failed" /tmp/mpv-direct-test.log || true)
		kerr=$(dmesg | tail -n +$((dmesg_mark + 1)) |
			grep -cE "Page fault|timed out|iommu" || true)
		pkill -x mpv 2>/dev/null || true

		grep -iE "Using hardware decoding|VO: \[drm\]|direct DRM PRIME" \
			/tmp/mpv-direct-test.log | sed "s/^/    /"
		echo "    video plane:     ${plane:-<none reported>}"
		echo "    plane crtc:      ${pcrtc:-<unread>}"
		echo "    plane fb:        ${pfb1:-<unread>} then ${pfb2:-<unread>}"
		echo "    swapchain holes: $holes"
		echo "    decode failures: $fails"
		echo "    new kernel faults/timeouts: $kerr"

		ok=1
		grep -q "Using hardware decoding (vaapi)" /tmp/mpv-direct-test.log || ok=0
		grep -q "vaapi\[nv12\]" /tmp/mpv-direct-test.log || ok=0
		grep -qF "direct DRM PRIME video-plane scanout" /tmp/mpv-direct-test.log || ok=0
		# The plane must exist, be attached to a CRTC, hold a framebuffer, and
		# that framebuffer must CHANGE -- a frozen fb id is a still picture, which
		# looks identical to working video in every log line mpv emits.
		[ -n "${plane:-}" ] || { echo "    no drmprime plane reported"; ok=0; }
		[ -n "${pcrtc:-}" ] && [ "${pcrtc:-}" != "(null)" ] ||
			{ echo "    the video plane is not attached to a CRTC"; ok=0; }
		[ -n "${pfb1:-}" ] && [ "${pfb1:-0}" != "0" ] ||
			{ echo "    the video plane holds no framebuffer -- nothing is displayed"; ok=0; }
		[ "${pfb1:-x}" != "${pfb2:-y}" ] ||
			{ echo "    the video plane framebuffer never changed -- frames are not flipping"; ok=0; }
		[ "$holes" = 0 ] ||
			{ echo "    frames are being dropped before the flip"; ok=0; }
		[ "$fails" = 0 ] || ok=0
		[ "$kerr" = 0 ] ||
			{ echo "    the kernel logged faults or timeouts during playback"; ok=0; }

		if [ "$ok" = 1 ]; then
			echo "    PASS -- decoded frames are on the video plane and flipping"
		else
			echo "    FAIL -- see /tmp/mpv-direct-test.log on the board"
			exit 1
		fi'
fi
