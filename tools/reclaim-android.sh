#!/usr/bin/env bash
# Retire the vendor Android stack's two large partitions and give the space to
# Linux.  The inverse of tools/split-udisk.sh, plus one repurpose.
#
#   p27 UDISK   (1.88 GiB, Android userdata)  DELETED; p26 grown back over it
#   p26 linux   (2.75 GiB, our Debian root)    grown in place to 4.63 GiB --
#                                              same start sector, same GUID, so
#                                              root=PARTUUID and root=/dev/..p26
#                                              both keep working
#   p9  super   (2 GiB, Android system)        renamed "scratch", reformatted
#                                              ext4 -- NOT deleted, so no other
#                                              partition number moves
#
# Everything else is left exactly as it is, deliberately:
#
#   - the ~270 MiB of small Android partitions (boot_*, vendor_boot_*, vbmeta_*,
#     dtbo_*, misc, metadata, frp) -- little to gain, and every extra GPT edit
#     is risk on the one disk this board boots from;
#   - "private" -- on Allwinner it can hold device-unique data (MAC addresses,
#     serials); nothing here needs its 16 MiB;
#   - "empty" (p18) -- despite the name, it holds OUR U-Boot proper, its env
#     and the on-board SPL stash (tools/boot-switch.sh).  Deleting it would
#     leave the board unable to boot past the SPL;
#   - bootloader_a (vendor mips/display.bin, which our display needs),
#     bootloader_b (our kernel FIT), env_a/b, media_data, and the raw regions
#     below the first partition (SPL at LBA 16, vendor boot0 at 0x100, TOC1
#     with BL31 and the SCP firmware).
#
# THE GPT ENTRY COUNT IS LOAD-BEARING.  This table holds 28 entries so the
# primary array ends at LBA 8, short of the first-stage SPL at LBA 16.  A
# standard 128-entry array reaches LBA 33 and destroys the first 9 KiB of the
# SPL -- the 2026-08-28 split hit exactly that.  This script never resizes the
# table, refuses to run if it is not 28 entries, and hashes the SPL both before
# and after every GPT write.
#
# Afterwards the vendor stack cannot boot: remove "switch_vendor" from the
# U-Boot environment so nobody reaches for it.  The 2026-07-05 full-eMMC
# captures under local/h713-lab/captures/board-b/ restore Android via FEL.
#
# Run only against the whole eMMC exposed by a cold-boot U-Boot UMS session:
#
#   sudo tools/reclaim-android.sh --dev /dev/sdX                    # dry run
#   sudo tools/reclaim-android.sh --dev /dev/sdX --backup-dir D --backup-root
#   sudo tools/reclaim-android.sh --dev /dev/sdX --backup-dir D --apply
set -euo pipefail

DISK_SECTORS=15269888
P26_START=5555200
P26_END_NOW=11322367
P27_START=11322368
DISK_LAST=15269854                      # p27's end == the last usable LBA
SPL_LBA=16
SPL_SHA256=cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec
UBOOT_LBA=4828160                       # start of p18 "empty"
BASIC_DATA=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7

DEV=
BACKUP_DIR=
APPLY=0
BACKUP_ROOT=0

die() { echo "error: $*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
	case "$1" in
	--dev)         DEV=${2:?}; shift 2 ;;
	--backup-dir)  BACKUP_DIR=${2:?}; shift 2 ;;
	--backup-root) BACKUP_ROOT=1; shift ;;
	--apply)       APPLY=1; shift ;;
	-h|--help)     sed -n '2,45p' "$0"; exit 0 ;;
	*)             die "unknown argument: $1" ;;
	esac
done

[ -n "$DEV" ] || die "--dev is required"
[ -b "$DEV" ] || die "$DEV is not a block device"
[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"
for tool in blockdev blkid e2fsck resize2fs tune2fs mkfs.ext4 sgdisk \
	partprobe udevadm lsblk sha256sum mount umount; do
	command -v "$tool" >/dev/null || die "missing required tool: $tool"
done

case "$DEV" in
*[0-9]) PART() { echo "${DEV}p$1"; } ;;
*)      PART() { echo "${DEV}$1"; } ;;
esac
P9=$(PART 9); P18=$(PART 18); P26=$(PART 26); P27=$(PART 27)

spl_hash() {
	dd if="$DEV" bs=512 skip=$SPL_LBA count=64 status=none | sha256sum | cut -d' ' -f1
}

field() {  # partition-number  label-regex
	# No early "exit" in awk, for the same SIGPIPE-under-pipefail reason.
	sgdisk -i "$1" "$DEV" | awk -F': ' -v k="$2" '$0 ~ k && !n++ {sub(/ .*/, "", $2); print $2}'
}
pname() { sgdisk -i "$1" "$DEV" | awk -F"'" '/Partition name:/ {print $2}'; }

check_table() {
	local p n e
	p=$(sgdisk -p "$DEV")
	n=$(awk '/Partition table holds up to/ {print $(NF - 1)}' <<<"$p")
	e=$(awk '/Main partition table begins/ {print $NF}' <<<"$p")
	[ "$n" -eq 28 ] || die "GPT holds $n entries, expected 28 (see the header)"
	# sgdisk prints "Main partition table begins at sector 2 and ends at
	# sector 8": $NF is already the END.  28 x 128-byte entries = 7 sectors.
	[ "$e" -lt $SPL_LBA ] || die "primary GPT array ends at LBA $e, reaching the SPL at LBA $SPL_LBA"
}

# ---------------------------------------------------------------- identity ---
mounted=$(lsblk -nrpo NAME,MOUNTPOINT "$DEV" | awk 'NF > 1 && $2 != "" {print $1 " on " $2}')
[ -z "$mounted" ] || die "a partition of $DEV is mounted; unmount it first:\n$mounted"

sectors=$(blockdev --getsz "$DEV")
[ "$sectors" -eq "$DISK_SECTORS" ] || die "$DEV has $sectors sectors, not the H713 eMMC's $DISK_SECTORS"
check_table

[ "$(spl_hash)" = "$SPL_SHA256" ] \
	|| die "first stage at LBA $SPL_LBA is not our SPL (cb9da874...); refusing to touch this disk"
# grep -c, never grep -q: -q exits on the first match, dd then dies of SIGPIPE,
# and under pipefail the pipeline reports failure precisely BECAUSE it matched.
[ "$(dd if="$DEV" bs=512 skip=$UBOOT_LBA count=2048 status=none | grep -ac "U-Boot 20")" -gt 0 ] \
	|| die "no U-Boot proper at LBA $UBOOT_LBA (p18 'empty'); refusing"

[ "$(pname 18)" = empty ] || die "p18 is '$(pname 18)', expected 'empty'"
[ "$(pname 9)" = super ] || die "p9 is '$(pname 9)', expected 'super' (already reclaimed?)"
[ "$(pname 26)" = linux ] || die "p26 is '$(pname 26)', expected 'linux'"
[ "$(pname 27)" = UDISK ] || die "p27 is '$(pname 27)', expected 'UDISK' (already reclaimed?)"

[ "$(field 26 'First sector')" -eq $P26_START ] || die "p26 does not start at $P26_START"
[ "$(field 26 'Last sector')" -eq $P26_END_NOW ] || die "p26 does not end at $P26_END_NOW"
[ "$(field 27 'First sector')" -eq $P27_START ] || die "p27 does not start at $P27_START"
[ "$(field 27 'Last sector')" -eq $DISK_LAST ] || die "p27 does not end at $DISK_LAST"
[ "$(field 26 'Partition GUID code')" = "$BASIC_DATA" ] || die "p26 type is not basic data"
[ "$(field 26 'Attribute flags')" = 8000000000000000 ] || die "p26 attributes changed"
P26_GUID=$(sgdisk -i 26 "$DEV" | awk -F': ' '/Partition unique GUID:/ {print $2}')

[ "$(blkid -s TYPE -o value "$P26")" = ext4 ] || die "$P26 is not ext4"
[ "$(tune2fs -l "$P26" | awk -F': *' '/Block size:/ {print $2}')" -eq 4096 ] \
	|| die "$P26 block size is not 4096"

# Nothing in Debian may still point at the partitions being repurposed.
mnt=$(mktemp -d)
mount -o ro,noload "$P26" "$mnt"
refs=$(grep -vE '^\s*#' "$mnt/etc/fstab" 2>/dev/null \
	| grep -iE 'UDISK|super|mmcblk0p9\b|mmcblk0p27\b' || true)
umount "$mnt"; rmdir "$mnt"
[ -z "$refs" ] || die "Debian's /etc/fstab still references a reclaimed partition:\n$refs"

echo "validated H713 eMMC on $DEV"
echo "  GPT       28 entries, primary array clear of the SPL"
echo "  SPL       LBA $SPL_LBA = cb9da874... (ours)"
echo "  U-Boot    present at LBA $UBOOT_LBA in p18 'empty'"
echo "  fstab     no references to UDISK/super"
echo "proposed:"
echo "  p27 UDISK  $P27_START..$DISK_LAST  DELETE"
echo "  p26 linux  $P26_START..$DISK_LAST  $(( (DISK_LAST - P26_START + 1) * 512 / 1048576 )) MiB (grow ext4, keep GUID $P26_GUID)"
echo "  p9  super  -> 'scratch', type 8300, new ext4 (Android system image is DESTROYED)"
echo "  everything else untouched"

if [ -n "$BACKUP_DIR" ]; then
	mkdir -p "$BACKUP_DIR"
	stamp=$(date -u +%Y%m%dT%H%M%SZ)
	sgdisk --backup="$BACKUP_DIR/gpt-before-reclaim-$stamp.bin" "$DEV"
	sgdisk -p "$DEV" >"$BACKUP_DIR/gpt-before-reclaim-$stamp.txt"
	echo "==> GPT backed up to $BACKUP_DIR"
	if [ "$BACKUP_ROOT" -eq 1 ]; then
		img="$BACKUP_DIR/p26-linux-before-reclaim-$stamp.img"
		echo "==> imaging p26 to $img"
		dd if="$P26" of="$img" bs=4M status=progress conv=fsync
		a=$(sha256sum <"$P26" | cut -d' ' -f1); b=$(sha256sum <"$img" | cut -d' ' -f1)
		[ "$a" = "$b" ] || die "p26 image does not match the partition ($a vs $b)"
		echo "$a  $(basename "$img")" >"$img.sha256"
		echo "    verified: $a"
	fi
fi

if [ "$APPLY" -ne 1 ]; then
	echo "dry run only; pass --apply to perform the reclaim"
	exit 0
fi
[ -n "$BACKUP_DIR" ] || die "--apply requires --backup-dir, so the GPT is saved first"

run_e2fsck() {
	local rc
	set +e; e2fsck -fp "$1"; rc=$?; set -e
	[ "$rc" -le 1 ] || die "e2fsck $1 failed with status $rc"
}

echo "==> checking $P26"
run_e2fsck "$P26"

echo "==> rewriting the GPT (delete p27, grow p26, rename p9)"
sgdisk \
	--delete=27 \
	--delete=26 \
	--new=26:"$P26_START":"$DISK_LAST" \
	--typecode=26:0700 \
	--change-name=26:linux \
	--partition-guid=26:"$P26_GUID" \
	--attributes=26:set:63 \
	--typecode=9:8300 \
	--change-name=9:scratch \
	"$DEV"
sgdisk --verify "$DEV"
check_table
[ "$(spl_hash)" = "$SPL_SHA256" ] \
	|| die "THE SPL AT LBA $SPL_LBA CHANGED DURING THE GPT WRITE. Do not reboot; restore it (boot region backup, or FEL restore SPL)."

partprobe "$DEV"; udevadm settle
[ -b "$P26" ] || die "$P26 did not reappear"
[ ! -e "$P27" ] || die "$P27 still exists"
[ "$(blockdev --getsz "$P26")" -eq $((DISK_LAST - P26_START + 1)) ] || die "$P26 has the wrong size"

echo "==> growing ext4 on $P26"
run_e2fsck "$P26"
resize2fs "$P26"
run_e2fsck "$P26"

echo "==> formatting $P9 as scratch"
mkfs.ext4 -F -q -L scratch "$P9"
[ "$(blkid -s LABEL -o value "$P9")" = scratch ] || die "$P9 label verification failed"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
sgdisk --backup="$BACKUP_DIR/gpt-after-reclaim-$stamp.bin" "$DEV"
sgdisk -p "$DEV" >"$BACKUP_DIR/gpt-after-reclaim-$stamp.txt"
[ "$(spl_hash)" = "$SPL_SHA256" ] || die "SPL hash changed at the end"
sync

echo "reclaim complete and verified"
echo "  p26 linux    $(( $(blockdev --getsz "$P26") * 512 / 1048576 )) MiB, ext4, GUID $P26_GUID"
echo "  p9  scratch  $(( $(blockdev --getsz "$P9") * 512 / 1048576 )) MiB, ext4"
echo "  SPL at LBA $SPL_LBA unchanged; GPT backups in $BACKUP_DIR"
echo "next: remove switch_vendor from the U-Boot env; add scratch to /etc/fstab"
