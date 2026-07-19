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
#   BOARD=ddr3|lpddr3   board profile (default ddr3): ddr3=HY200 QZ713DF_A1 bench, lpddr3=HY200 QZ713_V2 projector
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

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

kernel_inputs_digest() {
  local p
  {
    printf 'versions.env %s\n' "$(hash_file "$ROOT/config/versions.env")"
    printf 'series %s\n' "$(hash_file "$ROOT/patches/kernel/series")"
    printf 'defconfig %s\n' "$(hash_file "$ROOT/patches/kernel/board/$KERNEL_DEFCONFIG")"
    while IFS= read -r p || [ -n "$p" ]; do
      [ -n "$p" ] || continue
      printf '%s %s\n' "$p" "$(hash_file "$ROOT/patches/kernel/$p")"
    done < "$ROOT/patches/kernel/series"
  } | sha256sum | awk '{print $1}'
}

verify_kernel_tarball() {
  local tarball="$1"
  printf '%s  %s\n' "$KERNEL_TARBALL_SHA256" "$tarball" |
    sha256sum --check --status
}

# --- TF-A BL31 --------------------------------------------------------------
build_bl31() {
  have
  log "TF-A BL31  (PLAT=$ATF_PLAT, BL31_IN_DRAM=1)"
  make -C "$ATF" -j"$JOBS" \
    PLAT="$ATF_PLAT" DEBUG=0 BL31_IN_DRAM=1 \
    CC=clang LD=ld.lld AR=llvm-ar OC=llvm-objcopy OD=llvm-objdump \
    NM=llvm-nm READELF=llvm-readelf \
    CFLAGS='-Wno-error=deprecated-non-prototype -fno-stack-protector' bl31
  install -m 0644 "$ATF/build/$ATF_PLAT/release/bl31.bin" "$OUT/bl31.bin"
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
  install -m 0644 "$O/u-boot-sunxi-with-spl.bin" "$OUT/u-boot-sunxi-with-spl-$BOARD.bin"
  log "image -> $OUT/u-boot-sunxi-with-spl-$BOARD.bin ($(stat -c%s "$OUT/u-boot-sunxi-with-spl-$BOARD.bin") bytes)"
}

# --- Kernel (mainline tarball + patches/kernel) -----------------------------
prepare_kernel() {
  local digest tree
  digest=$(kernel_inputs_digest)
  tree="$ROOT/build/linux-$KERNEL_VERSION-$digest"
  local tarball="$CACHE/linux-$KERNEL_VERSION.tar.xz"
  if [ -f "$tree/.h713-inputs-$digest" ]; then echo "$tree"; return; fi
  if [ -e "$tree" ]; then
    echo "error: incomplete kernel tree exists at $tree; remove it and retry" >&2
    return 1
  fi

  if [ -f "$tarball" ]; then
    verify_kernel_tarball "$tarball" || {
      echo "error: checksum mismatch for $tarball; remove it and retry" >&2
      return 1
    }
  else
    local partial="$tarball.part"
    log "fetch linux-$KERNEL_VERSION" >&2
    curl --fail --location --retry 3 --output "$partial" "$KERNEL_TARBALL_URL"
    verify_kernel_tarball "$partial" || {
      rm -f "$partial"
      echo "error: downloaded linux-$KERNEL_VERSION tarball failed SHA-256 verification" >&2
      return 1
    }
    mv "$partial" "$tarball"
  fi

  local tmp
  tmp=$(mktemp -d "$ROOT/build/.linux-$KERNEL_VERSION.XXXXXX")
  log "extract + patch linux-$KERNEL_VERSION" >&2
  tar -C "$tmp" --strip-components=1 -xf "$tarball"
  local n=0 p
  while read -r p; do
    [ -n "$p" ] || continue
    if ! patch -s -d "$tmp" -p1 < "$ROOT/patches/kernel/$p"; then
      rm -rf "$tmp"
      return 1
    fi
    n=$((n+1))
  done < "$ROOT/patches/kernel/series"
  # our arm64 defconfig (the R-CCU arm64 enable is patch 0023; see patches/kernel/README.md)
  cp "$ROOT/patches/kernel/board/$KERNEL_DEFCONFIG" "$tmp/arch/arm64/configs/"
  : > "$tmp/.h713-inputs-$digest"
  mv "$tmp" "$tree"
  note "applied $n series patches + arm64 defconfig" >&2
  echo "$tree"
}
# locate a mkimage: prefer one the U-Boot stage already built, else build tools-only
find_mkimage() {
  local m
  for m in "$ROOT"/build/uboot-*/tools/mkimage; do [ -x "$m" ] && { echo "$m"; return; }; done
  m="$ROOT/build/uboot-tools/tools/mkimage"
  if [ ! -x "$m" ]; then
    log "building mkimage (u-boot tools-only)" >&2
    make -C "$UBOOT" O="$ROOT/build/uboot-tools" HOSTCC=clang tools-only_defconfig >/dev/null 2>&1
    make -C "$UBOOT" O="$ROOT/build/uboot-tools" HOSTCC=clang -j"$JOBS" tools-only >/dev/null 2>&1
  fi
  [ -x "$m" ] && echo "$m"
}

build_kernel() {
  local tree; tree=$(prepare_kernel)
  log "Linux kernel  ($KERNEL_DEFCONFIG, arch=$KERNEL_ARCH)"
  make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1 "$KERNEL_DEFCONFIG"
  make -C "$tree" ARCH="$KERNEL_ARCH" LLVM=1 -j"$JOBS" Image dtbs modules
  gzip -9 -kf "$tree/arch/arm64/boot/Image"
  install -m 0644 "$tree/arch/arm64/boot/Image.gz" "$OUT/Image.gz"
  install -m 0644 "$tree/arch/arm64/boot/dts/allwinner/$KERNEL_DTB.dtb" "$OUT/$KERNEL_DTB.dtb"
  install -m 0644 "$tree/arch/arm64/boot/dts/allwinner/$KERNEL_DTB_PROJECTOR.dtb" \
    "$OUT/$KERNEL_DTB_PROJECTOR.dtb"
  log "Image.gz -> $OUT/Image.gz ($(stat -c%s "$OUT/Image.gz") bytes); bench + projector DTBs built"
  build_kernel_fit
}

# package Image.gz + DTB into a bootable FIT (bootm at KERNEL_LOAD)
build_kernel_fit() {
  local mkimage; mkimage=$(find_mkimage)
  [ -n "$mkimage" ] || { note "no mkimage — skipping FIT (install u-boot-tools or run the uboot stage)"; return; }
  cat > "$OUT/h713-kernel.its" <<ITS
/dts-v1/;
/ {
	description = "H713 arm64 kernel ($KERNEL_VERSION) + DTB";
	#address-cells = <1>;
	images {
		kernel {
			description = "Linux $KERNEL_VERSION";
			data = /incbin/("$OUT/Image.gz");
			type = "kernel";
			arch = "arm64";
			os = "linux";
			compression = "gzip";
			load = <$KERNEL_LOAD>;
			entry = <$KERNEL_LOAD>;
			hash-1 {
				algo = "sha256";
			};
		};
		fdt-1 {
			description = "$KERNEL_DTB";
			data = /incbin/("$OUT/$KERNEL_DTB.dtb");
			type = "flat_dt";
			arch = "arm64";
			compression = "none";
			hash-1 {
				algo = "sha256";
			};
		};
	};
	configurations {
		default = "conf-1";
		conf-1 {
			description = "H713 HY200";
			kernel = "kernel";
			fdt = "fdt-1";
		};
	};
};
ITS
  "$mkimage" -f "$OUT/h713-kernel.its" "$OUT/h713-kernel.fit" >/dev/null
  log "FIT -> $OUT/h713-kernel.fit ($(stat -c%s "$OUT/h713-kernel.fit") bytes)"
  note "Boot: load to DRAM + 'bootm' (arch=arm64, load $KERNEL_LOAD). See docs/flash.md."
}

# --- Images / summary -------------------------------------------------------
build_images() {
  local files=(bl31.bin Image.gz "$KERNEL_DTB.dtb" "$KERNEL_DTB_PROJECTOR.dtb" h713-kernel.fit)
  local image
  for image in "$OUT"/u-boot-sunxi-with-spl-*.bin; do
    [ -f "$image" ] && files+=("${image##*/}")
  done
  for image in "${files[@]}"; do
    [ -f "$OUT/$image" ] || {
      echo "error: missing $OUT/$image; run build/build.sh all first" >&2
      return 1
    }
  done
  log "Artifacts in $OUT"
  ls -la "$OUT" 2>/dev/null || true
  (
    cd "$OUT"
    sha256sum "${files[@]}" > SHA256SUMS
  )
  note "SHA-256 manifest -> $OUT/SHA256SUMS"
  note "Flash U-Boot to eMMC sector 16 using a verified raw write — see docs/flash.md."
}

case "${1:-all}" in
  bl31)   build_bl31 ;;
  uboot)  build_uboot ;;
  kernel) build_kernel ;;
  images) build_images ;;
  all)    build_bl31; build_uboot; build_kernel; build_images ;;
  *) echo "usage: $0 [all|bl31|uboot|kernel|images]" >&2; exit 2 ;;
esac
