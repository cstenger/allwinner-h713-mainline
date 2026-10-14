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
#include "h713-hdmi-tvfe.h"

#define CCU_TV_PHYS_BASE	0x02001d10u
#define CCU_TV_SIZE		0x58u
#define TVFE_PHYS_BASE		0x06e00000u
#define TVFE_SIZE		0x100u

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
static u32 bus_saved;
static bool bus_saved_valid;
static bool tvfe_ready;
static u32 tvfe_saved;

void h713_hdmi_tvfe_release(void)
{
	int i;
	bool failed = false;

	if (bus_enabled) {
		writel(bus_saved | BIT(16), ccu_tv + 0x54);
		readl(ccu_tv + 0x54);
		bus_enabled = false;
	}
	if (words_applied) {
		for (i = ARRAY_SIZE(functional_words) - 1; i >= 0; i--) {
			writel(functional_words[i].saved,
			       ccu_tv + functional_words[i].offset);
			if (readl(ccu_tv + functional_words[i].offset) != functional_words[i].saved)
				failed = true;
		}
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
		if (reset_control_assert(demod_reset))
			failed = true;
		reset_deasserted = false;
	}
	if (!IS_ERR_OR_NULL(demod_reset)) {
		reset_control_put(demod_reset);
		demod_reset = NULL;
	}
	if (ccu_tv && bus_saved_valid) {
		writel(bus_saved, ccu_tv + 0x54);
		if (readl(ccu_tv + 0x54) != bus_saved)
			failed = true;
		bus_saved_valid = false;
	}
	if (tvfe) {
		iounmap(tvfe);
		tvfe = NULL;
	}
	if (ccu_tv) {
		iounmap(ccu_tv);
		ccu_tv = NULL;
	}
	if (failed)
		pr_err("h713-hdmi-audio: TVFE restoration verification failed; cold boot required\n");
	else if (tvfe_ready)
		pr_info("h713-hdmi-audio: managed TVFE clock/reset state restored; 15 clock words and bus verified\n");
	tvfe_ready = false;
}

int h713_hdmi_tvfe_prepare(void)
{
	struct device_node *ccu, *tvtop;
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;
	int reset_status;
	int ret = 0;

	for (i = 0; i < ARRAY_SIZE(functional_words); i++) {
		if (functional_words[i].offset != expected_offsets[i]) {
			pr_err("h713-hdmi-audio: TVFE: internal offset mismatch at %u\n", i);
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
	bus_saved_valid = true;
	if (bus_saved & (BIT(16) | BIT(0))) {
		pr_err("h713-hdmi-audio: TVFE: refusing inherited demod state %08x\n",
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
		pr_err("h713-hdmi-audio: TVFE: expected asserted reset, got %d\n",
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
		pr_info("h713-hdmi-audio: TVFE: parent=%s rate=%lu inherited_on=%u enabled_by_probe=%u\n",
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
			pr_err("h713-hdmi-audio: TVFE: clock offset %03x did not latch\n",
			       functional_words[i].offset + 0xd10);
			ret = -EIO;
			goto fail;
		}
	}
	/* The demod bus is last, unlike the unsafe bus-first experiment. */
	writel(readl(ccu_tv + 0x54) | BIT(0), ccu_tv + 0x54);
	if ((readl(ccu_tv + 0x54) & (BIT(16) | BIT(0))) !=
	    (BIT(16) | BIT(0))) {
		pr_err("h713-hdmi-audio: TVFE: demod bus/reset did not latch: %08x\n",
		       readl(ccu_tv + 0x54));
		ret = -EIO;
		goto fail;
	}
	bus_enabled = true;
	usleep_range(10000, 15000);

	/* Source 3 is already live and owns the TVFE control word.  The cold
	 * stock driver writes 0x003003ff here, but doing that after firmware
	 * startup replaces the observed live value (0x00111111) and prevents
	 * HDMI1 from reaching receiver state 5.  Preserve the live word and
	 * fail closed if firmware did not initialize it.
	 */
	tvfe_saved = readl(tvfe);
	if (!tvfe_saved) {
		pr_err("h713-hdmi-audio: TVFE: refusing uninitialized live TVFE control\n");
		ret = -EBUSY;
		goto fail;
	}
	pr_info("h713-hdmi-audio: TVFE: stock-order clock hold active; bus %08x->%08x live tvfe preserved=%08x\n",
		bus_saved, readl(ccu_tv + 0x54), tvfe_saved);

	tvfe_ready = true;
	of_node_put(tvtop);
	of_node_put(ccu);
	return 0;

fail:
	h713_hdmi_tvfe_release();
out_nodes:
	of_node_put(tvtop);
	of_node_put(ccu);
	return ret;
}
