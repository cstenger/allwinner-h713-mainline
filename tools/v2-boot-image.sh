#!/usr/bin/env bash
# Build the projector's slot boot partition image (HY200_QZ713_V2, A/B with
# U-Boot's bootmeth_rauc; U-Boot patch 0012).
#
#   tools/v2-boot-image.sh [FIT] [OUT]
#
# FIT defaults to build/out/h713-kernel.fit, OUT to build/out/v2-boot.vfat. The
# image is a 64 MiB vfat (the size of boot_a/boot_b) holding the FIT and a
# boot.scr. bootmeth_rauc runs that script with devtype, devnum,
# distro_bootpart and distro_rootpart (hex) set for the chosen slot, and
# raucargs = "rauc.slot=A|B". The script names the root by PARTUUID, so the
# same image works in either slot. Built without root (mtools).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fit=${1:-$ROOT/build/out/h713-kernel.fit}
out=${2:-$ROOT/build/out/v2-boot.vfat}
mkimage=$ROOT/build/uboot-lpddr3/tools/mkimage
[ -f "$fit" ] || { echo "missing $fit" >&2; exit 1; }
[ -x "$mkimage" ] || { echo "missing $mkimage (BOARD=lpddr3 tools/build/build.sh uboot)" >&2; exit 1; }
for t in mkfs.vfat mcopy mdir; do command -v "$t" >/dev/null || { echo "$t not installed (dosfstools/mtools)" >&2; exit 1; }; done

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/boot.cmd" <<'EOF'
# HY200_QZ713_V2 slot boot script, run by U-Boot's bootmeth_rauc.
# `reboot usbdev` (RTC GP7 = 0x05bdb007, kernel 0215) asks for the USB port
# in device mode for this one boot. Read and cleared here, not in PREBOOT:
# bootmeth_rauc saves the environment before this script runs, so a variable
# set earlier would persist and every later boot would come up in device mode.
setenv h713_usbargs
if itest.l *0x0709011c == 0x05bdb007; then mw.l 0x0709011c 0; setenv h713_usbargs h713.usb=device; fi
# A failed load can leave old data at the FIT address after a warm reboot.
if part uuid ${devtype} ${devnum}:${distro_rootpart} h713_rootuuid && load ${devtype} ${devnum}:${distro_bootpart} 0x50000000 /h713-kernel.fit; then
	setenv bootargs "console=ttyS0,115200 console=tty0 earlycon root=PARTUUID=${h713_rootuuid} rootfstype=erofs ro rootwait init=/usr/lib/h713/preinit net.ifnames=0 panic=5 clk_ignore_unused pd_ignore_unused hy310_board_mgr.no_rpm_shutdown=1 cma=128M ${raucargs} ${h713_usbargs}"
	bootm 0x50000000#conf-v2
else
	exit 1
fi
EOF
"$mkimage" -A arm64 -T script -C none -n "h713 v2 slot boot" -d "$tmp/boot.cmd" "$tmp/boot.scr" >/dev/null
rm -f "$out"
mkfs.vfat -C -n BOOT "$out" 65536 >/dev/null
mcopy -i "$out" "$fit" ::/h713-kernel.fit
mcopy -i "$out" "$tmp/boot.scr" ::/boot.scr
mcopy -i "$out" "$tmp/boot.cmd" ::/boot.cmd
# Read back what was stored.
for f in h713-kernel.fit boot.scr; do
	src=$([ $f = boot.scr ] && echo "$tmp/boot.scr" || echo "$fit")
	cmp -s "$src" <(mcopy -i "$out" "::/$f" -) || { echo "read-back of $f differs" >&2; exit 1; }
done
echo "$out: $(stat -c %s "$out") bytes; FIT sha256 $(sha256sum "$fit" | cut -c1-12), boot.scr checked"
