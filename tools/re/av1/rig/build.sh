#!/bin/sh
# Build the host rig (see rig.c). The VPU981 entropy/film-grain helpers are
# taken unmodified from a kernel tree: KSRC, or the newest build/linux-*.
set -e
cd "$(dirname "$0")"
D=../driver
KSRC=${KSRC:-$(ls -td ../../../../build/linux-*/ | head -1)}
V=$KSRC/drivers/media/platform/verisilicon
[ -f "$V/rockchip_av1_entropymode.c" ] || { echo "no verisilicon sources under KSRC=$KSRC" >&2; exit 1; }
# copied, so their #include "hantro.h" finds shim/hantro.h, not the kernel's
mkdir -p obj
cp $V/rockchip_av1_entropymode.[ch] $V/rockchip_av1_filmgrain.[ch] obj/
CF="-O1 -g -Wall -Wno-unused-function -DGST_USE_UNSTABLE_API -include $D/sunxi_h713_av1_compat.h -Ishim -Iobj -I$D"
gcc $CF -DH713_NO_CLAMP -c -o obj/fg.o obj/rockchip_av1_filmgrain.c
gcc $CF -c -o obj/entropy.o obj/rockchip_av1_entropymode.c
gcc $CF $(pkg-config --cflags gstreamer-codecparsers-1.0) -o obj/rig rig.c $D/sunxi_h713_av1_gen.c \
	obj/entropy.o obj/fg.o $(pkg-config --libs gstreamer-codecparsers-1.0)
echo "built $(pwd)/obj/rig"
