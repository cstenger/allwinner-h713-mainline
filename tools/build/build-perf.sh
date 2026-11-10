#!/usr/bin/env bash
# Build perf for the board, from our own kernel tree. RUNS ON THE HOST.
#
# WHY. The GPU path costs ~17% whole-board CPU against ~8% for the plane
# routes, and stock mpv knobs do not move it (docs/gpu-fallback-plan.md, WP2
# follow-up). The candidates -- EGL dma-buf import, Mesa/Panfrost per-draw CPU,
# the GBM page flip -- can only be told apart by a profiler, and the board has
# none: no perf, and tracefs is not reachable.
#
# HOW. Same route as tools/video/build-mpv.sh: there is no aarch64 cross
# toolchain on the host, so perf builds natively inside an arm64 Debian trixie
# chroot under qemu-user. The source is perf's MANIFEST file list from a
# build/linux-6.18.38-* tree, so the tool matches the running kernel's perf
# ABI (`make perf-tar-src-pkg` would do the same but needs a git checkout).
#
# DYNAMIC, EXCEPT LIBTRACEEVENT. A fully static perf is not possible from
# Debian: its libelf.a needs elfutils' private libeu, which is not shipped. The
# board already has the rest (trixie's elfutils 0.192, zlib, zstd, xz, bzip2,
# libcap), but not libtraceevent, so its .so is hidden in the chroot and the
# linker takes libtraceevent.a. `ldd` on the board is the gate. The build
# prints perf's feature table; libdw is the one that matters -- without
# it `perf record --call-graph dwarf` is unavailable.
#
# NO HARDWARE PMU. The H713 device tree has no arm,cortex-a53-pmu node, so the
# board only offers software events. Sample with `-e cpu-clock` (hrtimer-based),
# which is enough to see where the CPU time goes.
#
#   usage: tools/build/build-perf.sh [--install] [--rebuild-rootfs]
#
# Installs to /usr/local/bin/perf on the board.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# shellcheck source=../../config/paths.sh
source "$ROOT/config/paths.sh"
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=8 root@$BOARD"
WORK=${WORK:-$ROOT/local/upstream/perf-arm64}
KTREE=${KTREE:-$(ls -td "$H713_BUILD_DIR"/linux-6.18.38-*/ 2>/dev/null | head -1)}
DEST=/usr/local/bin/perf
SUITE=trixie
# perf's optional features, as Debian packages. Static archives (.a) come with
# each -dev package. python3 builds the PMU event tables, and once PYTHON is
# set perf also insists on python3-config, hence python3-dev.
DEPS=build-essential,flex,bison,pkg-config,python3,python3-dev,\
libelf-dev,libdw-dev,libtraceevent-dev,libzstd-dev,zlib1g-dev,\
liblzma-dev,libbz2-dev,libcap-dev

install=0; rebuild=0
for arg in "$@"; do
	case $arg in
	--install) install=1 ;;
	--rebuild-rootfs) rebuild=1 ;;
	*) echo "unknown argument: $arg" >&2; exit 1 ;;
	esac
done

[ -n "$KTREE" ] && [ -d "$KTREE/tools/perf" ] || {
	echo "no kernel tree with tools/perf under $H713_BUILD_DIR" >&2; exit 1; }
KTREE=${KTREE%/}
echo "==> kernel tree: ${KTREE##*/}"

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
mkdir -p "$RFS/build-perf"
rm -f "$RFS"/usr/lib/aarch64-linux-gnu/libtraceevent.so*
# perf's own file list. `make perf-tar-src-pkg` would do this but refuses to
# run outside a git checkout, and build/ trees are not one. Globs in the
# MANIFEST (arch/*/...) are expanded by the shell here, on purpose.
(cd "$KTREE" && tar -cf - $(cat tools/perf/MANIFEST) Makefile) |
	tar -xf - -C "$RFS/build-perf"
make -s -C "$KTREE" kernelversion > "$RFS/build-perf/tools/perf/.kernelversion" 2>/dev/null || true

cat > "$RFS/do-build.sh" <<'EOS'
#!/bin/bash
set -e
cd /build-perf
# NO_LIBBPF: BPF skeletons need clang/bpftool. NO_LIBUNWIND: libdw unwinds.
make -C tools/perf -j"$(nproc)" WERROR=0 PYTHON=python3 \
	NO_LIBPYTHON=1 NO_LIBPERL=1 NO_SLANG=1 NO_GTK2=1 NO_LIBBPF=1 \
	NO_BPF_SKEL=1 NO_LIBUNWIND=1 NO_LIBNUMA=1 NO_LIBBABELTRACE=1 \
	NO_LIBCRYPTO=1 NO_LIBLLVM=1 NO_CAPSTONE=1 NO_LIBPFM4=1 \
	NO_SHELLCHECK=1 2>&1 | tee /build-perf/build.log
EOS
chmod +x "$RFS/do-build.sh"
echo "==> building perf under emulation (slow)"
unshare -r --mount --pid --fork chroot "$RFS" /bin/bash -c \
	'mount -t proc proc /proc 2>/dev/null; /do-build.sh' >/dev/null 2>&1 || true

BIN=$RFS/build-perf/tools/perf/perf
echo "==> verifying the built binary"
[ -f "$BIN" ] || { echo "    ERROR: no binary; see $RFS/build-perf/build.log"; exit 1; }
grep -q 'ARM aarch64' < <(file "$BIN") || { echo "    ERROR: not an aarch64 binary"; exit 1; }
# The feature table perf printed while configuring: dwarf is the one we need.
grep -E '^\.\.\. +(libdw|libelf|libtraceevent|zlib|libzstd|lzma):' \
	"$RFS/build-perf/build.log" | sed 's/^/    /' || true
cp "$BIN" "$WORK/perf"
echo "    $WORK/perf ($(du -h "$WORK/perf" | cut -f1))"

if [ "$install" -eq 1 ]; then
	echo "==> installing to $BOARD:$DEST"
	scp -q "$WORK/perf" "root@$BOARD:/tmp/perf-staged"
	$SSH "install -m 0755 /tmp/perf-staged $DEST && rm -f /tmp/perf-staged"
	echo "==> checking runtime links on the board"
	missing=$($SSH "ldd $DEST | grep 'not found'" || true)
	[ -z "$missing" ] || { echo "    ERROR: unresolved on the board:"; echo "$missing"; exit 1; }
	$SSH "$DEST --version; $DEST version --build-options | grep -E 'dwarf|libelf|traceevent'"
fi
