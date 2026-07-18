#!/usr/bin/env bash
# H713 firmware build orchestrator.
#
#   TF-A BL31  ->  U-Boot (SPL + BL31 + proper)  ->  Linux kernel  ->  images
#
# Sources are the git submodules under external/ and the kernel patch series in
# patches/kernel/; versions are pinned in config/versions.env. LLVM-only
# (clang / ld.lld) — see config/toolchain.md.
#
# Usage:
#   build/build.sh [all|bl31|uboot|kernel|images]   # default: all
#
# Env:
#   BOARD=ddr3|lpddr3   which U-Boot board profile (default: ddr3 = HY200 bench)
#   JOBS=N              parallelism (default: nproc)
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=../config/versions.env
source "$ROOT/config/versions.env"

BOARD=${BOARD:-ddr3}
JOBS=${JOBS:-$(nproc)}
OUT="$ROOT/build/out"
CACHE="$ROOT/build/cache"
UBOOT="$ROOT/external/u-boot"
ATF="$ROOT/external/arm-trusted-firmware"
mkdir -p "$OUT" "$CACHE"

case "$BOARD" in
  ddr3)   UBOOT_DEFCONFIG=$UBOOT_DEFCONFIG_DDR3 ;;
  lpddr3) UBOOT_DEFCONFIG=$UBOOT_DEFCONFIG_LPDDR3 ;;
  *) echo "error: BOARD='$BOARD' must be ddr3 or lpddr3" >&2; exit 2 ;;
esac

log()  { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
note() { printf '    \033[33m%s\033[0m\n' "$*"; }
have() { [ -e "$ROOT/external/u-boot/Makefile" ] || { echo "error: submodules not checked out — run: git submodule update --init" >&2; exit 1; }; }

# --- TF-A BL31 --------------------------------------------------------------
build_bl31() {
  have
  log "TF-A BL31  (PLAT=$ATF_PLAT, BL31_IN_DRAM=1)"
  make -C "$ATF" -j"$JOBS" \
    PLAT="$ATF_PLAT" DEBUG=0 BL31_IN_DRAM=1 \
    CC=clang LD=ld.lld AR=llvm-ar OC=llvm-objcopy OD=llvm-objdump \
    NM=llvm-nm READELF=llvm-readelf \
    CFLAGS='-Wno-error=deprecated-non-prototype -fno-stack-protector' bl31
  cp "$ATF/build/$ATF_PLAT/release/bl31.bin" "$OUT/bl31.bin"
  log "bl31.bin -> $OUT/bl31.bin ($(stat -c%s "$OUT/bl31.bin") bytes)"
}

# --- U-Boot (embeds BL31) ---------------------------------------------------
uboot_make() {
  local O="$1"; shift
  make -C "$UBOOT" O="$O" \
    ARCH=arm HOSTCC=clang CC='clang -target aarch64-linux-gnu' \
    LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump \
    READELF=llvm-readelf STRIP=llvm-strip \
    KAFLAGS=-fintegrated-as \
    KCFLAGS='-fintegrated-as -Wno-error=deprecated-non-prototype -fno-stack-protector' \
    BL31="$OUT/bl31.bin" "$@"
}
build_uboot() {
  have
  [ -f "$OUT/bl31.bin" ] || build_bl31
  local O="$ROOT/build/uboot-$BOARD"
  log "U-Boot  ($UBOOT_DEFCONFIG, board=$BOARD)"
  uboot_make "$O" "$UBOOT_DEFCONFIG"
  uboot_make "$O" -j"$JOBS"
  cp "$O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-sunxi-with-spl-$BOARD.bin"
  log "image -> $OUT/u-boot-sunxi-with-spl-$BOARD.bin ($(stat -c%s "$OUT/u-boot-sunxi-with-spl-$BOARD.bin") bytes)"
}

# --- Kernel (mainline tarball + patches/kernel) -----------------------------
prepare_kernel() {
  local tree="$ROOT/build/linux-$KERNEL_VERSION"
  local tarball="$CACHE/linux-$KERNEL_VERSION.tar.xz"
  if [ -d "$tree" ]; then echo "$tree"; return; fi
  [ -f "$tarball" ] || { log "fetch linux-$KERNEL_VERSION" >&2; curl -fL "$KERNEL_TARBALL_URL" -o "$tarball"; }
  log "extract + patch linux-$KERNEL_VERSION" >&2
  tar -C "$ROOT/build" -xf "$tarball"
  local n=0 p
  while read -r p; do
    [ -n "$p" ] || continue
    patch -s -d "$tree" -p1 < "$ROOT/patches/kernel/$p"
    n=$((n+1))
  done < "$ROOT/patches/kernel/series"
  # our arm64 additions (see patches/kernel/README.md)
  cp "$ROOT/patches/kernel/board/$KERNEL_DEFCONFIG" "$tree/arch/arm64/configs/"
  if grep -q 'depends on MACH_SUN8I || RISCV || COMPILE_TEST' "$tree/drivers/clk/sunxi-ng/Kconfig"; then
    sed -i 's/\(depends on MACH_SUN8I || RISCV\) || COMPILE_TEST/\1 || ARM64 || COMPILE_TEST/' \
      "$tree/drivers/clk/sunxi-ng/Kconfig"
  fi
  note "applied $n series patches + arm64 defconfig + R-CCU arm64 enable" >&2
  echo "$tree"
}
build_kernel() {
  local tree; tree=$(prepare_kernel)
  log "Linux kernel  ($KERNEL_DEFCONFIG, arch=$KERNEL_ARCH)"
  make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1 "$KERNEL_DEFCONFIG"
  make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1 -j"$JOBS" Image
  gzip -9 -kf "$tree/arch/arm64/boot/Image"
  cp "$tree/arch/arm64/boot/Image.gz" "$OUT/Image.gz"
  log "Image.gz -> $OUT/Image.gz ($(stat -c%s "$OUT/Image.gz") bytes)"
  note "DTB + bootable FIT are not built yet — the arm64 board DTS is pending."
  note "See patches/kernel/README.md and docs/kernel-bump.md."
}

# --- Images / summary -------------------------------------------------------
build_images() {
  log "Artifacts in $OUT"
  ls -la "$OUT" 2>/dev/null || true
  note "Flash u-boot-sunxi-with-spl-*.bin to eMMC sector 16 — see docs/flash.md (TODO)."
}

case "${1:-all}" in
  bl31)   build_bl31 ;;
  uboot)  build_uboot ;;
  kernel) build_kernel ;;
  images) build_images ;;
  all)    build_bl31; build_uboot; build_kernel; build_images ;;
  *) echo "usage: $0 [all|bl31|uboot|kernel|images]" >&2; exit 2 ;;
esac
