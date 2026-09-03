#!/usr/bin/env bash
# Build and install the patched mpv on the board, reproducibly. RUNS ON THE HOST.
#
# WHY THIS EXISTS. The direct DRM-PRIME video path is a downstream mpv patch
# (patches/mpv/). Until now the only artifact was one unversioned binary sitting
# in /root on the board, reproducible solely by hand-following a README. That is
# the same failure mode build-va-driver.sh was written to end for the VA driver:
# nothing in the rootfs build produces it, so **a fresh flash silently loses the
# no-GPU video path** and the way back lives in somebody's shell history.
#
# THE BUILD HAPPENS ON THE BOARD, for the same reason the VA driver's does: mpv
# links against the board's FFmpeg, libva, libdrm and ALSA. A host build would
# have to match all four ABIs exactly, and when it did not the failure would be
# a dlopen or a silent software fallback rather than a build error.
#
# INSTALLS TO /usr/local/bin, not /usr/bin. Debian owns /usr/bin/mpv; overwriting
# it means the next apt upgrade quietly reverts the video path with no sign that
# anything changed. /usr/local/bin precedes /usr/bin in the board's PATH, so the
# patched build wins while the distro package stays intact and reinstallable.
#
#   usage: tools/video/build-mpv.sh [--install] [--test]
#          BOARD=192.168.4.1 tools/video/build-mpv.sh --install --test
#
# Without --install it builds and verifies but leaves the running mpv alone.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
SRC=${SRC:-$ROOT/local/upstream/mpv-src}
PATCHES=$ROOT/patches/mpv
UPSTREAM=https://github.com/mpv-player/mpv.git
TAG=v0.40.0
BASE=e48ac7ce08462f5e33af6ef9deeac6fa87eef01e
DEST=/usr/local/bin/mpv

# The marker the patch prints when it takes the direct path. Verifying the built
# binary contains it is what distinguishes "mpv built" from "mpv built WITH the
# patch" -- a series that silently failed to apply would otherwise install a
# stock mpv and look like success until someone watched the logs.
MARKER='Using direct DRM PRIME video-plane scanout'

install=0; test=0
for arg in "$@"; do
	case $arg in
	--install) install=1 ;;
	--test) test=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 1 ;;
	esac
done

# --- 0. the board must be able to build this at all -------------------------
# The board has no internet (it is an access point, not a client), so apt cannot
# fix a missing dependency in place. Failing here with the exact package list is
# far better than a meson error 200 lines deep.
echo "==> checking the board's build dependencies"
missing=$($SSH 'set +e
	for t in meson ninja cc pkg-config; do
		command -v $t >/dev/null || echo "tool:$t"
	done
	for p in libva libdrm libavcodec libavformat libavutil libswscale alsa; do
		pkg-config --exists $p || echo "pkgconfig:$p"
	done')
if [ -n "$missing" ]; then
	echo "    MISSING on $BOARD:"
	echo "$missing" | sed 's/^/      /'
	cat <<'EOF'
    The board has no default route, so `apt install` there will not work.
    Supply the arm64 -dev packages by one of:
      * give the board a route to the internet temporarily, then apt install
        meson libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
        libasound2-dev libva-dev libdrm-dev
      * copy the matching arm64 .deb files over and `dpkg -i` them
    Re-run this script once they are present.
EOF
	exit 1
fi
echo "    all present"

# --- 1. the source tree, patched, on the host -------------------------------
if [ ! -d "$SRC/.git" ]; then
	echo "==> cloning $UPSTREAM ($TAG)"
	git clone -q --branch "$TAG" "$UPSTREAM" "$SRC"
fi

echo "==> checking out the pinned commit and applying the series"
git -C "$SRC" fetch -q --tags origin
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

# --- 2. build it on the board ----------------------------------------------
echo "==> shipping the tree to $BOARD and building there"
$SSH 'rm -rf /root/mpv-build && mkdir -p /root/mpv-build'
tar -C "$SRC" --exclude .git -cz . | $SSH 'tar -xz -C /root/mpv-build'

# The board's clock can trail the host's after a power cycle, and meson refuses
# to configure a tree dated in the future ("Clock skew detected"). Restamping
# costs nothing and removes a confusing failure.
#
# auto_features=disabled keeps this to the features the video path actually
# needs: without it meson enables whatever happens to be installed, and the
# build both slows down and starts depending on packages nobody chose.
$SSH "cd /root/mpv-build && find . -exec touch {} + &&
      rm -rf build &&
      meson setup build --buildtype=release -Dauto_features=disabled \
          -Dalsa=enabled -Ddrm=enabled -Dgl=disabled -Dlibmpv=false \
          -Dvaapi=enabled -Dvaapi-drm=enabled >/dev/null &&
      ninja -C build mpv" 2>&1 | tail -3

# --- 3. verify the patch is actually IN the binary --------------------------
echo "==> verifying the direct path is present"
$SSH "set -e
	if strings -a /root/mpv-build/build/mpv | grep -qF '$MARKER'; then
		echo '    direct DRM PRIME path present'
	else
		echo '    ERROR: built mpv has no direct-path marker.'
		echo '    The series applied but the feature is absent -- treat this'
		echo '    as a failed build, not a working mpv.'
		exit 1
	fi
	/root/mpv-build/build/mpv --version | head -1 | sed 's/^/    /'"

if [ "$install" -eq 0 ]; then
	echo "==> built and verified; NOT installed (pass --install)"
	exit 0
fi

# --- 4. install, keeping whatever was there --------------------------------
stamp=$(date +%Y%m%d-%H%M%S)
echo "==> installing to $DEST"
$SSH "set -e
	[ -f $DEST ] && cp $DEST $DEST.$stamp.bak &&
		echo '    kept the outgoing binary at $DEST.$stamp.bak'
	install -m 0755 /root/mpv-build/build/mpv $DEST
	sync
	echo \"    which mpv -> \$(command -v mpv)\""

# Record WHAT was installed, alongside the VA driver's entry, so drift is one
# command to detect rather than an archaeology problem. Appending keeps both
# halves of the video stack in one file.
echo "==> stamping the install"
series_id=$(while read -r p; do
	[ -n "$p" ] && sha256sum "$PATCHES/$p"
done < "$PATCHES/series" | sha256sum | cut -c1-16)
$SSH "sed -i '/^mpv_/d' /etc/h713-video-stack 2>/dev/null || true
	cat >> /etc/h713-video-stack <<EOF
mpv_series=$series_id
mpv_installed=$stamp
mpv_base=$BASE
mpv_patches=$(grep -c . "$PATCHES/series")
EOF"
echo "    series id $series_id"

# --- 5. optional: prove the direct path on hardware ------------------------
if [ "$test" -eq 1 ]; then
	echo "==> testing the direct path"
	$SSH 'set -e
		clip=$(ls /root/video-test/*.h264 2>/dev/null | head -1)
		[ -n "$clip" ] || { echo "    no test clip in /root/video-test"; exit 1; }
		cat > /tmp/mpv-direct-test.sh <<EOF
export LIBVA_DRIVER_NAME=v4l2_request
exec mpv --no-config --no-audio --vo=drm --hwdec=vaapi --length=5 \
    --msg-level=all=v "$clip"
EOF
		setsid bash /tmp/mpv-direct-test.sh </dev/null >/tmp/mpv-direct-test.log 2>&1 &
		sleep 18
		ok=1
		grep -q "Using hardware decoding (vaapi)" /tmp/mpv-direct-test.log || ok=0
		grep -q "vaapi\[nv12\]" /tmp/mpv-direct-test.log || ok=0
		grep -qF "direct DRM PRIME video-plane scanout" /tmp/mpv-direct-test.log || ok=0
		grep -iE "Using hardware decoding|VO: \[drm\]|direct DRM PRIME" \
			/tmp/mpv-direct-test.log | sed "s/^/    /"
		fails=$(grep -c "hardware accelerator failed" /tmp/mpv-direct-test.log || true)
		echo "    decode failures: $fails"
		if [ "$ok" = 1 ] && [ "$fails" = 0 ]; then
			echo "    PASS -- hardware decode reaching the plane with no GPU"
		else
			echo "    FAIL -- see /tmp/mpv-direct-test.log on the board"
			exit 1
		fi'
fi
