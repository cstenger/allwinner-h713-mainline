#!/usr/bin/env bash
# Export a pinned, patched U-Boot tree without changing the source submodule.
# Usage: prepare-uboot.sh <prepared-kernel-tree>
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$ROOT/config/versions.env"
source "$ROOT/config/paths.sh"
K=${1:?usage: prepare-uboot.sh <prepared-kernel-tree>}
repo="$ROOT/external/u-boot"
series="$ROOT/patches/u-boot/series"
commit=$(git -C "$repo" rev-parse --verify "$UBOOT_SOURCE_COMMIT^{commit}")
patches=()
while IFS= read -r p || [ -n "$p" ]; do
  [ -n "$p" ] || continue
  case "$p" in \#*) continue ;; esac
  [[ "$p" != */* && "$p" == *.patch ]] || { echo "invalid U-Boot series entry: $p" >&2; exit 1; }
  patches+=("$p")
done < "$series"
kernel_files=(
  arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi
  arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713df-a1.dts
  arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713-v2.dts
  include/dt-bindings/clock/sun50i-h713-ccu.h
  include/dt-bindings/reset/sun50i-h713-ccu.h
  include/dt-bindings/clock/sun50i-h713-r-ccu.h
  include/dt-bindings/reset/sun50i-h713-r-ccu.h
  include/dt-bindings/clock/sun20i-d1-r-ccu.h
  include/dt-bindings/reset/sun20i-d1-r-ccu.h
  drivers/clk/sunxi-ng/ccu-sun50i-h713.c
)
hash() { sha256sum "$1" | awk '{print $1}'; }
inputs() {
  printf 'source %s\n' "$commit"
  printf 'series %s\n' "$(hash "$series")"
  for p in "${patches[@]}"; do
    printf 'patch %s %s\n' "$p" "$(hash "$ROOT/patches/u-boot/$p")"
  done
  for p in prepare-uboot.sh sync-uboot-dts.sh gen-uboot-h713-ccu.py; do
    printf 'tool %s %s\n' "$p" "$(hash "$ROOT/tools/build/$p")"
  done
  for p in "${kernel_files[@]}"; do
    printf 'kernel %s %s\n' "$p" "$(hash "$K/$p")"
  done
}
# Hashes are formed from logical names and contents, never absolute paths.
digest=$(inputs | sha256sum | awk '{print $1}')
tree="$H713_BUILD_DIR/uboot-src-$digest"
if [ -f "$tree/.h713-uboot-inputs-$digest" ]; then
  printf '%s\n' "$tree"
  exit 0
fi
[ ! -e "$tree" ] || { echo "incomplete U-Boot tree: $tree" >&2; exit 1; }
mkdir -p "$H713_BUILD_DIR"
tmp=$(mktemp -d "$H713_BUILD_DIR/.uboot-src.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
git -C "$repo" archive "$commit" | tar -x -C "$tmp"
for p in "${patches[@]}"; do
  echo "U-Boot patch: $p" >&2
  patch --batch --fuzz=0 -s -d "$tmp" -p1 < "$ROOT/patches/u-boot/$p"
done
"$ROOT/tools/build/sync-uboot-dts.sh" "$K" "$tmp" >&2
printf -- '-g%s-h713-%s\n' "${commit:0:12}" "${digest:0:8}" > "$tmp/.scmversion"
inputs > "$tmp/.h713-build-inputs"
: > "$tmp/.h713-uboot-inputs-$digest"
# Another board build may have prepared the same inputs concurrently. Never
# move our temporary directory *inside* its published tree or overwrite it.
if ! mv -T "$tmp" "$tree" 2>/dev/null; then
  [ -f "$tree/.h713-uboot-inputs-$digest" ] || {
    echo "could not publish U-Boot source: $tree" >&2
    exit 1
  }
  rm -rf "$tmp"
fi
trap - EXIT
printf '%s\n' "$tree"
