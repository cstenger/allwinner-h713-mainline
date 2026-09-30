/* SPDX-License-Identifier: GPL-2.0 */
/*
 * H713 AV1 decoder: register-image generation.
 *
 * A pure function of the V4L2 AV1 controls and the decoder's reference
 * state: it fills the 1168-byte register image and the CPU-written
 * auxiliary buffers (tile info, global model, probabilities, film grain,
 * reference-decompressor config). It touches no hardware, so the same file
 * builds into the kernel driver and into a host test rig that compares its
 * output with the vendor library's, frame by frame
 * (docs/reference/av1-google-ip-interface.md).
 *
 * Derived from the Rockchip VPU981 AV1 code (rockchip_vpu981_hw_av1_dec.c,
 * Collabora), a sibling core: same CDF layout, mostly the same register
 * vocabulary, different register positions (a packed bit vector here, see
 * sunxi_h713_av1_regs.h) and a different buffer set.
 */
#ifndef SUNXI_H713_AV1_GEN_H_
#define SUNXI_H713_AV1_GEN_H_

#include "sunxi_h713_av1_regs.h"
#include "rockchip_av1_entropymode.h"

#define H713_AV1_NUM_REF_FRAMES		8	/* AV1 reference slots */
#define H713_AV1_MAX_FRAMES		16	/* decode buffers tracked */
#define H713_AV1_NWORDS			(H713_AV1_REGS_SIZE / 4)

/* Fixed-size buffers, sizes as the vendor allocates them. */
#define H713_AV1_TILE_INFO_SIZE		0x500
#define H713_AV1_GLOBAL_MODEL_SIZE	0xe0
#define H713_AV1_PROB_SIZE		0x2fe0
#define H713_AV1_FILM_GRAIN_SIZE	0x3300
#define H713_AV1_PDEC_SIZE		0x1000
#define H713_AV1_SCRATCH_SIZE		0x50c000	/* ref0_sindex / out_scaled_lu */
#define H713_AV1_SCRATCH_SCALED_OFF	0x66000
#define H713_AV1_FILTER_CTRL_SIZE	0x4400		/* + LR params at 0x1100 */
#define H713_AV1_FILTER_LR_OFF		0x1100
#define H713_AV1_FG_COLBUF_SIZE		0x8800
#define H713_AV1_CDEF_COLBUF_SIZE	0x1100
#define H713_AV1_REC_SINDEX_SIZE	0x66000
#define H713_AV1_SEC_COLBUF_SIZE	0x44000		/* out_secondary_colbuf, every size */

struct h713_av1_dma {
	void *cpu;
	u64 dma;
	size_t size;
};

/* One decoded frame's private buffers: compressed reconstruction + MVs. */
struct h713_av1_frame_bufs {
	u64 rec;	/* sb * 0x2400 */
	u64 hdr;	/* compression header */
	u64 mv;		/* sb * 0x400 */
};

struct h713_av1_ref {
	bool used;
	u64 timestamp;
	int width, height, mi_cols, mi_rows;
	int frame_type;
	u32 order_hint;
	u32 order_hints[V4L2_AV1_TOTAL_REFS_PER_FRAME];
	struct h713_av1_frame_bufs bufs;	/* the caller's, kept across reuse */
	u8 fc_luma[8];		/* reference-compressor entropy modes */
	u8 fc_chroma[8];
};

struct h713_av1_bufs {
	struct h713_av1_dma tile_info, global_model, prob, prob_out;
	struct h713_av1_dma film_grain, pdec, scratch, filter_ctrl;
	struct h713_av1_dma fg_colbuf, cdef_colbuf, rec_sindex, sec_colbuf;
};

/* CDF storage lives here, not in hantro_ctx, so the host rig can use it. */
struct h713_av1_cdf {
	struct av1cdfs *cdfs;
	struct mvcdfs *cdfs_ndvc;
	struct av1cdfs default_cdfs;
	struct mvcdfs default_cdfs_ndvc;
	struct av1cdfs last[H713_AV1_NUM_REF_FRAMES];
	struct mvcdfs last_ndvc[H713_AV1_NUM_REF_FRAMES];
};

struct h713_av1 {
	/* per run, set by the caller */
	const struct v4l2_ctrl_av1_sequence *seq;
	const struct v4l2_ctrl_av1_frame *frame;
	const struct v4l2_ctrl_av1_tile_group_entry *tge;
	unsigned int num_tge;
	const struct v4l2_ctrl_av1_film_grain *film_grain;
	u64 src_dma;		/* bitstream buffer */
	u32 src_len, src_size;
	u64 dst_luma, dst_chroma;	/* NV12 capture (secondary output) */
	int bit_depth;

	/* persistent */
	struct h713_av1_cdf *cdf;	/* ~120 KiB: allocate it */
	struct h713_av1_bufs b;
	struct h713_av1_ref refs[H713_AV1_MAX_FRAMES];
	int cur;			/* index into refs[] */
	u32 ref_frame_sign_bias[V4L2_AV1_TOTAL_REFS_PER_FRAME];
	u8 fc_modes[16];		/* compressor modes: luma 0..7, chroma 8..15 */

	/* output */
	u32 regs[H713_AV1_NWORDS];
};

/*
 * Per frame, with the controls set: h713_av1_gen_slot() retires references
 * no longer in use and picks this frame's slot in refs[] (or -ENOSPC); the
 * caller makes sure refs[slot].bufs holds buffers of at least
 * h713_av1_frame_bufs_size() for this frame; h713_av1_gen_frame() then
 * builds the image and CPU-side buffers.
 */
int h713_av1_gen_slot(struct h713_av1 *h, u64 timestamp);
void h713_av1_frame_bufs_size(int width, int height, size_t *rec, size_t *hdr, size_t *mv);
int h713_av1_gen_frame(struct h713_av1 *h);
/*
 * After the hardware finished: pick up CDFs and re-rank the compressor
 * modes. The caller first refreshes h->regs from the hardware (at least the
 * fc_*_count words).
 */
void h713_av1_gen_done(struct h713_av1 *h);
int h713_av1_gen_init(struct h713_av1 *h);

static inline void h713_av1_set(u32 *img, struct h713_av1_field f, u32 val)
{
	unsigned int i;

	for (i = 0; i < f.width; i++) {
		unsigned int b = f.lo + i;

		if (val & (1u << i))
			img[b / 32] |= 1u << (b % 32);
		else
			img[b / 32] &= ~(1u << (b % 32));
	}
}

static inline u32 h713_av1_get(const u32 *img, struct h713_av1_field f)
{
	unsigned int i;
	u32 val = 0;

	for (i = 0; i < f.width; i++) {
		unsigned int b = f.lo + i;

		if (img[b / 32] & (1u << (b % 32)))
			val |= 1u << i;
	}
	return val;
}

#endif
