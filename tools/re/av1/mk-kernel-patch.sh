#!/bin/bash
# Regenerate the kernel patch that carries the H713 AV1 decoder from the
# sources in tools/re/av1/driver/ -- the same files the host rig builds, so
# the code the gate checks is the code the kernel gets.
#
#   mk-kernel-patch.sh            writes patches/kernel/0147-...patch
#
# The patch is: driver/kernel-patch-message.txt, driver/kernel-glue.diff (the
# hunks in existing hantro files) and each driver file as a new file. The
# hantro-core hooks it builds on are patch 0145, kept by hand.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
D=$here/driver
V=drivers/media/platform/verisilicon
out=$root/patches/kernel/0147-media-verisilicon-add-the-h713-av1-decoder.patch
gate=${GATE:-"312 of 312 frames identical over 48 clips"}
tested=${TESTED:-$(cat "$D/kernel-patch-tested.txt")}
{
	awk -v g="$gate" -v t="$tested" '{ sub(/@GATE@/, g); sub(/@TESTED@/, t); print }' \
		"$D/kernel-patch-message.txt"
	echo
	cat "$D/kernel-glue.diff"
	for f in sunxi_h713_av1_compat.h sunxi_h713_av1_gen.c sunxi_h713_av1_gen.h \
		 sunxi_h713_av1_hw.c sunxi_h713_av1_regs.h; do
		n=$(wc -l < "$D/$f")
		echo "diff --color -Naur pa/$V/$f pb/$V/$f"
		echo "--- /dev/null"
		echo "+++ b/$V/$f"
		echo "@@ -0,0 +1,$n @@"
		sed 's/^/+/' "$D/$f"
	done
} > "$out"
echo "wrote ${out#$root/} ($(wc -l < "$out") lines)"
