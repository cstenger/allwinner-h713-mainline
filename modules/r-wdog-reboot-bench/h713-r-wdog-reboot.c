// SPDX-License-Identifier: GPL-2.0-only
/*
 * BENCH ONLY: restart the SoC the way stock does, through the R-domain
 * watchdog at 0x07020400, instead of the main watchdog at 0x02051000 that
 * our TF-A's PSCI SYSTEM_RESET uses.
 *
 * Stock BL31 hands SYSTEM_RESET to the ARISC ("Sunxi System Reset: SCP
 * error"); the ARISC firmware's "watchdog reset" path (board-A scp.bin,
 * 0xcd70) writes, in order: +0x00 <- 0, +0x10 <- 0x16aa0101,
 * +0x14 <- 0x16aa0000, a short delay, +0x14 |= 0x16aa0001, then spins.
 * This replays exactly that from a restart handler that outranks PSCI
 * (bench priority 200, above PSCI 129), so device shutdown -- the panel power-down included --
 * has already run. Tests whether the lit-but-black panel after a cold-path
 * session survives a reset from the always-on domain.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/notifier.h>
#include <linux/printk.h>
#include <linux/reboot.h>

#define R_WDOG_PHYS	0x07020400u

static bool armed;
module_param(armed, bool, 0400);
MODULE_PARM_DESC(armed, "Opt in to routing the next restart through the bench R_WDOG handler");

static void __iomem *r_wdog;

static int h713_r_wdog_restart(struct notifier_block *nb, unsigned long mode,
			       void *cmd)
{
	pr_emerg("h713-r-wdog-reboot: resetting through R_WDOG 0x%08x (stock ARISC sequence)\n",
		 R_WDOG_PHYS);
	writel(0, r_wdog + 0x00);
	writel(0x16aa0101, r_wdog + 0x10);
	writel(0x16aa0000, r_wdog + 0x14);
	mdelay(1);
	writel(readl(r_wdog + 0x14) | 0x16aa0001, r_wdog + 0x14);
	mdelay(2000);
	pr_emerg("h713-r-wdog-reboot: R_WDOG did not reset; falling back\n");
	return NOTIFY_DONE;
}

static struct notifier_block h713_r_wdog_nb = {
	.notifier_call = h713_r_wdog_restart,
	.priority = 200,
};

static int __init h713_r_wdog_init(void)
{
	int ret;

	if (!armed) {
		pr_err("h713-r-wdog-reboot: refusing: armed=1 required\n");
		return -EPERM;
	}
	if (!request_mem_region(R_WDOG_PHYS, 0x20, "h713-r-wdog-reboot-bench"))
		return -EBUSY;
	r_wdog = ioremap(R_WDOG_PHYS, 0x20);
	if (!r_wdog) {
		release_mem_region(R_WDOG_PHYS, 0x20);
		return -ENOMEM;
	}
	ret = register_restart_handler(&h713_r_wdog_nb);
	if (ret) {
		iounmap(r_wdog);
		release_mem_region(R_WDOG_PHYS, 0x20);
		return ret;
	}
	pr_info("h713-r-wdog-reboot: armed; the next restart goes through R_WDOG\n");
	return 0;
}

static void __exit h713_r_wdog_exit(void)
{
	unregister_restart_handler(&h713_r_wdog_nb);
	iounmap(r_wdog);
	release_mem_region(R_WDOG_PHYS, 0x20);
}

module_init(h713_r_wdog_init);
module_exit(h713_r_wdog_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("BENCH: H713 restart through the R-domain watchdog, as stock does");
