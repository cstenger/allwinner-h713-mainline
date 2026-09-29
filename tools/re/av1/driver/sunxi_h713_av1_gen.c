// SPDX-License-Identifier: GPL-2.0-only
/*
 * H713 AV1 decoder: register-image generation. See sunxi_h713_av1_gen.h.
 *
 * Ported from rockchip_vpu981_hw_av1_dec.c:
 *   Copyright (c) 2023, Collabora
 *   Author: Benjamin Gaignard <benjamin.gaignard@collabora.com>
 *
 * Where the H713 differs from the VPU981, the vendor library's own register
 * images (captured by running it under emulation, tools/re/av1/) are the
 * reference; those places say so.
 */

#include "sunxi_h713_av1_compat.h"
#include "sunxi_h713_av1_gen.h"
#include "rockchip_av1_entropymode.h"
#include "rockchip_av1_filmgrain.h"

#define GM_GLOBAL_MODELS_PER_FRAME	7
#define AV1_REF_SCALE_SHIFT		14
#define AV1_INVALID_IDX			-1
#define MAX_FRAME_DISTANCE		31
#define AV1_PRIMARY_REF_NONE		7

#define V4L2_AV1_SEG_LVL_ALT_LF_Y_H	2
#define V4L2_AV1_SEG_LVL_ALT_LF_U	3
#define V4L2_AV1_SEG_LVL_ALT_LF_V	4

#define SUPERRES_SCALE_BITS		3
#define SCALE_NUMERATOR			8
#define SUPERRES_SCALE_DENOMINATOR_MIN	(SCALE_NUMERATOR + 1)
#define RS_SUBPEL_BITS			6
#define RS_SCALE_SUBPEL_BITS		14
#define RS_SCALE_SUBPEL_MASK		((1 << RS_SCALE_SUBPEL_BITS) - 1)
#define RS_SCALE_EXTRA_BITS		(RS_SCALE_SUBPEL_BITS - RS_SUBPEL_BITS)

#define IS_INTRA(type) ((type) == V4L2_AV1_KEY_FRAME || (type) == V4L2_AV1_INTRA_ONLY_FRAME)

#define LST_BUF_IDX	(V4L2_AV1_REF_LAST_FRAME - V4L2_AV1_REF_LAST_FRAME)
#define LST2_BUF_IDX	(V4L2_AV1_REF_LAST2_FRAME - V4L2_AV1_REF_LAST_FRAME)
#define GLD_BUF_IDX	(V4L2_AV1_REF_GOLDEN_FRAME - V4L2_AV1_REF_LAST_FRAME)
#define BWD_BUF_IDX	(V4L2_AV1_REF_BWDREF_FRAME - V4L2_AV1_REF_LAST_FRAME)
#define ALT2_BUF_IDX	(V4L2_AV1_REF_ALTREF2_FRAME - V4L2_AV1_REF_LAST_FRAME)
#define ALT_BUF_IDX	(V4L2_AV1_REF_ALTREF_FRAME - V4L2_AV1_REF_LAST_FRAME)

#define DIV_LUT_PREC_BITS	14
#define DIV_LUT_BITS		8
#define DIV_LUT_NUM		(1 << DIV_LUT_BITS)
#define WARP_PARAM_REDUCE_BITS	6
#define WARPEDMODEL_PREC_BITS	16

#define AV1_DIV_ROUND_UP_POW2(value, n)	(((value) + ((1LL << (n)) >> 1)) >> (n))
#define AV1_DIV_ROUND_UP_POW2_SIGNED(value, n) \
	(((value) < 0) ? -AV1_DIV_ROUND_UP_POW2(-(value), (n)) \
		       : AV1_DIV_ROUND_UP_POW2((value), (n)))

#define W(h, field, val)	h713_av1_set((h)->regs, H713_AV1_##field, (u32)(val))
#define WADDR(h, field, a)	W(h, field, lower_32_bits(a))

enum { H713_TX_ONLY_4X4 = 0, H713_TX_32X32 = 3, H713_TX_SELECT = 4 };

static const short div_lut[DIV_LUT_NUM + 1] = {
	16384, 16320, 16257, 16194, 16132, 16070, 16009, 15948, 15888, 15828, 15768,
	15709, 15650, 15592, 15534, 15477, 15420, 15364, 15308, 15252, 15197, 15142,
	15087, 15033, 14980, 14926, 14873, 14821, 14769, 14717, 14665, 14614, 14564,
	14513, 14463, 14413, 14364, 14315, 14266, 14218, 14170, 14122, 14075, 14028,
	13981, 13935, 13888, 13843, 13797, 13752, 13707, 13662, 13618, 13574, 13530,
	13487, 13443, 13400, 13358, 13315, 13273, 13231, 13190, 13148, 13107, 13066,
	13026, 12985, 12945, 12906, 12866, 12827, 12788, 12749, 12710, 12672, 12633,
	12596, 12558, 12520, 12483, 12446, 12409, 12373, 12336, 12300, 12264, 12228,
	12193, 12157, 12122, 12087, 12053, 12018, 11984, 11950, 11916, 11882, 11848,
	11815, 11782, 11749, 11716, 11683, 11651, 11619, 11586, 11555, 11523, 11491,
	11460, 11429, 11398, 11367, 11336, 11305, 11275, 11245, 11215, 11185, 11155,
	11125, 11096, 11067, 11038, 11009, 10980, 10951, 10923, 10894, 10866, 10838,
	10810, 10782, 10755, 10727, 10700, 10673, 10645, 10618, 10592, 10565, 10538,
	10512, 10486, 10460, 10434, 10408, 10382, 10356, 10331, 10305, 10280, 10255,
	10230, 10205, 10180, 10156, 10131, 10107, 10082, 10058, 10034, 10010, 9986,
	9963,  9939,  9916,  9892,  9869,  9846,  9823,  9800,  9777,  9754,  9732,
	9709,  9687,  9664,  9642,  9620,  9598,  9576,  9554,  9533,  9511,  9489,
	9468,  9447,  9425,  9404,  9383,  9362,  9341,  9321,  9300,  9279,  9259,
	9239,  9218,  9198,  9178,  9158,  9138,  9118,  9098,  9079,  9059,  9039,
	9020,  9001,  8981,  8962,  8943,  8924,  8905,  8886,  8867,  8849,  8830,
	8812,  8793,  8775,  8756,  8738,  8720,  8702,  8684,  8666,  8648,  8630,
	8613,  8595,  8577,  8560,  8542,  8525,  8508,  8490,  8473,  8456,  8439,
	8422,  8405,  8389,  8372,  8355,  8339,  8322,  8306,  8289,  8273,  8257,
	8240,  8224,  8208,  8192,
};

/* ---- reference bookkeeping (as VPU981) ---------------------------------- */

static int get_frame_index(struct h713_av1 *h, int ref)
{
	int i, idx = h->frame->ref_frame_idx[ref];
	u64 ts;

	if (idx >= V4L2_AV1_TOTAL_REFS_PER_FRAME || idx < 0)
		return AV1_INVALID_IDX;
	ts = h->frame->reference_frame_ts[idx];
	for (i = 0; i < H713_AV1_MAX_FRAMES; i++)
		if (h->refs[i].used && h->refs[i].timestamp == ts)
			return i;
	return AV1_INVALID_IDX;
}

static int get_order_hint(struct h713_av1 *h, int ref)
{
	int idx = get_frame_index(h, ref);

	return idx != AV1_INVALID_IDX ? h->refs[idx].order_hint : 0;
}

static int frame_ref(struct h713_av1 *h, u64 timestamp)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	int i, j;

	for (i = 0; i < H713_AV1_MAX_FRAMES; i++) {
		struct h713_av1_ref *r = &h->refs[i];

		if (r->used)
			continue;
		r->width = f->frame_width_minus_1 + 1;
		r->height = f->frame_height_minus_1 + 1;
		r->mi_cols = DIV_ROUND_UP(r->width, 8);
		r->mi_rows = DIV_ROUND_UP(r->height, 8);
		r->timestamp = timestamp;
		r->frame_type = f->frame_type;
		r->order_hint = f->order_hint;
		r->bufs = h->cur_bufs;
		for (j = 0; j < V4L2_AV1_TOTAL_REFS_PER_FRAME; j++)
			r->order_hints[j] = f->order_hints[j];
		r->used = true;
		h->cur = i;
		return i;
	}
	return AV1_INVALID_IDX;
}

static void clean_refs(struct h713_av1 *h)
{
	int idx, ref;

	for (idx = 0; idx < H713_AV1_MAX_FRAMES; idx++) {
		bool used = false;

		if (!h->refs[idx].used)
			continue;
		for (ref = 0; ref < V4L2_AV1_TOTAL_REFS_PER_FRAME; ref++)
			if (h->frame->reference_frame_ts[ref] == h->refs[idx].timestamp)
				used = true;
		if (!used)
			h->refs[idx].used = false;
	}
}

static int get_dist(struct h713_av1 *h, int a, int b)
{
	int bits = h->seq->order_hint_bits - 1;
	int diff, m;

	if (!h->seq->order_hint_bits)
		return 0;
	diff = a - b;
	m = 1 << bits;
	return (diff & (m - 1)) - (diff & m);
}

/* ---- global motion ------------------------------------------------------ */

static int get_msb(u32 n)
{
	return n ? 31 ^ __builtin_clz(n) : 0;
}

static short resolve_divisor_32(u32 d, short *shift)
{
	int f;
	u64 e;

	*shift = get_msb(d);
	e = d - ((u32)1 << *shift);
	if (*shift > DIV_LUT_BITS)
		f = AV1_DIV_ROUND_UP_POW2(e, *shift - DIV_LUT_BITS);
	else
		f = e << (DIV_LUT_BITS - *shift);
	if (f > DIV_LUT_NUM)
		return -1;
	*shift += DIV_LUT_PREC_BITS;
	return div_lut[f];
}

static void get_shear_params(const s32 *mat, s64 *alpha, s64 *beta, s64 *gamma,
			     s64 *delta)
{
	short shift, y;
	long long gv, dv;

	if (mat[2] <= 0)
		return;
	*alpha = clamp_val(mat[2] - (1 << WARPEDMODEL_PREC_BITS), S16_MIN, S16_MAX);
	*beta = clamp_val(mat[3], S16_MIN, S16_MAX);
	y = resolve_divisor_32(abs(mat[2]), &shift) * (mat[2] < 0 ? -1 : 1);
	gv = ((long long)mat[4] * (1 << WARPEDMODEL_PREC_BITS)) * y;
	*gamma = clamp_val((int)AV1_DIV_ROUND_UP_POW2_SIGNED(gv, shift), S16_MIN, S16_MAX);
	dv = ((long long)mat[3] * mat[4]) * y;
	*delta = clamp_val(mat[5] - (int)AV1_DIV_ROUND_UP_POW2_SIGNED(dv, shift) -
			   (1 << WARPEDMODEL_PREC_BITS), S16_MIN, S16_MAX);
	*alpha = AV1_DIV_ROUND_UP_POW2_SIGNED(*alpha, WARP_PARAM_REDUCE_BITS) * (1 << WARP_PARAM_REDUCE_BITS);
	*beta = AV1_DIV_ROUND_UP_POW2_SIGNED(*beta, WARP_PARAM_REDUCE_BITS) * (1 << WARP_PARAM_REDUCE_BITS);
	*gamma = AV1_DIV_ROUND_UP_POW2_SIGNED(*gamma, WARP_PARAM_REDUCE_BITS) * (1 << WARP_PARAM_REDUCE_BITS);
	*delta = AV1_DIV_ROUND_UP_POW2_SIGNED(*delta, WARP_PARAM_REDUCE_BITS) * (1 << WARP_PARAM_REDUCE_BITS);
}

/*
 * 7 models x (6 x s32 params + 4 x s16 shear). The vendor writes the params
 * in natural order; the VPU981 swaps [2] and [3].
 */
static void set_global_model(struct h713_av1 *h)
{
	const struct v4l2_av1_global_motion *gm = &h->frame->global_motion;
	u8 *dst = h->b.global_model.cpu;
	int ref, i;

	memset(dst, 0, H713_AV1_GLOBAL_MODEL_SIZE);
	for (ref = 0; ref < GM_GLOBAL_MODELS_PER_FRAME; ref++) {
		const s32 *p = &gm->params[V4L2_AV1_REF_LAST_FRAME + ref][0];
		s64 alpha = 0, beta = 0, gamma = 0, delta = 0;

		for (i = 0; i < 6; i++) {
			put_unaligned_le32(p[i], dst);
			dst += 4;
		}
		if (gm->type[V4L2_AV1_REF_LAST_FRAME + ref] <= V4L2_AV1_WARP_MODEL_AFFINE)
			get_shear_params(p, &alpha, &beta, &gamma, &delta);
		put_unaligned_le16(alpha, dst);
		put_unaligned_le16(beta, dst + 2);
		put_unaligned_le16(gamma, dst + 4);
		put_unaligned_le16(delta, dst + 6);
		dst += 8;
	}
	WADDR(h, GLOBAL_MODEL_BASE, h->b.global_model.dma);
}

/* ---- tiles -------------------------------------------------------------- */

/*
 * Where the hardware's view of the tile data starts, as an offset into the
 * bitstream buffer: the first tile's payload, or with several tiles the
 * tile_size_bytes size field in front of it (every tile but the last carries
 * one) -- the vendor points the stream there.
 */
static u32 tile_data_start(struct h713_av1 *h)
{
	const struct v4l2_av1_tile_info *ti = &h->frame->tile_info;

	if (!h->tge)
		return 0;
	if (ti->tile_cols * ti->tile_rows > 1)
		return h->tge[0].tile_offset - ti->tile_size_bytes;
	return h->tge[0].tile_offset;
}

/*
 * The buffer holds {width_in_sbs, height_in_sbs} per tile, column-major
 * (tile_transpose), and at 0x100 one {start, end} pair per tile, also
 * column-major, in bytes from tile_data_start(). The tile*_stream_size
 * registers stay 0.
 */
static void set_tile_info(struct h713_av1 *h)
{
	const struct v4l2_av1_tile_info *ti = &h->frame->tile_info;
	int cu_y = ti->context_update_tile_id / ti->tile_cols;
	int cu_x = ti->context_update_tile_id % ti->tile_cols;
	u8 *dst = h->b.tile_info.cpu;
	u32 base = tile_data_start(h);
	int c, r;

	memset(dst, 0, H713_AV1_TILE_INFO_SIZE);
	for (c = 0; c < ti->tile_cols; c++)
		for (r = 0; r < ti->tile_rows; r++) {
			int id = r * ti->tile_cols + c;
			int slot = c * ti->tile_rows + r;
			u32 start = h->tge[id].tile_offset - base;
			u8 *pos = (u8 *)h->b.tile_info.cpu + 0x100 + 8 * slot;

			*dst++ = ti->width_in_sbs_minus_1[c] + 1;
			*dst++ = ti->height_in_sbs_minus_1[r] + 1;
			put_unaligned_le32(start, pos);
			put_unaligned_le32(start + h->tge[id].tile_size, pos + 4);
		}

	W(h, MULTICORE_EXPECT_CONTEXT_UPDATE, cu_x == 0);
	W(h, TILE_ENABLE, ti->tile_cols > 1 || ti->tile_rows > 1);
	for (c = 0; (1 << c) < ti->tile_cols; c++)
		;
	W(h, LOG2_TILE_COLS, c);	/* ceil(log2(tile_cols)) */
	W(h, AV1_TILE_COLS, ti->tile_cols);
	W(h, AV1_TILE_ROWS, ti->tile_rows);
	W(h, CONTEXT_UPDATE_TILE_ID, cu_x * ti->tile_rows + cu_y);
	W(h, TILE_TRANSPOSE, 1);
	if (ti->tile_cols > 1 || ti->tile_rows > 1)
		W(h, DEC_TILE_SIZE_MAG, ti->tile_size_bytes - 1);
	else
		W(h, DEC_TILE_SIZE_MAG, 3);
	WADDR(h, TILE_BASE, h->b.tile_info.dma);
}

/* ---- references --------------------------------------------------------- */

static void set_frame_sign_bias(struct h713_av1 *h)
{
	int i;

	if (!h->seq->order_hint_bits || IS_INTRA(h->frame->frame_type)) {
		for (i = 0; i < V4L2_AV1_TOTAL_REFS_PER_FRAME; i++)
			h->ref_frame_sign_bias[i] = 0;
		return;
	}
	for (i = 0; i < V4L2_AV1_TOTAL_REFS_PER_FRAME - 1; i++)
		if (get_frame_index(h, i) >= 0) {
			int rel = get_dist(h, get_order_hint(h, i), h->frame->order_hint);

			h->ref_frame_sign_bias[i + 1] = rel <= 0 ? 0 : 1;
		}
}

static const struct h713_av1_field ref_width[7] = {
	H713_AV1_REF0_WIDTH, H713_AV1_REF1_WIDTH, H713_AV1_REF2_WIDTH, H713_AV1_REF3_WIDTH,
	H713_AV1_REF4_WIDTH, H713_AV1_REF5_WIDTH, H713_AV1_REF6_WIDTH };
static const struct h713_av1_field ref_height[7] = {
	H713_AV1_REF0_HEIGHT, H713_AV1_REF1_HEIGHT, H713_AV1_REF2_HEIGHT, H713_AV1_REF3_HEIGHT,
	H713_AV1_REF4_HEIGHT, H713_AV1_REF5_HEIGHT, H713_AV1_REF6_HEIGHT };
static const struct h713_av1_field ref_hscale[7] = {
	H713_AV1_REF0_HOR_SCALE, H713_AV1_REF1_HOR_SCALE, H713_AV1_REF2_HOR_SCALE,
	H713_AV1_REF3_HOR_SCALE, H713_AV1_REF4_HOR_SCALE, H713_AV1_REF5_HOR_SCALE,
	H713_AV1_REF6_HOR_SCALE };
static const struct h713_av1_field ref_vscale[7] = {
	H713_AV1_REF0_VER_SCALE, H713_AV1_REF1_VER_SCALE, H713_AV1_REF2_VER_SCALE,
	H713_AV1_REF3_VER_SCALE, H713_AV1_REF4_VER_SCALE, H713_AV1_REF5_VER_SCALE,
	H713_AV1_REF6_VER_SCALE };
static const struct h713_av1_field ref_sign[7] = {
	H713_AV1_REF0_SIGN_BIAS, H713_AV1_REF1_SIGN_BIAS, H713_AV1_REF2_SIGN_BIAS,
	H713_AV1_REF3_SIGN_BIAS, H713_AV1_REF4_SIGN_BIAS, H713_AV1_REF5_SIGN_BIAS,
	H713_AV1_REF6_SIGN_BIAS };
static const struct h713_av1_field ref_gm[7] = {
	H713_AV1_REF0_GM_MODE, H713_AV1_REF1_GM_MODE, H713_AV1_REF2_GM_MODE,
	H713_AV1_REF3_GM_MODE, H713_AV1_REF4_GM_MODE, H713_AV1_REF5_GM_MODE,
	H713_AV1_REF6_GM_MODE };
static const struct h713_av1_field ref_lum[7] = {
	H713_AV1_REF0_LUM_BASE, H713_AV1_REF1_LUM_BASE, H713_AV1_REF2_LUM_BASE,
	H713_AV1_REF3_LUM_BASE, H713_AV1_REF4_LUM_BASE, H713_AV1_REF5_LUM_BASE,
	H713_AV1_REF6_LUM_BASE };
static const struct h713_av1_field ref_cb[7] = {
	H713_AV1_REF0_CB_BASE, H713_AV1_REF1_CB_BASE, H713_AV1_REF2_CB_BASE,
	H713_AV1_REF3_CB_BASE, H713_AV1_REF4_CB_BASE, H713_AV1_REF5_CB_BASE,
	H713_AV1_REF6_CB_BASE };
static const struct h713_av1_field ref_cr[7] = {
	H713_AV1_REF0_CR_BASE, H713_AV1_REF1_CR_BASE, H713_AV1_REF2_CR_BASE,
	H713_AV1_REF3_CR_BASE, H713_AV1_REF4_CR_BASE, H713_AV1_REF5_CR_BASE,
	H713_AV1_REF6_CR_BASE };

static bool set_ref(struct h713_av1 *h, int ref, int idx, int width, int height)
{
	int cur_w = h->frame->frame_width_minus_1 + 1;
	int cur_h = h->frame->frame_height_minus_1 + 1;
	int scale_w = ((width << AV1_REF_SCALE_SHIFT) + cur_w / 2) / cur_w;
	int scale_h = ((height << AV1_REF_SCALE_SHIFT) + cur_h / 2) / cur_h;
	const struct h713_av1_frame_bufs *fb = &h->refs[idx].bufs;

	h713_av1_set(h->regs, ref_height[ref], height);
	h713_av1_set(h->regs, ref_width[ref], width);
	/* the VPU981 names these crosswise; kept as it writes them */
	h713_av1_set(h->regs, ref_vscale[ref], scale_w);
	h713_av1_set(h->regs, ref_hscale[ref], scale_h);
	/* compressed reference: luma data, then one header for both chroma */
	h713_av1_set(h->regs, ref_lum[ref], lower_32_bits(fb->rec));
	h713_av1_set(h->regs, ref_cb[ref], lower_32_bits(fb->hdr));
	h713_av1_set(h->regs, ref_cr[ref], lower_32_bits(fb->hdr));

	return scale_w != (1 << AV1_REF_SCALE_SHIFT) || scale_h != (1 << AV1_REF_SCALE_SHIFT);
}

/* ---- segmentation ------------------------------------------------------- */

#define SEGF(n) H713_AV1_QUANT_SCALE_IDX_SEG##n, H713_AV1_FILT_LEVEL_DELTA0_SEG##n, \
	H713_AV1_FILT_LEVEL_DELTA1_SEG##n, H713_AV1_FILT_LEVEL_DELTA2_SEG##n, \
	H713_AV1_FILT_LEVEL_DELTA3_SEG##n, H713_AV1_REFPIC_SEG##n, \
	H713_AV1_SKIP_SEG##n, H713_AV1_GLOBAL_MV_SEG##n
static const struct h713_av1_field seg_fields[8][8] = {
	{ SEGF(0) }, { SEGF(1) }, { SEGF(2) }, { SEGF(3) },
	{ SEGF(4) }, { SEGF(5) }, { SEGF(6) }, { SEGF(7) },
};

static void set_segmentation(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	const struct v4l2_av1_segmentation *seg = &f->segmentation;
	u32 segval[V4L2_AV1_MAX_SEGMENTS][V4L2_AV1_SEG_LVL_MAX] = { { 0 } };
	u8 segsign = 0, preskip = 0, last_active = 0;
	int i, j;

	W(h, USE_TEMPORAL3_MVS, 0);
	if ((seg->flags & V4L2_AV1_SEGMENTATION_FLAG_ENABLED) &&
	    f->primary_ref_frame < V4L2_AV1_REFS_PER_FRAME) {
		int idx = get_frame_index(h, f->primary_ref_frame);

		if (idx >= 0) {
			/* the previous segment map rides in the primary ref's MV buffer */
			WADDR(h, TEMPORAL3_READ_BASE, h->refs[idx].bufs.mv);
			W(h, USE_TEMPORAL3_MVS, 1);
		}
	}

	W(h, SEGMENT_TEMP_UPD_E, !!(seg->flags & V4L2_AV1_SEGMENTATION_FLAG_TEMPORAL_UPDATE));
	W(h, SEGMENT_UPD_E, !!(seg->flags & V4L2_AV1_SEGMENTATION_FLAG_UPDATE_MAP));
	W(h, SEGMENT_E, !!(seg->flags & V4L2_AV1_SEGMENTATION_FLAG_ENABLED));
	W(h, ERROR_RESILIENT, !!(f->flags & V4L2_AV1_FRAME_FLAG_ERROR_RESILIENT_MODE));
	if (IS_INTRA(f->frame_type) || (f->flags & V4L2_AV1_FRAME_FLAG_ERROR_RESILIENT_MODE))
		W(h, USE_TEMPORAL3_MVS, 0);

	if (seg->flags & V4L2_AV1_SEGMENTATION_FLAG_ENABLED) {
		for (i = 0; i < V4L2_AV1_MAX_SEGMENTS; i++) {
			u8 en = seg->feature_enabled[i];
			const s16 *d = seg->feature_data[i];

			if (en & V4L2_AV1_SEGMENT_FEATURE_ENABLED(V4L2_AV1_SEG_LVL_ALT_Q)) {
				segval[i][V4L2_AV1_SEG_LVL_ALT_Q] = clamp(abs(d[V4L2_AV1_SEG_LVL_ALT_Q]), 0, 255);
				segsign |= (d[V4L2_AV1_SEG_LVL_ALT_Q] < 0) << i;
			}
			for (j = V4L2_AV1_SEG_LVL_ALT_LF_Y_V; j <= V4L2_AV1_SEG_LVL_ALT_LF_V; j++)
				if (en & V4L2_AV1_SEGMENT_FEATURE_ENABLED(j))
					segval[i][j] = clamp(abs(d[j]), -63, 63);
			if (f->frame_type && (en & V4L2_AV1_SEGMENT_FEATURE_ENABLED(V4L2_AV1_SEG_LVL_REF_FRAME)))
				segval[i][V4L2_AV1_SEG_LVL_REF_FRAME]++;
			if (en & V4L2_AV1_SEGMENT_FEATURE_ENABLED(V4L2_AV1_SEG_LVL_REF_SKIP))
				segval[i][V4L2_AV1_SEG_LVL_REF_SKIP] = 1;
			if (en & V4L2_AV1_SEGMENT_FEATURE_ENABLED(V4L2_AV1_SEG_LVL_REF_GLOBALMV))
				segval[i][V4L2_AV1_SEG_LVL_REF_GLOBALMV] = 1;
		}
	}
	for (i = 0; i < V4L2_AV1_MAX_SEGMENTS; i++)
		for (j = 0; j < V4L2_AV1_SEG_LVL_MAX; j++)
			if (seg->feature_enabled[i] & V4L2_AV1_SEGMENT_FEATURE_ENABLED(j)) {
				preskip |= j >= V4L2_AV1_SEG_LVL_REF_FRAME;
				last_active = max_t(u8, i, last_active);
			}

	W(h, LAST_ACTIVE_SEG, last_active);
	W(h, PRESKIP_SEGID, preskip);
	W(h, SEG_QUANT_SIGN, segsign);
	for (i = 0; i < V4L2_AV1_MAX_SEGMENTS; i++)
		for (j = 0; j < V4L2_AV1_SEG_LVL_MAX; j++)
			h713_av1_set(h->regs, seg_fields[i][j], segval[i][j]);
}

static bool is_lossless(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	const struct v4l2_av1_quantization *q = &f->quantization;
	int i;

	for (i = 0; i < V4L2_AV1_MAX_SEGMENTS; i++) {
		int qi = q->base_q_idx;

		if (f->segmentation.feature_enabled[i] &
		    V4L2_AV1_SEGMENT_FEATURE_ENABLED(V4L2_AV1_SEG_LVL_ALT_Q))
			qi += f->segmentation.feature_data[i][V4L2_AV1_SEG_LVL_ALT_Q];
		qi = clamp(qi, 0, 255);
		if (qi || q->delta_q_y_dc || q->delta_q_u_dc || q->delta_q_u_ac ||
		    q->delta_q_v_dc || q->delta_q_v_ac)
			return false;
	}
	return true;
}

/* ---- loop filter -------------------------------------------------------- */

static const struct h713_av1_field filt_ref_delta[V4L2_AV1_TOTAL_REFS_PER_FRAME] = {
	H713_AV1_FILT_REF0_DELTA, H713_AV1_FILT_REF1_DELTA, H713_AV1_FILT_REF2_DELTA,
	H713_AV1_FILT_REF3_DELTA, H713_AV1_FILT_REF4_DELTA, H713_AV1_FILT_REF5_DELTA,
	H713_AV1_FILT_REF6_DELTA, H713_AV1_FILT_REF7_DELTA,
};

/*
 * Levels 2/3 (U, V) and the deltas the vendor carries over from earlier
 * frames when the bitstream does not code them; they are don't-cares there
 * and this writes what the frame header says.
 */
static void set_loopfilter(struct h713_av1 *h)
{
	const struct v4l2_av1_loop_filter *lf = &h->frame->loop_filter;
	int i;

	if (lf->flags & V4L2_AV1_LOOP_FILTER_FLAG_DELTA_ENABLED) {
		for (i = 0; i < V4L2_AV1_TOTAL_REFS_PER_FRAME; i++)
			h713_av1_set(h->regs, filt_ref_delta[i], lf->ref_deltas[i]);
		W(h, FILT_MODE0_DELTA, lf->mode_deltas[0]);
		W(h, FILT_MODE1_DELTA, lf->mode_deltas[1]);
	}

	W(h, FILTERING_DIS, lf->level[0] == 0 && lf->level[1] == 0);
	W(h, FILT_LEVEL_BASE_GT32, lf->level[0] > 32);
	W(h, FILTER_SHARPNESS, lf->sharpness);
	W(h, BASE_LF_LEVEL_0, lf->level[0]);
	W(h, BASE_LF_LEVEL_1, lf->level[1]);
	W(h, BASE_LF_LEVEL_2, lf->level[2]);
	W(h, BASE_LF_LEVEL_3, lf->level[3]);
}

/* ---- probabilities ------------------------------------------------------ */

static void get_cdfs(struct h713_av1_cdf *c, u32 ref_idx)
{
	c->cdfs = &c->last[ref_idx];
	c->cdfs_ndvc = &c->last_ndvc[ref_idx];
}

static void store_cdfs(struct h713_av1_cdf *c, u32 refresh)
{
	int i;

	for (i = 0; i < H713_AV1_NUM_REF_FRAMES; i++)
		if ((refresh & (1 << i)) && &c->last[i] != c->cdfs) {
			c->last[i] = *c->cdfs;
			c->last_ndvc[i] = *c->cdfs_ndvc;
		}
}

static void set_prob(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	struct h713_av1_cdf *c = h->cdf;

	if ((f->flags & V4L2_AV1_FRAME_FLAG_ERROR_RESILIENT_MODE) ||
	    IS_INTRA(f->frame_type) || f->primary_ref_frame == AV1_PRIMARY_REF_NONE) {
		c->cdfs = &c->default_cdfs;
		c->cdfs_ndvc = &c->default_cdfs_ndvc;
		rockchip_av1_default_coeff_probs(f->quantization.base_q_idx, c->cdfs);
	} else {
		get_cdfs(c, f->ref_frame_idx[f->primary_ref_frame]);
	}
	store_cdfs(c, f->refresh_frame_flags);

	memcpy(h->b.prob.cpu, c->cdfs, sizeof(struct av1cdfs));
	if (IS_INTRA(f->frame_type))
		memcpy((u8 *)h->b.prob.cpu + offsetof(struct av1cdfs, mv_cdf),
		       c->cdfs_ndvc, sizeof(struct mvcdfs));

	WADDR(h, PROB_TAB_OUT_BASE, h->b.prob_out.dma);
	WADDR(h, PROB_TAB_BASE, h->b.prob.dma);
}

static void update_prob(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	struct h713_av1_cdf *c = h->cdf;
	struct av1cdfs *out = h->b.prob_out.cpu;
	int i;

	if (f->flags & V4L2_AV1_FRAME_FLAG_DISABLE_FRAME_END_UPDATE_CDF)
		return;
	for (i = 0; i < H713_AV1_NUM_REF_FRAMES; i++)
		if (f->refresh_frame_flags & (1 << i)) {
			struct mvcdfs mv = c->cdfs->mv_cdf;

			get_cdfs(c, i);
			*c->cdfs = *out;
			if (IS_INTRA(f->frame_type)) {
				c->cdfs->mv_cdf = mv;
				*c->cdfs_ndvc = out->mv_cdf;
			}
			store_cdfs(c, f->refresh_frame_flags);
			break;
		}
}

/*
 * ---- film grain ----
 * The VPU981's 0x3300-byte buffer, except that the 32x32 Cb and Cr grain
 * blocks are planar (Cb, then Cr) where the VPU981 interleaves them.
 */

struct h713_av1_film_grain {
	u8 scaling_lut_y[256];
	u8 scaling_lut_cb[256];
	u8 scaling_lut_cr[256];
	s16 cropped_luma_grain_block[4096];
	s16 cropped_cb_grain_block[1024];
	s16 cropped_cr_grain_block[1024];
};

static void init_scaling_function(const u8 *values, const u8 *scaling,
				  u8 num_points, u8 *lut)
{
	int i, point;

	if (!num_points) {
		memset(lut, 0, 256);
		return;
	}
	for (point = 0; point < num_points - 1; point++) {
		int x;
		s32 dy = scaling[point + 1] - scaling[point];
		s32 dx = values[point + 1] - values[point];
		s64 delta = dx ? dy * ((65536 + (dx >> 1)) / dx) : 0;

		for (x = 0; x < dx; x++)
			lut[values[point] + x] = scaling[point] + (s32)((x * delta + 32768) >> 16);
	}
	for (i = values[num_points - 1]; i < 256; i++)
		lut[i] = scaling[num_points - 1];
}

static void set_fgs(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_film_grain *fg = h->film_grain;
	struct h713_av1_film_grain *mem = h->b.film_grain.cpu;
	s32 (*ar_y)[24], (*ar_cb)[25], (*ar_cr)[25];
	s32 (*luma)[73][82], (*cb)[38][44], (*cr)[38][44];
	s32 lag, shift, gss, bitdepth, center, gmin, gmax;
	int i, j;

	W(h, APPLY_GRAIN, 0);
	if (!fg || !(fg->flags & V4L2_AV1_FILM_GRAIN_FLAG_APPLY_GRAIN)) {
		W(h, NUM_Y_POINTS_B, 0); W(h, NUM_CB_POINTS_B, 0); W(h, NUM_CR_POINTS_B, 0);
		W(h, SCALING_SHIFT, 0); W(h, CB_MULT, 0); W(h, CB_LUMA_MULT, 0);
		W(h, CB_OFFSET, 0); W(h, CR_MULT, 0); W(h, CR_LUMA_MULT, 0);
		W(h, CR_OFFSET, 0); W(h, OVERLAP_FLAG, 0);
		W(h, CLIP_TO_RESTRICTED_RANGE, 0); W(h, CHROMA_SCALING_FROM_LUMA, 0);
		W(h, RANDOM_SEED, 0);
		W(h, FILM_GRAIN_BASE, 0);
		return;
	}

	ar_y = kzalloc(sizeof(*ar_y), GFP_KERNEL);
	ar_cb = kzalloc(sizeof(*ar_cb), GFP_KERNEL);
	ar_cr = kzalloc(sizeof(*ar_cr), GFP_KERNEL);
	luma = kzalloc(sizeof(*luma), GFP_KERNEL);
	cb = kzalloc(sizeof(*cb), GFP_KERNEL);
	cr = kzalloc(sizeof(*cr), GFP_KERNEL);
	if (!ar_y || !ar_cb || !ar_cr || !luma || !cb || !cr)
		goto out;

	W(h, APPLY_GRAIN, 1);
	W(h, NUM_Y_POINTS_B, fg->num_y_points > 0);
	W(h, NUM_CB_POINTS_B, fg->num_cb_points > 0);
	W(h, NUM_CR_POINTS_B, fg->num_cr_points > 0);
	W(h, SCALING_SHIFT, fg->grain_scaling_minus_8 + 8);
	if (!(fg->flags & V4L2_AV1_FILM_GRAIN_FLAG_CHROMA_SCALING_FROM_LUMA)) {
		W(h, CB_MULT, fg->cb_mult - 128);
		W(h, CB_LUMA_MULT, fg->cb_luma_mult - 128);
		W(h, CB_OFFSET, fg->cb_offset - 256);
		W(h, CR_MULT, fg->cr_mult - 128);
		W(h, CR_LUMA_MULT, fg->cr_luma_mult - 128);
		W(h, CR_OFFSET, fg->cr_offset - 256);
	} else {
		W(h, CB_MULT, 0); W(h, CB_LUMA_MULT, 0); W(h, CB_OFFSET, 0);
		W(h, CR_MULT, 0); W(h, CR_LUMA_MULT, 0); W(h, CR_OFFSET, 0);
	}
	W(h, OVERLAP_FLAG, !!(fg->flags & V4L2_AV1_FILM_GRAIN_FLAG_OVERLAP));
	W(h, CLIP_TO_RESTRICTED_RANGE, !!(fg->flags & V4L2_AV1_FILM_GRAIN_FLAG_CLIP_TO_RESTRICTED_RANGE));
	W(h, CHROMA_SCALING_FROM_LUMA, !!(fg->flags & V4L2_AV1_FILM_GRAIN_FLAG_CHROMA_SCALING_FROM_LUMA));
	W(h, RANDOM_SEED, fg->grain_seed);

	init_scaling_function(fg->point_y_value, fg->point_y_scaling, fg->num_y_points, mem->scaling_lut_y);
	if (fg->flags & V4L2_AV1_FILM_GRAIN_FLAG_CHROMA_SCALING_FROM_LUMA) {
		memcpy(mem->scaling_lut_cb, mem->scaling_lut_y, 256);
		memcpy(mem->scaling_lut_cr, mem->scaling_lut_y, 256);
	} else {
		init_scaling_function(fg->point_cb_value, fg->point_cb_scaling, fg->num_cb_points, mem->scaling_lut_cb);
		init_scaling_function(fg->point_cr_value, fg->point_cr_scaling, fg->num_cr_points, mem->scaling_lut_cr);
	}

	for (i = 0; i < V4L2_AV1_AR_COEFFS_SIZE; i++) {
		if (i < 24)
			(*ar_y)[i] = fg->ar_coeffs_y_plus_128[i] - 128;
		(*ar_cb)[i] = fg->ar_coeffs_cb_plus_128[i] - 128;
		(*ar_cr)[i] = fg->ar_coeffs_cr_plus_128[i] - 128;
	}
	lag = fg->ar_coeff_lag;
	shift = fg->ar_coeff_shift_minus_6 + 6;
	gss = fg->grain_scale_shift;
	bitdepth = h->bit_depth;
	center = 128 << (bitdepth - 8);
	gmin = 0 - center;
	gmax = (256 << (bitdepth - 8)) - 1 - center;

	rockchip_av1_generate_luma_grain_block(luma, bitdepth, fg->num_y_points, gss,
					       lag, ar_y, shift, gmin, gmax, fg->grain_seed);
	rockchip_av1_generate_chroma_grain_block(luma, cb, cr, bitdepth,
						 fg->num_y_points, fg->num_cb_points,
						 fg->num_cr_points, gss, lag, ar_cb,
						 ar_cr, shift, gmin, gmax,
						 !!(fg->flags & V4L2_AV1_FILM_GRAIN_FLAG_CHROMA_SCALING_FROM_LUMA),
						 fg->grain_seed);

	for (i = 0; i < 64; i++)
		for (j = 0; j < 64; j++)
			mem->cropped_luma_grain_block[i * 64 + j] = (*luma)[i + 9][j + 9];
	for (i = 0; i < 32; i++)
		for (j = 0; j < 32; j++) {
			mem->cropped_cb_grain_block[i * 32 + j] = (*cb)[i + 6][j + 6];
			mem->cropped_cr_grain_block[i * 32 + j] = (*cr)[i + 6][j + 6];
		}
	WADDR(h, FILM_GRAIN_BASE, h->b.film_grain.dma);
out:
	kfree(ar_y); kfree(ar_cb); kfree(ar_cr);
	kfree(luma); kfree(cb); kfree(cr);
}

/* ---- CDEF, loop restoration, superres, dimensions ----------------------- */

static void set_cdef(struct h713_av1 *h)
{
	const struct v4l2_av1_cdef *cdef = &h->frame->cdef;
	u32 lp = 0, cp = 0;
	u16 ls = 0, cs = 0;
	int i;

	W(h, ENABLE_CDEF, !(cdef->bits == 0 && cdef->damping_minus_3 == 0 &&
			    cdef->y_pri_strength[0] == 0 && cdef->y_sec_strength[0] == 0 &&
			    cdef->uv_pri_strength[0] == 0 && cdef->uv_sec_strength[0] == 0));
	W(h, CDEF_BITS, cdef->bits);
	W(h, CDEF_DAMPING, cdef->damping_minus_3);
	for (i = 0; i < (1 << cdef->bits); i++) {
		lp |= cdef->y_pri_strength[i] << (i * 4);
		ls |= (cdef->y_sec_strength[i] == 4 ? 3 : cdef->y_sec_strength[i]) << (i * 2);
		cp |= cdef->uv_pri_strength[i] << (i * 4);
		cs |= (cdef->uv_sec_strength[i] == 4 ? 3 : cdef->uv_sec_strength[i]) << (i * 2);
	}
	W(h, CDEF_LUMA_PRIMARY_STRENGTH, lp);
	W(h, CDEF_LUMA_SECONDARY_STRENGTH, ls);
	W(h, CDEF_CHROMA_PRIMARY_STRENGTH, cp);
	W(h, CDEF_CHROMA_SECONDARY_STRENGTH, cs);
}

static void set_lr(struct h713_av1 *h)
{
	const struct v4l2_av1_loop_restoration *lr = &h->frame->loop_restoration;
	u8 size[V4L2_AV1_NUM_PLANES_MAX] = { 3, 3, 3 };
	u16 type = 0, unit = 0;
	int i;

	if (lr->flags & V4L2_AV1_LOOP_RESTORATION_FLAG_USES_LR) {
		size[0] = 1 + lr->lr_unit_shift;
		size[1] = size[2] = 1 + lr->lr_unit_shift - lr->lr_uv_shift;
	}
	for (i = 0; i < V4L2_AV1_NUM_PLANES_MAX; i++) {
		type |= lr->frame_restoration_type[i] << (i * 2);
		unit |= size[i] << (i * 2);
	}
	W(h, LR_TYPE, type);
	W(h, LR_UNIT_SIZE, unit);
}

static void set_superres(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	u8 denom = SCALE_NUMERATOR;
	int step_l = RS_SCALE_SUBPEL_BITS, step_c = RS_SCALE_SUBPEL_BITS;
	int init_l = 0, init_c = 0, scaled = 0;
	int min_w = min_t(u32, 16, f->upscaled_width);
	int width;

	if (f->flags & V4L2_AV1_FRAME_FLAG_USE_SUPERRES)
		denom = f->superres_denom;
	if (denom > SCALE_NUMERATOR) {
		width = (f->upscaled_width * SCALE_NUMERATOR + denom / 2) / denom;
		if (width < min_w)
			width = min_w;
		if (width != f->upscaled_width) {
			int up_l = f->upscaled_width, down_l = width;
			int down_c = (down_l + 1) >> 1, up_c = (up_l + 1) >> 1;
			int sl = ((down_l << RS_SCALE_SUBPEL_BITS) + up_l / 2) / up_l;
			int sc = ((down_c << RS_SCALE_SUBPEL_BITS) + up_c / 2) / up_c;
			int el = up_l * sl - (down_l << RS_SCALE_SUBPEL_BITS);
			int ec = up_c * sc - (down_c << RS_SCALE_SUBPEL_BITS);

			scaled = 1;
			init_l = ((-((up_l - down_l) << (RS_SCALE_SUBPEL_BITS - 1)) + up_l / 2) / up_l +
				  (1 << (RS_SCALE_EXTRA_BITS - 1)) - el / 2) & RS_SCALE_SUBPEL_MASK;
			init_c = ((-((up_c - down_c) << (RS_SCALE_SUBPEL_BITS - 1)) + up_c / 2) / up_c +
				  (1 << (RS_SCALE_EXTRA_BITS - 1)) - ec / 2) & RS_SCALE_SUBPEL_MASK;
			step_l = sl;
			step_c = sc;
		}
	}
	W(h, SUPERRES_PIC_WIDTH, f->upscaled_width);
	W(h, SCALE_DENOM_MINUS9, (f->flags & V4L2_AV1_FRAME_FLAG_USE_SUPERRES) ?
				 f->superres_denom - SUPERRES_SCALE_DENOMINATOR_MIN :
				 f->superres_denom);
	W(h, SUPERRES_LUMA_STEP, step_l);
	W(h, SUPERRES_CHROMA_STEP, step_c);
	W(h, SUPERRES_INIT_LUMA_SUBPEL_X, init_l);
	W(h, SUPERRES_INIT_CHROMA_SUBPEL_X, init_c);
	W(h, SUPERRES_IS_SCALED, scaled);
}

static void set_picture_dimensions(struct h713_av1 *h)
{
	int w = h->frame->frame_width_minus_1 + 1;
	int ht = h->frame->frame_height_minus_1 + 1;

	/* pixels, not 8x8 blocks as on the VPU981 (vendor: 0x500 x 0x2d0) */
	W(h, PIC_WIDTH, w);
	W(h, PIC_HEIGHT, ht);
	W(h, PIC_WIDTH_PAD, ALIGN(w, 8) - w);
	W(h, PIC_HEIGHT_PAD, ALIGN(ht, 8) - ht);
	W(h, SLICE_HEIGHT, ht);
	W(h, PP_PIC_WIDTH, w);
	W(h, PP_PIC_HEIGHT, ht);
	set_superres(h);
}

/* ---- motion-field projection (as VPU981) -------------------------------- */

static const struct h713_av1_field mf_off[3][7] = {
	{ H713_AV1_MF1_LAST_OFFSET, H713_AV1_MF1_LAST2_OFFSET, H713_AV1_MF1_LAST3_OFFSET,
	  H713_AV1_MF1_GOLDEN_OFFSET, H713_AV1_MF1_BWDREF_OFFSET, H713_AV1_MF1_ALTREF2_OFFSET,
	  H713_AV1_MF1_ALTREF_OFFSET },
	{ H713_AV1_MF2_LAST_OFFSET, H713_AV1_MF2_LAST2_OFFSET, H713_AV1_MF2_LAST3_OFFSET,
	  H713_AV1_MF2_GOLDEN_OFFSET, H713_AV1_MF2_BWDREF_OFFSET, H713_AV1_MF2_ALTREF2_OFFSET,
	  H713_AV1_MF2_ALTREF_OFFSET },
	{ H713_AV1_MF3_LAST_OFFSET, H713_AV1_MF3_LAST2_OFFSET, H713_AV1_MF3_LAST3_OFFSET,
	  H713_AV1_MF3_GOLDEN_OFFSET, H713_AV1_MF3_BWDREF_OFFSET, H713_AV1_MF3_ALTREF2_OFFSET,
	  H713_AV1_MF3_ALTREF_OFFSET },
};
static const struct h713_av1_field cur_off[7] = {
	H713_AV1_CUR_LAST_OFFSET, H713_AV1_CUR_LAST2_OFFSET, H713_AV1_CUR_LAST3_OFFSET,
	H713_AV1_CUR_GOLDEN_OFFSET, H713_AV1_CUR_BWDREF_OFFSET, H713_AV1_CUR_ALTREF2_OFFSET,
	H713_AV1_CUR_ALTREF_OFFSET };
static const struct h713_av1_field cur_roff[7] = {
	H713_AV1_CUR_LAST_ROFFSET, H713_AV1_CUR_LAST2_ROFFSET, H713_AV1_CUR_LAST3_ROFFSET,
	H713_AV1_CUR_GOLDEN_ROFFSET, H713_AV1_CUR_BWDREF_ROFFSET, H713_AV1_CUR_ALTREF2_ROFFSET,
	H713_AV1_CUR_ALTREF_ROFFSET };
static const struct h713_av1_field use_tmv[3] = {
	H713_AV1_USE_TEMPORAL0_MVS, H713_AV1_USE_TEMPORAL1_MVS, H713_AV1_USE_TEMPORAL2_MVS };
/* the MVs each projection reads: mf1..3 -> temporal, temporal1, temporal2 */
static const struct h713_av1_field tmv_base[3] = {
	H713_AV1_TEMPORAL_READ_BASE, H713_AV1_TEMPORAL1_READ_BASE, H713_AV1_TEMPORAL2_READ_BASE };
static const struct h713_av1_field mf_type[3] = {
	H713_AV1_MF1_TYPE, H713_AV1_MF2_TYPE, H713_AV1_MF3_TYPE };

static bool mf_candidate(struct h713_av1 *h, int ref, int cur_mi_cols, int cur_mi_rows)
{
	int idx = get_frame_index(h, ref);

	return idx >= 0 && h->refs[idx].mi_cols == cur_mi_cols &&
	       h->refs[idx].mi_rows == cur_mi_rows && !IS_INTRA(h->refs[idx].frame_type);
}

static void set_other_frames(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	bool use_ref_mvs = !!(f->flags & V4L2_AV1_FRAME_FLAG_USE_REF_FRAME_MVS);
	int cur_off_hint = f->order_hint;
	int alt_o = get_order_hint(h, ALT_BUF_IDX), gld_o = get_order_hint(h, GLD_BUF_IDX);
	int bwd_o = get_order_hint(h, BWD_BUF_IDX), alt2_o = get_order_hint(h, ALT2_BUF_IDX);
	int cur_mi_cols = DIV_ROUND_UP(f->frame_width_minus_1 + 1, 8);
	int cur_mi_rows = DIV_ROUND_UP(f->frame_height_minus_1 + 1, 8);
	int sel[3] = { 0, 0, 0 }, types[3] = { 0, 0, 0 };
	int co[7], cro[7];
	int stamp = 2, n = 0, rf, idx, k;

	idx = get_frame_index(h, LST_BUF_IDX);
	if (idx >= 0) {
		bool overlay = h->refs[idx].order_hints[V4L2_AV1_REF_ALTREF_FRAME] == gld_o;

		if (!overlay && mf_candidate(h, LST_BUF_IDX, cur_mi_cols, cur_mi_rows)) {
			types[n] = V4L2_AV1_REF_LAST_FRAME;
			sel[n++] = LST_BUF_IDX;
		}
		stamp--;
	}
	if (get_dist(h, bwd_o, cur_off_hint) > 0 &&
	    mf_candidate(h, BWD_BUF_IDX, cur_mi_cols, cur_mi_rows)) {
		types[n] = V4L2_AV1_REF_BWDREF_FRAME;
		sel[n++] = BWD_BUF_IDX;
		stamp--;
	}
	if (get_dist(h, alt2_o, cur_off_hint) > 0 &&
	    mf_candidate(h, ALT2_BUF_IDX, cur_mi_cols, cur_mi_rows)) {
		types[n] = V4L2_AV1_REF_ALTREF2_FRAME;
		sel[n++] = ALT2_BUF_IDX;
		stamp--;
	}
	if (get_dist(h, alt_o, cur_off_hint) > 0 && stamp >= 0 &&
	    mf_candidate(h, ALT_BUF_IDX, cur_mi_cols, cur_mi_rows)) {
		types[n] = V4L2_AV1_REF_ALTREF_FRAME;
		sel[n++] = ALT_BUF_IDX;
		stamp--;
	}
	if (stamp >= 0 && n < 3 && mf_candidate(h, LST2_BUF_IDX, cur_mi_cols, cur_mi_rows)) {
		types[n] = V4L2_AV1_REF_LAST2_FRAME;
		sel[n++] = LST2_BUF_IDX;
		stamp--;
	}

	for (rf = 0; rf < V4L2_AV1_TOTAL_REFS_PER_FRAME - 1; rf++) {
		if (get_frame_index(h, rf) >= 0) {
			int oh = get_order_hint(h, rf);

			co[rf] = get_dist(h, cur_off_hint, oh);
			cro[rf] = get_dist(h, oh, cur_off_hint);
		} else {
			co[rf] = cro[rf] = 0;
		}
	}

	for (k = 0; k < 3; k++) {
		h713_av1_set(h->regs, use_tmv[k], 0);
		for (rf = 0; rf < 7; rf++)
			h713_av1_set(h->regs, mf_off[k][rf], 0);
		if (use_ref_mvs && n > k &&
		    co[types[k] - V4L2_AV1_REF_LAST_FRAME] <= MAX_FRAME_DISTANCE &&
		    co[types[k] - V4L2_AV1_REF_LAST_FRAME] >= -MAX_FRAME_DISTANCE) {
			int oh = get_order_hint(h, sel[k]);
			int ri = get_frame_index(h, sel[k]);
			u32 *ohs = h->refs[ri].order_hints;

			h713_av1_set(h->regs, use_tmv[k], 1);
			h713_av1_set(h->regs, tmv_base[k], lower_32_bits(h->refs[ri].bufs.mv));
			for (rf = 0; rf < 7; rf++)
				h713_av1_set(h->regs, mf_off[k][rf],
					     get_dist(h, oh, ohs[V4L2_AV1_REF_LAST_FRAME + rf]));
		}
		/* the AV1 reference type itself; the VPU981 writes it minus one */
		h713_av1_set(h->regs, mf_type[k], types[k]);
	}
	for (rf = 0; rf < 7; rf++) {
		h713_av1_set(h->regs, cur_off[rf], co[rf]);
		h713_av1_set(h->regs, cur_roff[rf], cro[rf]);
	}
}

/*
 * The reference decompressor. References are stored compressed (luma, Cb and
 * Cr streams back to back in the frame's rec buffer, one header buffer), and
 * the core fetches them through a separate decompressor whose configuration
 * it reads from DRAM at pdec_config_base: PdecSwRegs, 496 bytes, one "input"
 * per AV1 reference (in0 = LAST .. in6 = ALTREF). It mirrors the vendor's
 * AsicRefDecompressionSetup (MapPdecGen/Dim/Entropy/BaseSwRegs,
 * SetupPdecBaseRegs, WritePdecRegsToDram). Intra frames get none.
 */
#define PDEC_ENT(i, p) { H713_PDEC_IN##i##_PLANE##p##_ENTROPY0, \
	H713_PDEC_IN##i##_PLANE##p##_ENTROPY1, H713_PDEC_IN##i##_PLANE##p##_ENTROPY2, \
	H713_PDEC_IN##i##_PLANE##p##_ENTROPY3, H713_PDEC_IN##i##_PLANE##p##_ENTROPY4, \
	H713_PDEC_IN##i##_PLANE##p##_ENTROPY5, H713_PDEC_IN##i##_PLANE##p##_ENTROPY6, \
	H713_PDEC_IN##i##_PLANE##p##_ENTROPY7 }
#define PDEC_PLANES(i, f) { H713_PDEC_IN##i##_PLANE0_##f, \
	H713_PDEC_IN##i##_PLANE1_##f, H713_PDEC_IN##i##_PLANE2_##f }
#define PDEC_IN(i) { \
	.strm = PDEC_PLANES(i, STRM_BASE), .hdr = PDEC_PLANES(i, HDR_BASE), \
	.w = PDEC_PLANES(i, WIDTH), .h = PDEC_PLANES(i, HEIGHT), \
	.ent = { PDEC_ENT(i, 0), PDEC_ENT(i, 1), PDEC_ENT(i, 2) } }

static const struct {
	struct h713_av1_field strm[3], hdr[3], w[3], h[3], ent[3][8];
} pdec_in[7] = {
	PDEC_IN(0), PDEC_IN(1), PDEC_IN(2), PDEC_IN(3),
	PDEC_IN(4), PDEC_IN(5), PDEC_IN(6),
};

/* Worst-case compressed bytes per 64x4 luma / 32x4 chroma block (GetMaxCBSizeBytes). */
#define PDEC_CB_LUMA_BYTES	384
#define PDEC_CB_CHROMA_BYTES	192

static void set_pdec(struct h713_av1 *h, const int *idx)
{
	u32 p[H713_PDEC_SIZE / 4] = { 0 };
	int i, j;

	/*
	 * Constants outside any printed member: the header/cache/bit-depth
	 * config bits (bits 0-9) and sw_cb_size = {0, 4, 4} (bits 3780-3788).
	 */
	p[0] |= 0x3aa;
	p[3785 / 32] |= BIT(3785 % 32);
	p[3788 / 32] |= BIT(3788 % 32);

	/* MapPdecGenSwRegs: fixed routing, plus three bits of the main image */
	h713_av1_set(p, H713_PDEC_PDEC_E, 1);
	h713_av1_set(p, H713_PDEC_DEDICATED_PDEC_E, !h713_av1_get(h->regs, H713_AV1_MODE_DEC));
	h713_av1_set(p, H713_PDEC_CB_HEADER_DRAM_ID, 6);
	h713_av1_set(p, H713_PDEC_CB_STRM_DRAM_ID, 2);
	h713_av1_set(p, H713_PDEC_CB_PLANE_MODE, 1);
	h713_av1_set(p, H713_PDEC_CB_HEADER_DRAM_SEL, 1);
	h713_av1_set(p, H713_PDEC_BIT_DEPTH, h713_av1_get(h->regs, H713_AV1_BITDEPTH));
	h713_av1_set(p, H713_PDEC_FLUSH_ALL, h713_av1_get(h->regs, H713_AV1_MODE_DEC));
	h713_av1_set(p, H713_PDEC_CHROMA_SKIP, h713_av1_get(h->regs, H713_AV1_CODING_MODE) == 2);

	for (i = 0; i < 7; i++) {
		const struct h713_av1_ref *r = &h->refs[idx[i]];
		u32 w = h713_av1_get(h->regs, ref_width[i]);
		u32 ht = h713_av1_get(h->regs, ref_height[i]);
		u32 pw[3], ph[3], base;

		/* MapPdecDimSwRegs: 8-aligned luma, chroma width 4-aligned */
		pw[0] = (w + 7) & 0x3ff8;
		ph[0] = (ht + 7) & ~7u;
		pw[1] = pw[2] = ((w + 7) >> 1) & 0x1ffc;
		ph[1] = ph[2] = ph[0] >> 1;

		/* SetupPdecBaseRegs: the three planes' streams back to back */
		base = lower_32_bits(r->bufs.rec);
		for (j = 0; j < 3; j++) {
			h713_av1_set(p, pdec_in[i].w[j], pw[j]);
			h713_av1_set(p, pdec_in[i].h[j], ph[j]);
			h713_av1_set(p, pdec_in[i].strm[j], base);
			/*
			 * One header buffer for all planes. The vendor fills
			 * plane 1/2 before this frame's plane 0, so its copies
			 * lag a frame (0 on frame 1) and evidently go unused.
			 */
			h713_av1_set(p, pdec_in[i].hdr[j], lower_32_bits(r->bufs.hdr));
			if (j == 0)
				base += DIV_ROUND_UP(pw[0], 64) * DIV_ROUND_UP(ph[0], 4) *
					PDEC_CB_LUMA_BYTES;
			else
				base += DIV_ROUND_UP(pw[j], 32) * DIV_ROUND_UP(ph[j], 4) *
					PDEC_CB_CHROMA_BYTES;
		}

		/* MapPdecEntropySwRegs: the modes this reference was written with */
		for (j = 0; j < 8; j++) {
			h713_av1_set(p, pdec_in[i].ent[0][j], r->fc_luma[j] & 7);
			h713_av1_set(p, pdec_in[i].ent[1][j], r->fc_chroma[j] & 7);
			h713_av1_set(p, pdec_in[i].ent[2][j], r->fc_chroma[j] & 7);
		}
	}

	memset(h->b.pdec.cpu, 0, h->b.pdec.size);
	memcpy(h->b.pdec.cpu, p, sizeof(p));
	WADDR(h, PDEC_CONFIG_BASE, h->b.pdec.dma);
}

static void set_reference_frames(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	bool intrabc = !!(f->flags & V4L2_AV1_FRAME_FLAG_ALLOW_INTRABC);
	bool scale = false;
	int idx_of[7];
	int i;

	if (IS_INTRA(f->frame_type) && !intrabc)
		return;

	set_frame_sign_bias(h);
	for (i = V4L2_AV1_REF_LAST_FRAME; i < V4L2_AV1_TOTAL_REFS_PER_FRAME; i++) {
		int ref = i - 1, idx = 0, w, ht;

		if (intrabc) {
			idx = h->cur;
			w = f->frame_width_minus_1 + 1;
			ht = f->frame_height_minus_1 + 1;
		} else {
			if (get_frame_index(h, ref) > 0)
				idx = get_frame_index(h, ref);
			w = h->refs[idx].width;
			ht = h->refs[idx].height;
		}
		scale |= set_ref(h, ref, idx, w, ht);
		h713_av1_set(h->regs, ref_sign[ref], h->ref_frame_sign_bias[i]);
		idx_of[ref] = idx;
	}
	W(h, REF_SCALING_ENABLE, scale);
	for (i = 0; i < 7; i++)
		h713_av1_set(h->regs, ref_gm[i], f->global_motion.type[V4L2_AV1_REF_LAST_FRAME + i]);

	set_other_frames(h);
	set_pdec(h, idx_of);
}

/* ---- the rest of the frame header --------------------------------------- */

static int hw_tx_mode(enum v4l2_av1_tx_mode m)
{
	switch (m) {
	case V4L2_AV1_TX_MODE_ONLY_4X4:
		return H713_TX_ONLY_4X4;
	case V4L2_AV1_TX_MODE_SELECT:
		return H713_TX_SELECT;
	default:
		return H713_TX_32X32;
	}
}

static void set_parameters(struct h713_av1 *h)
{
	const struct v4l2_ctrl_av1_frame *f = h->frame;
	const struct v4l2_ctrl_av1_sequence *s = h->seq;
	const struct v4l2_av1_quantization *q = &f->quantization;

	W(h, SKIP_MODE_FLAG, !!(f->flags & V4L2_AV1_FRAME_FLAG_SKIP_MODE_PRESENT));
	W(h, TEMPORAL_MV_E, !!(f->flags & V4L2_AV1_FRAME_FLAG_USE_REF_FRAME_MVS));
	W(h, DELTA_LF_RES_LOG, f->loop_filter.delta_lf_res);
	W(h, DELTA_LF_MULTI, !!(f->loop_filter.flags & V4L2_AV1_LOOP_FILTER_FLAG_DELTA_LF_MULTI));
	W(h, DELTA_LF_PRESENT, !!(f->loop_filter.flags & V4L2_AV1_LOOP_FILTER_FLAG_DELTA_LF_PRESENT));
	W(h, DISABLE_CDF_UPDATE, !!(f->flags & V4L2_AV1_FRAME_FLAG_DISABLE_CDF_UPDATE));
	W(h, SHOW_FRAME, !!(f->flags & V4L2_AV1_FRAME_FLAG_SHOW_FRAME));
	W(h, SECONDARY_OUTPUT_HBD, h->bit_depth > 8);
	/* no raster for a frame that can never be displayed */
	W(h, SECONDARY_OUTPUT_E, !!(f->flags & (V4L2_AV1_FRAME_FLAG_SHOW_FRAME |
						V4L2_AV1_FRAME_FLAG_SHOWABLE_FRAME)));
	W(h, SWITCHABLE_MOTION_MODE, !!(f->flags & V4L2_AV1_FRAME_FLAG_IS_MOTION_MODE_SWITCHABLE));
	W(h, ALLOW_MASKED_COMPOUND, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_ENABLE_MASKED_COMPOUND));
	W(h, ALLOW_INTERINTRA, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_ENABLE_INTERINTRA_COMPOUND));
	W(h, ENABLE_INTRA_EDGE_FILTER, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_ENABLE_INTRA_EDGE_FILTER));
	W(h, ALLOW_FILTER_INTRA, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_ENABLE_FILTER_INTRA));
	W(h, ENABLE_JNT_COMP, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_ENABLE_JNT_COMP));
	W(h, ENABLE_DUAL_FILTER, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_ENABLE_DUAL_FILTER));
	W(h, REDUCED_TX_SET_USED, !!(f->flags & V4L2_AV1_FRAME_FLAG_REDUCED_TX_SET));
	W(h, ALLOW_SCREEN_CONTENT_TOOLS, !!(f->flags & V4L2_AV1_FRAME_FLAG_ALLOW_SCREEN_CONTENT_TOOLS));
	W(h, ALLOW_INTRABC, !!(f->flags & V4L2_AV1_FRAME_FLAG_ALLOW_INTRABC));
	/* the spec forces it on intra frames; the vendor writes 0 there */
	W(h, FORCE_INTEGER_MV, !IS_INTRA(f->frame_type) &&
			       (f->flags & V4L2_AV1_FRAME_FLAG_ALLOW_SCREEN_CONTENT_TOOLS) &&
			       (f->flags & V4L2_AV1_FRAME_FLAG_FORCE_INTEGER_MV));
	W(h, MONOCHROME, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_MONO_CHROME));
	W(h, DELTA_Q_RES_LOG, q->delta_q_res);
	W(h, DELTA_Q_PRESENT, !!(q->flags & V4L2_AV1_QUANTIZATION_FLAG_DELTA_Q_PRESENT));
	W(h, PIC_TYPE, !IS_INTRA(f->frame_type));
	W(h, QUANT_BASE_QINDEX, q->base_q_idx);
	W(h, BITDEPTH, h->bit_depth > 8);
	W(h, MCOMP_FILTER_TYPE, f->interpolation_filter);
	W(h, HIGH_PREC_MV_E, !!(f->flags & V4L2_AV1_FRAME_FLAG_ALLOW_HIGH_PRECISION_MV));
	W(h, HYBRID_PRED_ENABLE, !!(f->flags & V4L2_AV1_FRAME_FLAG_REFERENCE_SELECT));
	W(h, TRANSFORM_MODE, hw_tx_mode(f->tx_mode));
	W(h, SB_SIZE, !!(s->flags & V4L2_AV1_SEQUENCE_FLAG_USE_128X128_SUPERBLOCK));
	W(h, QUANT_DELTA_Y_DC, q->delta_q_y_dc);
	W(h, QUANT_DELTA_UV_DC, q->delta_q_u_dc);
	W(h, QUANT_DELTA_UV_AC, q->delta_q_u_ac);
	W(h, QUANT_DELTA_V_DC, q->delta_q_v_dc);
	W(h, QUANT_DELTA_V_AC, q->delta_q_v_ac);
	if (q->flags & V4L2_AV1_QUANTIZATION_FLAG_USING_QMATRIX) {
		W(h, QMLEVEL_Y, q->qm_y); W(h, QMLEVEL_U, q->qm_u); W(h, QMLEVEL_V, q->qm_v);
	} else {
		W(h, QMLEVEL_Y, 0xf); W(h, QMLEVEL_U, 0xf); W(h, QMLEVEL_V, 0xf);
	}
	W(h, LOSSLESS_E, is_lossless(h));
	/* raw, 0 when unused (the VPU981 writes 1 there; the vendor does not) */
	W(h, SKIP_REF0, f->skip_mode_frame[0]);
	W(h, SKIP_REF1, f->skip_mode_frame[1]);
}

/* ---- buffers and fixed configuration ------------------------------------ */

static void set_buffers(struct h713_av1 *h)
{
	u32 off = tile_data_start(h);

	/*
	 * input: a 32-byte aligned base, the tile data's byte offset from it in
	 * strm_start_pos (5 bits), stream_len counted from the base
	 */
	WADDR(h, OUT_STREAM0_BASE, (h->src_dma + off) & ~0x1full);
	W(h, STRM_START_POS, (h->src_dma + off) & 0x1f);
	W(h, STREAM_LEN, h->src_len - off + ((h->src_dma + off) & 0x1f));

	/* this frame: compressed reconstruction, its header, its MVs */
	WADDR(h, REC_LUM_BASE, h->cur_bufs.rec);
	WADDR(h, REC_CH_BASE, h->cur_bufs.hdr);
	WADDR(h, REC_LUM_COMP_BASE, h->cur_bufs.hdr);
	WADDR(h, TEMPORAL_WRITE_BASE, h->cur_bufs.mv);

	/* display: NV12 through the secondary output */
	WADDR(h, OUT_SECONDARY_LU_BASE, h->dst_luma);
	WADDR(h, OUT_SECONDARY_CB_BASE, h->dst_chroma);
	WADDR(h, OUT_SECONDARY_CR_BASE, h->dst_chroma);
	WADDR(h, OUT_SECONDARY_COLBUF_BASE, h->b.sec_colbuf.dma);

	/* fixed-size working buffers, as the vendor wires them */
	WADDR(h, REF0_SINDEX_BASE, h->b.scratch.dma);
	WADDR(h, OUT_SCALED_LU_BASE, h->b.scratch.dma + H713_AV1_SCRATCH_SCALED_OFF);
	WADDR(h, FILTER_CTRL_INFO_COLBUF_BASE, h->b.filter_ctrl.dma);
	WADDR(h, FILTER_LR_PARAMS_COLBUF_BASE, h->b.filter_ctrl.dma + H713_AV1_FILTER_LR_OFF);
	WADDR(h, FILM_GRAIN_COLBUF_BASE, h->b.fg_colbuf.dma);
	WADDR(h, FILTER_CDEF_DIR_COLBUF_BASE, h->b.cdef_colbuf.dma);
	WADDR(h, REC_SINDEX_BASE, h->b.rec_sindex.dma);
}

/* Constants of every stock register image (tools/re/av1 captures). */
static void set_fixed(struct h713_av1 *h)
{
	W(h, MODE_DEC, 1);
	W(h, CODING_MODE, 1);
	W(h, ENC_IRQ_ENABLE, 1);
	W(h, CLOCK_GATE_ENABLE, 1);
	W(h, TIMEOUT_ENABLE, 1);
	W(h, TIMEOUT_LIMIT, 0x1000000);
	W(h, REF_COMPRESS_E, 1);
	W(h, SECONDARY_OUTPUT_FORMAT, 1);	/* NV12 */
	W(h, ENC_OUT_SWAP, 0x1f);
	W(h, AXI_RD_MAXBURST, 0x20);
	W(h, AXI_WR_MAXBURST, 0x100);
	W(h, ME_SUPER_INDEX_DISABLE, 1);
	W(h, DEC_STREAM_ERROR_DETECTION, 1);
	W(h, DEC_INVALID_MARKER_DETECTION, 1);
	W(h, DEC_MV_ERROR_DETECTION, 1);
	W(h, DEC_COEFF_ERROR_DETECTION, 1);
	W(h, FC_CB_SIZE, 1);
	W(h, FC_PLANE_MODE, 1);
}

/*
 * Reference compression. The core compresses each reconstructed frame with
 * one of eight entropy modes per 4x4-ish block class and counts how often it
 * picked each; the vendor (FcUpdateModes) re-ranks the modes by those counts
 * after every frame, most-used first, and the next frame codes with that
 * ranking. The decompressor needs to know the ranking each reference was
 * written with, so it travels with the frame (refs[].fc_*, used by pdec).
 * The initial ranking is the vendor's .rodata table, set once per stream.
 */
static const u8 fc_default_modes[16] = {
	2, 3, 4, 1, 0, 5, 6, 7,		/* luma */
	1, 2, 0, 3, 4, 5, 6, 7,		/* chroma */
};

static const struct h713_av1_field fc_cur[16] = {
	H713_AV1_FC_CUR_LUMA_ENTROPY0, H713_AV1_FC_CUR_LUMA_ENTROPY1,
	H713_AV1_FC_CUR_LUMA_ENTROPY2, H713_AV1_FC_CUR_LUMA_ENTROPY3,
	H713_AV1_FC_CUR_LUMA_ENTROPY4, H713_AV1_FC_CUR_LUMA_ENTROPY5,
	H713_AV1_FC_CUR_LUMA_ENTROPY6, H713_AV1_FC_CUR_LUMA_ENTROPY7,
	H713_AV1_FC_CUR_CHROMA_ENTROPY0, H713_AV1_FC_CUR_CHROMA_ENTROPY1,
	H713_AV1_FC_CUR_CHROMA_ENTROPY2, H713_AV1_FC_CUR_CHROMA_ENTROPY3,
	H713_AV1_FC_CUR_CHROMA_ENTROPY4, H713_AV1_FC_CUR_CHROMA_ENTROPY5,
	H713_AV1_FC_CUR_CHROMA_ENTROPY6, H713_AV1_FC_CUR_CHROMA_ENTROPY7,
};

static const struct h713_av1_field fc_count[16] = {
	H713_AV1_FC_LUMA_CUR_ENTROPY0_COUNT, H713_AV1_FC_LUMA_CUR_ENTROPY1_COUNT,
	H713_AV1_FC_LUMA_CUR_ENTROPY2_COUNT, H713_AV1_FC_LUMA_CUR_ENTROPY3_COUNT,
	H713_AV1_FC_LUMA_CUR_ENTROPY4_COUNT, H713_AV1_FC_LUMA_CUR_ENTROPY5_COUNT,
	H713_AV1_FC_LUMA_CUR_ENTROPY6_COUNT, H713_AV1_FC_LUMA_CUR_ENTROPY7_COUNT,
	H713_AV1_FC_CHROMA_CUR_ENTROPY0_COUNT, H713_AV1_FC_CHROMA_CUR_ENTROPY1_COUNT,
	H713_AV1_FC_CHROMA_CUR_ENTROPY2_COUNT, H713_AV1_FC_CHROMA_CUR_ENTROPY3_COUNT,
	H713_AV1_FC_CHROMA_CUR_ENTROPY4_COUNT, H713_AV1_FC_CHROMA_CUR_ENTROPY5_COUNT,
	H713_AV1_FC_CHROMA_CUR_ENTROPY6_COUNT, H713_AV1_FC_CHROMA_CUR_ENTROPY7_COUNT,
};

static void set_fc_modes(struct h713_av1 *h)
{
	struct h713_av1_ref *r = &h->refs[h->cur];
	int i;

	for (i = 0; i < 16; i++)
		h713_av1_set(h->regs, fc_cur[i], h->fc_modes[i] & 7);
	memcpy(r->fc_luma, h->fc_modes, 8);
	memcpy(r->fc_chroma, h->fc_modes + 8, 8);
}

/*
 * Rank one plane's eight modes by count, descending. For ties the vendor's
 * std::sort (libc++: sorting network + insertion sort for n = 8) keeps index
 * order, so a stable insertion sort reproduces it; all-zero counts give the
 * identity ranking, which is what the vendor shows after frame 0 in emulation.
 */
static void fc_rank(const u32 *counts, u8 *modes)
{
	u8 idx[8];
	int i, j;

	for (i = 0; i < 8; i++) {
		u8 k = i;

		for (j = i; j > 0 && counts[k] > counts[idx[j - 1]]; j--)
			idx[j] = idx[j - 1];
		idx[j] = k;
	}
	memcpy(modes, idx, 8);
}

static void update_fc_modes(struct h713_av1 *h)
{
	u32 counts[16];
	int i;

	for (i = 0; i < 16; i++)
		counts[i] = h713_av1_get(h->regs, fc_count[i]);
	fc_rank(counts, h->fc_modes);
	fc_rank(counts + 8, h->fc_modes + 8);
}

int h713_av1_gen_init(struct h713_av1 *h)
{
	struct h713_av1_cdf *c = h->cdf;

	memset(h->refs, 0, sizeof(h->refs));
	c->cdfs = &c->default_cdfs;
	c->cdfs_ndvc = &c->default_cdfs_ndvc;
	rockchip_av1_set_default_cdfs(c->cdfs, c->cdfs_ndvc);
	memcpy(h->fc_modes, fc_default_modes, sizeof(h->fc_modes));
	return 0;
}

int h713_av1_gen_frame(struct h713_av1 *h, u64 timestamp)
{
	memset(h->regs, 0, sizeof(h->regs));

	clean_refs(h);
	if (frame_ref(h, timestamp) < 0)
		return -ENOSPC;

	set_fixed(h);
	set_parameters(h);
	set_global_model(h);
	set_tile_info(h);
	set_reference_frames(h);
	set_segmentation(h);
	set_loopfilter(h);
	set_picture_dimensions(h);
	set_cdef(h);
	set_lr(h);
	set_fgs(h);
	set_prob(h);
	set_buffers(h);
	set_fc_modes(h);
	return 0;
}

void h713_av1_gen_done(struct h713_av1 *h)
{
	update_prob(h);
	update_fc_modes(h);
}
