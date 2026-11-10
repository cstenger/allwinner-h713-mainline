// SPDX-License-Identifier: GPL-2.0-only
/*
 * BENCH ONLY: the production stock-order TVFE clock/reset hold, alone, and
 * optionally the audio module's audio-IHB word and AudioTop setup on top.
 *
 * Bisects the lit-but-black panel after a warm reboot: h713-hdmi-audio with
 * its DSP unmanaged triggers it (trial 12), the TVFE hold alone does not
 * (trial 13). audio_top=1 adds the next step of the audio module's init,
 * copied from h713-hdmi-pcm.c in the same order with the same restore, so
 * it splits AudioTop from the Audio Bridge and SPDI1. h713-hdmi-tvfe.c is
 * the production file (a symlink to ../hdmi-audio), so the hold is identical.
 * Load after the receiver owner has powered TVFE (bench-receiver-only.py
 * start); unload before parking it. Never load beside h713-hdmi-audio.
 */
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <dt-bindings/clock/sun50i-h713-ccu.h>
#include "h713-hdmi-tvfe.h"
#include "h713-receiver.h"

/* From h713-hdmi-pcm.c */
#define AUDIO_TOP_PHYS_BASE	0x0614a000u
#define AUDIO_TOP_SIZE		0x10u
#define AUDIO_IHB_CLK_PHYS	0x02001d50u
#define AUDIO_IHB_CLK_STOCK	0x81000002u

static const unsigned int audio_clock_ids[] = {
	CLK_BUS_HDMI_AUDIO, CLK_HDMI_AUDIO, CLK_AUDIO_CPU, CLK_AUDIO_UMAC,
	CLK_AUDIO_IHB,
};

static bool armed;
module_param(armed, bool, 0400);
static bool audio_top;
module_param(audio_top, bool, 0400);
/*
 * Historical trial 15 left AudioTop set until reset. Retain the parameter
 * name for an explicit refusal; current tooling always restores its changes.
 */
static bool keep_audio_top;
module_param(keep_audio_top, bool, 0400);
/*
 * Which parts of AudioTop's setup to apply (trials 17+): the control bits
 * OR-ed into +0x0 (production: 0x700) and whether to write the config word
 * at +0xc (production: 0x001a5e00, then with bit 24). Defaults = production.
 */
static uint top_ctl = 0x700;
module_param(top_ctl, uint, 0400);
static bool top_cfg = true;
module_param(top_cfg, bool, 0400);

static int (*receiver_acquire)(void);
static void (*receiver_release)(void);
static bool receiver_held, region_held;
static void __iomem *ihb, *top;
static u32 ihb_saved, top_saved_ctl, top_saved_cfg;
static bool ihb_retimed, top_initialized;

/* AudioTop must not be touched with an audio gate closed: refuse instead. */
static int audio_clocks_on(void)
{
	struct of_phandle_args spec = { .args_count = 1 };
	struct device_node *ccu;
	unsigned int i;
	int ret = 0;

	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	if (!ccu)
		return -ENODEV;
	spec.np = ccu;
	for (i = 0; i < ARRAY_SIZE(audio_clock_ids) && !ret; i++) {
		struct clk *clk;

		spec.args[0] = audio_clock_ids[i];
		clk = of_clk_get_from_provider(&spec);
		if (IS_ERR(clk)) {
			ret = PTR_ERR(clk);
			break;
		}
		if (!__clk_is_enabled(clk)) {
			pr_err("h713-tvfe-bench: audio clock %u is gated; refusing AudioTop\n",
			       audio_clock_ids[i]);
			ret = -EBUSY;
		}
		clk_put(clk);
	}
	of_node_put(ccu);
	return ret;
}

static void audio_top_release(void)
{
	if (top_initialized) {
		writel(top_saved_cfg, top + 0xc);
		writel(top_saved_ctl, top + 0x0);
		readl(top + 0x0);
		top_initialized = false;
		if (readl(top) != top_saved_ctl || readl(top + 0xc) != top_saved_cfg)
			pr_err("h713-tvfe-bench: audio-top restore readback failed\n");
		else
			pr_info("h713-tvfe-bench: restored audio-top ctl=%08x cfg=%08x\n",
				top_saved_ctl, top_saved_cfg);
	}
	if (ihb_retimed) {
		writel(ihb_saved, ihb);
		readl(ihb);
		ihb_retimed = false;
		if (readl(ihb) != ihb_saved)
			pr_err("h713-tvfe-bench: audio-IHB restore readback failed\n");
		else
			pr_info("h713-tvfe-bench: restored audio-IHB clock=%08x\n", ihb_saved);
	}
	if (top)
		iounmap(top);
	if (ihb)
		iounmap(ihb);
	top = ihb = NULL;
}

/* h713_hdmi_audio_init()'s IHB and AudioTop steps, in its order. */
static int audio_top_prepare(void)
{
	u32 cfg, ctl;
	int ret = audio_clocks_on();

	if (ret)
		return ret;
	ihb = ioremap(AUDIO_IHB_CLK_PHYS, 4);
	top = ioremap(AUDIO_TOP_PHYS_BASE, AUDIO_TOP_SIZE);
	if (!ihb || !top)
		return -ENOMEM;

	ihb_saved = readl(ihb);
	writel(AUDIO_IHB_CLK_STOCK, ihb);
	if (readl(ihb) != AUDIO_IHB_CLK_STOCK) {
		writel(ihb_saved, ihb);
		readl(ihb);
		return -EIO;
	}
	ihb_retimed = true;

	top_saved_ctl = readl(top + 0x0);
	top_saved_cfg = readl(top + 0xc);
	ctl = top_saved_ctl | top_ctl;
	cfg = top_cfg ? ((top_saved_cfg & 0xff000000) | 0x011a5e00) : top_saved_cfg;
	top_initialized = true;
	if (top_ctl)
		writel(top_saved_ctl | top_ctl, top + 0x0);
	if (top_cfg) {
		writel((top_saved_cfg & 0xff000000) | 0x001a5e00, top + 0xc);
		writel(cfg, top + 0xc);
	}
	if (readl(top) != ctl || readl(top + 0xc) != cfg)
		return -EIO;
	pr_info("h713-tvfe-bench: audio-IHB %08x->%08x, audio-top (top_ctl=%03x top_cfg=%d) ctl=%08x->%08x cfg=%08x->%08x\n",
		ihb_saved, readl(ihb), top_ctl, top_cfg, top_saved_ctl, readl(top + 0x0),
		top_saved_cfg, readl(top + 0xc));
	return 0;
}

static void release_ownership(void)
{
	if (region_held) {
		release_mem_region(AUDIO_TOP_PHYS_BASE, AUDIO_TOP_SIZE);
		region_held = false;
	}
	if (receiver_held) {
		receiver_release();
		receiver_held = false;
	}
	if (receiver_acquire)
		symbol_put(h713_receiver_acquire);
	if (receiver_release)
		symbol_put(h713_receiver_release);
	receiver_acquire = NULL;
	receiver_release = NULL;
}

static int __init h713_tvfe_bench_init(void)
{
	int ret;

	if (!armed)
		return -EPERM;
	/* Retained-state experiments are historical only. Validate before MMIO. */
	if (keep_audio_top || (top_ctl & ~0x700u))
		return -EINVAL;
	receiver_acquire = symbol_get(h713_receiver_acquire);
	receiver_release = symbol_get(h713_receiver_release);
	if (!receiver_acquire || !receiver_release) {
		ret = -ENODEV;
		goto fail_owner;
	}
	ret = receiver_acquire();
	if (ret)
		goto fail_owner;
	receiver_held = true;
	/* Also excludes production audio's TVFE-only setup before any writes. */
	if (!request_mem_region(AUDIO_TOP_PHYS_BASE, AUDIO_TOP_SIZE, "h713-tvfe-bench")) {
		ret = -EBUSY;
		goto fail_owner;
	}
	region_held = true;
	ret = h713_hdmi_tvfe_prepare();
	if (ret)
		goto fail_owner;
	pr_info("h713-tvfe-bench: production TVFE hold applied\n");
	if (audio_top) {
		ret = audio_top_prepare();
		if (ret) {
			audio_top_release();
			h713_hdmi_tvfe_release();
			goto fail_owner;
		}
	}
	return 0;
fail_owner:
	release_ownership();
	return ret;
}

static void __exit h713_tvfe_bench_exit(void)
{
	audio_top_release();
	h713_hdmi_tvfe_release();
	release_ownership();
	pr_info("h713-tvfe-bench: production TVFE hold released\n");
}

module_init(h713_tvfe_bench_init);
module_exit(h713_tvfe_bench_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("BENCH: H713 stock-order TVFE hold, optionally with AudioTop");
