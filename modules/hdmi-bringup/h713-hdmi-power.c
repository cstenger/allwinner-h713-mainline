// SPDX-License-Identifier: GPL-2.0-only
/* Removable TVFE/TVCAP power hold for HDMI receiver investigation.
 * No receiver MMIO, resets, IRQs, GPIOs, or clock-rate changes.
 */
#include <linux/clk.h>
#include <linux/device.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/pm_domain.h>
#include <linux/pm_runtime.h>
#include <dt-bindings/clock/sun50i-h713-ccu.h>

static struct device *domain_devs[2];
static struct clk_bulk_data clocks[] = {
	{ .id = "bus-tvcap" },
	{ .id = "bus-cap-300m" },
	{ .id = "vincap-dma" },
	{ .id = "tvfe-1296m" },
};
static const unsigned int clock_ids[] = {
	CLK_BUS_TVCAP, CLK_BUS_CAP_300M, CLK_VINCAP_DMA, CLK_TVFE_1296M,
};
static const char * const domain_names[] = {
	"h713-hdmi-tvfe", "h713-hdmi-tvcap",
};
static unsigned int attached, resumed, acquired;
static bool clocks_enabled;

static void release_resources(void)
{
	int ret;

	if (clocks_enabled) {
		clk_bulk_disable_unprepare(ARRAY_SIZE(clocks), clocks);
		clocks_enabled = false;
	}
	while (acquired)
		clk_put(clocks[--acquired].clk);
	while (resumed) {
		struct device *dev = domain_devs[--resumed];

		ret = pm_runtime_put_sync_suspend(dev);
		if (ret < 0)
			pr_warn("h713-hdmi-power: suspend failed: %d\n", ret);
		pm_runtime_disable(dev);
	}
	while (attached) {
		struct device *dev = domain_devs[--attached];

		ret = pm_genpd_remove_device(dev);
		if (ret) {
			/* Keep the device allocated if domain removal is refused. */
			pr_err("h713-hdmi-power: domain detach failed: %d\n", ret);
			continue;
		}
		root_device_unregister(dev);
	}
}

static int __init h713_hdmi_power_init(void)
{
	struct device_node *ppu, *ccu;
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;
	int ret;

	ppu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ppu");
	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	if (!ppu || !ccu || !of_device_is_available(ppu) ||
	    !of_device_is_available(ccu)) {
		ret = -ENODEV;
		goto out_nodes;
	}

	/* Provider indices 1=TVFE and 2=TVCAP, as in experiment 0087. */
	spec.np = ppu;
	for (i = 0; i < ARRAY_SIZE(domain_devs); i++) {
		domain_devs[i] = root_device_register(domain_names[i]);
		if (IS_ERR(domain_devs[i])) {
			ret = PTR_ERR(domain_devs[i]);
			goto fail;
		}
		spec.args[0] = i + 1;
		ret = of_genpd_add_device(&spec, domain_devs[i]);
		if (ret) {
			root_device_unregister(domain_devs[i]);
			goto fail;
		}
		attached++;
		pm_runtime_enable(domain_devs[i]);
		ret = pm_runtime_resume_and_get(domain_devs[i]);
		if (ret < 0) {
			pm_runtime_disable(domain_devs[i]);
			goto fail;
		}
		resumed++;
		pr_info("h713-hdmi-power: domain %u resumed\n", i + 1);
	}

	spec.np = ccu;
	for (i = 0; i < ARRAY_SIZE(clocks); i++) {
		spec.args[0] = clock_ids[i];
		clocks[i].clk = of_clk_get_from_provider(&spec);
		if (IS_ERR(clocks[i].clk)) {
			ret = PTR_ERR(clocks[i].clk);
			goto fail;
		}
		acquired++;
	}
	ret = clk_bulk_prepare_enable(ARRAY_SIZE(clocks), clocks);
	if (ret)
		goto fail;
	clocks_enabled = true;
	pr_info("h713-hdmi-power: TVFE/TVCAP and four receiver clocks held on; no receiver MMIO\n");
	ret = 0;
	goto out_nodes;
fail:
	release_resources();
out_nodes:
	of_node_put(ccu);
	of_node_put(ppu);
	return ret;
}

static void __exit h713_hdmi_power_exit(void)
{
	release_resources();
	pr_info("h713-hdmi-power: released power and clock references\n");
}

module_init(h713_hdmi_power_init);
module_exit(h713_hdmi_power_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 HDMI receiver power hold without receiver register access");
