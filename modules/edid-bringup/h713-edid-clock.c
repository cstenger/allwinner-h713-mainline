// SPDX-License-Identifier: GPL-2.0-only
/* Test-only clock/reset consumer. No EDID/HPD register access. */
#include <linux/clk.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/reset.h>

struct edid_hold {
	struct clk *clock;
	struct reset_control *reset;
	int was_asserted;
};

static int h713_edid_clock_probe(struct platform_device *pdev)
{
	struct edid_hold *hold;
	int ret;

	hold = devm_kzalloc(&pdev->dev, sizeof(*hold), GFP_KERNEL);
	if (!hold)
		return -ENOMEM;
	hold->clock = devm_clk_get(&pdev->dev, NULL);
	if (IS_ERR(hold->clock))
		return PTR_ERR(hold->clock);
	hold->reset = devm_reset_control_get_exclusive(&pdev->dev, NULL);
	if (IS_ERR(hold->reset))
		return PTR_ERR(hold->reset);
	hold->was_asserted = reset_control_status(hold->reset);
	if (hold->was_asserted < 0)
		return hold->was_asserted;
	ret = clk_prepare_enable(hold->clock);
	if (ret)
		return ret;
	ret = reset_control_deassert(hold->reset);
	if (ret) {
		clk_disable_unprepare(hold->clock);
		return ret;
	}
	platform_set_drvdata(pdev, hold);
	dev_info(&pdev->dev, "EDID clock held at %lu Hz, reset released (was_asserted=%d); no peripheral access\n",
		clk_get_rate(hold->clock), hold->was_asserted);
	return 0;
}

static void h713_edid_clock_remove(struct platform_device *pdev)
{
	struct edid_hold *hold = platform_get_drvdata(pdev);

	if (hold->was_asserted)
		reset_control_assert(hold->reset);
	clk_disable_unprepare(hold->clock);
	dev_info(&pdev->dev, "EDID reset state and clock reference released\n");
}

static const struct of_device_id h713_edid_clock_match[] = {
	{ .compatible = "h713-lab,edid-clock-hold" },
	{}
};
MODULE_DEVICE_TABLE(of, h713_edid_clock_match);
static struct platform_driver h713_edid_clock_driver = {
	.probe = h713_edid_clock_probe,
	.remove = h713_edid_clock_remove,
	.driver = {
		.name = "h713-edid-clock-hold",
		.of_match_table = h713_edid_clock_match,
	},
};
module_platform_driver(h713_edid_clock_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Removable H713 EDID clock/reset hold, no peripheral MMIO");
