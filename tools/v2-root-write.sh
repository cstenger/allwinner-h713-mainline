#!/usr/bin/env bash
# Write a read-only root image to the projector's super partition, and
# optionally format its data partition (docs/lpddr3-bringup-plan.md, Phase 4
# stage 2 step 3). HY200_QZ713_V2 only; the eMMC is exported over UMS from our
# U-Boot (`ums 0 mmc 1`).
#
#   sudo tools/v2-root-write.sh /dev/sdX IMAGE [--format-data]
#
# IMAGE is one of tools/rootfs/make-ro-images.sh's outputs. Refuses unless the
# board guard confirms V2 on the block device, partition 9 is "super" at LBA
# 0x92400 (2 GiB) and partition 26 is "UDISK" at LBA 0x54c400, and nothing on
# the device is mounted. Writes IMAGE to super and reads it back. With
# --format-data, makes UDISK ext4 (label "data"): this DESTROYS its contents
# (Android's userdata until the first format) and is never done implicitly.
# Partition names and the GPT are not touched.
#
# Super is discarded (blkdiscard) before the image goes in: the projector's
# eMMC (Samsung FNX2MB) misbehaved once it ran out of free blocks -- writes
# stalled and some LBAs returned the eMMC's own RAM (2026-11-19/20; see
# docs/lpddr3-bringup-plan.md, stage 2 step 3). UMS was never the fault. The
# read-back below is still the check that matters.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
dev=${1:?DEV}; img=${2:?IMAGE}; fmt=${3:-}
say() { printf '[v2-root-write] %s\n' "$*"; }
die() { say "FAIL: $*"; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root (raw block device writes)"
[ -b "$dev" ] || die "$dev is not a block device"
[ -f "$img" ] || die "missing $img"
case "$fmt" in ""|--format-data) ;; *) die "unknown option $fmt" ;; esac

python3 "$ROOT/tools/board-guard.py" --expect hy200-qz713-v2 --dev "$dev" || die "board guard refused $dev"

name=${dev##*/}
part() {  # NUM -> /dev path, after checking label, start and size via sysfs
  local n=$1 want_label=$2 want_start=$3 want_size=$4 p label
  p=$(lsblk -lnpo NAME "$dev" | grep -E "^${dev}p?${n}\$") || die "no partition $n on $dev"
  label=$(lsblk -no PARTLABEL "$p")
  [ "$label" = "$want_label" ] || die "partition $n is \"$label\", not \"$want_label\""
  [ "$(cat "/sys/class/block/${p##*/}/start")" = "$want_start" ] || die "partition $n does not start at LBA $want_start"
  [ -z "$want_size" ] || [ "$(cat "/sys/class/block/${p##*/}/size")" = "$want_size" ] ||
    die "partition $n is not $want_size sectors"
  echo "$p"
}
super=$(part 9 super $((0x92400)) $((0x400000)))
data=$(part 26 UDISK $((0x54c400)) "")

if findmnt -rno SOURCE | grep -q "^/dev/${name}"; then
  die "something on $dev is mounted: $(findmnt -rno SOURCE,TARGET | grep "^/dev/${name}" | tr '\n' ' ')"
fi

isz=$(stat -c %s "$img"); psz=$(blockdev --getsize64 "$super")
[ "$isz" -le "$psz" ] || die "$img ($isz bytes) is larger than super ($psz)"
say "discarding $super before writing"
blkdiscard -f "$super"
say "writing $(basename "$img") ($((isz >> 20)) MiB, sha256 $(sha256sum "$img" | cut -c1-12)) to $super"
dd if="$img" of="$super" bs=4M oflag=direct conv=fsync status=progress
sync
say "reading back"
cmp -n "$isz" "$img" <(dd if="$super" bs=4M iflag=direct count=$(( (isz + 4194303) / 4194304 )) status=none) ||
  die "read-back of super DIFFERS"
say "super: $(basename "$img") read back identical"

if [ "$fmt" = --format-data ]; then
  say "formatting $data (UDISK) as ext4, label data: its contents are destroyed"
  blkdiscard -f "$data"
  mkfs.ext4 -q -F -L data -m 1 -E lazy_itable_init=0,lazy_journal_init=0,discard "$data"
  e2fsck -fn "$data" >/dev/null || die "e2fsck of the new data filesystem failed"
  say "data: $(blkid -o export "$data" | grep -E '^(TYPE|LABEL|UUID)=' | tr '\n' ' ')"
fi
sync
say "done. Stop UMS on the board (Ctrl-C at the console) before booting."
