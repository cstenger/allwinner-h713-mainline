// SPDX-License-Identifier: GPL-2.0-only
/* H713 HDMI PCM capture with managed DSP setup; receiver/source3 must be ready. */
#include <linux/clk.h>
#include <linux/clk-provider.h>
#include <linux/device.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/of_irq.h>
#include <linux/ktime.h>
#include <linux/ioport.h>
#include <sound/core.h>
#include <sound/pcm.h>
#include <sound/pcm_params.h>
#include <sound/initval.h>
#include "h713-pcm-ring.h"
#include "h713-hdmi-dsp.h"
#include "h713-hdmi-tvfe.h"
#include "../hdmi-receiver/h713-receiver.h"
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
#define AUDIF_EVENT_CLEAR		0x08
#define AUDIF_SPDS_STATUS	0x10
#define AUDIF_SPDI1_CTL0	0x34
#define AUDIF_SPDI1_CTL1	0x38
#define AUDIF_SPDI1_STATUS	0x3c
#define AUDIF_SPDI2_CFG		0x48
#define AUDIF_SPDI2_STATUS	0x4c
#define AUDIF_SPDI1_W1C		0x00300052u
#define AUDIF_SPDI1_EVENT_CLEAR	0x00000400u

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
/* Observed during correlated stock Trident HDMI capture, 2026-10-08.
 * Stock audbrg_ostream_config bounds the mode field (bits 13:12) to 0..2.
 * See docs/hdmi-evidence/2026-10-08-android-capture/stock-ostream-config.asm.
 */
#define AUDBRG_OSTREAM0_CONFIG	0x00002207u
#define AUDBRG_ADDR_HI_PHYS	0x06142044u
#define AUDBRG_ADDR_HI_SIZE	0x4u
#define AUDBRG_ADDR_HI_MASK	0x000000f0u

struct audio_clock {
	const char *name;
	unsigned int id;
	struct clk *clk;
	bool inherited_on;
	bool enabled_by_driver;
};

static struct audio_clock audio_clocks[] = {
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
static struct device *audbrg_dma_dev;
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

/* Exclude another Linux owner before touching either audio window. CCU
 * register ownership remains with CCF; the temporary IHB setting follows the
 * proven workaround and is restored before releasing our clock references.
 */
static const struct {
	resource_size_t base, size;
} audio_regions[] = {
	{ AUDIF_PHYS_BASE, AUDIF_SIZE },
	{ AUDBRG_PHYS_BASE, AUDBRG_SIZE },
	{ AUDBRG_ADDR_HI_PHYS, AUDBRG_ADDR_HI_SIZE },
	{ AUDIO_TOP_PHYS_BASE, AUDIO_TOP_SIZE },
};
static unsigned int regions_claimed;

static bool armed;
module_param(armed, bool, 0400);
MODULE_PARM_DESC(armed, "Required explicit acknowledgment before touching audio clocks");

static bool live_source3;
module_param(live_source3, bool, 0400);
MODULE_PARM_DESC(live_source3, "Required acknowledgment that guarded source 3 is live");

static bool receiver_powered;
module_param(receiver_powered, bool, 0400);
MODULE_PARM_DESC(receiver_powered, "Required acknowledgment that TVFE/TVCAP holds are active");
static bool require_receiver_owner = true;
module_param(require_receiver_owner, bool, 0400);
MODULE_PARM_DESC(require_receiver_owner, "Require the firmware-lifetime receiver owner (default); false permits the legacy diagnostic holds");
static int (*receiver_acquire)(void);
static void (*receiver_release)(void);
static bool receiver_reference;

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

#define AUDBRG_STREAM_POINTER 0x18
#define PCM_RING_NS (NSEC_PER_SEC * (u64)AUDBRG_DMA_SIZE / (48000 * 4))

static struct snd_card *capture_card;
/* Owned by this driver, not ALSA preallocation/free-for-all. */
static struct snd_dma_buffer capture_buffer;
static struct snd_pcm_substream *capture_stream;
static DEFINE_SPINLOCK(pcm_lock);
static bool pcm_running;
static u32 pcm_last_offset, pcm_period_pending;
static u64 pcm_last_irq_ns;
static bool graph_ready;
static bool manage_dsp = true;
static bool manage_tvfe = true;
module_param(manage_tvfe, bool, 0400);
MODULE_PARM_DESC(manage_tvfe, "Prepare/restore stock TVFE clocks and reset automatically (default); base power/receiver holds still required");
module_param(manage_dsp, bool, 0400);
MODULE_PARM_DESC(manage_dsp, "Prepare/restore the pinned DSP patch and graph automatically (default)");
module_param_named(dsp_failed, h713_dsp_failed, bool, 0444);
static unsigned int period_irq_seen, period_irq_status, period_notifications;
static unsigned int period_active, period_bytes, period_xruns;
module_param(period_irq_seen, uint, 0444);
module_param(period_irq_status, uint, 0444);
module_param(period_notifications, uint, 0444);
module_param(period_active, uint, 0444);
module_param(period_bytes, uint, 0444);
module_param(period_xruns, uint, 0444);

static int set_graph_ready(const char *value, const struct kernel_param *parameter)
{
	unsigned long flags;
	bool next;
	int ret = kstrtobool(value, &next);

	if (ret)
		return ret;
	if (manage_dsp)
		return -EPERM;
	spin_lock_irqsave(&pcm_lock, flags);
	if (pcm_running)
		ret = -EBUSY;
	else
		graph_ready = next;
	spin_unlock_irqrestore(&pcm_lock, flags);
	return ret;
}

static const struct kernel_param_ops graph_ready_ops = {
	.set = set_graph_ready,
	.get = param_get_bool,
};
module_param_cb(graph_ready, &graph_ready_ops, &graph_ready, 0600);
MODULE_PARM_DESC(graph_ready,
	"Set only after the external stock DSP patch and all 22 graph words passed verification");

static const struct snd_pcm_hardware capture_hardware = {
	.info = SNDRV_PCM_INFO_INTERLEAVED | SNDRV_PCM_INFO_BLOCK_TRANSFER,
	.formats = SNDRV_PCM_FMTBIT_S16_LE,
	.rates = SNDRV_PCM_RATE_48000,
	.rate_min = 48000, .rate_max = 48000,
	.channels_min = 2, .channels_max = 2,
	.buffer_bytes_max = AUDBRG_DMA_SIZE,
	.period_bytes_min = AUDBRG_DMA_BLOCK,
	.period_bytes_max = AUDBRG_DMA_BLOCK,
	.periods_min = AUDBRG_DMA_SIZE / AUDBRG_DMA_BLOCK,
	.periods_max = AUDBRG_DMA_SIZE / AUDBRG_DMA_BLOCK,
};

/* Caller holds pcm_lock. A cached software IRQ count is not a DMA pointer. */
static int pcm_dma_offset(u32 *offset)
{
	u32 address = h713_pcm_address(readl(audbrg_addr_hi),
		readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_POINTER));

	return h713_pcm_offset((u32)audbrg_dma_addr, AUDBRG_DMA_SIZE,
			       address, offset);
}

static void pcm_stop_locked(void)
{
	pcm_running = false;
	/* Stop SPDI1 input before masking the period IRQ. The persistent coherent
	 * allocation remains valid across closes; DMA is never aimed at freed
	 * ALSA pages. Final teardown also restores the inert stream registers.
	 */
	writel(0, audif + AUDIF_SPDI1_CTL0);
	readl(audif + AUDIF_SPDI1_CTL0);
	writel(audbrg_saved_irq_mask, audbrg + AUDBRG_IRQ_MASK);
	readl(audbrg + AUDBRG_IRQ_MASK);
}

static irqreturn_t audbrg_interrupt(int irq, void *data)
{
	struct snd_pcm_substream *stream = NULL;
	unsigned long flags;
	u32 status, offset, delta;
	u64 now;
	bool notify = false, xrun = false;

	spin_lock_irqsave(&pcm_lock, flags);
	period_irq_seen++;
	status = readl(audbrg + AUDBRG_IRQ_STATUS) & AUDBRG_OSTREAM0_IRQ;
	if (!status) {
		spin_unlock_irqrestore(&pcm_lock, flags);
		return IRQ_NONE;
	}
	period_irq_status++;
	writel(status, audbrg + AUDBRG_IRQ_STATUS);
	atomic_inc(&audbrg_irq_count);
	if (pcm_running && capture_stream) {
		period_active++;
		stream = capture_stream;
		now = ktime_get_ns();
		/* A modulo pointer cannot disambiguate a whole lost ring. */
		if (now - pcm_last_irq_ns >= PCM_RING_NS || pcm_dma_offset(&offset)) {
			period_xruns++;
			pcm_stop_locked();
			xrun = true;
		} else {
			delta = h713_pcm_advance(pcm_last_offset, offset, AUDBRG_DMA_SIZE);
			period_bytes += delta;
			pcm_last_offset = offset;
			pcm_last_irq_ns = now;
			pcm_period_pending += delta;
			if (pcm_period_pending >= AUDBRG_DMA_BLOCK) {
				pcm_period_pending %= AUDBRG_DMA_BLOCK;
				dma_rmb();
				notify = true;
				period_notifications++;
			}
		}
	}
	spin_unlock_irqrestore(&pcm_lock, flags);
	/* ALSA may take its stream lock and call .trigger(STOP); never hold our
	 * hardware lock while invoking either callback. .sync_stop drains this
	 * threaded handler before the runtime can be detached.
	 */
	if (xrun)
		snd_pcm_stop_xrun(stream);
	else if (notify)
		snd_pcm_period_elapsed(stream);
	return IRQ_HANDLED;
}

static int pcm_open(struct snd_pcm_substream *stream)
{
	unsigned long flags;
	int ret;

	if (!READ_ONCE(graph_ready))
		return -EAGAIN;
	stream->runtime->hw = capture_hardware;
	ret = snd_pcm_hw_constraint_integer(stream->runtime, SNDRV_PCM_HW_PARAM_PERIODS);
	/* Positive means the constraint changed successfully, not an error. */
	if (ret < 0)
		return ret;
	spin_lock_irqsave(&pcm_lock, flags);
	capture_stream = stream;
	spin_unlock_irqrestore(&pcm_lock, flags);
	return 0;
}

static int pcm_sync_stop(struct snd_pcm_substream *stream)
{
	synchronize_irq(audbrg_irq);
	return 0;
}

static int pcm_close(struct snd_pcm_substream *stream)
{
	unsigned long flags;

	spin_lock_irqsave(&pcm_lock, flags);
	pcm_stop_locked();
	spin_unlock_irqrestore(&pcm_lock, flags);
	pcm_sync_stop(stream);
	spin_lock_irqsave(&pcm_lock, flags);
	capture_stream = NULL;
	spin_unlock_irqrestore(&pcm_lock, flags);
	return 0;
}

static int pcm_hw_params(struct snd_pcm_substream *stream,
			 struct snd_pcm_hw_params *params)
{
	if (params_buffer_bytes(params) != AUDBRG_DMA_SIZE ||
	    params_period_bytes(params) != AUDBRG_DMA_BLOCK)
		return -EINVAL;
	snd_pcm_set_runtime_buffer(stream, &capture_buffer);
	stream->runtime->dma_bytes = AUDBRG_DMA_SIZE;
	return 0;
}

static int pcm_hw_free(struct snd_pcm_substream *stream)
{
	unsigned long flags;

	spin_lock_irqsave(&pcm_lock, flags);
	pcm_stop_locked();
	spin_unlock_irqrestore(&pcm_lock, flags);
	pcm_sync_stop(stream);
	snd_pcm_set_runtime_buffer(stream, NULL);
	return 0;
}

static int pcm_prepare(struct snd_pcm_substream *stream)
{
	unsigned long flags;

	spin_lock_irqsave(&pcm_lock, flags);
	pcm_stop_locked();
	spin_unlock_irqrestore(&pcm_lock, flags);
	pcm_sync_stop(stream);
	memset(audbrg_dma_area, 0, AUDBRG_DMA_SIZE);
	dma_wmb();
	spin_lock_irqsave(&pcm_lock, flags);
	/* Stock start/stop use this flush pulse to reset the producer cursor. */
	writel(1, audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	writel(0, audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	writel(AUDBRG_OSTREAM0_IRQ, audbrg + AUDBRG_IRQ_STATUS);
	pcm_last_offset = 0;
	pcm_period_pending = 0;
	spin_unlock_irqrestore(&pcm_lock, flags);
	return 0;
}

static int pcm_trigger(struct snd_pcm_substream *stream, int command)
{
	unsigned long flags;
	int ret = 0;

	spin_lock_irqsave(&pcm_lock, flags);
	switch (command) {
	case SNDRV_PCM_TRIGGER_START:
		if (!graph_ready) {
			ret = -EPIPE;
			break;
		}
		audbrg_stage_applied = 4;
		pcm_last_irq_ns = ktime_get_ns();
		pcm_running = true;
		writel(AUDBRG_OSTREAM0_IRQ, audbrg + AUDBRG_IRQ_STATUS);
		writel(audbrg_saved_irq_mask | AUDBRG_OSTREAM0_IRQ,
		       audbrg + AUDBRG_IRQ_MASK);
		writel(0x00003000, audif + AUDIF_SPDI1_CTL1);
		writel(0x90000000, audif + AUDIF_SPDI1_CTL0);
		readl(audif + AUDIF_SPDI1_CTL0);
		break;
	case SNDRV_PCM_TRIGGER_STOP:
	case SNDRV_PCM_TRIGGER_SUSPEND:
		pcm_stop_locked();
		break;
	default:
		ret = -EINVAL;
	}
	spin_unlock_irqrestore(&pcm_lock, flags);
	return ret;
}

static snd_pcm_uframes_t pcm_pointer(struct snd_pcm_substream *stream)
{
	unsigned long flags;
	u32 offset = 0;
	int ret = 0;

	spin_lock_irqsave(&pcm_lock, flags);
	if (pcm_running)
		ret = pcm_dma_offset(&offset);
	else
		offset = pcm_last_offset;
	spin_unlock_irqrestore(&pcm_lock, flags);
	return ret ? SNDRV_PCM_POS_XRUN : bytes_to_frames(stream->runtime, offset);
}

static const struct snd_pcm_ops capture_ops = {
	.open = pcm_open, .close = pcm_close,
	.ioctl = snd_pcm_lib_ioctl,
	.hw_params = pcm_hw_params, .hw_free = pcm_hw_free,
	.prepare = pcm_prepare, .trigger = pcm_trigger,
	.sync_stop = pcm_sync_stop, .pointer = pcm_pointer,
};

static int register_pcm(void)
{
	struct snd_pcm *pcm;
	struct snd_dma_buffer *buffer;
	int ret;

	ret = snd_card_new(audbrg_dma_dev, -1, "H713HDMI", THIS_MODULE, 0,
			   &capture_card);
	if (ret)
		return ret;
	strscpy(capture_card->driver, "H713HDMI", sizeof(capture_card->driver));
	strscpy(capture_card->shortname, "H713 HDMI Input", sizeof(capture_card->shortname));
	strscpy(capture_card->longname, "H713 HDMI input, DSP to Audio Bridge ostream0",
		sizeof(capture_card->longname));
	ret = snd_pcm_new(capture_card, "HDMI Capture", 0, 0, 1, &pcm);
	if (ret)
		return ret;
	strscpy(pcm->name, "HDMI Capture", sizeof(pcm->name));
	snd_pcm_set_ops(pcm, SNDRV_PCM_STREAM_CAPTURE, &capture_ops);
	buffer = &capture_buffer;
	buffer->dev.type = SNDRV_DMA_TYPE_DEV;
	buffer->dev.dev = audbrg_dma_dev;
	buffer->area = audbrg_dma_area;
	buffer->addr = audbrg_dma_addr;
	buffer->bytes = AUDBRG_DMA_SIZE;
	return snd_card_register(capture_card);
}

static int configure_audbrg_ostream0(struct device_node *audio_bridge)
{
	u32 addr_hi;
	u32 start;
	u32 end;
	u32 active;
	int ret;

	pr_info("h713-hdmi-audio: Audio Bridge stage 1 creating private direct-DMA device; disabled DT IRQ 0 remains unmapped\n");
	audbrg_dma_dev = root_device_register("h713-hdmi-audio-dma");
	if (IS_ERR(audbrg_dma_dev)) {
		ret = PTR_ERR(audbrg_dma_dev);
		audbrg_dma_dev = NULL;
		return ret;
	}
	ret = dma_coerce_mask_and_coherent(audbrg_dma_dev, DMA_BIT_MASK(32));
	if (ret)
		return ret;
	pr_info("h713-hdmi-audio: Audio Bridge private direct-DMA device ready\n");

	active = readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG) |
		 readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
	if (active ||
	    (readl(audbrg + AUDBRG_GLOBAL_IRQ_EN) & AUDBRG_GLOBAL_IRQ_BIT) ||
	    (readl(audbrg + AUDBRG_IRQ_MASK) & (BIT(4) | BIT(5)))) {
		pr_err("h713-hdmi-audio: refusing to replace an active Audio Bridge output stream\n");
		return -EBUSY;
	}

	audbrg_dma_area = dma_alloc_coherent(audbrg_dma_dev,
					     AUDBRG_DMA_SIZE,
					     &audbrg_dma_addr,
					     GFP_KERNEL | GFP_DMA32);
	if (!audbrg_dma_area)
		return -ENOMEM;
	if (upper_32_bits(audbrg_dma_addr) || (audbrg_dma_addr & 0xf)) {
		pr_err("h713-hdmi-audio: unsuitable bridge DMA address %pad\n",
		       &audbrg_dma_addr);
		return -ERANGE;
	}
	memset(audbrg_dma_area, 0, AUDBRG_DMA_SIZE);
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
	pr_info("h713-hdmi-audio: Audio Bridge stage 1 ready dma=%pad size=%u; bridge IRQ unmapped and no bridge registers written\n",
		&audbrg_dma_addr, AUDBRG_DMA_SIZE);

	addr_hi = (audbrg_saved_addr_hi & ~AUDBRG_ADDR_HI_MASK) |
		  (((u32)audbrg_dma_addr >> 28) << 4);
	start = ((u32)audbrg_dma_addr >> 4) & 0x00ffffff;
	end = ((u32)(audbrg_dma_addr + AUDBRG_DMA_SIZE - 1) >> 4) &
	      0x00ffffff;
	audbrg_stage_applied = 2;
	pr_info("h713-hdmi-audio: Audio Bridge entering stage 2: inert stream registers\n");
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
		pr_err("h713-hdmi-audio: Audio Bridge stream configuration did not latch\n");
		return -EIO;
	}
	pr_info("h713-hdmi-audio: Audio Bridge stage 2 ready start=%08x end=%08x block=%u config=%08x\n",
		start, end, AUDBRG_DMA_BLOCK, AUDBRG_OSTREAM0_CONFIG);

	pr_info("h713-hdmi-audio: Audio Bridge entering stage 3: pre-map status=%08x; clear all bridge W1C bits before mapping DT interrupt 0\n",
		readl(audbrg + AUDBRG_IRQ_STATUS));
	writel(readl(audbrg + AUDBRG_IRQ_STATUS) & AUDBRG_IRQ_W1C_MASK,
	       audbrg + AUDBRG_IRQ_STATUS);
	readl(audbrg + AUDBRG_IRQ_STATUS);
	audbrg_irq = irq_of_parse_and_map(audio_bridge, 0);
	if (!audbrg_irq)
		return -EINVAL;
	pr_info("h713-hdmi-audio: Audio Bridge DT interrupt 0 mapped to Linux IRQ %d\n",
		audbrg_irq);
	audbrg_stage_applied = 3;
	pr_info("h713-hdmi-audio: Audio Bridge stage 3 post-map status=%08x; request stock-style threaded IRQ and enable\n",
		readl(audbrg + AUDBRG_IRQ_STATUS));
	ret = request_threaded_irq(audbrg_irq, NULL, audbrg_interrupt,
				   IRQF_ONESHOT, "h713-hdmi-audio",
				   &audbrg_irq);
	if (ret) {
		pr_err("h713-hdmi-audio: Audio Bridge threaded IRQ request failed: %d\n",
		       ret);
		return ret;
	}
	audbrg_irq_requested = true;
	writel(audbrg_saved_irq_mask | AUDBRG_OSTREAM0_IRQ,
	       audbrg + AUDBRG_IRQ_MASK);
	writel(audbrg_saved_global_irq_en | AUDBRG_GLOBAL_IRQ_BIT,
	       audbrg + AUDBRG_GLOBAL_IRQ_EN);
	readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
	pr_info("h713-hdmi-audio: Audio Bridge stage 3 ready enable=%08x mask=%08x status=%08x\n",
		readl(audbrg + AUDBRG_GLOBAL_IRQ_EN),
		readl(audbrg + AUDBRG_IRQ_MASK),
		readl(audbrg + AUDBRG_IRQ_STATUS));
	return 0;
}

static void release_resources(void)
{
	int i;

	if (capture_card) {
		snd_card_free(capture_card);
		capture_card = NULL;
	}
	graph_ready = false;
	h713_hdmi_dsp_release();

	if (spdi1_activated) {
		writel(spdi1_saved_ctl0, audif + AUDIF_SPDI1_CTL0);
		writel(spdi1_saved_ctl1, audif + AUDIF_SPDI1_CTL1);
		readl(audif + AUDIF_SPDI1_CTL1);
		spdi1_activated = false;
		pr_info("h713-hdmi-audio: restored SPDI1 ctl0=%08x ctl1=%08x\n",
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
		pr_info("h713-hdmi-audio: restored Audio Bridge output stream 0\n");
	}
	audbrg_configured = false;
	audbrg_stage_applied = 0;
	if (audbrg_irq >= 0) {
		irq_dispose_mapping(audbrg_irq);
		audbrg_irq = -1;
	}
	if (audbrg_dma_area) {
		dma_free_coherent(audbrg_dma_dev, AUDBRG_DMA_SIZE,
				  audbrg_dma_area, audbrg_dma_addr);
		audbrg_dma_area = NULL;
		audbrg_dma_addr = 0;
	}
	if (audbrg_dma_dev) {
		root_device_unregister(audbrg_dma_dev);
		audbrg_dma_dev = NULL;
	}
	if (audio_top_initialized) {
		writel(audio_top_saved_cfg, audio_top + 0xc);
		writel(audio_top_saved_ctl, audio_top + 0x0);
		readl(audio_top + 0x0);
		audio_top_initialized = false;
		pr_info("h713-hdmi-audio: restored audio-top ctl=%08x cfg=%08x\n",
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
		pr_info("h713-hdmi-audio: restored audio-IHB clock=%08x\n",
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
	for (i = ARRAY_SIZE(audio_clocks) - 1; i >= 0; i--) {
		if (audio_clocks[i].enabled_by_driver)
			clk_disable_unprepare(audio_clocks[i].clk);
		if (!IS_ERR_OR_NULL(audio_clocks[i].clk))
			clk_put(audio_clocks[i].clk);
		audio_clocks[i].clk = NULL;
	}
	while (regions_claimed) {
		--regions_claimed;
		release_mem_region(audio_regions[regions_claimed].base,
				   audio_regions[regions_claimed].size);
	}
	h713_hdmi_tvfe_release();
	if (receiver_reference) {
		receiver_release();
		receiver_reference = false;
	}
	if (receiver_acquire) {
		symbol_put(h713_receiver_acquire);
		receiver_acquire = NULL;
	}
	if (receiver_release) {
		symbol_put(h713_receiver_release);
		receiver_release = NULL;
	}
}

static int verify_stock_irqs(void)
{
	struct device_node *node;
	struct of_phandle_args spec;
	int ret, index;

	node = of_find_compatible_node(NULL, NULL, "vs,trid-audio-bridge");
	if (!node)
		return -ENODEV;
	for (index = 0; index < 2; index++) {
		ret = of_irq_parse_one(node, index, &spec);
		if (ret)
			goto out;
		ret = (spec.args_count == 3 && spec.args[0] == 0 &&
		       spec.args[1] == (index ? 113 : 115) && spec.args[2] == 4) ? 0 : -EINVAL;
		of_node_put(spec.np);
		if (ret) {
			pr_err("h713-hdmi-audio: refusing reversed/unknown DT IRQs; stock bridge=SPI115, AudIf=SPI113\n");
			goto out;
		}
	}
out:
	of_node_put(node);
	return ret;
}

static int __init h713_hdmi_audio_init(void)
{
	struct device_node *audio_bridge = NULL;
	struct device_node *ccu;
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;
	u32 cfg;
	int ret = 0;

	if (!armed || !live_source3 || !receiver_powered) {
		pr_err("h713-hdmi-audio: refusing: armed=1 live_source3=1 receiver_powered=1 are all required\n");
		return -EPERM;
	}

	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	if (!ccu || !of_device_is_available(ccu)) {
		ret = -ENODEV;
		goto out_node;
	}

	spec.np = ccu;
	ret = verify_stock_irqs();
	if (ret)
		goto out_node;
	if (require_receiver_owner) {
		receiver_acquire = symbol_get(h713_receiver_acquire);
		receiver_release = symbol_get(h713_receiver_release);
		if (!receiver_acquire || !receiver_release) {
			ret = -ENODEV;
			goto fail;
		}
		ret = receiver_acquire();
		if (ret)
			goto fail;
		receiver_reference = true;
	}
	/* Exclude another ARM DSP client before touching audio clocks/registers. */
	if (manage_dsp) {
		ret = h713_hdmi_dsp_reserve();
		if (ret)
			goto fail;
	}

	for (i = 0; i < ARRAY_SIZE(audio_regions); i++) {
		if (!request_mem_region(audio_regions[i].base, audio_regions[i].size,
					"h713-hdmi-audio")) {
			ret = -EBUSY;
			goto fail;
		}
		regions_claimed++;
	}
	if (manage_tvfe) {
		ret = h713_hdmi_tvfe_prepare();
		if (ret)
			goto fail;
	}
	for (i = 0; i < ARRAY_SIZE(audio_clocks); i++) {
		spec.args[0] = audio_clocks[i].id;
		audio_clocks[i].clk = of_clk_get_from_provider(&spec);
		if (IS_ERR(audio_clocks[i].clk)) {
			ret = PTR_ERR(audio_clocks[i].clk);
			audio_clocks[i].clk = NULL;
			goto fail;
		}
	}

	/* Preserve gates inherited from U-Boot/MIPS: do not create a temporary
	 * CCF reference whose release would turn an inherited gate off.
	 */
	for (i = 0; i < ARRAY_SIZE(audio_clocks); i++) {
		audio_clocks[i].inherited_on = __clk_is_enabled(audio_clocks[i].clk);
		if (!audio_clocks[i].inherited_on) {
			ret = clk_prepare_enable(audio_clocks[i].clk);
			if (ret)
				goto fail;
			audio_clocks[i].enabled_by_driver = true;
		}
		pr_info("h713-hdmi-audio: clock=%s inherited_on=%u enabled_by_driver=%u rate=%lu\n",
			audio_clocks[i].name, audio_clocks[i].inherited_on,
			audio_clocks[i].enabled_by_driver,
			clk_get_rate(audio_clocks[i].clk));
	}

	audif = ioremap(AUDIF_PHYS_BASE, AUDIF_SIZE);
	audbrg = ioremap(AUDBRG_PHYS_BASE, AUDBRG_SIZE);
	audbrg_addr_hi = ioremap(AUDBRG_ADDR_HI_PHYS,
					 AUDBRG_ADDR_HI_SIZE);
	audio_ihb_clk_reg = ioremap(AUDIO_IHB_CLK_PHYS, AUDIO_IHB_CLK_SIZE);
	audio_top = ioremap(AUDIO_TOP_PHYS_BASE, AUDIO_TOP_SIZE);
	if (!audif || !audbrg || !audbrg_addr_hi ||
	    !audio_ihb_clk_reg || !audio_top) {
		ret = -ENOMEM;
		goto fail;
	}
	audio_bridge = of_find_compatible_node(NULL, NULL,
					       "vs,trid-audio-bridge");
	if (!audio_bridge) {
		ret = -ENODEV;
		goto fail;
	}

	audio_ihb_saved = readl(audio_ihb_clk_reg);
	writel(AUDIO_IHB_CLK_STOCK, audio_ihb_clk_reg);
	if (readl(audio_ihb_clk_reg) != AUDIO_IHB_CLK_STOCK) {
		pr_err("h713-hdmi-audio: audio-IHB clock write did not latch: %08x\n",
		       readl(audio_ihb_clk_reg));
		writel(audio_ihb_saved, audio_ihb_clk_reg);
		readl(audio_ihb_clk_reg);
		ret = -EIO;
		goto fail;
	}
	audio_ihb_retimed = true;
	pr_info("h713-hdmi-audio: audio-IHB clock stock word applied %08x->%08x\n",
		audio_ihb_saved, readl(audio_ihb_clk_reg));

	audio_top_saved_ctl = readl(audio_top + 0x0);
	audio_top_saved_cfg = readl(audio_top + 0xc);
	writel(audio_top_saved_ctl | 0x700, audio_top + 0x0);
	cfg = (audio_top_saved_cfg & 0xff000000) | 0x001a5e00;
	writel(cfg, audio_top + 0xc);
	writel(cfg | 0x01000000, audio_top + 0xc);
	readl(audio_top + 0xc);
	audio_top_initialized = true;
	pr_info("h713-hdmi-audio: audio-top initialized ctl=%08x->%08x cfg=%08x->%08x\n",
		audio_top_saved_ctl, readl(audio_top + 0x0),
		audio_top_saved_cfg, readl(audio_top + 0xc));

	/* Follow the proven IHB retiming and AudioTop setup before any AudIf
	 * access, including an ownership read or an IRQ callback. The initial
	 * ALSA build introduced an ownership read before this setup; do not
	 * assume that enabling CCF gates alone permits the additional access.
	 */
	pr_info("h713-hdmi-audio: audio clocks initialized; checking SPDI1 ownership\n");
	if (readl(audif + AUDIF_SPDI1_CTL0) ||
	    (readl(audif + AUDIF_IRQ_MASK) & AUDIF_SPDI1_W1C)) {
		pr_err("h713-hdmi-audio: refusing an active SPDI1 owner\n");
		ret = -EBUSY;
		goto fail;
	}

	audif_irq = irq_of_parse_and_map(audio_bridge, 1);
	if (!audif_irq) {
		ret = -EINVAL;
		goto fail;
	}
	ret = request_irq(audif_irq, audif_interrupt, 0,
			  "h713-hdmi-audio-audif", &audif_irq);
	if (ret)
		goto fail;
	audif_irq_requested = true;

	ret = configure_audbrg_ostream0(audio_bridge);
	if (ret)
		goto fail;

	/* Keep the stock SPDI1 setup, with its source disabled until START. */
	spdi1_saved_ctl0 = readl(audif + AUDIF_SPDI1_CTL0);
	spdi1_saved_ctl1 = readl(audif + AUDIF_SPDI1_CTL1);
	audif_saved_mask = readl(audif + AUDIF_IRQ_MASK);
	audif_saved_route = readl(audif + AUDIF_EVENT_CLEAR);
	writel(0, audif + AUDIF_SPDI1_CTL0);
	writel(0, audif + AUDIF_SPDI1_CTL1);
	writel(AUDIF_SPDI1_W1C, audif + AUDIF_IRQ_STATUS);
	writel(AUDIF_SPDI1_EVENT_CLEAR, audif + AUDIF_EVENT_CLEAR);
	spdi1_opened = true;
	writel(audif_saved_mask | AUDIF_SPDI1_W1C,
	       audif + AUDIF_IRQ_MASK);
	readl(audif + AUDIF_IRQ_MASK);
	pr_info("h713-hdmi-audio: SPDI1 opened irq=%d mask=%08x->%08x route=%08x->%08x\n",
		audif_irq, audif_saved_mask,
		readl(audif + AUDIF_IRQ_MASK), audif_saved_route,
		readl(audif + AUDIF_EVENT_CLEAR));

	writel(0x00003000, audif + AUDIF_SPDI1_CTL1);
	writel(0, audif + AUDIF_SPDI1_CTL0);
	if (readl(audif + AUDIF_SPDI1_CTL0) != 0 ||
	    readl(audif + AUDIF_SPDI1_CTL1) != 0x00003000) {
		pr_err("h713-hdmi-audio: SPDI1 activation did not latch ctl0=%08x ctl1=%08x\n",
		       readl(audif + AUDIF_SPDI1_CTL0),
		       readl(audif + AUDIF_SPDI1_CTL1));
		writel(spdi1_saved_ctl0, audif + AUDIF_SPDI1_CTL0);
		writel(spdi1_saved_ctl1, audif + AUDIF_SPDI1_CTL1);
		readl(audif + AUDIF_SPDI1_CTL1);
		ret = -EIO;
		goto fail;
	}
	spdi1_activated = true;
	pr_info("h713-hdmi-audio: SPDI1 configured (input disabled) ctl0=%08x->%08x ctl1=%08x->%08x open=%u\n",
		spdi1_saved_ctl0, readl(audif + AUDIF_SPDI1_CTL0),
		spdi1_saved_ctl1, readl(audif + AUDIF_SPDI1_CTL1),
		true);

	/* Source and bridge period IRQ stay off until ALSA START. */
	writel(0, audif + AUDIF_SPDI1_CTL0);
	writel(audbrg_saved_irq_mask, audbrg + AUDBRG_IRQ_MASK);
	if (manage_dsp) {
		ret = h713_hdmi_dsp_prepare(audbrg_dma_dev);
		if (ret)
			goto fail;
		graph_ready = true;
	}
	ret = register_pcm();
	if (ret)
		goto fail;
	pr_info("h713-hdmi-audio: registered fixed 48-kHz stereo S16_LE capture; DSP graph %s\n",
		manage_dsp ? "verified automatically" : "requires external setup");
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

static void __exit h713_hdmi_audio_exit(void)
{
	release_resources();
	pr_info("h713-hdmi-audio: removed; clocks enabled by the driver restored to off\n");
}

module_init(h713_hdmi_audio_init);
module_exit(h713_hdmi_audio_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 fixed 48-kHz stereo HDMI PCM capture");
