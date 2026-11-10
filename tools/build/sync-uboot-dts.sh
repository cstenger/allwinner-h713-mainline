#!/bin/sh
# Give U-Boot the kernel's H713 device tree, so the two share one hardware
# description instead of keeping two that drift.
#
# Copies, verbatim, from a kernel tree built from patches/kernel/series into a
# U-Boot tree (OF_UPSTREAM reads dts/upstream):
#   - the H713 dtsi and both board .dts files,
#   - the H713 clock/reset binding headers (DTS and U-Boot C code use them),
#     and the D1 R-CCU ones they include (kernel patch 0027 adds R-PWM IDs),
# and regenerates U-Boot's CCU gate/reset table from the kernel's CCU driver
# (gen-uboot-h713-ccu.py), keyed by those same binding IDs.
#
# What U-Boot must see differently lives in U-Boot's own overlays,
# arch/arm/dts/sun50i-h713*-u-boot.dtsi, never in the copies.
#
#   usage: sync-uboot-dts.sh <kernel-tree> <u-boot-tree>          copy
#          sync-uboot-dts.sh <kernel-tree> <u-boot-tree> --check  fail on drift
set -eu
K=${1:?usage: $0 <kernel-tree> <u-boot-tree> [--check]}
U=${2:?usage: $0 <kernel-tree> <u-boot-tree> [--check]}
CHECK=${3:-}
HERE=$(cd "$(dirname "$0")" && pwd)

FILES="
arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi:dts/upstream/src/arm64/allwinner/sun50i-h713.dtsi
arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713df-a1.dts:dts/upstream/src/arm64/allwinner/sun50i-h713-hy200-qz713df-a1.dts
arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713-v2.dts:dts/upstream/src/arm64/allwinner/sun50i-h713-hy200-qz713-v2.dts
include/dt-bindings/clock/sun50i-h713-ccu.h:dts/upstream/include/dt-bindings/clock/sun50i-h713-ccu.h
include/dt-bindings/reset/sun50i-h713-ccu.h:dts/upstream/include/dt-bindings/reset/sun50i-h713-ccu.h
include/dt-bindings/clock/sun50i-h713-r-ccu.h:dts/upstream/include/dt-bindings/clock/sun50i-h713-r-ccu.h
include/dt-bindings/reset/sun50i-h713-r-ccu.h:dts/upstream/include/dt-bindings/reset/sun50i-h713-r-ccu.h
include/dt-bindings/clock/sun20i-d1-r-ccu.h:dts/upstream/include/dt-bindings/clock/sun20i-d1-r-ccu.h
include/dt-bindings/reset/sun20i-d1-r-ccu.h:dts/upstream/include/dt-bindings/reset/sun20i-d1-r-ccu.h
"
CCU_SRC=drivers/clk/sunxi-ng/ccu-sun50i-h713.c
CCU_OUT=drivers/clk/sunxi/clk_h713.c

drift=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 "$HERE/gen-uboot-h713-ccu.py" "$K/$CCU_SRC" "$tmp/clk_h713.c" >/dev/null

for pair in $FILES; do
	src=${pair%%:*} dst=${pair#*:}
	[ -f "$K/$src" ] || { echo "missing in kernel tree: $src" >&2; exit 1; }
	if [ "$CHECK" = --check ]; then
		cmp -s "$K/$src" "$U/$dst" || { echo "drift: $dst"; drift=1; }
	else
		cp "$K/$src" "$U/$dst"
	fi
done
if [ "$CHECK" = --check ]; then
	cmp -s "$tmp/clk_h713.c" "$U/$CCU_OUT" || { echo "drift: $CCU_OUT"; drift=1; }
	[ $drift = 0 ] && echo "U-Boot's H713 device tree matches the kernel's"
	exit $drift
fi
cp "$tmp/clk_h713.c" "$U/$CCU_OUT"
echo "synced the kernel's H713 device tree and CCU table into $U"
