// SPDX-License-Identifier: GPL-2.0-only
/* Bench test: reserve the DSP command range; never map or access hardware. */
#include <linux/ioport.h>
#include <linux/module.h>

#define DSP_PORT_START 0x06144000
#define DSP_PORT_SIZE  0x1c

static bool armed;
module_param(armed, bool, 0400);
MODULE_PARM_DESC(armed, "Explicitly allow a bench-only DSP command-region reservation");

static int __init owner_init(void)
{
	if (!armed)
		return -EPERM;
	if (!request_mem_region(DSP_PORT_START, DSP_PORT_SIZE,
				"h713-dsp-region-owner-test"))
		return -EBUSY;
	return 0;
}

static void __exit owner_exit(void)
{
	release_mem_region(DSP_PORT_START, DSP_PORT_SIZE);
}

module_init(owner_init);
module_exit(owner_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("No-MMIO DSP resource exclusion test");
