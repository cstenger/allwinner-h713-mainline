// SPDX-License-Identifier: GPL-2.0
/*
 * Allwinner H713 AV1 decoder.
 *
 * The H713 carries a Google AV1 decoder core (core ID 0x0003b16d, AV1
 * baseline only) next to its Allwinner video engine: a sibling of the
 * VPU981 with the same CDF layout but a different register file -- one
 * packed 1168-byte bit vector, written out whole -- and references that are
 * always stored compressed. The display picture comes out through the
 * core's secondary output as plain NV12.
 *
 * The register image and every CPU-written buffer are built by
 * sunxi_h713_av1_gen.c, a pure function of the V4L2 controls that a host
 * rig checks against the vendor library frame by frame
 * (tools/re/av1/rig/gate.sh in the H713 tree). This file is the glue:
 * buffers, the flush-and-start, the interrupt, and the clock and reset
 * the core borrows from the video engine.
 *
 * The core runs from the video engine's module clock and needs the VE's
 * bus clock and reset released, all of which belong to cedrus. A runtime-PM
 * device link to the VE (named by the allwinner,video-engine phandle) keeps
 * them up whenever this device is active. Above 432 MHz the core stalls
 * into its own timeout, so the VE clock must be at or below that.
 *
 * Three hardware rules, each learnt from a wedged or stalled SoC:
 *  - the reset must be released with the core's bus and MBUS clocks running
 *    (hantro releases it at probe with them only prepared, so they are
 *    enabled before that and kept on); released unclocked, the core stalls
 *    on its first memory transfer, and nothing short of a power cycle
 *    recovers it;
 *  - the interrupt line reads pending at boot, and the handler reads the
 *    core's registers, so the line is enabled only while a frame is in
 *    flight;
 *  - image words 0 and 1 (ID and configuration) are never written, and no
 *    register is written while the start bit is still set.
 */

#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/reset.h>
#include <linux/vmalloc.h>

#include "hantro.h"
#include "hantro_hw.h"
#include "sunxi_h713_av1_gen.h"

#define H713_AV1_CTRL			0x008	/* image word 2 */
#define H713_AV1_CTRL_START		BIT(0)
#define H713_AV1_IRQ_TIMEOUT		BIT(2)
#define H713_AV1_IRQ_BUS_ERROR		BIT(3)
#define H713_AV1_IRQ_FRAME_READY	BIT(4)
#define H713_AV1_IRQ_DEC_ERROR		BIT(5)
#define H713_AV1_IRQ			BIT(6)
#define H713_AV1_IRQ_BITS		GENMASK(6, 2)
#define H713_AV1_IRQ_ERRORS		(H713_AV1_IRQ_TIMEOUT | H713_AV1_IRQ_BUS_ERROR | \
					 H713_AV1_IRQ_DEC_ERROR)

#define H713_AV1_MAX_VE_RATE		432000000

enum { SLOT_REC, SLOT_HDR, SLOT_MV, SLOT_NBUFS };

static bool h713_av1_trace;
module_param(h713_av1_trace, bool, 0644);
MODULE_PARM_DESC(h713_av1_trace, "H713 AV1: log each frame, its register image and its interrupt");

#define h713_trace(vpu, fmt, ...) \
	do { if (h713_av1_trace) dev_info((vpu)->dev, fmt, ##__VA_ARGS__); } while (0)

struct sunxi_h713_av1_hw {
	int irq;
	unsigned long armed;	/* bit 0: the line is enabled */
	struct mutex lock;	/* streams */
	unsigned int streams;	/* contexts holding the core powered */
};

static void h713_av1_irq_arm(struct hantro_dev *vpu)
{
	struct sunxi_h713_av1_hw *hw = vpu->variant_priv;

	if (!test_and_set_bit(0, &hw->armed))
		enable_irq(hw->irq);
}

static void h713_av1_irq_disarm(struct hantro_dev *vpu)
{
	struct sunxi_h713_av1_hw *hw = vpu->variant_priv;

	if (test_and_clear_bit(0, &hw->armed))
		disable_irq_nosync(hw->irq);
}

struct sunxi_h713_av1_dec_ctx {
	bool powered;		/* holding the domain and clocks while streaming */
	struct h713_av1 gen;
	struct h713_av1_cdf *cdf;
	/* each reference slot's compressed reconstruction, header and MVs */
	struct h713_av1_dma slot[H713_AV1_MAX_FRAMES][SLOT_NBUFS];
};

static int h713_av1_alloc(struct hantro_dev *vpu, struct h713_av1_dma *d,
			  size_t size, bool cpu)
{
	d->size = size;
	d->kmap = cpu;
	d->cpu = dma_alloc_attrs(vpu->dev, size, &d->dma, GFP_KERNEL,
				 cpu ? 0 : DMA_ATTR_NO_KERNEL_MAPPING);
	return d->cpu ? 0 : -ENOMEM;
}

static void h713_av1_free(struct hantro_dev *vpu, struct h713_av1_dma *d)
{
	if (d->cpu)
		dma_free_attrs(vpu->dev, d->size, d->cpu, d->dma,
			       d->kmap ? 0 : DMA_ATTR_NO_KERNEL_MAPPING);
	d->cpu = NULL;
}

/* The fixed buffers: which the CPU writes or reads, and their sizes. */
static const struct {
	size_t off;	/* in struct h713_av1_bufs */
	size_t size;
	bool cpu;
} h713_av1_fixed[] = {
	{ offsetof(struct h713_av1_bufs, tile_info), H713_AV1_TILE_INFO_SIZE, true },
	{ offsetof(struct h713_av1_bufs, global_model), H713_AV1_GLOBAL_MODEL_SIZE, true },
	{ offsetof(struct h713_av1_bufs, prob), H713_AV1_PROB_SIZE, true },
	{ offsetof(struct h713_av1_bufs, prob_out), H713_AV1_PROB_SIZE, true },
	{ offsetof(struct h713_av1_bufs, film_grain), H713_AV1_FILM_GRAIN_SIZE, true },
	{ offsetof(struct h713_av1_bufs, pdec), H713_AV1_PDEC_SIZE, true },
	{ offsetof(struct h713_av1_bufs, scratch), H713_AV1_SCRATCH_SIZE, false },
	{ offsetof(struct h713_av1_bufs, filter_ctrl), H713_AV1_FILTER_CTRL_SIZE, false },
	{ offsetof(struct h713_av1_bufs, fg_colbuf), H713_AV1_FG_COLBUF_SIZE, false },
	{ offsetof(struct h713_av1_bufs, cdef_colbuf), H713_AV1_CDEF_COLBUF_SIZE, false },
	{ offsetof(struct h713_av1_bufs, rec_sindex), H713_AV1_REC_SINDEX_SIZE, false },
	{ offsetof(struct h713_av1_bufs, sec_colbuf), H713_AV1_SEC_COLBUF_SIZE, false },
	{ offsetof(struct h713_av1_bufs, vert_filt), H713_AV1_VERT_FILT_SIZE, false },
};

static struct h713_av1_dma *fixed_buf(struct sunxi_h713_av1_dec_ctx *a, int i)
{
	return (void *)&a->gen.b + h713_av1_fixed[i].off;
}

static void h713_av1_block_reset(struct hantro_dev *vpu)
{
	reset_control_assert(vpu->resets);
	udelay(10);
	reset_control_deassert(vpu->resets);
}

static void sunxi_h713_av1_dec_exit(struct hantro_ctx *ctx)
{
	struct sunxi_h713_av1_dec_ctx *a = ctx->h713_av1_dec;
	struct hantro_dev *vpu = ctx->dev;
	int i, j;

	if (!a)
		return;
	if (a->powered) {
		struct sunxi_h713_av1_hw *hw = vpu->variant_priv;

		mutex_lock(&hw->lock);
		hw->streams--;
		clk_bulk_disable(vpu->variant->num_clocks, vpu->clocks);
		pm_runtime_put_autosuspend(vpu->dev);
		mutex_unlock(&hw->lock);
	}
	for (i = 0; i < H713_AV1_MAX_FRAMES; i++)
		for (j = 0; j < SLOT_NBUFS; j++)
			h713_av1_free(vpu, &a->slot[i][j]);
	for (i = 0; i < ARRAY_SIZE(h713_av1_fixed); i++)
		h713_av1_free(vpu, fixed_buf(a, i));
	vfree(a->cdf);
	kfree(a);
	ctx->h713_av1_dec = NULL;
}

static int sunxi_h713_av1_dec_init(struct hantro_ctx *ctx)
{
	struct hantro_dev *vpu = ctx->dev;
	struct sunxi_h713_av1_hw *hw = vpu->variant_priv;
	struct sunxi_h713_av1_dec_ctx *a;
	int i, ret;

	a = kzalloc(sizeof(*a), GFP_KERNEL);
	if (!a)
		return -ENOMEM;
	ctx->h713_av1_dec = a;

	a->cdf = vzalloc(sizeof(*a->cdf));
	if (!a->cdf) {
		ret = -ENOMEM;
		goto err;
	}
	for (i = 0; i < ARRAY_SIZE(h713_av1_fixed); i++) {
		ret = h713_av1_alloc(vpu, fixed_buf(a, i), h713_av1_fixed[i].size,
				     h713_av1_fixed[i].cpu);
		if (ret)
			goto err;
	}

	a->gen.cdf = a->cdf;
	ret = h713_av1_gen_init(&a->gen);
	if (ret)
		goto err;

	/*
	 * Power and clocks for the whole stream. The first stream to power
	 * the core also resets it; a later one must not, because the core may
	 * be in the middle of another context's frame.
	 */
	mutex_lock(&hw->lock);
	ret = pm_runtime_resume_and_get(vpu->dev);
	if (ret < 0)
		goto err_unlock;
	ret = clk_bulk_enable(vpu->variant->num_clocks, vpu->clocks);
	if (ret) {
		pm_runtime_put_autosuspend(vpu->dev);
		goto err_unlock;
	}
	a->powered = true;
	if (!hw->streams++)
		h713_av1_block_reset(vpu);
	mutex_unlock(&hw->lock);
	return 0;

err_unlock:
	mutex_unlock(&hw->lock);

err:
	sunxi_h713_av1_dec_exit(ctx);
	return ret;
}

/*
 * A slot keeps its buffers once allocated -- slots are reused lowest-first,
 * so a stream settles on the handful it needs -- and grows them when a frame
 * needs more than they hold.
 */
static int h713_av1_slot_bufs(struct hantro_ctx *ctx, int slot, int w, int h)
{
	struct sunxi_h713_av1_dec_ctx *a = ctx->h713_av1_dec;
	struct h713_av1_dma *d = a->slot[slot];
	size_t size[SLOT_NBUFS];
	int j, ret;

	h713_av1_frame_bufs_size(w, h, &size[SLOT_REC], &size[SLOT_HDR], &size[SLOT_MV]);
	for (j = 0; j < SLOT_NBUFS; j++) {
		if (d[j].cpu && d[j].size >= size[j])
			continue;
		h713_av1_free(ctx->dev, &d[j]);
		ret = h713_av1_alloc(ctx->dev, &d[j], size[j], false);
		if (ret)
			return ret;
	}
	a->gen.refs[slot].bufs.rec = d[SLOT_REC].dma;
	a->gen.refs[slot].bufs.hdr = d[SLOT_HDR].dma;
	a->gen.refs[slot].bufs.mv = d[SLOT_MV].dma;
	return 0;
}

static int sunxi_h713_av1_dec_run(struct hantro_ctx *ctx)
{
	struct sunxi_h713_av1_dec_ctx *a = ctx->h713_av1_dec;
	struct hantro_dev *vpu = ctx->dev;
	struct h713_av1 *h = &a->gen;
	struct vb2_v4l2_buffer *src, *dst;
	struct v4l2_ctrl *tge;
	u32 width, height;
	int slot, ret, i;

	hantro_start_prepare_run(ctx);

	src = hantro_get_src_buf(ctx);
	dst = hantro_get_dst_buf(ctx);

	h->seq = hantro_get_ctrl(ctx, V4L2_CID_STATELESS_AV1_SEQUENCE);
	h->frame = hantro_get_ctrl(ctx, V4L2_CID_STATELESS_AV1_FRAME);
	h->film_grain = hantro_get_ctrl(ctx, V4L2_CID_STATELESS_AV1_FILM_GRAIN);
	tge = v4l2_ctrl_find(&ctx->ctrl_handler, V4L2_CID_STATELESS_AV1_TILE_GROUP_ENTRY);
	if (WARN_ON(!h->seq || !h->frame || !tge)) {
		ret = -EINVAL;
		goto out;
	}
	h->tge = tge->p_cur.p;
	h->num_tge = tge->elems;
	if (!(h->seq->flags & V4L2_AV1_SEQUENCE_FLAG_FILM_GRAIN_PARAMS_PRESENT))
		h->film_grain = NULL;
	h->bit_depth = h->seq->bit_depth;

	h->src_dma = vb2_dma_contig_plane_dma_addr(&src->vb2_buf, 0);
	h->src_len = vb2_get_plane_payload(&src->vb2_buf, 0);
	h->src_size = vb2_plane_size(&src->vb2_buf, 0);
	h->dst_luma = hantro_get_dec_buf_addr(ctx, &dst->vb2_buf);
	h->dst_chroma = h->dst_luma +
			ctx->dst_fmt.plane_fmt[0].bytesperline * ctx->dst_fmt.height;

	/*
	 * The picture is stored and shown after superres, so at the upscaled
	 * width. The core lays the raster out at a stride of the width rounded
	 * up to 64 -- there is no stride it is told -- so a frame has to fit
	 * the capture buffer that way, whatever size the format was set to.
	 */
	width = max_t(u32, h->frame->upscaled_width, h->frame->frame_width_minus_1 + 1);
	height = h->frame->frame_height_minus_1 + 1;
	if (width > FMT_4K_WIDTH || height > FMT_4K_HEIGHT ||
	    ALIGN(width, 64) > ctx->dst_fmt.plane_fmt[0].bytesperline ||
	    ALIGN(height, 8) > ctx->dst_fmt.height) {
		ret = -EINVAL;
		goto out;
	}

	slot = h713_av1_gen_slot(h, src->vb2_buf.timestamp);
	if (slot < 0) {
		ret = slot;
		goto out;
	}
	ret = h713_av1_slot_bufs(ctx, slot, width, height);
	if (ret)
		goto out;
	ret = h713_av1_gen_frame(h);

out:
	hantro_end_prepare_run(ctx);
	if (ret) {
		/*
		 * Finish the job here, watchdog included, and report success
		 * to device_run: an error return would make it finish the job
		 * a second time.
		 */
		dev_warn_ratelimited(vpu->dev, "cannot set up the frame: %d\n", ret);
		hantro_irq_done(vpu, VB2_BUF_STATE_ERROR);
		return 0;
	}

	h713_trace(vpu, "frame: slot %d %ux%u type %u show %u, src %pad+%u dst %pad\n",
		   slot, h->frame->frame_width_minus_1 + 1, h->frame->frame_height_minus_1 + 1,
		   h->frame->frame_type, !!(h->frame->flags & V4L2_AV1_FRAME_FLAG_SHOW_FRAME),
		   &h->src_dma, h->src_len, &h->dst_luma);
	if (h713_av1_trace) {
		print_hex_dump(KERN_INFO, "h713av1 img ", DUMP_PREFIX_OFFSET, 32, 4,
			       h->regs, sizeof(h->regs), false);
		/*
		 * Let the dump leave the machine before the core starts: when
		 * a frame hangs the SoC, this image is the evidence. Debug only.
		 */
		mdelay(50);
	}

	/* After an error interrupt the core can still be busy: reset it first. */
	if (readl_relaxed(vpu->dec_base + H713_AV1_CTRL) & H713_AV1_CTRL_START) {
		dev_warn_ratelimited(vpu->dev, "core still busy; resetting it\n");
		h713_av1_block_reset(vpu);
	}

	/*
	 * As the vendor's AsicFlushRegs: words 0 and 1 are left alone, the rest
	 * go in top-down with the start bit held back, then start on its own.
	 */
	for (i = H713_AV1_NWORDS - 1; i >= 2; i--)
		writel_relaxed(i == H713_AV1_CTRL / 4 ? h->regs[i] & ~H713_AV1_CTRL_START :
			       h->regs[i], vpu->dec_base + 4 * i);
	wmb();
	h713_av1_irq_arm(vpu);
	writel(h->regs[H713_AV1_CTRL / 4] | H713_AV1_CTRL_START,
	       vpu->dec_base + H713_AV1_CTRL);
	return 0;
}

/* The core wrote its compressor statistics back into the image; fetch them. */
static void sunxi_h713_av1_dec_done(struct hantro_ctx *ctx)
{
	struct sunxi_h713_av1_dec_ctx *a = ctx->h713_av1_dec;
	int i;

	for (i = 0; i < H713_AV1_NWORDS; i++)
		a->gen.regs[i] = readl_relaxed(ctx->dev->dec_base + 4 * i);
	h713_av1_gen_done(&a->gen);
}

/* Timeout: clearing the start bit does not stop the core; the reset does. */
static void sunxi_h713_av1_dec_reset(struct hantro_ctx *ctx)
{
	h713_av1_irq_disarm(ctx->dev);
	h713_av1_block_reset(ctx->dev);
}

static irqreturn_t sunxi_h713_av1_irq(int irq, void *dev_id)
{
	struct hantro_dev *vpu = dev_id;
	enum vb2_buffer_state state;
	u32 ctrl;

	/* one interrupt per frame; a line stuck high must not storm */
	h713_av1_irq_disarm(vpu);

	ctrl = readl_relaxed(vpu->dec_base + H713_AV1_CTRL);
	h713_trace(vpu, "irq: ctrl 0x%08x\n", ctrl);
	if (!(ctrl & H713_AV1_IRQ_BITS)) {
		/* no cause: leave the job to the watchdog, which resets */
		dev_warn_ratelimited(vpu->dev, "interrupt without a cause, 0x%08x\n", ctrl);
		return IRQ_HANDLED;
	}
	writel_relaxed(ctrl & ~(H713_AV1_IRQ_BITS | H713_AV1_CTRL_START),
		       vpu->dec_base + H713_AV1_CTRL);

	state = (ctrl & H713_AV1_IRQ_FRAME_READY) && !(ctrl & H713_AV1_IRQ_ERRORS) ?
		VB2_BUF_STATE_DONE : VB2_BUF_STATE_ERROR;
	if (state == VB2_BUF_STATE_ERROR) {
		dev_warn_ratelimited(vpu->dev, "decode failed, status 0x%08x\n", ctrl);
		/* whatever state the failed frame left the core in, start clean */
		h713_av1_block_reset(vpu);
	}

	hantro_irq_done(vpu, state);
	return IRQ_HANDLED;
}

static void h713_av1_clocks_off(void *data)
{
	struct hantro_dev *vpu = data;

	clk_bulk_disable_unprepare(vpu->variant->num_clocks, vpu->clocks);
}

static int sunxi_h713_av1_hw_init(struct hantro_dev *vpu)
{
	struct sunxi_h713_av1_hw *hw;
	struct device_node *np;
	struct platform_device *ve;
	struct device_link *link;
	struct clk *mod;
	unsigned long rate;
	int ret;

	hw = devm_kzalloc(vpu->dev, sizeof(*hw), GFP_KERNEL);
	if (!hw)
		return -ENOMEM;
	mutex_init(&hw->lock);
	vpu->variant_priv = hw;

	/* requested disabled: armed per frame only (see the top of this file) */
	hw->irq = platform_get_irq(vpu->pdev, 0);
	if (hw->irq < 0)
		return hw->irq;
	ret = devm_request_irq(vpu->dev, hw->irq, sunxi_h713_av1_irq, IRQF_NO_AUTOEN,
			       dev_name(vpu->dev), vpu);
	if (ret)
		return ret;

	/*
	 * hantro_probe releases the reset after this init with the clocks only
	 * prepared; the core must come out of reset clocked. Enable them now,
	 * with the reset held, and keep them on for the device's lifetime.
	 */
	reset_control_assert(vpu->resets);
	ret = clk_bulk_prepare_enable(vpu->variant->num_clocks, vpu->clocks);
	if (ret)
		return ret;
	ret = devm_add_action_or_reset(vpu->dev, h713_av1_clocks_off, vpu);
	if (ret)
		return ret;

	np = of_parse_phandle(vpu->dev->of_node, "allwinner,video-engine", 0);
	if (!np) {
		dev_err(vpu->dev, "no allwinner,video-engine phandle\n");
		return -ENODEV;
	}
	ve = of_find_device_by_node(np);
	if (!ve) {
		ret = -EPROBE_DEFER;
		goto out_node;
	}
	if (!device_is_bound(&ve->dev)) {
		ret = -EPROBE_DEFER;
		goto out_dev;
	}

	mod = of_clk_get_by_name(np, "mod");
	if (IS_ERR(mod)) {
		ret = PTR_ERR(mod);
		goto out_dev;
	}
	rate = clk_get_rate(mod);
	clk_put(mod);
	if (rate > H713_AV1_MAX_VE_RATE) {
		dev_err(vpu->dev, "VE clock %lu Hz: the core stalls above %u Hz\n",
			rate, H713_AV1_MAX_VE_RATE);
		ret = -EINVAL;
		goto out_dev;
	}

	link = device_link_add(vpu->dev, &ve->dev,
			       DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_CONSUMER);
	if (!link) {
		dev_err(vpu->dev, "cannot link to the video engine\n");
		ret = -EINVAL;
	}

out_dev:
	put_device(&ve->dev);
out_node:
	of_node_put(np);
	return ret;
}

static const struct hantro_fmt sunxi_h713_av1_dec_fmts[] = {
	{
		.fourcc = V4L2_PIX_FMT_NV12,
		.codec_mode = HANTRO_MODE_NONE,
		.match_depth = true,
		.frmsize = {
			.min_width = 64,
			.max_width = FMT_4K_WIDTH,
			.step_width = 64,
			.min_height = 64,
			.max_height = FMT_4K_HEIGHT,
			.step_height = 64,
		},
	},
	{
		.fourcc = V4L2_PIX_FMT_AV1_FRAME,
		.codec_mode = HANTRO_MODE_AV1_DEC,
		.max_depth = 2,
		.frmsize = {
			.min_width = 64,
			.max_width = FMT_4K_WIDTH,
			.step_width = 64,
			.min_height = 64,
			.max_height = FMT_4K_HEIGHT,
			.step_height = 64,
		},
	},
};

static const struct hantro_codec_ops sunxi_h713_av1_codec_ops[] = {
	[HANTRO_MODE_AV1_DEC] = {
		.run = sunxi_h713_av1_dec_run,
		.init = sunxi_h713_av1_dec_init,
		.exit = sunxi_h713_av1_dec_exit,
		.done = sunxi_h713_av1_dec_done,
		.reset = sunxi_h713_av1_dec_reset,
	},
};

static const char * const sunxi_h713_av1_clk_names[] = { "bus", "mbus" };

const struct hantro_variant sun50i_h713_av1_variant = {
	.dec_fmts = sunxi_h713_av1_dec_fmts,
	.num_dec_fmts = ARRAY_SIZE(sunxi_h713_av1_dec_fmts),
	.codec = HANTRO_AV1_DECODER,
	.codec_ops = sunxi_h713_av1_codec_ops,
	.init = sunxi_h713_av1_hw_init,
	/* no .irqs: the line is requested above, disabled */
	.clk_names = sunxi_h713_av1_clk_names,
	.num_clocks = ARRAY_SIZE(sunxi_h713_av1_clk_names),
};
