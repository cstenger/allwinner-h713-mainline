// SPDX-License-Identifier: GPL-2.0-only
/* Bounded H713 HDMI-input audio status probe. */
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <dt-bindings/clock/sun50i-h713-ccu.h>

#define AUDIF_PHYS_BASE		0x06146000u
#define AUDIF_SIZE		0x88u
#define AUDBRG_PHYS_BASE	0x06148000u
#define AUDBRG_SIZE		0x394u
#define AUDIO_TOP_PHYS_BASE	0x0614a000u
#define AUDIO_TOP_SIZE		0x10u
#define AUDIO_IHB_CLK_PHYS	0x02001d50u
#define AUDIO_IHB_CLK_SIZE	0x4u
#define AUDIO_IHB_CLK_STOCK	0x81000002u

#define AUDIF_IRQ_STATUS	0x00
#define AUDIF_IRQ_MASK		0x04
#define AUDIF_IRQ_ROUTE		0x08
#define AUDIF_SPDS_STATUS	0x10
#define AUDIF_SPDI1_CTL0	0x34
#define AUDIF_SPDI1_CTL1	0x38
#define AUDIF_SPDI1_STATUS	0x3c
#define AUDIF_SPDI2_CFG		0x48
#define AUDIF_SPDI2_STATUS	0x4c

#define AUDBRG_GLOBAL_IRQ_EN	0x384
#define AUDBRG_IRQ_MASK		0x388
#define AUDBRG_IRQ_STATUS	0x38c
#define AUDBRG_STREAM_SYNC	0x390

struct probe_clock {
	const char *name;
	unsigned int id;
	struct clk *clk;
	bool inherited_on;
	bool enabled_by_probe;
};

static struct probe_clock probe_clocks[] = {
	{ "bus-hdmi-audio", CLK_BUS_HDMI_AUDIO },
	{ "hdmi-audio", CLK_HDMI_AUDIO },
	{ "audio-cpu", CLK_AUDIO_CPU },
	{ "audio-umac", CLK_AUDIO_UMAC },
	{ "audio-ihb", CLK_AUDIO_IHB },
};

static void __iomem *audif;
static void __iomem *audbrg;
static void __iomem *audio_top;
static void __iomem *audio_ihb_clk_reg;
static bool resources_ready;
static bool audio_top_initialized;
static bool audio_ihb_retimed;
static bool spdi1_activated;
static u32 audio_top_saved_ctl;
static u32 audio_top_saved_cfg;
static u32 audio_ihb_saved;
static u32 spdi1_saved_ctl0;
static u32 spdi1_saved_ctl1;

static bool armed;
module_param(armed, bool, 0400);
MODULE_PARM_DESC(armed, "Required explicit acknowledgement before touching audio clocks");

static bool live_source3;
module_param(live_source3, bool, 0400);
MODULE_PARM_DESC(live_source3, "Required acknowledgement that guarded source 3 is live");

static bool receiver_powered;
module_param(receiver_powered, bool, 0400);
MODULE_PARM_DESC(receiver_powered, "Required acknowledgement that TVFE/TVCAP holds are active");

static bool init_audio_top;
module_param(init_audio_top, bool, 0400);
MODULE_PARM_DESC(init_audio_top, "Apply only the stock audio-top clock sequence, saved and restored on unload");

static bool stock_audio_ihb;
module_param(stock_audio_ihb, bool, 0400);
MODULE_PARM_DESC(stock_audio_ihb, "Temporarily apply the stock audio-IHB mux/divider word, saved and restored on unload");

static bool activate_spdi1;
module_param(activate_spdi1, bool, 0400);
MODULE_PARM_DESC(activate_spdi1, "Apply only the stock 48-kHz LPCM SPDI1 activation words, saved and restored on unload");

static unsigned int snapshot;

static void take_snapshot(unsigned int sequence)
{
	u32 ai_irq, ai_mask, ai_route, spds, spdi1_ctl0, spdi1_ctl1;
	u32 spdi1_status;
	u32 spdi2_cfg, spdi2_status, ab_enable, ab_mask, ab_status, ab_sync;
	u32 top_ctl, top_cfg, ihb_clk;

	/* None of these offsets is a FIFO/data port. Several are W1C when
	 * written, but this probe only performs reads.
	 */
	ai_irq = readl(audif + AUDIF_IRQ_STATUS);
	ai_mask = readl(audif + AUDIF_IRQ_MASK);
	ai_route = readl(audif + AUDIF_IRQ_ROUTE);
	spds = readl(audif + AUDIF_SPDS_STATUS);
	spdi1_ctl0 = readl(audif + AUDIF_SPDI1_CTL0);
	spdi1_ctl1 = readl(audif + AUDIF_SPDI1_CTL1);
	spdi1_status = readl(audif + AUDIF_SPDI1_STATUS);
	spdi2_cfg = readl(audif + AUDIF_SPDI2_CFG);
	spdi2_status = readl(audif + AUDIF_SPDI2_STATUS);
	ab_enable = readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
	ab_mask = readl(audbrg + AUDBRG_IRQ_MASK);
	ab_status = readl(audbrg + AUDBRG_IRQ_STATUS);
	ab_sync = readl(audbrg + AUDBRG_STREAM_SYNC);
	top_ctl = readl(audio_top + 0x0);
	top_cfg = readl(audio_top + 0xc);
	ihb_clk = readl(audio_ihb_clk_reg);

	pr_info("h713-hdmi-audio-probe: snapshot=%u audif_irq=%08x audif_mask=%08x audif_route=%08x spds=%08x spdi1_ctl0=%08x spdi1_ctl1=%08x spdi1_status=%08x spdi2_cfg=%08x spdi2_status=%08x audbrg_enable=%08x audbrg_mask=%08x audbrg_status=%08x audbrg_sync=%08x top_ctl=%08x top_cfg=%08x ihb_clk=%08x\n",
		sequence, ai_irq, ai_mask, ai_route, spds, spdi1_ctl0,
		spdi1_ctl1, spdi1_status, spdi2_cfg, spdi2_status, ab_enable, ab_mask,
		ab_status, ab_sync, top_ctl, top_cfg, ihb_clk);
}

static int set_snapshot(const char *value, const struct kernel_param *kp)
{
	unsigned int next;
	int ret;

	ret = kstrtouint(value, 0, &next);
	if (ret)
		return ret;
	if (!next || next <= snapshot)
		return -EINVAL;
	if (resources_ready)
		take_snapshot(next);
	snapshot = next;
	return 0;
}

static const struct kernel_param_ops snapshot_ops = {
	.set = set_snapshot,
	.get = param_get_uint,
};
module_param_cb(snapshot, &snapshot_ops, &snapshot, 0600);
MODULE_PARM_DESC(snapshot, "Strictly increasing sequence; each write performs status-only reads");

static void release_resources(void)
{
	int i;

	resources_ready = false;
	if (spdi1_activated) {
		writel(spdi1_saved_ctl0, audif + AUDIF_SPDI1_CTL0);
		writel(spdi1_saved_ctl1, audif + AUDIF_SPDI1_CTL1);
		readl(audif + AUDIF_SPDI1_CTL1);
		spdi1_activated = false;
		pr_info("h713-hdmi-audio-probe: restored SPDI1 ctl0=%08x ctl1=%08x\n",
			spdi1_saved_ctl0, spdi1_saved_ctl1);
	}
	if (audio_top_initialized) {
		writel(audio_top_saved_cfg, audio_top + 0xc);
		writel(audio_top_saved_ctl, audio_top + 0x0);
		readl(audio_top + 0x0);
		audio_top_initialized = false;
		pr_info("h713-hdmi-audio-probe: restored audio-top ctl=%08x cfg=%08x\n",
			audio_top_saved_ctl, audio_top_saved_cfg);
	}
	if (audio_top) {
		iounmap(audio_top);
		audio_top = NULL;
	}
	if (audio_ihb_retimed) {
		writel(audio_ihb_saved, audio_ihb_clk_reg);
		readl(audio_ihb_clk_reg);
		audio_ihb_retimed = false;
		pr_info("h713-hdmi-audio-probe: restored audio-IHB clock=%08x\n",
			audio_ihb_saved);
	}
	if (audio_ihb_clk_reg) {
		iounmap(audio_ihb_clk_reg);
		audio_ihb_clk_reg = NULL;
	}
	if (audbrg) {
		iounmap(audbrg);
		audbrg = NULL;
	}
	if (audif) {
		iounmap(audif);
		audif = NULL;
	}
	for (i = ARRAY_SIZE(probe_clocks) - 1; i >= 0; i--) {
		if (probe_clocks[i].enabled_by_probe)
			clk_disable_unprepare(probe_clocks[i].clk);
		if (!IS_ERR_OR_NULL(probe_clocks[i].clk))
			clk_put(probe_clocks[i].clk);
		probe_clocks[i].clk = NULL;
	}
}

static int __init h713_hdmi_audio_probe_init(void)
{
	struct device_node *ccu;
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;
	int ret = 0;

	if (!armed || !live_source3 || !receiver_powered) {
		pr_err("h713-hdmi-audio-probe: refusing: armed=1 live_source3=1 receiver_powered=1 are all required\n");
		return -EPERM;
	}

	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	if (!ccu || !of_device_is_available(ccu)) {
		ret = -ENODEV;
		goto out_node;
	}

	spec.np = ccu;
	for (i = 0; i < ARRAY_SIZE(probe_clocks); i++) {
		spec.args[0] = probe_clocks[i].id;
		probe_clocks[i].clk = of_clk_get_from_provider(&spec);
		if (IS_ERR(probe_clocks[i].clk)) {
			ret = PTR_ERR(probe_clocks[i].clk);
			probe_clocks[i].clk = NULL;
			goto fail;
		}
	}

	/* Preserve gates inherited from U-Boot/MIPS: do not create a temporary
	 * CCF reference whose release would turn an inherited gate off.
	 */
	for (i = 0; i < ARRAY_SIZE(probe_clocks); i++) {
		probe_clocks[i].inherited_on = __clk_is_enabled(probe_clocks[i].clk);
		if (!probe_clocks[i].inherited_on) {
			ret = clk_prepare_enable(probe_clocks[i].clk);
			if (ret)
				goto fail;
			probe_clocks[i].enabled_by_probe = true;
		}
		pr_info("h713-hdmi-audio-probe: clock=%s inherited_on=%u enabled_by_probe=%u rate=%lu\n",
			probe_clocks[i].name, probe_clocks[i].inherited_on,
			probe_clocks[i].enabled_by_probe,
			clk_get_rate(probe_clocks[i].clk));
	}

	audif = ioremap(AUDIF_PHYS_BASE, AUDIF_SIZE);
	audbrg = ioremap(AUDBRG_PHYS_BASE, AUDBRG_SIZE);
	audio_ihb_clk_reg = ioremap(AUDIO_IHB_CLK_PHYS, AUDIO_IHB_CLK_SIZE);
	audio_top = ioremap(AUDIO_TOP_PHYS_BASE, AUDIO_TOP_SIZE);
	if (!audif || !audbrg || !audio_ihb_clk_reg || !audio_top) {
		ret = -ENOMEM;
		goto fail;
	}
	if (stock_audio_ihb) {
		audio_ihb_saved = readl(audio_ihb_clk_reg);
		writel(AUDIO_IHB_CLK_STOCK, audio_ihb_clk_reg);
		if (readl(audio_ihb_clk_reg) != AUDIO_IHB_CLK_STOCK) {
			pr_err("h713-hdmi-audio-probe: audio-IHB clock write did not latch: %08x\n",
				readl(audio_ihb_clk_reg));
			writel(audio_ihb_saved, audio_ihb_clk_reg);
			readl(audio_ihb_clk_reg);
			ret = -EIO;
			goto fail;
		}
		audio_ihb_retimed = true;
		pr_info("h713-hdmi-audio-probe: audio-IHB clock stock word applied %08x->%08x\n",
			audio_ihb_saved, readl(audio_ihb_clk_reg));
	}
	if (init_audio_top) {
		u32 cfg;

		audio_top_saved_ctl = readl(audio_top + 0x0);
		audio_top_saved_cfg = readl(audio_top + 0xc);
		writel(audio_top_saved_ctl | 0x700, audio_top + 0x0);
		cfg = (audio_top_saved_cfg & 0xff000000) | 0x001a5e00;
		writel(cfg, audio_top + 0xc);
		writel(cfg | 0x01000000, audio_top + 0xc);
		readl(audio_top + 0xc);
		audio_top_initialized = true;
		pr_info("h713-hdmi-audio-probe: audio-top initialized ctl=%08x->%08x cfg=%08x->%08x\n",
			audio_top_saved_ctl, readl(audio_top + 0x0),
			audio_top_saved_cfg, readl(audio_top + 0xc));
	}
	if (activate_spdi1) {
		/* Stock capture-device 0 (SPDI1) activation for LPCM writes ctl1
		 * first, then ctl0. It does not need an IRQ mask to clock/status
		 * the input, so this probe deliberately leaves all masks at zero.
		 */
		spdi1_saved_ctl0 = readl(audif + AUDIF_SPDI1_CTL0);
		spdi1_saved_ctl1 = readl(audif + AUDIF_SPDI1_CTL1);
		writel(0x00003000, audif + AUDIF_SPDI1_CTL1);
		writel(0x90000000, audif + AUDIF_SPDI1_CTL0);
		if (readl(audif + AUDIF_SPDI1_CTL0) != 0x90000000 ||
		    readl(audif + AUDIF_SPDI1_CTL1) != 0x00003000) {
			pr_err("h713-hdmi-audio-probe: SPDI1 activation did not latch ctl0=%08x ctl1=%08x\n",
				readl(audif + AUDIF_SPDI1_CTL0),
				readl(audif + AUDIF_SPDI1_CTL1));
			writel(spdi1_saved_ctl0, audif + AUDIF_SPDI1_CTL0);
			writel(spdi1_saved_ctl1, audif + AUDIF_SPDI1_CTL1);
			readl(audif + AUDIF_SPDI1_CTL1);
			ret = -EIO;
			goto fail;
		}
		spdi1_activated = true;
		pr_info("h713-hdmi-audio-probe: SPDI1 activated ctl0=%08x->%08x ctl1=%08x->%08x; IRQ masks unchanged\n",
			spdi1_saved_ctl0, readl(audif + AUDIF_SPDI1_CTL0),
			spdi1_saved_ctl1, readl(audif + AUDIF_SPDI1_CTL1));
	}

	resources_ready = true;
	pr_info("h713-hdmi-audio-probe: armed; status snapshots available\n");
	if (snapshot)
		take_snapshot(snapshot);
	of_node_put(ccu);
	return 0;

fail:
	release_resources();
out_node:
	of_node_put(ccu);
	return ret;
}

static void __exit h713_hdmi_audio_probe_exit(void)
{
	release_resources();
	pr_info("h713-hdmi-audio-probe: removed; clocks enabled by the probe restored to off\n");
}

module_init(h713_hdmi_audio_probe_init);
module_exit(h713_hdmi_audio_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded H713 HDMI-input audio status probe");
