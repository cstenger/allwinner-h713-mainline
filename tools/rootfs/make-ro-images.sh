#!/usr/bin/env bash
# Build read-only root images from a rootfs.tar (tools/rootfs/build.sh output),
# for the root-filesystem comparison in docs/lpddr3-bringup-plan.md (Phase 4
# stage 2). Needs no host root: runs in a user namespace with subuid mapping.
#
#   tools/rootfs/make-ro-images.sh ROOTFS_TAR [OUT_DIR]
#
# OUT_DIR defaults to build/out/ro-root/. Every image holds the same tree:
# rootfs.tar with tools/rootfs/ro-root.sh applied (preinit, fstab, tmp cap).
#
#   root-lz4hc.erofs      EROFS, lz4hc level 12, 4 KiB physical clusters (the
#                         production root, chosen 2026-11-20)
#   root-plain.erofs      EROFS, uncompressed          (comparison only)
#   root-ext4.img         ext4, mounted ro             (comparison only)
#
# IMAGES selects the set (default "lz4hc"; e.g. IMAGES="lz4hc plain ext4"). Each must fit super (2 GiB); each is
# reported as fitting a 1 GiB A/B slot (half of super) or single slot only.
# Kernel command line for each (U-Boot setenv bootargs ...):
#   root=/dev/mmcblk0p9 rootfstype=erofs|ext4 ro rootwait
#   init=/usr/lib/h713/preinit
# SOURCE_DATE_EPOCH, if set, pins timestamps.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
tar_in=$(realpath "${1:?ROOTFS_TAR}")
out=$(realpath -m "${2:-$ROOT/build/out/ro-root}")
images=${IMAGES:-lz4hc}
SLOT=$((1024 * 1024 * 1024)); SUPER=$((2 * SLOT))

need() { command -v "$1" >/dev/null || { echo "error: $1 not installed${2:+ ($2)}" >&2; exit 1; }; }
need unshare; need mke2fs
case " $images " in *" plain "*|*" lz4hc "*) need mkfs.erofs erofs-utils ;; esac
[ -f "$tar_in" ] || { echo "error: no $tar_in" >&2; exit 1; }
mkdir -p "$out"
work=$(mktemp -d "$out/.work.XXXXXX")
trap 'unshare --map-auto --map-root-user rm -rf "$work"' EXIT

export tar_in out work images SLOT SUPER ROOT
unshare --map-auto --map-root-user bash -ceu '
  T=$work/tree; mkdir -p "$T"
  tar --numeric-owner --xattrs --acls --exclude="./dev/*" -C "$T" -xf "$tar_in"
  "$ROOT/tools/rootfs/ro-root.sh" "$T"
  epoch=${SOURCE_DATE_EPOCH:-}
  [ -z "$epoch" ] || find "$T" -xdev -exec touch -h -d "@$epoch" {} +
  for i in $images; do
    case $i in
    ext4)
      f=root-ext4.img
      # Content plus 15 % and 64 MiB: a read-only image needs no free space
      # beyond what mke2fs wants for metadata.
      kib=$(du -sk --apparent-size "$T" | cut -f1)
      size=$(( (kib * 115 / 100 + 65536) / 4096 * 4096 ))K
      rm -f "$work/$f"; truncate -s "$size" "$work/$f"
      mke2fs -q -F -t ext4 -L root -m 0 ${epoch:+-E hash_seed=00000000-0000-0000-0000-000000000000} \
        -d "$T" "$work/$f"
      e2fsck -fn "$work/$f" >/dev/null ;;
    plain)
      f=root-plain.erofs
      mkfs.erofs --quiet ${epoch:+-T "$epoch"} -Lroot "$work/$f" "$T" ;;
    lz4hc)
      f=root-lz4hc.erofs
      mkfs.erofs --quiet -zlz4hc,12 -C4096 ${epoch:+-T "$epoch"} -Lroot "$work/$f" "$T" ;;
    *) echo "error: unknown image $i" >&2; exit 2 ;;
    esac
    sz=$(stat -c %s "$work/$f")
    if [ "$sz" -gt "$SUPER" ]; then
      echo "error: $f is $sz bytes, over super ($SUPER bytes)" >&2; exit 1
    fi
    fit="fits an A/B slot"; [ "$sz" -le "$SLOT" ] || fit="single slot only (over 1 GiB)"
    mv -f "$work/$f" "$out/$f"
    printf "%-20s %6d MiB  %s\n" "$f" $((sz >> 20)) "$fit"
  done
'
(cd "$out" && sha256sum root-* > SHA256SUMS)
printf 'source %s (%s)\n' "${tar_in##*/}" "$(sha256sum "$tar_in" | cut -c1-12)" > "$out/SOURCE"
echo "images in $out"
