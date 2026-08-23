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
#     FITs, so the outgoing kernel is copied to the rootfs first and the script
#     refuses to continue if that backup fails;
#   * the copy is verified by md5 on the board after unmount, not assumed from
#     scp's exit status;
#   * the board is left running the OLD kernel unless --reboot is given, so a
#     bad FIT is a reboot away from being replaced rather than already booted.
#
# The way back is always: install the backup it just made.
#
#   usage: tools/install-kernel-fit.sh build/out/h713-kernel-sysrq.fit [--reboot]
#          BOARD=192.168.4.1 tools/install-kernel-fit.sh <fit> [--reboot]
set -euo pipefail

FIT=${1:?usage: install-kernel-fit.sh <fit-file> [--reboot]}
REBOOT=${2:-}
BOARD=${BOARD:-192.168.4.1}
SSH="ssh -o ConnectTimeout=5 root@$BOARD"
TARGET_NAME=${TARGET_NAME:-h713-kernel.fit}
STAMP=$(date +%Y%m%d-%H%M%S)

[ -r "$FIT" ] || { echo "error: no such FIT: $FIT" >&2; exit 1; }

# A FIT starts with the device-tree magic d00dfeed. Catching a truncated or
# wrong-file argument here is cheaper than catching it at the boot prompt.
magic=$(head -c4 "$FIT" | od -An -tx1 | tr -d ' \n')
[ "$magic" = "d00dfeed" ] || { echo "error: $FIT is not a FIT (magic $magic)" >&2; exit 1; }

size=$(stat -c%s "$FIT")
sum=$(md5sum "$FIT" | cut -d' ' -f1)
echo "==> $FIT ($size bytes, md5 $sum) -> $BOARD:$TARGET_NAME"

$SSH "mkdir -p /root/fits"
echo "==> uploading to /root/fits/staged-$STAMP.fit"
scp -o ConnectTimeout=5 "$FIT" "root@$BOARD:/root/fits/staged-$STAMP.fit" >/dev/null

$SSH "set -e
	got=\$(md5sum /root/fits/staged-$STAMP.fit | cut -d' ' -f1)
	[ \"\$got\" = '$sum' ] || { echo 'error: upload corrupted'; exit 1; }

	mkdir -p /mnt/boot
	mountpoint -q /mnt/boot || mount -t vfat /dev/mmcblk0p2 /mnt/boot

	if [ -f /mnt/boot/$TARGET_NAME ]; then
		cp /mnt/boot/$TARGET_NAME /root/fits/replaced-$STAMP.fit
		echo \"    backed up the outgoing kernel to /root/fits/replaced-$STAMP.fit\"
	else
		echo '    note: no existing $TARGET_NAME on the FAT'
	fi

	cp /root/fits/staged-$STAMP.fit /mnt/boot/$TARGET_NAME
	sync
	umount /mnt/boot

	mount -t vfat /dev/mmcblk0p2 /mnt/boot
	got=\$(md5sum /mnt/boot/$TARGET_NAME | cut -d' ' -f1)
	umount /mnt/boot
	[ \"\$got\" = '$sum' ] || { echo \"error: FAT copy is \$got, expected $sum\"; exit 1; }
	echo '    installed and verified on the FAT'"

if [ "$REBOOT" = "--reboot" ]; then
	echo "==> rebooting"
	$SSH "( sleep 1; reboot ) >/dev/null 2>&1 &" || true
	echo "    give it ~30 s, then: ssh root@$BOARD uname -a"
else
	echo "==> NOT rebooting (pass --reboot to boot it now)"
fi
