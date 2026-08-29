#!/usr/bin/env bash
# Split the factory UDISK into a 2.75 GiB Debian partition and a 1.88 GiB
# Android userdata partition without moving Debian's start sector.
#
# The factory GPT declares only 26 entry slots.  That is intentional: 26 entries
# occupy LBAs 2..8, leaving the BROM's first-stage image at LBA 16 untouched.
# Expand to 28 entries (sgdisk fills the seven-sector entry array), never the
# standard 128: a 128-entry primary array occupies LBAs 2..33 and destroys the
# first 9 KiB of the SPL.  The live migration caught and repaired this once on
# 2026-08-28; keep the explicit overlap guard below.
#
# Run only against the whole eMMC exposed by a cold-boot U-Boot UMS session:
#
#   sudo tools/split-udisk.sh --dev /dev/sdX --apply
#
# With no --apply, the script performs every read-only identity check and
# prints the proposed layout.
set -euo pipefail

DISK_SECTORS=15269888
OLD_START=5555200
OLD_SECTORS=9714655
OLD_END=$((OLD_START + OLD_SECTORS - 1))
LINUX_SECTORS=$((11 * 512 * 1024))      # exactly 2.75 GiB at 512 B/sector
LINUX_END=$((OLD_START + LINUX_SECTORS - 1))
ANDROID_START=$((LINUX_END + 1))
ANDROID_END=$OLD_END
EXT4_BLOCKS=720896                       # 2.75 GiB at the required 4096 B/block
EXPECTED_TYPE=EBD0A0A2-B9E5-4433-87C0-68B6B72699C7

DEV=
BACKUP_DIR=
APPLY=0

die() { echo "error: $*" >&2; exit 1; }

usage() {
	cat <<'EOF'
usage: split-udisk.sh --dev /dev/sdX [--backup-dir DIR] [--apply]

Without --apply, validate the device and print the proposed split.  --apply
shrinks ext4 on p26, expands the GPT entry array, renames p26 to "linux",
creates p27 as "UDISK", and formats p27 as Android f2fs.
EOF
}

while [ "$#" -gt 0 ]; do
	case "$1" in
	--dev)        [ "$#" -ge 2 ] || die "--dev needs an argument"; DEV=$2; shift 2 ;;
	--backup-dir) [ "$#" -ge 2 ] || die "--backup-dir needs an argument"; BACKUP_DIR=$2; shift 2 ;;
	--apply)      APPLY=1; shift ;;
	-h|--help)    usage; exit 0 ;;
	*)            die "unknown argument: $1" ;;
	esac
done

[ -n "$DEV" ] || die "--dev is required"
[ -b "$DEV" ] || die "$DEV is not a block device"
[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"

for tool in blockdev blkid e2fsck resize2fs tune2fs e2label sgdisk \
	partprobe udevadm make_f2fs fsck.f2fs lsblk; do
	command -v "$tool" >/dev/null || die "missing required tool: $tool"
done

case "$DEV" in
*[0-9]) P26="${DEV}p26"; P27="${DEV}p27" ;;
*)      P26="${DEV}26";  P27="${DEV}27" ;;
esac

mounted=$(lsblk -nrpo NAME,MOUNTPOINT "$DEV" | awk 'NF > 1 && $2 != "" {print $1 " on " $2}')
[ -z "$mounted" ] || die "a target partition is mounted; unmount it first:\n$mounted"

sectors=$(blockdev --getsz "$DEV")
[ "$sectors" -eq "$DISK_SECTORS" ] \
	|| die "$DEV has $sectors sectors, expected the H713 eMMC's $DISK_SECTORS"

info=$(sgdisk -i 26 "$DEV")
start=$(awk -F': ' '/First sector:/ {sub(/ .*/, "", $2); print $2}' <<<"$info")
end=$(awk -F': ' '/Last sector:/ {sub(/ .*/, "", $2); print $2}' <<<"$info")
name=$(awk -F"'" '/Partition name:/ {print $2}' <<<"$info")
type=$(awk -F': ' '/Partition GUID code:/ {sub(/ .*/, "", $2); print $2}' <<<"$info")
guid=$(awk -F': ' '/Partition unique GUID:/ {print $2}' <<<"$info")
attrs=$(awk -F': ' '/Attribute flags:/ {print $2}' <<<"$info")

[ "$start" -eq "$OLD_START" ] || die "p26 starts at $start, expected $OLD_START"
[ "$end" -eq "$OLD_END" ] || die "p26 ends at $end, expected $OLD_END"
[ "$name" = UDISK ] || die "p26 is named '$name', expected UDISK"
[ "$type" = "$EXPECTED_TYPE" ] || die "p26 type is $type, expected $EXPECTED_TYPE"
[ "$attrs" = 8000000000000000 ] || die "p26 attributes are $attrs, expected 8000000000000000"
[ ! -e "$P27" ] || die "$P27 already exists; this disk may already be split"
[ "$(blkid -s TYPE -o value "$P26")" = ext4 ] || die "$P26 is not ext4"

echo "validated factory H713 layout on $DEV"
echo "  p26 UDISK  $OLD_START..$OLD_END  $((OLD_SECTORS * 512 / 1024 / 1024)) MiB"
echo "proposed split:"
echo "  p26 linux  $OLD_START..$LINUX_END  2816 MiB (existing ext4, GUID $guid)"
echo "  p27 UDISK  $ANDROID_START..$ANDROID_END  $(((ANDROID_END - ANDROID_START + 1) * 512 / 1024 / 1024)) MiB (new f2fs)"

if [ "$APPLY" -ne 1 ]; then
	echo "dry run only; pass --apply to perform the migration"
	exit 0
fi

[ -n "$BACKUP_DIR" ] || BACKUP_DIR="$(pwd)/h713-split-backup"
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
before="$BACKUP_DIR/h713-gpt-before-split-$stamp.bin"
after="$BACKUP_DIR/h713-gpt-after-split-$stamp.bin"

echo "==> backing up the original GPT to $before"
sgdisk --backup="$before" "$DEV"
sgdisk -p "$DEV" >"$before.txt"

run_e2fsck() {
	local rc
	set +e
	# Preen mode makes safe repairs without needing a controlling terminal and
	# refuses anything that would require operator judgement.  In that case the
	# status is >= 2 and the migration stops before resize2fs is allowed to run.
	e2fsck -fp "$1"
	rc=$?
	set -e
	[ "$rc" -le 1 ] || die "e2fsck failed with status $rc"
}

echo "==> checking $P26 before resize"
run_e2fsck "$P26"
block_size=$(tune2fs -l "$P26" | awk -F': *' '/Block size:/ {print $2}')
[ "$block_size" -eq 4096 ] || die "$P26 block size is $block_size, expected 4096"
minimum=$(resize2fs -P "$P26" 2>&1 | awk '/minimum size/ {print $NF}')
[ -n "$minimum" ] || die "could not determine the minimum ext4 size"
[ "$minimum" -le "$EXT4_BLOCKS" ] \
	|| die "ext4 needs at least $minimum blocks; target is $EXT4_BLOCKS"

echo "==> shrinking ext4 from $OLD_SECTORS sectors to $LINUX_SECTORS sectors"
resize2fs "$P26" "$EXT4_BLOCKS"
run_e2fsck "$P26"

echo "==> expanding the GPT to 28 entries and creating the split"
sgdisk --resize-table=28 "$DEV"
sgdisk \
	--delete=26 \
	--new=26:"$OLD_START":"$LINUX_END" \
	--typecode=26:0700 \
	--change-name=26:linux \
	--partition-guid=26:"$guid" \
	--attributes=26:set:63 \
	--new=27:"$ANDROID_START":"$ANDROID_END" \
	--typecode=27:0700 \
	--change-name=27:UDISK \
	--attributes=27:set:63 \
	"$DEV"
sgdisk --verify "$DEV"

# 28 * 128-byte entries consume seven 512-byte sectors at LBA 2..8.  Refuse
# any tool behaviour that grows that array into the SPL at LBA 16.
gpt_print=$(sgdisk -p "$DEV")
entry_count=$(awk '/Partition table holds up to/ {print $(NF - 1)}' <<<"$gpt_print")
main_table_end=$(awk '/Main partition table begins/ {print $NF}' <<<"$gpt_print")
[ "$entry_count" -le 28 ] \
	|| die "GPT has $entry_count entries; its primary array may overlap the SPL"
[ "$main_table_end" -lt 16 ] \
	|| die "primary GPT ends at LBA $main_table_end and overlaps the SPL at LBA 16"

partprobe "$DEV"
udevadm settle
[ -b "$P26" ] || die "$P26 did not reappear after the GPT update"
[ -b "$P27" ] || die "$P27 did not appear after the GPT update"
[ "$(blockdev --getsz "$P26")" -eq "$LINUX_SECTORS" ] \
	|| die "$P26 has the wrong size after the GPT update"
[ "$(blockdev --getsz "$P27")" -eq "$((ANDROID_END - ANDROID_START + 1))" ] \
	|| die "$P27 has the wrong size after the GPT update"

echo "==> labelling Debian and creating Android userdata"
e2label "$P26" linux
make_f2fs -f -g android -l UDISK "$P27"
fsck.f2fs -f "$P27"

[ "$(blkid -s TYPE -o value "$P26")" = ext4 ] || die "$P26 lost its ext4 signature"
[ "$(blkid -s LABEL -o value "$P26")" = linux ] || die "$P26 label verification failed"
[ "$(blkid -s TYPE -o value "$P27")" = f2fs ] || die "$P27 f2fs verification failed"
[ "$(blkid -s LABEL -o value "$P27")" = UDISK ] || die "$P27 label verification failed"

sgdisk --backup="$after" "$DEV"
sgdisk -p "$DEV" >"$after.txt"
sync

echo "split complete and verified"
echo "  Debian: $P26 (GPT name linux, ext4 label linux)"
echo "  Android: $P27 (GPT name UDISK, f2fs label UDISK)"
echo "  GPT backups: $before and $after"
