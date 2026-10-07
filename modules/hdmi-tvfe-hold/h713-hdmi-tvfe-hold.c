// SPDX-License-Identifier: GPL-2.0-only
/* Reversible stock-order TVFE clock/reset hold for HDMI-input audio work. */
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/reset.h>
#include <dt-bindings/clock/sun50i-h713-ccu.h>

#define CCU_TV_PHYS_BASE	0x02001d10u
#define CCU_TV_SIZE		0x58u
#define TVFE_PHYS_BASE		0x06e00000u
#define TVFE_SIZE		0x100u
#define TVFE_INIT		0x003003ffu

struct tvfe_word {
	u16 offset;
	u32 stock;
	u32 saved;
};

/* Exact words are identical in two stock-idle and two stock-HDMI captures.
 * Order follows the stock tvfe_clks table. The demod bus word is separate and
 * is deliberately written only after every functional clock is configured.
 */
static struct tvfe_word functional_words[] = {
	{ 0x00, 0x80000017 }, /* ADC 54 MHz */
	{ 0x10, 0x80000000 }, /* TVFE 1296 MHz */
	{ 0x14, 0x81000005 }, /* I2H 200 MHz */
	{ 0x18, 0x80000002 }, /* CIP TSX 200 MHz */
	{ 0x1c, 0x80000005 }, /* CIP MCX 100 MHz */
	{ 0x20, 0x80000003 }, /* CIP TSP */
	{ 0x24, 0x80000003 }, /* TSA TSP */
	{ 0x28, 0x8000000b }, /* CIP27 27 MHz */
	{ 0x30, 0x80000117 }, /* CIP MTS0 27 MHz */
	{ 0x38, 0x80000002 }, /* audio CPU 400 MHz */
	{ 0x3c, 0x80000002 }, /* audio UMAC 200 MHz */
	{ 0x40, 0x81000002 }, /* audio IHB 200 MHz */
	{ 0x48, 0x80000002 }, /* TSA432 432 MHz */
	{ 0x4c, 0x8000020b }, /* MPG0 27 MHz */
	{ 0x50, 0x8000020b }, /* MPG1 27 MHz */
};

static const u16 expected_offsets[] = {
	0x00, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28,
	0x30, 0x38, 0x3c, 0x40, 0x48, 0x4c, 0x50,
};

struct parent_hold {
	const char *name;
	u32 id;
	struct clk *clk;
	bool inherited_on;
	bool enabled_by_probe;
};

static struct parent_hold parents[] = {
	{ "pll-video0", CLK_PLL_VIDEO0 },
	{ "pll-adc", CLK_PLL_ADC },
};

static void __iomem *ccu_tv;
static void __iomem *tvfe;
static struct reset_control *demod_reset;
static bool reset_deasserted;
static bool words_applied;
static bool bus_enabled;
static bool tvfe_written;
static u32 bus_saved;
static u32 tvfe_saved;

static bool armed;
module_param(armed, bool, 0400);
MODULE_PARM_DESC(armed, "Required acknowledgement before applying the stock TVFE sequence");

static bool live_source3;
module_param(live_source3, bool, 0400);
MODULE_PARM_DESC(live_source3, "Required acknowledgement that guarded source 3 is live");

static bool receiver_powered;
module_param(receiver_powered, bool, 0400);
MODULE_PARM_DESC(receiver_powered, "Required acknowledgement that TVFE/TVCAP power holds are active");

static void release_resources(void)
{
	int i;

	if (tvfe_written) {
		writel(tvfe_saved, tvfe);
		readl(tvfe);
		tvfe_written = false;
	}
	if (bus_enabled) {
		writel(bus_saved | BIT(16), ccu_tv + 0x54);
		readl(ccu_tv + 0x54);
		bus_enabled = false;
	}
	if (words_applied) {
		for (i = ARRAY_SIZE(functional_words) - 1; i >= 0; i--)
			writel(functional_words[i].saved,
			       ccu_tv + functional_words[i].offset);
		readl(ccu_tv + functional_words[0].offset);
		words_applied = false;
	}
	for (i = ARRAY_SIZE(parents) - 1; i >= 0; i--) {
		if (parents[i].enabled_by_probe) {
			clk_disable_unprepare(parents[i].clk);
			parents[i].enabled_by_probe = false;
		}
		if (!IS_ERR_OR_NULL(parents[i].clk)) {
			clk_put(parents[i].clk);
			parents[i].clk = NULL;
		}
	}
	if (reset_deasserted) {
		reset_control_assert(demod_reset);
		reset_deasserted = false;
	}
	if (!IS_ERR_OR_NULL(demod_reset)) {
		reset_control_put(demod_reset);
		demod_reset = NULL;
	}
	if (ccu_tv)
		writel(bus_saved, ccu_tv + 0x54);
	if (tvfe) {
		iounmap(tvfe);
		tvfe = NULL;
	}
	if (ccu_tv) {
		iounmap(ccu_tv);
		ccu_tv = NULL;
	}
}

static int __init h713_hdmi_tvfe_hold_init(void)
{
	struct device_node *ccu, *tvtop;
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;
	int reset_status;
	int ret = 0;

	if (!armed || !live_source3 || !receiver_powered) {
		pr_err("h713-hdmi-tvfe-hold: refusing: armed=1 live_source3=1 receiver_powered=1 are required\n");
		return -EPERM;
	}
	for (i = 0; i < ARRAY_SIZE(functional_words); i++) {
		if (functional_words[i].offset != expected_offsets[i]) {
			pr_err("h713-hdmi-tvfe-hold: internal offset mismatch at %u\n", i);
			return -EINVAL;
		}
	}

	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	tvtop = of_find_compatible_node(NULL, NULL, "allwinner,sunxi-tvtop");
	if (!ccu || !tvtop || !of_device_is_available(ccu)) {
		ret = -ENODEV;
		goto out_nodes;
	}

	ccu_tv = ioremap(CCU_TV_PHYS_BASE, CCU_TV_SIZE);
	tvfe = ioremap(TVFE_PHYS_BASE, TVFE_SIZE);
	if (!ccu_tv || !tvfe) {
		ret = -ENOMEM;
		goto fail;
	}

	bus_saved = readl(ccu_tv + 0x54);
	if (bus_saved & (BIT(16) | BIT(0))) {
		pr_err("h713-hdmi-tvfe-hold: refusing inherited demod state %08x\n",
		       bus_saved);
		ret = -EBUSY;
		goto fail;
	}
	demod_reset = of_reset_control_get_shared(tvtop, "reset_bus_demod");
	if (IS_ERR(demod_reset)) {
		ret = PTR_ERR(demod_reset);
		demod_reset = NULL;
		goto fail;
	}
	reset_status = reset_control_status(demod_reset);
	if (reset_status != 1) {
		pr_err("h713-hdmi-tvfe-hold: expected asserted reset, got %d\n",
		       reset_status);
		ret = reset_status < 0 ? reset_status : -EBUSY;
		goto fail;
	}

	/* Stock order: release reset first, wait, then functional clocks. */
	ret = reset_control_deassert(demod_reset);
	if (ret)
		goto fail;
	reset_deasserted = true;
	usleep_range(10000, 15000);

	spec.np = ccu;
	for (i = 0; i < ARRAY_SIZE(parents); i++) {
		spec.args[0] = parents[i].id;
		parents[i].clk = of_clk_get_from_provider(&spec);
		if (IS_ERR(parents[i].clk)) {
			ret = PTR_ERR(parents[i].clk);
			parents[i].clk = NULL;
			goto fail;
		}
		parents[i].inherited_on = __clk_is_enabled(parents[i].clk);
		if (!parents[i].inherited_on) {
			ret = clk_prepare_enable(parents[i].clk);
			if (ret)
				goto fail;
			parents[i].enabled_by_probe = true;
		}
		pr_info("h713-hdmi-tvfe-hold: parent=%s rate=%lu inherited_on=%u enabled_by_probe=%u\n",
			parents[i].name, clk_get_rate(parents[i].clk),
			parents[i].inherited_on, parents[i].enabled_by_probe);
	}

	for (i = 0; i < ARRAY_SIZE(functional_words); i++)
		functional_words[i].saved = readl(ccu_tv + functional_words[i].offset);
	words_applied = true;
	for (i = 0; i < ARRAY_SIZE(functional_words); i++) {
		writel(functional_words[i].stock,
		       ccu_tv + functional_words[i].offset);
		if (readl(ccu_tv + functional_words[i].offset) !=
		    functional_words[i].stock) {
			pr_err("h713-hdmi-tvfe-hold: clock offset %03x did not latch\n",
			       functional_words[i].offset + 0xd10);
			ret = -EIO;
			goto fail;
		}
	}
	/* The demod bus is last, unlike the unsafe bus-first experiment. */
	writel(readl(ccu_tv + 0x54) | BIT(0), ccu_tv + 0x54);
	if ((readl(ccu_tv + 0x54) & (BIT(16) | BIT(0))) !=
	    (BIT(16) | BIT(0))) {
		pr_err("h713-hdmi-tvfe-hold: demod bus/reset did not latch: %08x\n",
		       readl(ccu_tv + 0x54));
		ret = -EIO;
		goto fail;
	}
	bus_enabled = true;
	usleep_range(10000, 15000);

	tvfe_saved = readl(tvfe);
	writel(TVFE_INIT, tvfe);
	if (readl(tvfe) != TVFE_INIT) {
		pr_err("h713-hdmi-tvfe-hold: TVFE init did not latch: %08x\n",
		       readl(tvfe));
		ret = -EIO;
		goto fail;
	}
	tvfe_written = true;
	pr_info("h713-hdmi-tvfe-hold: stock-order TVFE hold active; bus %08x->%08x tvfe %08x->%08x\n",
		bus_saved, readl(ccu_tv + 0x54), tvfe_saved, readl(tvfe));

	of_node_put(tvtop);
	of_node_put(ccu);
	return 0;

fail:
	release_resources();
out_nodes:
	of_node_put(tvtop);
	of_node_put(ccu);
	return ret;
}

static void __exit h713_hdmi_tvfe_hold_exit(void)
{
	release_resources();
	pr_info("h713-hdmi-tvfe-hold: saved TVFE clock/reset state restored\n");
}

module_init(h713_hdmi_tvfe_hold_init);
module_exit(h713_hdmi_tvfe_hold_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Reversible stock-order H713 TVFE hold for HDMI audio diagnostics");
