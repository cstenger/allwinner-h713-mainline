#!/usr/bin/env bash
# Turn the MIPS display firmware's DRAM log (elog) on or off FOR THE VENDOR
# STACK, from our Debian, over ssh.
#
# The vendor's U-Boot loads bootloader_a:/mips/display_cfg.xml; ours loads
# bootloader_b's. The 2026-09-04 elog change (mode 1->2 "buf", level 1->5) was
# made only in ours, so under stock there is no DRAM log. This flips exactly
# the same two bytes in the vendor's copy -- nothing else:
#
#   bootloader_a (/dev/mmcblk0p1), file at partition offset 0x340200, 4743 bytes
#     +4642  <mode val='1'>   '1' -> '2'
#     +4668  <level val='1'>  '1' -> '5'
#
# Raw writes, no mount: no FAT metadata changes. Guarded both ways: it refuses
# to write unless the whole file hashes to one of the two known states, and
# checks the hash again after the write. Offsets and hashes are from the
# 2026-10-01 read of this board (board B).
#
#   tools/stock/vendor-elog-cfg.sh status
#   tools/stock/vendor-elog-cfg.sh on      before switching to stock
#   tools/stock/vendor-elog-cfg.sh off     after returning (restores stock exactly)
set -euo pipefail

BOARD=${BOARD:-192.168.4.1}
DEV=/dev/mmcblk0p1
OFF=3408384 LEN=4743
MODE_AT=$((OFF + 4642)) LEVEL_AT=$((OFF + 4668))
SHA_STOCK=b3e6e8f60d6f96ff458046af655f4b51e8e36ffc70f5107b0fef91badeca192a	# mode 1 level 1
SHA_ELOG=f97eec07346a4b95227970423da2b548c7f39f47e565f96efafaccf149200d8a	# mode 2 level 5 (= bootloader_b)

b() { ssh -F /dev/null -o ConnectTimeout=8 -o BatchMode=yes -o LogLevel=ERROR "root@$BOARD" "$@"; }

state() {
	local sha
	b "[ \"\$(cat /sys/class/block/mmcblk0p1/uevent | grep PARTNAME=)\" = PARTNAME=bootloader_a ]" \
		|| { echo "mmcblk0p1 is not bootloader_a -- refusing" >&2; exit 1; }
	sha=$(b "dd if=$DEV bs=1 skip=$OFF count=$LEN 2>/dev/null | sha256sum" | cut -d' ' -f1)
	case $sha in
	"$SHA_STOCK") echo stock ;;
	"$SHA_ELOG")  echo elog ;;
	*)            echo "unknown:$sha" ;;
	esac
}

set_bytes() {  # MODE LEVEL
	b "printf $1 | dd of=$DEV bs=1 seek=$MODE_AT count=1 conv=notrunc,fsync 2>/dev/null &&
	   printf $2 | dd of=$DEV bs=1 seek=$LEVEL_AT count=1 conv=notrunc,fsync 2>/dev/null && sync"
}

now=$(state)
case ${1:-status} in
status) echo "vendor display_cfg.xml: $now" ;;
on)
	case $now in
	elog)  echo "already elog" ;;
	stock) set_bytes 2 5; [ "$(state)" = elog ] && echo "vendor display_cfg.xml: stock -> elog (verified)" \
		|| { echo "VERIFY FAILED: $(state)" >&2; exit 1; } ;;
	*)     echo "refusing: file is $now, not a known state" >&2; exit 1 ;;
	esac ;;
off)
	case $now in
	stock) echo "already stock" ;;
	elog)  set_bytes 1 1; [ "$(state)" = stock ] && echo "vendor display_cfg.xml: elog -> stock (verified)" \
		|| { echo "VERIFY FAILED: $(state)" >&2; exit 1; } ;;
	*)     echo "refusing: file is $now, not a known state" >&2; exit 1 ;;
	esac ;;
*) sed -n '2,24p' "$0"; exit 2 ;;
esac
