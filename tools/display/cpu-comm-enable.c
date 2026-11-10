// SPDX-License-Identifier: GPL-2.0
/*
 * Test-only live-DT shim for an older H713 kernel whose cpu_comm node is
 * disabled.  A reboot is the supported cleanup path for bench experiments.
 */

#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/slab.h>

static struct platform_device *cpu_comm_pdev;

static int __init cpu_comm_enable_init(void)
{
	struct device_node *np;
	struct property *status;
	char *okay;

	np = of_find_node_by_path("/soc/cpu-comm@3003000");
	if (!np)
		return -ENODEV;

	status = of_find_property(np, "status", NULL);
	if (!status) {
		of_node_put(np);
		return -ENOENT;
	}

	pr_info("cpu_comm_enable: %pOF currently %s\n", np,
		status->value ? (char *)status->value : "<null>");

	/* Initial-DT values reside in the read-only FDT mapping. */
	okay = kmemdup("okay", sizeof("okay"), GFP_KERNEL);
	if (!okay) {
		of_node_put(np);
		return -ENOMEM;
	}
	status->value = okay;
	status->length = sizeof("okay");

	cpu_comm_pdev = of_platform_device_create(np, NULL, NULL);
	of_node_put(np);
	if (!cpu_comm_pdev) {
		pr_err("cpu_comm_enable: platform-device creation failed\n");
		return -ENODEV;
	}

	pr_info("cpu_comm_enable: status -> okay; platform device created\n");
	return 0;
}

static void __exit cpu_comm_enable_exit(void)
{
	if (cpu_comm_pdev)
		platform_device_unregister(cpu_comm_pdev);
}

module_init(cpu_comm_enable_init);
module_exit(cpu_comm_enable_exit);

MODULE_DESCRIPTION("Test-only live-DT enable shim for H713 CPU_COMM");
MODULE_LICENSE("GPL");
