#!/bin/sh
# Dump the display blocks U-Boot's h713_disp_regs[] covers, plus the AFBD
# window, as "address value" lines. Runs ON THE TARGET; diff two runs.
for r in 05700000:16 05800000:12 05880000:16 058c0000:12 051c0000:8 \
	 0525c000:16 05140050:4 051c0020:36 05200000:32 05248000:32 \
	 05240000:8 05280000:40 05288000:16 0529c000:16 051c00b0:16 \
	 0524c000:32 05600000:128 05600300:16; do
	base=$((0x${r%:*})); n=${r#*:}; i=0
	while [ $i -lt $n ]; do
		a=$(printf '0x%08x' $((base + i * 4)))
		echo "$a $(busybox devmem $a 32)"
		i=$((i + 1))
	done
done
