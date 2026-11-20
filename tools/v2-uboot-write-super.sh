#!/usr/bin/env bash
# Install a read-only root image into the projector's super partition from
# our U-Boot, with no host root and no UMS (HY200_QZ713_V2; docs/
# lpddr3-bringup-plan.md Phase 4 stage 2).
#
#   LOG=uart.log tools/v2-uboot-write-super.sh IMAGE FSTYPE
#
# The board must be at our U-Boot prompt on the UART, with a UART logger
# (tools/serial/soak-capture.py) writing LOG. FSTYPE is erofs, squashfs or
# ext4. Steps:
#   1. `fastboot usb 0` on the board; tools/board-guard.py --fastboot must
#      confirm the projector before anything is written.
#   2. `fastboot erase super` (the eMMC needs its free blocks back; see the
#      2026-11-20 eMMC write faults), then `fastboot flash super IMAGE` (the
#      host splits it into sparse pieces that fit U-Boot's 32 MiB buffer).
#   3. Back at the prompt, read the image back from the eMMC in 128 MiB pieces
#      and compare each piece's crc32 with the host's.
#   4. Set bootargs for FSTYPE and saveenv (bootcmd is unchanged).
set -uo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
img=${1:?IMAGE}; fstype=${2:?FSTYPE}
tty=${TTY:-/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0}
log=${LOG:?LOG=the UART logger output}
SUPER_LBA=$((0x92400)); SUPER_SIZE=$((2 << 30)); PIECE=$((128 << 20)); RAM=0x50000000
say() { printf '[write-super] %s\n' "$*"; }
die() { say "FAIL: $*"; exit 1; }
send() { printf '%s\n' "$1" > "$tty"; }
since() { tail -c +"$(($1 + 1))" "$log" | tr '\r' '\n'; }
# ub CMD WAIT_S PATTERN: run a U-Boot command, print its output once PATTERN
# appears (or after WAIT_S seconds).
ub() {
	local n0; n0=$(stat -c %s "$log"); send "$1"
	for _ in $(seq 1 $((${2:-5} * 4))); do
		sleep 0.25; since "$n0" | grep -aq -- "${3:-=> }" && break
	done
	since "$n0"
}

case "$fstype" in erofs|squashfs|ext4) ;; *) die "FSTYPE must be erofs, squashfs or ext4" ;; esac
[ -f "$img" ] || die "missing $img"
size=$(stat -c %s "$img")
[ "$size" -le "$SUPER_SIZE" ] || die "$img is larger than super"
[ $((size % 512)) = 0 ] || die "$img is not a whole number of 512-byte blocks"
ub "" 2 | grep -aq '=> ' || die "no U-Boot prompt on the UART"

say "fastboot on the board"
send "fastboot usb 0"; sleep 3
python3 "$ROOT/tools/board-guard.py" --expect hy200-qz713-v2 --fastboot || { send $'\003'; die "board guard refused"; }
part=$(fastboot getvar partition-size:super 2>&1 | sed -n 's/^partition-size:super: *//p')
[ $((part)) = "$SUPER_SIZE" ] || { send $'\003'; die "fastboot says super is ${part:-?}, not 2 GiB"; }
say "erasing super"
fastboot erase super || { send $'\003'; die "fastboot erase super failed"; }
say "flashing $(basename "$img") ($((size >> 20)) MiB, sha256 $(sha256sum "$img" | cut -c1-12))"
fastboot flash super "$img" || { send $'\003'; die "fastboot flash super failed"; }
send $'\003'; sleep 2
ub "" 2 | grep -aq '=> ' || die "U-Boot prompt did not come back after fastboot"

say "verifying from the eMMC in $((PIECE >> 20)) MiB pieces"
ub "mmc dev 1" 3 >/dev/null
for ((off = 0; off < size; off += PIECE)); do
	len=$(( size - off < PIECE ? size - off : PIECE ))
	want=$(tail -c +$((off + 1)) "$img" | head -c "$len" | python3 -c 'import sys,zlib; print("%08x" % zlib.crc32(sys.stdin.buffer.read()))')
	ub "mmc read $RAM $(printf '%#x %#x' $((SUPER_LBA + off / 512)) $((len / 512)))" 20 'blocks read' >/dev/null
	got=$(ub "crc32 $RAM $(printf '%#x' "$len")" 10 '==>' | grep -ao '==> [0-9a-f]*' | tail -1 | cut -c5-)
	[ "$got" = "$want" ] || die "piece at +$((off >> 20)) MiB: eMMC crc32 ${got:-?}, image $want"
	say "  +$((off >> 20)) MiB: $got ok"
done

args="console=ttyS0,115200 console=tty0 earlycon root=/dev/mmcblk0p9 rootfstype=$fstype ro rootwait init=/usr/lib/h713/preinit net.ifnames=0 panic=5 clk_ignore_unused pd_ignore_unused hy310_board_mgr.no_rpm_shutdown=1 cma=128M"
ub "setenv bootargs $args" 2 >/dev/null
ub "saveenv" 5 'OK' | grep -aq 'OK' || die "saveenv failed"
say "done: super holds $(basename "$img"), bootargs rootfstype=$fstype saved"
