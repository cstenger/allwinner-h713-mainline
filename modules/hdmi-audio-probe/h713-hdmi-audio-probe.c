// SPDX-License-Identifier: GPL-2.0-only
/* Read-only H713 HDMI-input audio status probe. */
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

#define AUDIF_IRQ_STATUS	0x00
#define AUDIF_IRQ_MASK		0x04
#define AUDIF_IRQ_ROUTE		0x08
#define AUDIF_SPDS_STATUS	0x10
#define AUDIF_SPDI1_CFG		0x38
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
static bool resources_ready;

static bool armed;
module_param(armed, bool, 0400);
MODULE_PARM_DESC(armed, "Required explicit acknowledgement before touching audio clocks");

static bool live_source3;
module_param(live_source3, bool, 0400);
MODULE_PARM_DESC(live_source3, "Required acknowledgement that guarded source 3 is live");

static bool receiver_powered;
module_param(receiver_powered, bool, 0400);
MODULE_PARM_DESC(receiver_powered, "Required acknowledgement that TVFE/TVCAP holds are active");

static unsigned int snapshot;

static void take_snapshot(unsigned int sequence)
{
	u32 ai_irq, ai_mask, ai_route, spds, spdi1_cfg, spdi1_status;
	u32 spdi2_cfg, spdi2_status, ab_enable, ab_mask, ab_status, ab_sync;

	/* None of these offsets is a FIFO/data port. Several are W1C when
	 * written, but this probe only performs reads.
	 */
	ai_irq = readl(audif + AUDIF_IRQ_STATUS);
	ai_mask = readl(audif + AUDIF_IRQ_MASK);
	ai_route = readl(audif + AUDIF_IRQ_ROUTE);
	spds = readl(audif + AUDIF_SPDS_STATUS);
	spdi1_cfg = readl(audif + AUDIF_SPDI1_CFG);
	spdi1_status = readl(audif + AUDIF_SPDI1_STATUS);
	spdi2_cfg = readl(audif + AUDIF_SPDI2_CFG);
	spdi2_status = readl(audif + AUDIF_SPDI2_STATUS);
	ab_enable = readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
	ab_mask = readl(audbrg + AUDBRG_IRQ_MASK);
	ab_status = readl(audbrg + AUDBRG_IRQ_STATUS);
	ab_sync = readl(audbrg + AUDBRG_STREAM_SYNC);

	pr_info("h713-hdmi-audio-probe: snapshot=%u audif_irq=%08x audif_mask=%08x audif_route=%08x spds=%08x spdi1_cfg=%08x spdi1_status=%08x spdi2_cfg=%08x spdi2_status=%08x audbrg_enable=%08x audbrg_mask=%08x audbrg_status=%08x audbrg_sync=%08x\n",
		sequence, ai_irq, ai_mask, ai_route, spds, spdi1_cfg,
		spdi1_status, spdi2_cfg, spdi2_status, ab_enable, ab_mask,
		ab_status, ab_sync);
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
	if (!audif || !audbrg) {
		ret = -ENOMEM;
		goto fail;
	}

	resources_ready = true;
	pr_info("h713-hdmi-audio-probe: armed; read-only status snapshots available\n");
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
MODULE_DESCRIPTION("Read-only H713 HDMI-input audio status probe");
