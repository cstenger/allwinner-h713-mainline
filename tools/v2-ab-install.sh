#!/usr/bin/env bash
# Install the projector's A/B layout from our U-Boot (HY200_QZ713_V2;
# docs/lpddr3-bringup-plan.md, Phase 4). No host root, no UMS.
#
#   LOG=uart.log tools/v2-ab-install.sh GPT_DIR ROOT_IMAGE [BOOT_IMAGE] [UBOOT_IMAGE]
#
# GPT_DIR holds the original primary/backup GPT (gpt-pri.bin, gpt-bak.bin) and
# tools/v2-gpt-ab-split.py's output (ab/new-primary.bin, ab/new-backup.bin).
# BOOT_IMAGE defaults to build/out/v2-boot.vfat (tools/v2-boot-image.sh),
# UBOOT_IMAGE to build/out/u-boot-sunxi-with-spl-lpddr3.bin (patch 0012).
# The board must be at our U-Boot prompt on the UART, with a UART logger
# writing LOG. Every write is checked by crc32 read back from the eMMC in
# U-Boot before the next step starts:
#   1. board guard over fastboot;
#   2. GPT: the board's LBA 1..8 and last 33 LBAs must equal the saved
#      original; then the split table (root_a p9, root_b p16) is written;
#   3. U-Boot proper (the image past its 32 KiB SPL) at LBA 0x49ac00, then both
#      environment copies cleared so it boots from its defaults; the SPL at
#      LBA 16 is not touched;
#   4. boot_a and boot_b get BOOT_IMAGE, root_a and root_b get ROOT_IMAGE,
#      each erased first (fastboot erase + flash, host-side sparse split).
# STEPS="gpt uboot slots" selects steps (default all, in that order).
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
gdir=${1:?GPT_DIR}; rootimg=${2:?ROOT_IMAGE}
bootimg=${3:-$ROOT/build/out/v2-boot.vfat}
ubimg=${4:-$ROOT/build/out/u-boot-sunxi-with-spl-lpddr3.bin}
steps=${STEPS:-gpt uboot slots}
tty=${TTY:-/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0}
log=${LOG:?LOG=the UART logger output}
DISK=$((0xE90000)); PROPER_LBA=$((0x49AC00)); RAM=0x50000000; STAGE=0x42000000
say() { printf '[ab-install] %s\n' "$*"; }
die() { say "FAIL: $*"; exit 1; }
send() { printf '%s\n' "$1" > "$tty"; }
since() { tail -c +"$(($1 + 1))" "$log" | tr '\r' '\n'; }
ub() {	# CMD WAIT_S PATTERN
	local n0; n0=$(stat -c %s "$log"); send "$1"
	for _ in $(seq 1 $((${2:-5} * 4))); do sleep 0.25; since "$n0" | grep -aq -- "${3:-=> }" && break; done
	since "$n0"
}
hcrc() { python3 -c 'import sys,zlib; print("%08x" % zlib.crc32(sys.stdin.buffer.read()))'; }
# board_crc LBA NBYTES: crc32 of eMMC bytes read in U-Boot (NBYTES <= 128 MiB)
board_crc() {
	ub "mmc read $RAM $(printf '%#x %#x' "$1" $((($2 + 511) / 512)))" 20 'blocks read' >/dev/null
	ub "crc32 $RAM $(printf '%#x' "$2")" 10 '==>' | grep -ao '==> [0-9a-f]*' | tail -1 | cut -c5-
}
# verify_file FILE LBA: whole file against the eMMC, 128 MiB at a time
verify_file() {
	local f=$1 lba=$2 size off len want got piece=$((128 << 20))
	size=$(stat -c %s "$f")
	for ((off = 0; off < size; off += piece)); do
		len=$(( size - off < piece ? size - off : piece ))
		want=$(tail -c +$((off + 1)) "$f" | head -c "$len" | hcrc)
		got=$(board_crc $((lba + off / 512)) "$len")
		[ "$got" = "$want" ] || die "$(basename "$f") +$((off >> 20)) MiB: eMMC ${got:-?}, file $want"
	done
	say "  $(basename "$f") verified at LBA $(printf '%#x' "$lba") ($((size >> 10)) KiB)"
}
fastboot_on() { send "fastboot usb 0"; sleep 3; }
fastboot_off() { send $'\003'; sleep 2; ub "" 2 | grep -aq '=> ' || die "no U-Boot prompt after fastboot"; }
# stage_write FILE LBA: fastboot stage (<= 32 MiB), crc in RAM, mmc write
stage_write() {
	local f=$1 lba=$2 size want got
	size=$(stat -c %s "$f"); want=$(hcrc < "$f")
	fastboot_on; fastboot stage "$f" >/dev/null 2>&1 || { fastboot_off; die "fastboot stage $(basename "$f")"; }; fastboot_off
	got=$(ub "crc32 $STAGE $(printf '%#x' "$size")" 10 '==>' | grep -ao '==> [0-9a-f]*' | tail -1 | cut -c5-)
	[ "$got" = "$want" ] || die "staged $(basename "$f") crc ${got:-?}, file $want"
	ub "mmc write $STAGE $(printf '%#x %#x' "$lba" $(((size + 511) / 512)))" 20 'blocks written' | grep -aq 'written: OK' ||
		die "mmc write of $(basename "$f") failed"
}
part_lba() {	# NAME -> start LBA from U-Boot's view of the GPT
	ub "part start mmc 1 $1 h713_ps; echo PS=\$h713_ps" 3 'PS=' | grep -ao 'PS=[0-9a-f]*' | tail -1 | cut -c4-
}

for f in "$gdir/gpt-pri.bin" "$gdir/gpt-bak.bin" "$gdir/ab/new-primary.bin" "$gdir/ab/new-backup.bin" "$rootimg" "$bootimg" "$ubimg"; do
	[ -f "$f" ] || die "missing $f"
done
ub "" 2 | grep -aq '=> ' || die "no U-Boot prompt on the UART"
fastboot_on
python3 "$ROOT/tools/board-guard.py" --expect hy200-qz713-v2 --fastboot || { fastboot_off; die "board guard refused"; }
fastboot_off
ub "mmc dev 1" 3 >/dev/null

if [[ " $steps " == *" gpt "* ]]; then
	say "GPT: checking the board still has the saved original"
	[ "$(board_crc 1 $((8 * 512)))" = "$(tail -c +513 "$gdir/gpt-pri.bin" | head -c $((8 * 512)) | hcrc)" ] ||
		die "primary GPT on the board is not the saved original"
	[ "$(board_crc $((DISK - 33)) $((33 * 512)))" = "$(hcrc < "$gdir/gpt-bak.bin")" ] ||
		die "backup GPT on the board is not the saved original"
	say "GPT: writing the split table"
	stage_write "$gdir/ab/new-primary.bin" 1
	verify_file "$gdir/ab/new-primary.bin" 1
	stage_write "$gdir/ab/new-backup.bin" $((DISK - 33))
	verify_file "$gdir/ab/new-backup.bin" $((DISK - 33))
	ub "mmc rescan" 5 >/dev/null
	ub "part list mmc 1" 5 | grep -aE '^\s+(9|16)\s' | sed 's/^/  /'
	[ "$(part_lba root_b)" = 292400 ] || die "U-Boot does not see root_b at 0x292400 after the GPT write"
fi

if [[ " $steps " == *" uboot "* ]]; then
	say "U-Boot proper from $(basename "$ubimg")"
	tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
	tail -c +32769 "$ubimg" > "$tmp/proper.bin"
	python3 - "$tmp/proper.bin" <<'EOF' || die "proper is not an FDT/FIT image of its own length"
import struct, sys
d = open(sys.argv[1], 'rb').read()
m, n = struct.unpack('>II', d[:8])
sys.exit(0 if m == 0xd00dfeed and n <= len(d) else 1)
EOF
	stage_write "$tmp/proper.bin" $PROPER_LBA
	verify_file "$tmp/proper.bin" $PROPER_LBA
	# Clear both environment copies (0x93d80000 and 0x93d90000, 128 KiB from
	# LBA 0x49ec00) so the new U-Boot starts from its built-in defaults; an
	# environment saved by an older build would override its bootcmd.
	say "clearing the saved environment (both copies)"
	ub "mw.b $STAGE 0 0x20000" 3 >/dev/null
	ub "mmc write $STAGE 0x49ec00 0x100" 10 'blocks written' | grep -aq 'written: OK' || die "clearing the environment failed"
	head -c $((128 << 10)) /dev/zero > "$tmp/zero-env.bin"
	verify_file "$tmp/zero-env.bin" $((0x49EC00))
fi

if [[ " $steps " == *" slots "* ]]; then
	for pair in "boot_a:$bootimg" "boot_b:$bootimg" "root_a:$rootimg" "root_b:$rootimg"; do
		part=${pair%%:*}; img=${pair#*:}
		lba=$(part_lba "$part"); [ -n "$lba" ] || die "U-Boot has no partition $part"
		say "$part (LBA 0x$lba): $(basename "$img")"
		fastboot_on
		fastboot erase "$part" >/dev/null 2>&1 || { fastboot_off; die "fastboot erase $part"; }
		fastboot flash "$part" "$img" >/dev/null 2>&1 || { fastboot_off; die "fastboot flash $part"; }
		fastboot_off
		verify_file "$img" $((16#$lba))
	done
fi
say "done: $steps"
