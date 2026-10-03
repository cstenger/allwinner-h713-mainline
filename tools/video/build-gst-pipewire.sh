#!/usr/bin/env bash
# Build and install the patched GStreamer PipeWire plugin (pipewiresink) on the
# board, reproducibly. RUNS ON THE HOST.
#
# RETIRED 2026-10-03: the plane player now uses stock alsasink through
# pipewire-alsa, which measured better (patches/pipewire/README.md). Kept so
# the patch stays reproducible. --install would replace Debian's plugin again.
#
# WHY. Stock pipewiresink kept audio late: +768 ms for the whole stream after
# the sink had been idle, +80 ms even warm, measured with av-sync-probe
# (patches/pipewire/README.md). WP4's plane routes play audio through it.
#
# HOW. Debian trixie's pipewire 1.4.2-1 source (the version the board runs),
# checksummed against its .dsc, plus patches/pipewire/series. Only src/gst/ is
# built, and on the board: it is a 2 MB tree, and building there links the
# board's own libpipewire-0.3.so.0 and GStreamer, so the plugin cannot disagree
# with them. The board has no libpipewire headers; the source tree's public
# headers (spa/include, src/pipewire) are the same version.
#
# INSTALLS OVER DEBIAN'S FILE WITH dpkg-divert, so the packaged plugin is kept
# as libgstpipewire.so.distrib and an apt upgrade of gstreamer1.0-pipewire
# installs beside it instead of silently reverting the fix.
#
#   usage: tools/video/build-gst-pipewire.sh [--install]
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -F /dev/null -o ConnectTimeout=8 root@$BOARD"
WORK=${WORK:-$ROOT/local/upstream/pipewire-deb}
PATCHES=$ROOT/patches/pipewire
MIRROR=https://deb.debian.org/debian/pool/main/p/pipewire
VERSION=1.4.2
DEBREV=1
ORIG_SHA256=aa9098001e1bc2f7742140727e19bcd57812b686840923afda2be6c227b88bf0
DEBIAN_SHA256=2c9fd6e1c5507a5fd063ea97ae5b2d4a28910a4c8a5a6d97923cc5ab5204fd81
PLUGIN=/usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstpipewire.so
# A string only the patched plugin contains: a series that failed to apply
# must not install a stock plugin that looks like success.
MARKER='graph not consuming yet'

install=0
for arg in "$@"; do
	case $arg in
	--install) install=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 1 ;;
	esac
done

# --- 1. source: Debian's, verified, patched ---------------------------------
mkdir -p "$WORK"
cd "$WORK"
for f in pipewire_$VERSION.orig.tar.bz2 pipewire_$VERSION-$DEBREV.debian.tar.xz; do
	[ -f "$f" ] || { echo "==> fetching $f"; curl -fsSLO "$MIRROR/$f"; }
done
echo "$ORIG_SHA256  pipewire_$VERSION.orig.tar.bz2
$DEBIAN_SHA256  pipewire_$VERSION-$DEBREV.debian.tar.xz" | sha256sum -c --quiet

echo "==> unpacking with Debian's patches, then the series"
rm -rf src
mkdir src
tar -xjf pipewire_$VERSION.orig.tar.bz2 -C src --strip-components=1
tar -xJf pipewire_$VERSION-$DEBREV.debian.tar.xz -C src
if [ -f src/debian/patches/series ]; then
	grep -v '^#' src/debian/patches/series | while read -r p; do
		[ -n "$p" ] && patch -s -d src -p1 < "src/debian/patches/$p"
	done
fi
git -C src init -q
git -C src add -A
git -C src -c user.name=build -c user.email=build@localhost commit -qm "pipewire $VERSION-$DEBREV (Debian)"
while read -r p; do
	[ -n "$p" ] || continue
	git -C src apply "$PATCHES/$p"
	echo "    $p"
done < "$PATCHES/series"

# --- 2. stage the plugin and the headers it needs ---------------------------
echo "==> staging src/gst and headers"
STAGE=$WORK/stage
rm -rf "$STAGE"
mkdir -p "$STAGE/src"
cp -a src/src/gst "$STAGE/src/"
cp -a src/src/pipewire "$STAGE/src/"
cp -a src/spa "$STAGE/"
IFS=. read -r major minor micro <<<"$VERSION"
sed -e "s/@PIPEWIRE_VERSION_MAJOR@/$major/; s/@PIPEWIRE_VERSION_MINOR@/$minor/" \
    -e "s/@PIPEWIRE_VERSION_MICRO@/$micro/; s/@PIPEWIRE_API_VERSION@/\"0.3\"/" \
	src/src/pipewire/version.h.in > "$STAGE/src/pipewire/version.h"
# The values src/gst (and GST_PLUGIN_DEFINE) read from meson's config.h, as
# meson.build:245-250 and Debian's build set them.
cat > "$STAGE/config.h" <<EOF
#define PACKAGE "pipewire"
#define PACKAGE_NAME "PipeWire"
#define PACKAGE_VERSION "$VERSION"
#define HAVE_GSTREAMER_DEVICE_PROVIDER 1
#define HAVE_GSTREAMER_DMA_DRM 1
EOF

# --- 3. build on the board ---------------------------------------------------
echo "==> building on $BOARD"
$SSH 'rm -rf /root/pw-gst-build && mkdir -p /root/pw-gst-build'
tar -C "$STAGE" -cz . | $SSH 'tar -xz -C /root/pw-gst-build 2>/dev/null'
$SSH "set -e
	cd /root/pw-gst-build
	gcc -O2 -g0 -fPIC -shared -Wall -Wno-unused -o libgstpipewire.so \
		-I. -Ispa/include -Isrc -DHAVE_CONFIG_H -include config.h \
		src/gst/*.c \
		\$(pkg-config --cflags --libs gstreamer-1.0 gstreamer-base-1.0 \
			gstreamer-video-1.0 gstreamer-audio-1.0 gstreamer-allocators-1.0) \
		/usr/lib/aarch64-linux-gnu/libpipewire-0.3.so.0 -lm
	grep -q '$MARKER' libgstpipewire.so || { echo '    ERROR: built plugin lacks the patch marker'; exit 1; }
	! ldd libgstpipewire.so | grep 'not found'
	echo '    built and verified (marker present, every library resolves)'"

if [ "$install" -eq 0 ]; then
	echo "==> built; NOT installed (pass --install)"
	exit 0
fi

# --- 4. install over Debian's plugin, diverted --------------------------------
echo "==> installing (dpkg-divert keeps Debian's as .distrib)"
$SSH "set -e
	dpkg-divert --list $PLUGIN | grep -q . ||
		dpkg-divert --local --rename --divert $PLUGIN.distrib --add $PLUGIN
	cp /root/pw-gst-build/libgstpipewire.so $PLUGIN
	rm -rf /root/.cache/gstreamer-1.0 /home/*/.cache/gstreamer-1.0
	gst-inspect-1.0 pipewiresink >/dev/null
	echo '    installed; gst-inspect loads it'"
series_id=$(while read -r p; do [ -n "$p" ] && sha256sum "$PATCHES/$p"; done < "$PATCHES/series" | sha256sum | cut -c1-16)
$SSH "touch /etc/h713-video-stack
	sed -i '/^gst_pipewire_/d' /etc/h713-video-stack
	echo 'gst_pipewire_series=$series_id' >> /etc/h713-video-stack
	echo 'gst_pipewire_installed=$(date +%Y%m%d-%H%M%S)' >> /etc/h713-video-stack"
echo "    series id $series_id"
