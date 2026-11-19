#!/usr/bin/env bash
# Build a RAM-only busybox initramfs for FEL-booting a board with nothing of
# ours on its eMMC (the LPDDR3 projector, Phase 3 of docs/lpddr3-bringup-plan.md).
#
#   tools/build-ram-initramfs.sh ROOTFS_TAR OUT.cpio.gz
#
# Takes busybox and its three libraries from a release rootfs.tar (Debian
# arm64; the cache has no runtime libc6 .deb) and packs them with
# usr/gen_init_cpio from the prepared kernel tree, so /dev/console needs no
# root. /init mounts proc, sys, devtmpfs and tmpfs only, prints the memory,
# CPU and eMMC facts, and starts a shell. It never mounts or writes eMMC.
#
# BIN="FILE ..." adds more arm64 programs to /bin. They may only need the three
# libraries above (e.g. Debian's memtester: libc.so.6).
#
# Boot it over FEL (see tools/fel-uboot.sh):
#   EXTRA="0x50000000=build/out/h713-kernel.fit 0x58000000=OUT.cpio.gz
#          0x4fa00000=build/out/sun50i-h713-hy200-qz713-v2.dtb" \
#     tools/fel-uboot.sh build/out/h713-v2-felrescue.bin
#   => setenv bootargs console=ttyS0,115200 earlycon loglevel=7 rdinit=/init \
#        clk_ignore_unused pd_ignore_unused panic=0
#   => bootm 0x50000000 0x58000000:<size in hex> 0x4fa00000
# panic=0: a panic must halt, because a reboot here starts the vendor stack.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tar_in=${1:?ROOTFS_TAR}; out=${2:?OUT.cpio.gz}
gen=$(ls -dt "$ROOT"/build/linux-*/usr/gen_init_cpio 2>/dev/null | head -1)
[ -x "$gen" ] || { echo "no gen_init_cpio: run tools/build/build.sh kernel" >&2; exit 1; }

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
libs=(ld-linux-aarch64.so.1 libc.so.6 libresolv.so.2)
tar -xf "$tar_in" -C "$work" ./usr/bin/busybox \
  "${libs[@]/#/./usr/lib/aarch64-linux-gnu/}"

cat > "$work/init" <<'EOF'
#!/bin/busybox sh
# RAM-only initramfs: mounts nothing from eMMC and writes nothing to it.
/bin/busybox --install -s /bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null
mount -t tmpfs tmpfs /tmp
echo
echo "=== H713 RAM initramfs: $(uname -r) ==="
cat /proc/device-tree/model 2>/dev/null; echo
grep -E 'MemTotal|MemFree|MemAvailable' /proc/meminfo
echo "cpus: $(grep -c ^processor /proc/cpuinfo)"
for b in /sys/block/mmcblk*; do
  [ -e "$b" ] && echo "$(basename "$b"): $(cat "$b/size") sectors, ro=$(cat "$b/ro")"
done
for m in /sys/class/mmc_host/*/mmc*; do
  [ -e "$m/type" ] && echo "$(basename "$m"): $(cat "$m/type") $(cat "$m/name" 2>/dev/null)"
done
echo "=== ready ==="
exec setsid cttyhack sh
EOF

{
  for d in /bin /lib /dev /proc /sys; do echo "dir $d 755 0 0"; done
  echo "dir /tmp 1777 0 0"
  echo "nod /dev/console 600 0 0 c 5 1"
  echo "file /bin/busybox $work/usr/bin/busybox 755 0 0"
  for l in "${libs[@]}"; do echo "file /lib/$l $work/usr/lib/aarch64-linux-gnu/$l 755 0 0"; done
  for b in ${BIN:-}; do
    [ -f "$b" ] || { echo "missing BIN $b" >&2; exit 1; }
    echo "file /bin/$(basename "$b" | sed 's/-arm64$//') $(readlink -f "$b") 755 0 0"
  done
  echo "file /init $work/init 755 0 0"
} > "$work/spec"

"$gen" "$work/spec" | gzip -9n > "$out"
printf '%s  %s bytes (0x%x)\n' "$out" "$(stat -c %s "$out")" "$(stat -c %s "$out")"
