// SPDX-License-Identifier: GPL-2.0-only
/* Bounded H713 HDMI-input audio status probe. */
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/of_irq.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
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
#define AUDIF_SPDI1_W1C		0x00300052u
#define AUDIF_SPDI1_ROUTE	0x00000400u

#define AUDBRG_GLOBAL_IRQ_EN	0x384
#define AUDBRG_IRQ_MASK		0x388
#define AUDBRG_IRQ_STATUS	0x38c
#define AUDBRG_STREAM_SYNC	0x390
#define AUDBRG_OSTREAM0		0x100
#define AUDBRG_STREAM_START	0x00
#define AUDBRG_STREAM_END	0x04
#define AUDBRG_STREAM_BLOCK	0x0c
#define AUDBRG_STREAM_CONFIG	0x10
#define AUDBRG_STREAM_FLUSH	0x14
#define AUDBRG_OSTREAM0_IRQ	BIT(4)
#define AUDBRG_GLOBAL_IRQ_BIT	BIT(0)
#define AUDBRG_IRQ_W1C_MASK	0x00003fffu
#define AUDBRG_DMA_SIZE		SZ_64K
#define AUDBRG_DMA_BLOCK	SZ_1K
#define AUDBRG_OSTREAM0_CONFIG	0x00003207u
#define AUDBRG_ADDR_HI_PHYS	0x06142044u
#define AUDBRG_ADDR_HI_SIZE	0x4u
#define AUDBRG_ADDR_HI_MASK	0x000000f0u
#define AUDBRG_DMA_SENTINEL	0xa5u

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
static void __iomem *audbrg_addr_hi;
static void __iomem *audio_top;
static void __iomem *audio_ihb_clk_reg;
static struct platform_device *audio_bridge_pdev;
static bool resources_ready;
static bool audio_top_initialized;
static bool audio_ihb_retimed;
static bool spdi1_opened;
static bool spdi1_activated;
static bool audif_irq_requested;
static int audif_irq = -1;
static atomic_t audif_irq_count = ATOMIC_INIT(0);
static u32 audif_irq_last;
static bool audbrg_configured;
static unsigned int audbrg_stage_applied;
static bool audbrg_irq_requested;
static int audbrg_irq = -1;
static atomic_t audbrg_irq_count = ATOMIC_INIT(0);
static u32 audbrg_irq_last;
static void *audbrg_dma_area;
static dma_addr_t audbrg_dma_addr;
static u32 audbrg_saved_global_irq_en;
static u32 audbrg_saved_irq_mask;
static u32 audbrg_saved_stream_sync;
static u32 audbrg_saved_addr_hi;
static u32 audbrg_saved_stream[6];
static u32 audif_saved_mask;
static u32 audif_saved_route;
static u32 audio_top_saved_ctl;
static u32 audio_top_saved_cfg;
static u32 audio_ihb_saved;
static u32 spdi1_saved_ctl0;
static u32 spdi1_saved_ctl1;

static bool armed;
module_param(armed, bool, 0400);
MODULE_PARM_DESC(armed, "Required explicit acknowledgment before touching audio clocks");

static bool live_source3;
module_param(live_source3, bool, 0400);
MODULE_PARM_DESC(live_source3, "Required acknowledgment that guarded source 3 is live");

static bool receiver_powered;
module_param(receiver_powered, bool, 0400);
MODULE_PARM_DESC(receiver_powered, "Required acknowledgment that TVFE/TVCAP holds are active");

static bool init_audio_top;
module_param(init_audio_top, bool, 0400);
MODULE_PARM_DESC(init_audio_top, "Apply only the stock audio-top clock sequence, saved and restored on unload");

static bool stock_audio_ihb;
module_param(stock_audio_ihb, bool, 0400);
MODULE_PARM_DESC(stock_audio_ihb, "Temporarily apply the stock audio-IHB mux/divider word, saved and restored on unload");

static bool activate_spdi1;
module_param(activate_spdi1, bool, 0400);
MODULE_PARM_DESC(activate_spdi1, "Apply only the stock 48-kHz LPCM SPDI1 activation words, saved and restored on unload");

static bool open_spdi1;
module_param(open_spdi1, bool, 0400);
MODULE_PARM_DESC(open_spdi1, "Apply the stock SPDI1 IRQ open sequence with an owned handler");

static bool configure_audbrg;
module_param(configure_audbrg, bool, 0400);
MODULE_PARM_DESC(configure_audbrg, "Configure stock Audio Bridge output stream 0 with private DMA and an owned IRQ");

static unsigned int audbrg_stage = 1;
module_param(audbrg_stage, uint, 0400);
MODULE_PARM_DESC(audbrg_stage, "Audio Bridge phase: 1=DMA only, 2=stream registers, 3=threaded IRQ enable, 4=flush/start");

static unsigned int snapshot;

static void inspect_audbrg_dma(unsigned int sequence)
{
	u32 hash = 2166136261u;
	unsigned int changed = 0;
	unsigned int first = AUDBRG_DMA_SIZE;
	unsigned int last = 0;
	unsigned int i;

	if (!audbrg_dma_area)
		return;
	dma_rmb();
	for (i = 0; i < AUDBRG_DMA_SIZE; i++) {
		u8 value = READ_ONCE(((u8 *)audbrg_dma_area)[i]);

		hash = (hash ^ value) * 16777619u;
		if (value == AUDBRG_DMA_SENTINEL)
			continue;
		if (!changed)
			first = i;
		last = i;
		changed++;
	}
	pr_info("h713-hdmi-audio-probe: dma_snapshot=%u addr=%pad changed=%u first=%u last=%u fnv1a=%08x bridge_irq_count=%d bridge_irq_last=%08x\n",
		sequence, &audbrg_dma_addr, changed, first, last, hash,
		atomic_read(&audbrg_irq_count), READ_ONCE(audbrg_irq_last));
}

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

	pr_info("h713-hdmi-audio-probe: snapshot=%u audif_irq=%08x audif_mask=%08x audif_route=%08x spds=%08x spdi1_ctl0=%08x spdi1_ctl1=%08x spdi1_status=%08x spdi2_cfg=%08x spdi2_status=%08x audbrg_enable=%08x audbrg_mask=%08x audbrg_status=%08x audbrg_sync=%08x top_ctl=%08x top_cfg=%08x ihb_clk=%08x irq_count=%d irq_last=%08x\n",
		sequence, ai_irq, ai_mask, ai_route, spds, spdi1_ctl0,
		spdi1_ctl1, spdi1_status, spdi2_cfg, spdi2_status, ab_enable, ab_mask,
		ab_status, ab_sync, top_ctl, top_cfg, ihb_clk,
		atomic_read(&audif_irq_count), READ_ONCE(audif_irq_last));
	if (configure_audbrg) {
		pr_info("h713-hdmi-audio-probe: bridge_snapshot=%u start=%08x end=%08x block=%08x config=%08x flush=%08x addr_hi=%08x\n",
			sequence,
			readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START),
			readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END),
			readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK),
			readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG),
			readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH),
			readl(audbrg_addr_hi));
		inspect_audbrg_dma(sequence);
	}
}

static irqreturn_t audif_interrupt(int irq, void *data)
{
	u32 status = readl(audif + AUDIF_IRQ_STATUS) & AUDIF_SPDI1_W1C;

	(void)irq;
	(void)data;
	if (!status)
		return IRQ_NONE;
	WRITE_ONCE(audif_irq_last, status);
	atomic_inc(&audif_irq_count);
	writel(status, audif + AUDIF_IRQ_STATUS);
	return IRQ_HANDLED;
}

static irqreturn_t audbrg_interrupt(int irq, void *data)
{
	u32 status = readl(audbrg + AUDBRG_IRQ_STATUS) &
		     AUDBRG_IRQ_W1C_MASK;

	(void)irq;
	(void)data;
	WRITE_ONCE(audbrg_irq_last, status);
	atomic_inc(&audbrg_irq_count);
	if (status)
		writel(status, audbrg + AUDBRG_IRQ_STATUS);
	return IRQ_HANDLED;
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

static int configure_audbrg_ostream0(void)
{
	u32 addr_hi;
	u32 start;
	u32 end;
	u32 active;
	int ret;

	active = readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	if (active ||
	    (readl(audbrg + AUDBRG_GLOBAL_IRQ_EN) & AUDBRG_GLOBAL_IRQ_BIT) ||
	    (readl(audbrg + AUDBRG_IRQ_MASK) & (BIT(4) | BIT(5)))) {
		pr_err("h713-hdmi-audio-probe: refusing to replace an active Audio Bridge output stream\n");
		return -EBUSY;
	}

	audbrg_dma_area = dma_alloc_coherent(&audio_bridge_pdev->dev,
					     AUDBRG_DMA_SIZE,
					     &audbrg_dma_addr,
					     GFP_KERNEL | GFP_DMA32);
	if (!audbrg_dma_area)
		return -ENOMEM;
	if (upper_32_bits(audbrg_dma_addr) || (audbrg_dma_addr & 0xf)) {
		pr_err("h713-hdmi-audio-probe: unsuitable bridge DMA address %pad\n",
		       &audbrg_dma_addr);
		return -ERANGE;
	}
	memset(audbrg_dma_area, AUDBRG_DMA_SENTINEL, AUDBRG_DMA_SIZE);
	dma_wmb();

	audbrg_saved_global_irq_en = readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
	audbrg_saved_irq_mask = readl(audbrg + AUDBRG_IRQ_MASK);
	audbrg_saved_stream_sync = readl(audbrg + AUDBRG_STREAM_SYNC);
	audbrg_saved_addr_hi = readl(audbrg_addr_hi);
	audbrg_saved_stream[0] =
		readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START);
	audbrg_saved_stream[1] =
		readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END);
	audbrg_saved_stream[2] =
		readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK);
	audbrg_saved_stream[3] =
		readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG);
	audbrg_saved_stream[4] =
		readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	audbrg_configured = true;
	audbrg_stage_applied = 1;
	pr_info("h713-hdmi-audio-probe: Audio Bridge stage 1 ready irq=%d dma=%pad size=%u; IRQ not requested and no bridge registers written\n",
		audbrg_irq, &audbrg_dma_addr, AUDBRG_DMA_SIZE);
	if (audbrg_stage == 1)
		return 0;

	addr_hi = (audbrg_saved_addr_hi & ~AUDBRG_ADDR_HI_MASK) |
		  (((u32)audbrg_dma_addr >> 28) << 4);
	start = ((u32)audbrg_dma_addr >> 4) & 0x00ffffff;
	end = ((u32)(audbrg_dma_addr + AUDBRG_DMA_SIZE - 1) >> 4) &
	      0x00ffffff;
	audbrg_stage_applied = 2;
	pr_info("h713-hdmi-audio-probe: Audio Bridge entering stage 2: inert stream registers\n");
	writel(addr_hi, audbrg_addr_hi);
	writel(start, audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START);
	writel(end, audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END);
	writel(AUDBRG_DMA_BLOCK >> 4,
	       audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK);
	writel(AUDBRG_OSTREAM0_CONFIG,
	       audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG);
	writel(0, audbrg + AUDBRG_STREAM_SYNC);
	if ((readl(audbrg_addr_hi) & AUDBRG_ADDR_HI_MASK) !=
	    (addr_hi & AUDBRG_ADDR_HI_MASK) ||
	    readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START) != start ||
	    readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END) != end ||
	    readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK) !=
		(AUDBRG_DMA_BLOCK >> 4) ||
	    readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG) !=
		AUDBRG_OSTREAM0_CONFIG) {
		pr_err("h713-hdmi-audio-probe: Audio Bridge stream configuration did not latch\n");
		return -EIO;
	}
	pr_info("h713-hdmi-audio-probe: Audio Bridge stage 2 ready start=%08x end=%08x block=%u config=%08x\n",
		start, end, AUDBRG_DMA_BLOCK, AUDBRG_OSTREAM0_CONFIG);
	if (audbrg_stage == 2)
		return 0;

	audbrg_stage_applied = 3;
	pr_info("h713-hdmi-audio-probe: Audio Bridge entering stage 3: status=%08x; clear, request stock-style threaded IRQ, and enable\n",
		readl(audbrg + AUDBRG_IRQ_STATUS));
	writel(readl(audbrg + AUDBRG_IRQ_STATUS) & AUDBRG_IRQ_W1C_MASK,
	       audbrg + AUDBRG_IRQ_STATUS);
	ret = request_threaded_irq(audbrg_irq, NULL, audbrg_interrupt,
				   IRQF_ONESHOT, "h713-hdmi-audbrg-probe",
				   &audbrg_irq);
	if (ret) {
		pr_err("h713-hdmi-audio-probe: Audio Bridge threaded IRQ request failed: %d\n",
		       ret);
		return ret;
	}
	audbrg_irq_requested = true;
	writel(audbrg_saved_irq_mask | AUDBRG_OSTREAM0_IRQ,
	       audbrg + AUDBRG_IRQ_MASK);
	writel(audbrg_saved_global_irq_en | AUDBRG_GLOBAL_IRQ_BIT,
	       audbrg + AUDBRG_GLOBAL_IRQ_EN);
	readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
	pr_info("h713-hdmi-audio-probe: Audio Bridge stage 3 ready enable=%08x mask=%08x status=%08x\n",
		readl(audbrg + AUDBRG_GLOBAL_IRQ_EN),
		readl(audbrg + AUDBRG_IRQ_MASK),
		readl(audbrg + AUDBRG_IRQ_STATUS));
	if (audbrg_stage == 3)
		return 0;

	audbrg_stage_applied = 4;
	pr_info("h713-hdmi-audio-probe: Audio Bridge entering stage 4: flush/start\n");
	writel(1, audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	writel(0, audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	pr_info("h713-hdmi-audio-probe: Audio Bridge stage 4 ready; output stream 0 started\n");
	return 0;
}

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
	if (spdi1_opened) {
		writel(audif_saved_mask, audif + AUDIF_IRQ_MASK);
		readl(audif + AUDIF_IRQ_MASK);
		spdi1_opened = false;
	}
	if (audif_irq_requested) {
		synchronize_irq(audif_irq);
		free_irq(audif_irq, &audif_irq);
		audif_irq_requested = false;
	}
	if (audif && (audif_saved_route || open_spdi1)) {
		writel(audif_saved_route, audif + AUDIF_IRQ_ROUTE);
		readl(audif + AUDIF_IRQ_ROUTE);
	}
	if (audif_irq >= 0) {
		irq_dispose_mapping(audif_irq);
		audif_irq = -1;
	}
	if (audbrg_configured && audbrg_stage_applied >= 3) {
		writel(audbrg_saved_irq_mask, audbrg + AUDBRG_IRQ_MASK);
		writel(audbrg_saved_global_irq_en,
		       audbrg + AUDBRG_GLOBAL_IRQ_EN);
		readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
	}
	if (audbrg_irq_requested) {
		synchronize_irq(audbrg_irq);
		free_irq(audbrg_irq, &audbrg_irq);
		audbrg_irq_requested = false;
	}
	if (audbrg_configured && audbrg_stage_applied >= 2) {
		if (audbrg_stage_applied >= 4) {
			writel(1, audbrg + AUDBRG_OSTREAM0 +
			       AUDBRG_STREAM_FLUSH);
			writel(0, audbrg + AUDBRG_OSTREAM0 +
			       AUDBRG_STREAM_FLUSH);
		}
		writel(audbrg_saved_stream[0],
		       audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START);
		writel(audbrg_saved_stream[1],
		       audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END);
		writel(audbrg_saved_stream[2],
		       audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK);
		writel(audbrg_saved_stream[3],
		       audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG);
		writel(audbrg_saved_stream[4],
		       audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
		writel(audbrg_saved_stream_sync, audbrg + AUDBRG_STREAM_SYNC);
		writel(audbrg_saved_addr_hi, audbrg_addr_hi);
		readl(audbrg_addr_hi);
		pr_info("h713-hdmi-audio-probe: restored Audio Bridge output stream 0\n");
	}
	audbrg_configured = false;
	audbrg_stage_applied = 0;
	if (audbrg_irq >= 0) {
		irq_dispose_mapping(audbrg_irq);
		audbrg_irq = -1;
	}
	if (audbrg_dma_area) {
		dma_free_coherent(&audio_bridge_pdev->dev, AUDBRG_DMA_SIZE,
				  audbrg_dma_area, audbrg_dma_addr);
		audbrg_dma_area = NULL;
		audbrg_dma_addr = 0;
	}
	if (audio_bridge_pdev) {
		put_device(&audio_bridge_pdev->dev);
		audio_bridge_pdev = NULL;
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
	if (audbrg_addr_hi) {
		iounmap(audbrg_addr_hi);
		audbrg_addr_hi = NULL;
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
	struct device_node *audio_bridge = NULL;
	struct device_node *ccu;
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;
	int ret = 0;

	if (!armed || !live_source3 || !receiver_powered) {
		pr_err("h713-hdmi-audio-probe: refusing: armed=1 live_source3=1 receiver_powered=1 are all required\n");
		return -EPERM;
	}
	if (open_spdi1 && !activate_spdi1) {
		pr_err("h713-hdmi-audio-probe: open_spdi1=1 requires activate_spdi1=1\n");
		return -EINVAL;
	}
	if (configure_audbrg && !open_spdi1) {
		pr_err("h713-hdmi-audio-probe: configure_audbrg=1 requires open_spdi1=1\n");
		return -EINVAL;
	}
	if (configure_audbrg && (audbrg_stage < 1 || audbrg_stage > 4)) {
		pr_err("h713-hdmi-audio-probe: audbrg_stage must be 1..4\n");
		return -EINVAL;
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
	if (configure_audbrg)
		audbrg_addr_hi = ioremap(AUDBRG_ADDR_HI_PHYS,
					   AUDBRG_ADDR_HI_SIZE);
	audio_ihb_clk_reg = ioremap(AUDIO_IHB_CLK_PHYS, AUDIO_IHB_CLK_SIZE);
	audio_top = ioremap(AUDIO_TOP_PHYS_BASE, AUDIO_TOP_SIZE);
	if (!audif || !audbrg || (configure_audbrg && !audbrg_addr_hi) ||
	    !audio_ihb_clk_reg || !audio_top) {
		ret = -ENOMEM;
		goto fail;
	}
	if (open_spdi1 || configure_audbrg) {
		audio_bridge = of_find_compatible_node(NULL, NULL,
						       "vs,trid-audio-bridge");
		if (!audio_bridge) {
			ret = -ENODEV;
			goto fail;
		}
	}
	if (configure_audbrg) {
		audio_bridge_pdev = of_find_device_by_node(audio_bridge);
		if (!audio_bridge_pdev) {
			ret = -ENODEV;
			goto fail;
		}
		audbrg_irq = irq_of_parse_and_map(audio_bridge, 0);
		if (!audbrg_irq) {
			ret = -EINVAL;
			goto fail;
		}
		pr_info("h713-hdmi-audio-probe: Audio Bridge IRQ mapped to Linux IRQ %d; request deferred to stage 3\n",
			audbrg_irq);
	}
	if (open_spdi1) {
		audif_irq = irq_of_parse_and_map(audio_bridge, 1);
		if (!audif_irq) {
			ret = -EINVAL;
			goto fail;
		}
		ret = request_irq(audif_irq, audif_interrupt, 0,
				  "h713-hdmi-audif-probe", &audif_irq);
		if (ret)
			goto fail;
		audif_irq_requested = true;
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
	if (configure_audbrg) {
		ret = configure_audbrg_ostream0();
		if (ret)
			goto fail;
	}
	if (activate_spdi1) {
		/* Stock capture-device 0 (SPDI1) activation for LPCM writes ctl1
		 * first, then ctl0. The optional open sequence owns the AudIf IRQ;
		 * otherwise this probe deliberately leaves all masks unchanged.
		 */
		spdi1_saved_ctl0 = readl(audif + AUDIF_SPDI1_CTL0);
		spdi1_saved_ctl1 = readl(audif + AUDIF_SPDI1_CTL1);
		if (open_spdi1) {
			audif_saved_mask = readl(audif + AUDIF_IRQ_MASK);
			audif_saved_route = readl(audif + AUDIF_IRQ_ROUTE);
			writel(0, audif + AUDIF_SPDI1_CTL0);
			writel(0, audif + AUDIF_SPDI1_CTL1);
			writel(AUDIF_SPDI1_W1C, audif + AUDIF_IRQ_STATUS);
			writel(AUDIF_SPDI1_ROUTE, audif + AUDIF_IRQ_ROUTE);
			spdi1_opened = true;
			writel(audif_saved_mask | AUDIF_SPDI1_W1C,
			       audif + AUDIF_IRQ_MASK);
			readl(audif + AUDIF_IRQ_MASK);
			pr_info("h713-hdmi-audio-probe: SPDI1 opened irq=%d mask=%08x->%08x route=%08x->%08x\n",
				audif_irq, audif_saved_mask,
				readl(audif + AUDIF_IRQ_MASK), audif_saved_route,
				readl(audif + AUDIF_IRQ_ROUTE));
		}
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
		pr_info("h713-hdmi-audio-probe: SPDI1 activated ctl0=%08x->%08x ctl1=%08x->%08x open=%u\n",
			spdi1_saved_ctl0, readl(audif + AUDIF_SPDI1_CTL0),
			spdi1_saved_ctl1, readl(audif + AUDIF_SPDI1_CTL1),
			open_spdi1);
	}

	resources_ready = true;
	pr_info("h713-hdmi-audio-probe: armed; status snapshots available\n");
	if (snapshot)
		take_snapshot(snapshot);
	of_node_put(audio_bridge);
	of_node_put(ccu);
	return 0;

fail:
	release_resources();
out_node:
	of_node_put(audio_bridge);
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
