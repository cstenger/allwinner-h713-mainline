// SPDX-License-Identifier: GPL-2.0-only
/* Opt-in terminal MIPS parking through the CCU reset/clock providers.
	* No firmware load/restart and no raw control-register writes.
	*/
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/reset.h>
#include <dt-bindings/clock/sun50i-h713-ccu.h>
#include <dt-bindings/reset/sun50i-h713-ccu.h>
#include "h713-receiver.h"

static struct reset_control *resets[3];
static struct clk *core_clocks[2];
static unsigned int got_resets, got_clocks, on_clocks;
bool h713_receiver_shutdown_ready;
static bool parked, park_failed;

bool h713_receiver_park_incomplete(void)
{
	return park_failed;
}

module_param_named(shutdown_ready, h713_receiver_shutdown_ready, bool, 0444);
module_param(parked, bool, 0444);
module_param(park_failed, bool, 0444);

/* Reject altered provider/line assignments before obtaining any resource. */
static int validate_consumer(struct device_node *node)
{
	const unsigned int reset_ids[] = { RST_BUS_MIPS, RST_BUS_MIPS_DBG, RST_BUS_MIPS_CFG };
	const unsigned int clk_ids[] = { CLK_MIPS, CLK_BUS_MIPS };
	struct of_phandle_args spec;
	unsigned int i;
	int ret;

	if (of_count_phandle_with_args(node, "resets", "#reset-cells") != 3 ||
     of_count_phandle_with_args(node, "clocks", "#clock-cells") != 2)
		return -EINVAL;
	for (i = 0; i < ARRAY_SIZE(reset_ids) + ARRAY_SIZE(clk_ids); i++) {
		bool reset = i < ARRAY_SIZE(reset_ids);
		unsigned int index = reset ? i : i - ARRAY_SIZE(reset_ids);

		ret = of_parse_phandle_with_args(node, reset ? "resets" : "clocks",
            reset ? "#reset-cells" : "#clock-cells", index, &spec);
		if (ret)
			return ret;
		ret = spec.args_count == 1 &&
        spec.args[0] == (reset ? reset_ids[index] : clk_ids[index]) &&
        of_device_is_compatible(spec.np, "allwinner,sun50i-h713-ccu") &&
        of_device_is_available(spec.np) ? 0 : -EINVAL;
		of_node_put(spec.np);
		if (ret)
			return ret;
	}
	return 0;
}

int h713_receiver_park_prepare(void)
{
	struct device_node *node;
	unsigned int i;
	int ret = 0;

	node = of_find_compatible_node(NULL, NULL, "h713,hdmi-mips-shutdown-bench");
	if (!node)
		return 0; /* Existing RAM/FIT remains a capture-only owner. */
	if (!of_device_is_available(node)) {
		ret = -ENODEV;
		goto out;
	}
	ret = validate_consumer(node);
	if (ret)
		goto out;
	for (i = 0; i < ARRAY_SIZE(resets); i++) {
		resets[i] = of_reset_control_get_exclusive_by_index(node, i);
		if (IS_ERR(resets[i])) {
			ret = PTR_ERR(resets[i]);
			goto out;
		}
		got_resets++;
		/* Acquisition must not reset or release anything. */
		if (reset_control_status(resets[i]) != 0) {
			ret = -EIO;
			goto out;
		}
	}
	for (i = 0; i < ARRAY_SIZE(core_clocks); i++) {
		core_clocks[i] = of_clk_get(node, i);
		if (IS_ERR(core_clocks[i])) {
			ret = PTR_ERR(core_clocks[i]);
			goto out;
		}
		got_clocks++;
		ret = clk_prepare_enable(core_clocks[i]);
		if (ret)
			goto out;
		on_clocks++;
	}
	h713_receiver_shutdown_ready = true;
	pr_info("h713-hdmi-receiver: terminal parking prepared; 3 exclusive resets and 2 MIPS clock holds, no reset writes\n");
out:
	of_node_put(node);
	return ret; /* Partial holds retained under live firmware. */
}

int h713_receiver_park_commit(void __iomem *status)
{
	unsigned int i;
	u32 value;
	int ret;

	if (!h713_receiver_shutdown_ready || parked || park_failed)
		return -EPERM;
	park_failed = true; /* Once any assertion is attempted, never retry/release. */
	for (i = 0; i < ARRAY_SIZE(resets); i++) {
		ret = reset_control_assert(resets[i]);
		if (ret)
			return ret;
		if (reset_control_status(resets[i]) != 1)
			return -EIO;
		pr_info("h713-hdmi-receiver: terminal MIPS reset %u asserted and verified\n", i);
	}
	ret = readl_poll_timeout(status, value, value == 0, 100, 20000);
	if (ret)
		return ret;
	/* Match U-Boot stop: gate MIPS only after reset is proven asserted. */
	while (on_clocks)
		clk_disable_unprepare(core_clocks[--on_clocks]);
	parked = true;
	park_failed = false;
	pr_info("h713-hdmi-receiver: terminal MIPS parked, hardware status zero; core clock holds released; cold boot required\n");
	return 0;
}

void h713_receiver_park_cleanup(void)
{
	/* Only reached after parked-only release removed the firmware pin. */
	while (on_clocks)
		clk_disable_unprepare(core_clocks[--on_clocks]);
	while (got_clocks)
		clk_put(core_clocks[--got_clocks]);
	while (got_resets)
		reset_control_put(resets[--got_resets]);
	h713_receiver_shutdown_ready = false;
}
