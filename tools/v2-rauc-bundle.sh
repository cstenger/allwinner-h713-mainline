#!/usr/bin/env bash
# Build a signed RAUC bundle for the projector (HY200_QZ713_V2): one slot's
# root image and boot partition image.
#
#   tools/v2-rauc-bundle.sh ROOT_IMAGE BOOT_IMAGE OUT.raucb [VERSION]
#
# ROOT_IMAGE is an EROFS root (tools/rootfs/make-ro-images.sh), BOOT_IMAGE a
# slot boot partition (tools/v2-boot-image.sh). VERSION defaults to the date
# and the git revision. Install on the board with `rauc install OUT.raucb`;
# RAUC writes the slot pair it is not running from and moves BOOT_ORDER to it.
#
# The bundle is signed with local/keys/rauc/signer.{cert,key}.pem
# (generated on first use) or the signer in H713_RAUC_KEYDIR. It is verified
# against the public keyring extracted from the EROFS root image.
#
# No RAUC on the host: this runs Debian's arm64 rauc, the same version as the
# board, from a sysroot taken from a rootfs.tar, under qemu-aarch64-static.
# rauc's own child processes (mksquashfs) are the host's native tools.
#   RAUC_SYSROOT  default build/rauc-sysroot, made from ROOTFS_TAR if missing
#   ROOTFS_TAR    default build/out/rootfs-v2-ro/rootfs.tar
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
rootimg=$(realpath "${1:?ROOT_IMAGE}"); bootimg=$(realpath "${2:?BOOT_IMAGE}")
out=$(realpath -m "${3:?OUT.raucb}")
version=${4:-$(date -u +%Y.%m.%d.%H%M)-$(git -C "$ROOT" rev-parse --short HEAD)}
kd=${H713_RAUC_KEYDIR:-$ROOT/local/keys/rauc}
sysroot=${RAUC_SYSROOT:-$ROOT/build/rauc-sysroot}
tar_in=${ROOTFS_TAR:-$ROOT/build/out/rootfs-v2-ro/rootfs.tar}
for f in "$rootimg" "$bootimg"; do
	[ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done
for t in qemu-aarch64-static mksquashfs dump.erofs; do
	command -v "$t" >/dev/null || { echo "$t not installed" >&2; exit 1; }
done
if [ -z "${H713_RAUC_KEYDIR:-}" ]; then
	"$ROOT/tools/keys/make-dev-keys.sh"
fi
for f in "$kd/signer.cert.pem" "$kd/signer.key.pem"; do
	[ -s "$f" ] || { echo "missing $f" >&2; exit 1; }
done

if [ ! -x "$sysroot/usr/bin/rauc" ]; then
	[ -f "$tar_in" ] || { echo "no RAUC sysroot and no $tar_in to make one" >&2; exit 1; }
	mkdir -p "$sysroot"
	tar -C "$sysroot" -xf "$tar_in" ./lib ./usr/lib/ld-linux-aarch64.so.1 \
		./usr/lib/aarch64-linux-gnu ./usr/bin/rauc
fi
# Host-side config: only what bundle and info need, with the board's
# check-purpose (the signer certificate's extendedKeyUsage is codeSigning).
tmp=$(mktemp -d "$(dirname "$out")/.rauc-bundle.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
hostconf=$tmp/system.conf
printf '[system]\ncompatible=hy200-qz713-v2\nbootloader=noop\n\n[keyring]\ncheck-purpose=codesign\n' > "$hostconf"
rauc() { qemu-aarch64-static -L "$sysroot" "$sysroot/usr/bin/rauc" --conf="$hostconf" "$@"; }
rauc --version >/dev/null || { echo "rauc does not run from $sysroot" >&2; exit 1; }

keyring=$tmp/keyring.pem
dump.erofs --cat --path=/usr/lib/h713/rauc-keyring.pem "$rootimg" > "$keyring"
mkdir "$tmp/content"
# RAUC 1.13 dispatches raw images by filename suffix. The bytes stay EROFS.
cp --reflink=auto "$rootimg" "$tmp/content/rootfs.img"
cp --reflink=auto "$bootimg" "$tmp/content/boot.vfat"
cat > "$tmp/content/manifest.raucm" <<EOF
[update]
compatible=hy200-qz713-v2
version=$version

[bundle]
format=verity

[image.rootfs]
filename=rootfs.img

[image.boot]
filename=boot.vfat
EOF
rauc bundle --cert="$kd/signer.cert.pem" --key="$kd/signer.key.pem" \
	"$tmp/content" "$tmp/bundle.raucb" >/dev/null
rauc info --keyring="$keyring" "$tmp/bundle.raucb" > "$tmp/info" ||
	{ echo "the bundle does not verify against the keyring in $rootimg" >&2; exit 1; }
grep -q "'hy200-qz713-v2'" "$tmp/info" || { echo "rauc info does not show compatible hy200-qz713-v2" >&2; exit 1; }
mv -fT "$tmp/bundle.raucb" "$out"
echo "$out: $(stat -c %s "$out") bytes, version $version, signature verified"
