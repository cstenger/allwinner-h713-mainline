/* SPDX-License-Identifier: GPL-2.0+ */
/* Bench-only read-only samples. Never open the PPU bus here. */
#ifndef H713_TVFE_BOOT_TRACE_H
#define H713_TVFE_BOOT_TRACE_H
#include <asm/io.h>
#include <linux/bitops.h>
#include <stdio.h>

static inline void h713_tvfe_boot_trace(const char *stage)
{
	u32 gate = readl(0x070101acUL);
	u32 tvfe, tvcap;

	printf("H713 TVFE v1 stage=%s gate=%08x state=begin\n", stage, gate);
	if ((gate & (BIT(0) | BIT(16))) != (BIT(0) | BIT(16))) {
		printf("H713 TVFE v1 stage=%s gate=%08x state=skipped\n",
		       stage, gate);
		return;
	}
	tvfe = readl(0x070010a4UL);
	tvcap = readl(0x07001124UL);
	printf("H713 TVFE v1 stage=%s gate=%08x state=sample tvfe=%08x tvcap=%08x\n",
	       stage, gate, tvfe, tvcap);
}
#endif
