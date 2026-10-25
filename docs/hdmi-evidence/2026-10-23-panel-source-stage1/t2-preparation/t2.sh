#!/bin/sh
# Panel-source T2: install / roll back the NRWinNode::WriteReg trace proper.
#   sh t2.sh check      read-only: report which proper is installed and verify
#                       every protected region (default)
#   sh t2.sh install    write the trial proper (requires the exact 1b1f702f
#                       image installed and all regions intact)
#   sh t2.sh rollback   write back the exact 1b1f702f proper
#   sh t2.sh install-dry  every install guard, then stop before writing
#                       (the only mode negative tests may use)
# Design: docs/hdmi-panel-source-design-2026-10-23.md section 10.8.
set -eu
base=/root/panel-source-t2
dev=/dev/mmcblk0
LBA=4828160; N=1877                       # 0x49ac00, U-Boot proper slot
BEFORE=1b1f702fc7b52adf8246b124b8fbe209b7dadc651a37e53a600689810c45302e
TRIAL=cb8e417aa31ac2df0b072e37446acef549a004fc51860fea9aa065140f0349fe
REGION_BEFORE=74b346e3b04516078ccbf8a0119c7eea162eeb074ffd84318f2afeee3f43ed25
region_hash() { dd if=$dev bs=512 skip="$1" count="$2" iflag=direct status=none | sha256sum | cut -d ' ' -f1; }
file_ok() { [ "$(wc -c < "$1")" -eq $((N * 512)) ] && [ "$(sha256sum "$1" | cut -d ' ' -f1)" = "$2" ]; }
others() {
	[ "$(region_hash 4852736 1798)" = c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7 ] || { echo "FAIL rescue slot"; return 1; }
	[ "$(region_hash 16 64)" = cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec ] || { echo "FAIL SPL"; return 1; }
	[ "$(region_hash 4844544 128)" = de2f256064a0af797747c2b97505dc0b9f3df0de4f489eac731c23ae9ca9cc31 ] || { echo "FAIL configured env"; return 1; }
	[ "$(region_hash 3337216 128)" = 6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc ] || { echo "FAIL active env"; return 1; }
	dd if=$dev bs=512 skip=$LBA count=4096 iflag=direct status=none | tail -c +$((N * 512 + 1)) | sha256sum | cut -d ' ' -f1 > $base/.tail-now
	tail -c +$((N * 512 + 1)) $base/proper-region-before-2MiB.bin | sha256sum | cut -d ' ' -f1 > $base/.tail-before
	cmp -s $base/.tail-now $base/.tail-before || { echo "FAIL 2-MiB region tail"; return 1; }
}
installed() {
	h=$(region_hash $LBA $N)
	case "$h" in $BEFORE) echo before ;; $TRIAL) echo trial ;; *) echo "unknown:$h" ;; esac
}
write() { # image expected
	dd if="$1" of=$dev bs=512 seek=$LBA count=$N conv=fsync,notrunc status=none
	sync
	[ "$(region_hash $LBA $N)" = "$2" ] || { echo "FAIL readback after write"; exit 1; }
}
file_ok $base/proper-before-1877.bin $BEFORE || { echo "FAIL rollback image"; exit 1; }
file_ok $base/proper-trial-1877.bin $TRIAL || { echo "FAIL trial image"; exit 1; }
[ "$(sha256sum $base/proper-region-before-2MiB.bin | cut -d ' ' -f1)" = $REGION_BEFORE ] || { echo "FAIL region backup"; exit 1; }
cmd=${1:-check}
state=$(installed)
case "$cmd" in
check)
	others; echo "PASS check: installed=$state; images, rescue, SPL, both environments and region tail verified" ;;
install-dry)
	[ "$state" = before ] || { echo "REFUSE install: installed=$state"; exit 1; }
	others; echo "PASS install-dry: all install guards pass; nothing written" ;;
install)
	[ "$state" = before ] || { echo "REFUSE install: installed=$state"; exit 1; }
	others; write $base/proper-trial-1877.bin $TRIAL; others
	echo "PASS install: trial proper written and read back; other regions unchanged; reboot separately" ;;
rollback)
	[ "$state" = trial ] || [ "$state" = before ] || { echo "REFUSE rollback: installed=$state"; exit 1; }
	write $base/proper-before-1877.bin $BEFORE; others
	echo "PASS rollback: 1b1f702f proper restored and read back; other regions unchanged; reboot separately" ;;
*) echo "usage: sh t2.sh [check|install-dry|install|rollback]"; exit 2 ;;
esac
