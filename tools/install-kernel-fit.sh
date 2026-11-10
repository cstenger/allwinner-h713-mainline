#!/usr/bin/env bash
# Install a kernel FIT onto the board's boot FAT, over the network. RUNS ON THE HOST.
#
# This exists because the documented alternative is a 17-minute YMODEM transfer
# at the U-Boot prompt, which was the only option while the WiFi link could not
# carry a file. It can now (patches 0046/0048), so a kernel swap is a copy and a
# reboot -- about twenty seconds -- and there is no reason to sit on a serial
# console for it.
#
# WHAT IT PROTECTS AGAINST, because overwriting the thing the board boots from
# deserves care:
#
#   * the FAT at mmcblk0p2 is 32 MiB and ~90% full -- there is NOT room for two
#     FITs, so the outgoing kernel is copied to the media-data filesystem first
#     and the script refuses to continue if that backup fails;
#   * the copy is verified by md5 on the board after unmount, not assumed from
#     scp's exit status;
#   * the board is left running the OLD kernel unless --reboot is given, so a
#     bad FIT is a reboot away from being replaced rather than already booted.
#
# WHAT PERSISTS, and why only that (2026-09-29, after both filesystems filled):
#
#   * the UPLOAD is staged in /tmp, a tmpfs.  Once it is md5-verified on the FAT
#     it is redundant -- the FAT has it and the host has the build -- so it is
#     deleted, and a failed transfer can no longer leave a truncated file behind
#     on persistent storage (two 0-byte ones had accumulated);
#   * the BACKUP of the outgoing kernel stays on media-data, NOT in /tmp: the
#     reboot is exactly when a bad kernel is discovered, tmpfs does not survive
#     it, and U-Boot can fatload from media-data for recovery.  It is also
#     sometimes the only copy -- a kernel built in another worktree;
#   * backups ROTATE: the oldest are pruned BEFORE the new one is written, so a
#     full partition cannot block the backup, keeping KEEP (default 2).  Only
#     files named replaced-*.fit / staged-*.fit in STAGE_DIR are ever removed.
#
# The way back is always: install the backup it just made.
#
#   usage: tools/install-kernel-fit.sh build/out/h713-kernel-sysrq.fit [--reboot]
#          BOARD=192.168.4.1 tools/install-kernel-fit.sh <fit> [--reboot]
set -euo pipefail

FIT=${1:?usage: install-kernel-fit.sh <fit-file> [--reboot]}
REBOOT=${2:-}
BOARD=${BOARD:-192.168.4.1}
SSH=(ssh -F /dev/null -o ConnectTimeout=5 "root@$BOARD")
TARGET_NAME=${TARGET_NAME:-h713-kernel.fit}
MEDIA_DEVICE=${MEDIA_DEVICE:-/dev/mmcblk0p23}
MEDIA_FSTYPE=${MEDIA_FSTYPE:-vfat}
MEDIA_MOUNT=${MEDIA_MOUNT:-/mnt/media-data}
STAGE_DIR=${STAGE_DIR:-$MEDIA_MOUNT/h713-kernel-fits}
STAMP=$(date +%Y%m%d-%H%M%S)
KEEP=${KEEP:-2}
UPLOAD=/tmp/h713-staged-$STAMP.fit

[ -r "$FIT" ] || { echo "error: no such FIT: $FIT" >&2; exit 1; }

# A FIT starts with the device-tree magic d00dfeed. Catching a truncated or
# wrong-file argument here is cheaper than catching it at the boot prompt.
magic=$(head -c4 "$FIT" | od -An -tx1 | tr -d ' \n')
[ "$magic" = "d00dfeed" ] || { echo "error: $FIT is not a FIT (magic $magic)" >&2; exit 1; }

size=$(stat -c%s "$FIT")
sum=$(md5sum "$FIT" | cut -d' ' -f1)
echo "==> $FIT ($size bytes, md5 $sum) -> $BOARD:$TARGET_NAME"

"${SSH[@]}" "set -e
	if ! mountpoint -q '$MEDIA_MOUNT'; then
		mount -t '$MEDIA_FSTYPE' '$MEDIA_DEVICE' '$MEDIA_MOUNT'
	fi
	mkdir -p '$STAGE_DIR'"
echo "==> uploading to $UPLOAD (tmpfs)"
scp -F /dev/null -o ConnectTimeout=5 "$FIT" "root@$BOARD:$UPLOAD" >/dev/null

"${SSH[@]}" "set -e
	got=\$(md5sum '$UPLOAD' | cut -d' ' -f1)
	[ \"\$got\" = '$sum' ] || { rm -f '$UPLOAD'; echo 'error: upload corrupted'; exit 1; }

	# Prune before backing up, so a full media-data cannot block the backup.
	# Legacy staged-*.fit are redundant uploads; keep the newest KEEP-1
	# replaced-*.fit so the one about to be written makes KEEP.
	find '$STAGE_DIR' -maxdepth 1 -name 'staged-*.fit' -print -delete |
		sed 's/^/    pruned legacy upload /'
	find '$STAGE_DIR' -maxdepth 1 -name 'replaced-*.fit' | sort |
		head -n -$((KEEP - 1)) | while read -r old; do
			rm -f \"\$old\"; echo \"    pruned old backup \$old\"
		done

	mkdir -p /mnt/boot
	mountpoint -q /mnt/boot || mount -t vfat /dev/mmcblk0p2 /mnt/boot

	if [ -f /mnt/boot/$TARGET_NAME ]; then
		cp /mnt/boot/$TARGET_NAME '$STAGE_DIR/replaced-$STAMP.fit'
		echo \"    backed up the outgoing kernel to $STAGE_DIR/replaced-$STAMP.fit\"
	else
		echo '    note: no existing $TARGET_NAME on the FAT'
	fi

	cp '$UPLOAD' /mnt/boot/$TARGET_NAME
	sync
	umount /mnt/boot

	mount -t vfat /dev/mmcblk0p2 /mnt/boot
	got=\$(md5sum /mnt/boot/$TARGET_NAME | cut -d' ' -f1)
	umount /mnt/boot
	[ \"\$got\" = '$sum' ] || { echo \"error: FAT copy is \$got, expected $sum\"; exit 1; }
	rm -f '$UPLOAD'
	echo '    installed and verified on the FAT; upload removed from /tmp'"

if [ "$REBOOT" = "--reboot" ]; then
	echo "==> rebooting"
	"${SSH[@]}" "( sleep 1; reboot ) >/dev/null 2>&1 &" || true
	echo "    give it ~30 s, then: ssh root@$BOARD uname -a"
else
	echo "==> NOT rebooting (pass --reboot to boot it now)"
fi
