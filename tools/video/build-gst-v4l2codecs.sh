#!/usr/bin/env bash
# Build and install the patched GStreamer v4l2codecs plugin for the board.
# RUNS ON THE HOST.
#
# WHAT AND WHY. The H713's AV1 core writes 10-bit pictures as P010 with the
# samples in the LOW bits (V4L2_PIX_FMT_P010_LSB, kernel patch 0150). Stock
# v4l2codecs does not know that pixel format, so v4l2slav1dec cannot negotiate
# 10-bit output. patches/gstreamer/ teaches it the format, as DMA_DRM
# "P010:0x0900000000000002", which kmssink can scan out zero-copy.
#
# ONLY THE ONE PLUGIN. The board runs Debian 13's GStreamer 1.26.2 and its
# system libraries stay untouched: this builds gst-plugins-bad 1.26.2 with
# every feature off except v4l2codecs, against the distro's own 1.26.2 dev
# packages, and installs libgstv4l2codecs.so to /opt/gst-h713/plugins/. The
# plugin links libgstcodecs-1.0.so.0 by soname, so it uses the board's copy.
#
# OFF-TARGET, like build-mpv.sh and for the same reason: the board's rootfs is
# nearly full and has no internet. An arm64 trixie rootfs under qemu-user does
# the build; the gates below replace building on the target.
#
# SELECTING IT. GStreamer keeps the FIRST plugin of a given name it finds on
# its path, so /opt/gst-h713/plugins must come first:
#   GST_PLUGIN_SYSTEM_PATH_1_0=/opt/gst-h713/plugins:/usr/lib/aarch64-linux-gnu/gstreamer-1.0
# /opt/gst-h713/env exports exactly that; source it. --test checks which file
# gst-inspect actually loaded rather than trusting the order.
#
#   usage: tools/video/build-gst-v4l2codecs.sh [--install] [--test] [--rebuild-rootfs]
#          BOARD=192.168.4.1 tools/video/build-gst-v4l2codecs.sh --install --test
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# shellcheck source=../../config/paths.sh
source "$ROOT/config/paths.sh"
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -F /dev/null -o ConnectTimeout=8 root@$BOARD"
SCP="scp -F /dev/null -q"
SRC=${SRC:-$ROOT/local/upstream/gstreamer-src}
WORK=${WORK:-$ROOT/local/upstream/gst-arm64}
PATCHES=$ROOT/patches/gstreamer
UPSTREAM=https://github.com/GStreamer/gstreamer.git
TAG=1.26.2
BASE=100c21e1faf68efe7f3830b6e9f856760697ab48
SUB=subprojects/gst-plugins-bad
DEST_DIR=/opt/gst-h713/plugins
SYS_DIR=/usr/lib/aarch64-linux-gnu/gstreamer-1.0
SUITE=trixie

DEPS=build-essential,meson,ninja-build,pkg-config,ca-certificates,\
libgstreamer1.0-dev,libgstreamer-plugins-base1.0-dev,libgudev-1.0-dev,\
libdrm-dev

# A debug string the patch adds. Its absence means the series did not apply.
MARKER='Allwinner LSB-aligned P010'

install=0; test=0; rebuild=0
for arg in "$@"; do
	case $arg in
	--install) install=1 ;;
	--test) test=1 ;;
	--rebuild-rootfs) rebuild=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 1 ;;
	esac
done

build=1
[ "$test" -eq 1 ] && [ "$install" -eq 0 ] && build=0

if [ "$build" -eq 1 ]; then

echo "==> checking host prerequisites"
fatal=0
command -v mmdebstrap >/dev/null || { echo "    missing: mmdebstrap"; fatal=1; }
[ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] || {
	echo "    missing: binfmt qemu-aarch64"; fatal=1; }
[ -e /usr/share/keyrings/debian-archive-keyring.gpg ] || {
	echo "    missing: /usr/share/keyrings/debian-archive-keyring.gpg (see build-mpv.sh)"; fatal=1; }
unshare -r true 2>/dev/null || { echo "    missing: unprivileged user namespaces"; fatal=1; }
[ "$fatal" -eq 0 ] || exit 1
echo "    ok"

# --- 1. the source tree, patched --------------------------------------------
# The monorepo is large; only gst-plugins-bad is checked out. GitHub is the
# official mirror -- freedesktop's GitLab sits behind bot protection.
if [ ! -d "$SRC/.git" ]; then
	echo "==> cloning $UPSTREAM ($TAG, gst-plugins-bad only)"
	git clone -q --depth 1 --branch "$TAG" --filter=blob:none --sparse \
		"$UPSTREAM" "$SRC"
	git -C "$SRC" sparse-checkout set "$SUB"
fi

echo "==> checking out the pinned commit and applying the series"
git -C "$SRC" reset -q --hard "$BASE"
git -C "$SRC" clean -qfd
# The series file is the authority. 0001/0002 (cedrus scaling) are on disk but
# not listed: they have never been deployed or tested on the board.
while read -r patch; do
	[ -n "$patch" ] || continue
	git -C "$SRC" apply "$PATCHES/$patch"
	echo "    $patch"
done < "$PATCHES/series"

# --- 2. the arm64 build environment ----------------------------------------
mkdir -p "$WORK"
TARBALL=$WORK/rootfs.tar
if [ "$rebuild" -eq 1 ] || [ ! -f "$TARBALL" ]; then
	echo "==> building the arm64 $SUITE rootfs"
	rm -f "$TARBALL"
	mmdebstrap --mode=unshare --architecture=arm64 --variant=apt \
		--skip=check/qemu --include="$DEPS" "$SUITE" "$TARBALL"
else
	echo "==> reusing cached rootfs ($TARBALL); --rebuild-rootfs to refresh"
fi

echo "==> unpacking the rootfs and staging the source"
RFS=$WORK/root
rm -rf "$RFS"; mkdir -p "$RFS"
unshare -r tar -xf "$TARBALL" -C "$RFS" 2>/dev/null || true
[ -d "$RFS/usr/lib/aarch64-linux-gnu" ] || { echo "    rootfs looks wrong"; exit 1; }
rm -rf "$RFS/build-gst"
cp -a "$SRC/$SUB" "$RFS/build-gst"

# The dev packages must be the version the board runs: a plugin built against
# other headers can load and then misbehave.
cat > "$RFS/do-build.sh" <<'EOS'
#!/bin/bash
set -e
v=$(pkg-config --modversion gstreamer-1.0)
echo "    distro GStreamer $v"
[ "$v" = 1.26.2 ] || { echo "    ERROR: expected 1.26.2"; exit 1; }
cd /build-gst
meson setup build --buildtype=release -Dauto_features=disabled \
	-Dv4l2codecs=enabled -Dexamples=disabled -Dtests=disabled \
	-Dintrospection=disabled -Dnls=disabled -Dorc=disabled
ninja -C build sys/v4l2codecs/libgstv4l2codecs.so
EOS
chmod +x "$RFS/do-build.sh"

echo "==> building v4l2codecs under emulation"
unshare -r --mount --pid --fork chroot "$RFS" /bin/bash -c \
	'mount -t proc proc /proc 2>/dev/null; /do-build.sh' 2>&1 | tail -5

SO=$RFS/build-gst/build/sys/v4l2codecs/libgstv4l2codecs.so

# --- 3. verify the artifact -------------------------------------------------
echo "==> verifying the built plugin"
[ -f "$SO" ] || { echo "    ERROR: no plugin produced"; exit 1; }
grep -q 'ARM aarch64' < <(file -L "$SO") || { echo "    ERROR: not aarch64"; exit 1; }
grep -qF "$MARKER" < <(strings -a "$SO") || {
	echo "    ERROR: the plugin has no P010_LSB support -- the series did not land"
	exit 1; }
mkdir -p "$WORK/out"
cp -L "$SO" "$WORK/out/libgstv4l2codecs.so"
echo "    aarch64 plugin with P010_LSB support: $WORK/out/libgstv4l2codecs.so"

if [ "$install" -eq 0 ]; then
	echo "==> built and verified; NOT installed (pass --install)"
	exit 0
fi

fi  # build

if [ "$install" -eq 1 ]; then
	stamp=$(date +%Y%m%d-%H%M%S)
	echo "==> installing to $BOARD:$DEST_DIR"
	$SCP "$WORK/out/libgstv4l2codecs.so" "root@$BOARD:/tmp/gstv4l2codecs.$stamp"
	$SSH "set -e
		mkdir -p $DEST_DIR
		if [ -f $DEST_DIR/libgstv4l2codecs.so ]; then
			cp $DEST_DIR/libgstv4l2codecs.so /opt/gst-h713/libgstv4l2codecs.so.$stamp.bak
		fi
		install -m 0644 /tmp/gstv4l2codecs.$stamp $DEST_DIR/libgstv4l2codecs.so
		rm -f /tmp/gstv4l2codecs.$stamp
		printf 'export GST_PLUGIN_SYSTEM_PATH_1_0=%s:%s\n' $DEST_DIR $SYS_DIR > /opt/gst-h713/env
		sync
		missing=\$(ldd $DEST_DIR/libgstv4l2codecs.so | grep 'not found' || true)
		[ -z \"\$missing\" ] || { echo \"    ERROR: unresolved: \$missing\"; exit 1; }
		echo '    installed; all libraries resolve'"
fi

if [ "$test" -eq 1 ]; then
	echo "==> checking which v4l2codecs GStreamer loads"
	$SSH ". /opt/gst-h713/env
		f=\$(gst-inspect-1.0 v4l2codecs | sed -n 's/^ *Filename *//p')
		echo \"    loaded: \$f\"
		[ \"\$f\" = $DEST_DIR/libgstv4l2codecs.so ] || {
			echo '    FAIL: the system copy still wins; use dpkg-divert instead'; exit 1; }
		gst-inspect-1.0 v4l2slav1dec >/dev/null &&
			echo '    PASS: v4l2slav1dec registers from the patched plugin'"
fi
