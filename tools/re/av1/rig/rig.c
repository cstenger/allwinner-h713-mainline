// SPDX-License-Identifier: GPL-2.0
/*
 * Host test rig for the H713 AV1 register generator.
 *
 * Parses an IVF AV1 stream with GStreamer's GstAV1Parser, fills the V4L2
 * stateless AV1 controls exactly as GStreamer's v4l2slav1dec does (the fill
 * code below is lifted from gstv4l2codecav1dec.c, 1.28.7), runs
 * sunxi_h713_av1_gen.c on them, and writes each decoded frame's register
 * image and CPU-side buffers:
 *
 *   OUT/frameNNN.regs  OUT/frameNNN.{tile,gm,prob,fg,pdec}.bin
 *
 * The hardware's outputs (probability table out, compressor statistics) are
 * zero, as in the vendor emulation (tools/re/av1/vendor-decode.py), so the two
 * can be compared field for field by tools/re/av1/compare.py.
 *
 *   rig stream.ivf OUT [max_frames]
 */
#include <gst/gst.h>
#include <gst/codecparsers/gstav1parser.h>
#include <stdio.h>
#include <sys/stat.h>

#include "sunxi_h713_av1_compat.h"
#include "sunxi_h713_av1_gen.h"

#define FAKE_BASE	0x40000000ull

static struct h713_av1 H;
static struct v4l2_ctrl_av1_sequence v4l2_sequence;
static struct v4l2_ctrl_av1_frame v4l2_frame;
static struct v4l2_ctrl_av1_film_grain v4l2_film_grain;
static struct v4l2_ctrl_av1_tile_group_entry tge[V4L2_AV1_MAX_TILE_COUNT];
static unsigned int num_tge;
static u8 bitstream[4 << 20];
static unsigned int bitstream_len;
static u64 ref_ts[8];
static const char *outdir;
static int frame_no;

/* ---- lifted from gstv4l2codecav1dec.c (GStreamer 1.28.7) --------------- */

static void fill_sequence(const GstAV1SequenceHeaderOBU *seq_hdr)
{
	v4l2_sequence = (struct v4l2_ctrl_av1_sequence) {
	.flags =
	  (seq_hdr->still_picture ? V4L2_AV1_SEQUENCE_FLAG_STILL_PICTURE : 0) |
	  (seq_hdr->use_128x128_superblock ? V4L2_AV1_SEQUENCE_FLAG_USE_128X128_SUPERBLOCK : 0) |
	  (seq_hdr->enable_filter_intra ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_FILTER_INTRA : 0) |
	  (seq_hdr->enable_intra_edge_filter ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_INTRA_EDGE_FILTER : 0) |
	  (seq_hdr->enable_interintra_compound ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_INTERINTRA_COMPOUND : 0) |
	  (seq_hdr->enable_masked_compound ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_MASKED_COMPOUND : 0) |
	  (seq_hdr->enable_warped_motion ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_WARPED_MOTION : 0) |
	  (seq_hdr->enable_dual_filter ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_DUAL_FILTER : 0) |
	  (seq_hdr->enable_order_hint ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_ORDER_HINT : 0) |
	  (seq_hdr->enable_jnt_comp ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_JNT_COMP : 0) |
	  (seq_hdr->enable_ref_frame_mvs ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_REF_FRAME_MVS : 0) |
	  (seq_hdr->enable_superres ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_SUPERRES : 0) |
	  (seq_hdr->enable_cdef ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_CDEF : 0) |
	  (seq_hdr->enable_restoration ? V4L2_AV1_SEQUENCE_FLAG_ENABLE_RESTORATION : 0) |
	  (seq_hdr->color_config.mono_chrome ? V4L2_AV1_SEQUENCE_FLAG_MONO_CHROME : 0) |
	  (seq_hdr->color_config.color_range ? V4L2_AV1_SEQUENCE_FLAG_COLOR_RANGE : 0) |
	  (seq_hdr->color_config.subsampling_x ? V4L2_AV1_SEQUENCE_FLAG_SUBSAMPLING_X : 0) |
	  (seq_hdr->color_config.subsampling_y ? V4L2_AV1_SEQUENCE_FLAG_SUBSAMPLING_Y : 0) |
	  (seq_hdr->film_grain_params_present ? V4L2_AV1_SEQUENCE_FLAG_FILM_GRAIN_PARAMS_PRESENT : 0) |
	  (seq_hdr->color_config.separate_uv_delta_q ? V4L2_AV1_SEQUENCE_FLAG_SEPARATE_UV_DELTA_Q : 0),
	.seq_profile = seq_hdr->seq_profile,
	.order_hint_bits = seq_hdr->order_hint_bits,
	.bit_depth = seq_hdr->bit_depth,
	.max_frame_width_minus_1 = seq_hdr->max_frame_width_minus_1,
	.max_frame_height_minus_1 = seq_hdr->max_frame_height_minus_1,
	};
}

static void fill_film_grain(const GstAV1FilmGrainParams *fg)
{
	struct v4l2_ctrl_av1_film_grain *v = &v4l2_film_grain;

	*v = (struct v4l2_ctrl_av1_film_grain) {
	.flags =
	    (fg->apply_grain ? V4L2_AV1_FILM_GRAIN_FLAG_APPLY_GRAIN : 0) |
	    (fg->update_grain ? V4L2_AV1_FILM_GRAIN_FLAG_UPDATE_GRAIN : 0) |
	    (fg->chroma_scaling_from_luma ? V4L2_AV1_FILM_GRAIN_FLAG_CHROMA_SCALING_FROM_LUMA : 0) |
	    (fg->overlap_flag ? V4L2_AV1_FILM_GRAIN_FLAG_OVERLAP : 0) |
	    (fg->clip_to_restricted_range ? V4L2_AV1_FILM_GRAIN_FLAG_CLIP_TO_RESTRICTED_RANGE : 0),
	.grain_seed = fg->grain_seed,
	.film_grain_params_ref_idx = fg->film_grain_params_ref_idx,
	.num_y_points = fg->num_y_points,
	.num_cb_points = fg->num_cb_points,
	.num_cr_points = fg->num_cr_points,
	.grain_scaling_minus_8 = fg->grain_scaling_minus_8,
	.ar_coeff_lag = fg->ar_coeff_lag,
	.ar_coeff_shift_minus_6 = fg->ar_coeff_shift_minus_6,
	.grain_scale_shift = fg->grain_scale_shift,
	.cb_mult = fg->cb_mult, .cb_luma_mult = fg->cb_luma_mult, .cb_offset = fg->cb_offset,
	.cr_mult = fg->cr_mult, .cr_luma_mult = fg->cr_luma_mult, .cr_offset = fg->cr_offset,
	};
	memcpy(v->point_y_value, fg->point_y_value, sizeof(v->point_y_value));
	memcpy(v->point_y_scaling, fg->point_y_scaling, sizeof(v->point_y_scaling));
	memcpy(v->point_cb_value, fg->point_cb_value, sizeof(v->point_cb_value));
	memcpy(v->point_cb_scaling, fg->point_cb_scaling, sizeof(v->point_cb_scaling));
	memcpy(v->point_cr_value, fg->point_cr_value, sizeof(v->point_cr_value));
	memcpy(v->point_cr_scaling, fg->point_cr_scaling, sizeof(v->point_cr_scaling));
	memcpy(v->ar_coeffs_y_plus_128, fg->ar_coeffs_y_plus_128, sizeof(v->ar_coeffs_y_plus_128));
	memcpy(v->ar_coeffs_cb_plus_128, fg->ar_coeffs_cb_plus_128, sizeof(v->ar_coeffs_cb_plus_128));
	memcpy(v->ar_coeffs_cr_plus_128, fg->ar_coeffs_cr_plus_128, sizeof(v->ar_coeffs_cr_plus_128));
}

static void fill_frame(const GstAV1FrameHeaderOBU *f)
{
	const GstAV1QuantizationParams *q = &f->quantization_params;
	const GstAV1SegmentationParams *seg = &f->segmentation_params;
	const GstAV1LoopFilterParams *lf = &f->loop_filter_params;
	const GstAV1LoopRestorationParams *lr = &f->loop_restoration_params;
	const GstAV1GlobalMotionParams *gm = &f->global_motion_params;
	struct v4l2_ctrl_av1_frame *v = &v4l2_frame;
	unsigned int i, j;

	*v = (struct v4l2_ctrl_av1_frame) {
	.flags =
	  (f->show_frame ? V4L2_AV1_FRAME_FLAG_SHOW_FRAME : 0) |
	  (f->showable_frame ? V4L2_AV1_FRAME_FLAG_SHOWABLE_FRAME : 0) |
	  (f->error_resilient_mode ? V4L2_AV1_FRAME_FLAG_ERROR_RESILIENT_MODE : 0) |
	  (f->disable_cdf_update ? V4L2_AV1_FRAME_FLAG_DISABLE_CDF_UPDATE : 0) |
	  (f->allow_screen_content_tools ? V4L2_AV1_FRAME_FLAG_ALLOW_SCREEN_CONTENT_TOOLS : 0) |
	  (f->force_integer_mv ? V4L2_AV1_FRAME_FLAG_FORCE_INTEGER_MV : 0) |
	  (f->allow_intrabc ? V4L2_AV1_FRAME_FLAG_ALLOW_INTRABC : 0) |
	  (f->use_superres ? V4L2_AV1_FRAME_FLAG_USE_SUPERRES : 0) |
	  (f->allow_high_precision_mv ? V4L2_AV1_FRAME_FLAG_ALLOW_HIGH_PRECISION_MV : 0) |
	  (f->is_motion_mode_switchable ? V4L2_AV1_FRAME_FLAG_IS_MOTION_MODE_SWITCHABLE : 0) |
	  (f->use_ref_frame_mvs ? V4L2_AV1_FRAME_FLAG_USE_REF_FRAME_MVS : 0) |
	  (f->disable_frame_end_update_cdf ? V4L2_AV1_FRAME_FLAG_DISABLE_FRAME_END_UPDATE_CDF : 0) |
	  (f->allow_warped_motion ? V4L2_AV1_FRAME_FLAG_ALLOW_WARPED_MOTION : 0) |
	  (f->reference_select ? V4L2_AV1_FRAME_FLAG_REFERENCE_SELECT : 0) |
	  (f->reduced_tx_set ? V4L2_AV1_FRAME_FLAG_REDUCED_TX_SET : 0) |
	  (f->skip_mode_frame[0] > 0 ? V4L2_AV1_FRAME_FLAG_SKIP_MODE_ALLOWED : 0) |
	  (f->skip_mode_present ? V4L2_AV1_FRAME_FLAG_SKIP_MODE_PRESENT : 0) |
	  (f->frame_size_override_flag ? V4L2_AV1_FRAME_FLAG_FRAME_SIZE_OVERRIDE : 0) |
	  (f->buffer_removal_time_present_flag ? V4L2_AV1_FRAME_FLAG_BUFFER_REMOVAL_TIME_PRESENT : 0) |
	  (f->frame_refs_short_signaling ? V4L2_AV1_FRAME_FLAG_FRAME_REFS_SHORT_SIGNALING : 0),
	.order_hint = f->order_hint,
	.superres_denom = f->superres_denom,
	.upscaled_width = f->upscaled_width,
	.frame_width_minus_1 = f->frame_width - 1,
	.frame_height_minus_1 = f->frame_height - 1,
	.render_width_minus_1 = f->render_width - 1,
	.render_height_minus_1 = f->render_height - 1,
	.current_frame_id = f->current_frame_id,
	.primary_ref_frame = f->primary_ref_frame,
	.refresh_frame_flags = f->refresh_frame_flags,
	.tile_info = {
	  .flags = f->tile_info.uniform_tile_spacing_flag ? V4L2_AV1_TILE_INFO_FLAG_UNIFORM_TILE_SPACING : 0,
	  .tile_size_bytes = f->tile_info.tile_size_bytes,
	  .context_update_tile_id = f->tile_info.context_update_tile_id,
	  .tile_cols = f->tile_info.tile_cols,
	  .tile_rows = f->tile_info.tile_rows,
	},
	.quantization = {
	  .flags = (q->diff_uv_delta ? V4L2_AV1_QUANTIZATION_FLAG_DIFF_UV_DELTA : 0) |
		   (q->using_qmatrix ? V4L2_AV1_QUANTIZATION_FLAG_USING_QMATRIX : 0) |
		   (q->delta_q_present ? V4L2_AV1_QUANTIZATION_FLAG_DELTA_Q_PRESENT : 0),
	  .base_q_idx = q->base_q_idx,
	  .delta_q_y_dc = q->delta_q_y_dc, .delta_q_u_dc = q->delta_q_u_dc,
	  .delta_q_u_ac = q->delta_q_u_ac, .delta_q_v_dc = q->delta_q_v_dc,
	  .delta_q_v_ac = q->delta_q_v_ac,
	  .qm_y = q->qm_y, .qm_u = q->qm_u, .qm_v = q->qm_v,
	  .delta_q_res = q->delta_q_res,
	},
	.segmentation = {
	  .flags = (seg->segmentation_enabled ? V4L2_AV1_SEGMENTATION_FLAG_ENABLED : 0) |
		   (seg->segmentation_update_map ? V4L2_AV1_SEGMENTATION_FLAG_UPDATE_MAP : 0) |
		   (seg->segmentation_temporal_update ? V4L2_AV1_SEGMENTATION_FLAG_TEMPORAL_UPDATE : 0) |
		   (seg->segmentation_update_data ? V4L2_AV1_SEGMENTATION_FLAG_UPDATE_DATA : 0) |
		   (seg->seg_id_pre_skip ? V4L2_AV1_SEGMENTATION_FLAG_SEG_ID_PRE_SKIP : 0),
	  .last_active_seg_id = seg->last_active_seg_id,
	},
	.loop_filter = {
	  .flags = (lf->loop_filter_delta_enabled ? V4L2_AV1_LOOP_FILTER_FLAG_DELTA_ENABLED : 0) |
		   (lf->loop_filter_delta_update ? V4L2_AV1_LOOP_FILTER_FLAG_DELTA_UPDATE : 0) |
		   (lf->delta_lf_present ? V4L2_AV1_LOOP_FILTER_FLAG_DELTA_LF_PRESENT : 0) |
		   (lf->delta_lf_multi ? V4L2_AV1_LOOP_FILTER_FLAG_DELTA_LF_MULTI : 0),
	  .sharpness = lf->loop_filter_sharpness,
	  .delta_lf_res = lf->delta_lf_res,
	},
	.cdef = {
	  .damping_minus_3 = f->cdef_params.cdef_damping - 3,
	  .bits = f->cdef_params.cdef_bits,
	},
	.loop_restoration = {
	  .flags = (lr->uses_lr ? V4L2_AV1_LOOP_RESTORATION_FLAG_USES_LR : 0) |
		   (lr->frame_restoration_type[1] ? V4L2_AV1_LOOP_RESTORATION_FLAG_USES_CHROMA_LR : 0),
	  .lr_unit_shift = lr->lr_unit_shift,
	  .lr_uv_shift = lr->lr_uv_shift,
	},
	};
	v->frame_type = f->frame_type;		/* GstAV1 enums match V4L2's */
	v->interpolation_filter = f->interpolation_filter;
	v->tx_mode = f->tx_mode == GST_AV1_TX_MODE_ONLY_4x4 ? V4L2_AV1_TX_MODE_ONLY_4X4 :
		     f->tx_mode == GST_AV1_TX_MODE_LARGEST ? V4L2_AV1_TX_MODE_LARGEST :
							       V4L2_AV1_TX_MODE_SELECT;
	for (i = 0; i < V4L2_AV1_NUM_PLANES_MAX; i++)
		v->loop_restoration.frame_restoration_type[i] = lr->frame_restoration_type[i];

	/* refs */
	for (i = 0; i < 8; i++)
		v->reference_frame_ts[i] = ref_ts[i];
	memcpy(v->ref_frame_idx, f->ref_frame_idx, sizeof(v->ref_frame_idx));
	/* tile info */
	memcpy(v->tile_info.mi_col_starts, f->tile_info.mi_col_starts, sizeof(v->tile_info.mi_col_starts));
	memcpy(v->tile_info.mi_row_starts, f->tile_info.mi_row_starts, sizeof(v->tile_info.mi_row_starts));
	memcpy(v->tile_info.width_in_sbs_minus_1, f->tile_info.width_in_sbs_minus_1, sizeof(v->tile_info.width_in_sbs_minus_1));
	memcpy(v->tile_info.height_in_sbs_minus_1, f->tile_info.height_in_sbs_minus_1, sizeof(v->tile_info.height_in_sbs_minus_1));
	/* segmentation */
	for (i = 0; i < V4L2_AV1_MAX_SEGMENTS; i++)
		for (j = 0; j < V4L2_AV1_SEG_LVL_MAX; j++)
			v->segmentation.feature_enabled[i] |= seg->feature_enabled[i][j] << j;
	memcpy(v->segmentation.feature_data, seg->feature_data, sizeof(v->segmentation.feature_data));
	/* loop filter */
	memcpy(v->loop_filter.level, lf->loop_filter_level, sizeof(v->loop_filter.level));
	memcpy(v->loop_filter.ref_deltas, lf->loop_filter_ref_deltas, sizeof(v->loop_filter.ref_deltas));
	memcpy(v->loop_filter.mode_deltas, lf->loop_filter_mode_deltas, sizeof(v->loop_filter.mode_deltas));
	/* cdef */
	memcpy(v->cdef.y_pri_strength, f->cdef_params.cdef_y_pri_strength, sizeof(v->cdef.y_pri_strength));
	memcpy(v->cdef.y_sec_strength, f->cdef_params.cdef_y_sec_strength, sizeof(v->cdef.y_sec_strength));
	memcpy(v->cdef.uv_pri_strength, f->cdef_params.cdef_uv_pri_strength, sizeof(v->cdef.uv_pri_strength));
	memcpy(v->cdef.uv_sec_strength, f->cdef_params.cdef_uv_sec_strength, sizeof(v->cdef.uv_sec_strength));
	/* loop restoration */
	memcpy(v->loop_restoration.loop_restoration_size, lr->loop_restoration_size,
	       sizeof(v->loop_restoration.loop_restoration_size));
	/* global motion */
	for (i = 0; i < V4L2_AV1_TOTAL_REFS_PER_FRAME; i++) {
		v->global_motion.flags[i] =
			(gm->is_global[i] ? V4L2_AV1_GLOBAL_MOTION_FLAG_IS_GLOBAL : 0) |
			(gm->is_rot_zoom[i] ? V4L2_AV1_GLOBAL_MOTION_FLAG_IS_ROT_ZOOM : 0) |
			(gm->is_translation[i] ? V4L2_AV1_GLOBAL_MOTION_FLAG_IS_TRANSLATION : 0);
		v->global_motion.invalid |= gm->invalid[i] << i;
	}
	memcpy(v->global_motion.type, gm->gm_type, sizeof(v->global_motion.type));
	memcpy(v->global_motion.params, gm->gm_params, sizeof(v->global_motion.params));

	fill_film_grain(&f->film_grain_params);
	memcpy(v->buffer_removal_time, f->buffer_removal_time, sizeof(v->buffer_removal_time));
	memcpy(v->order_hints, f->order_hints, sizeof(v->order_hints));
	memcpy(v->skip_mode_frame, f->skip_mode_frame, sizeof(v->skip_mode_frame));
}

/* ---- buffers ------------------------------------------------------------ */

static u64 fake_next = FAKE_BASE;

static void dma(struct h713_av1_dma *d, size_t size)
{
	d->cpu = calloc(1, size);
	d->dma = fake_next;
	d->size = size;
	fake_next += (size + 0xfffff) & ~0xfffffull;
}

static void dump(const char *what, const void *p, size_t n)
{
	char path[512];
	FILE *f;

	snprintf(path, sizeof(path), "%s/frame%03d.%s", outdir, frame_no, what);
	f = fopen(path, "wb");
	fwrite(p, 1, n, f);
	fclose(f);
}

/* One frame: controls are filled; bitstream holds this frame's tile data. */
static void decode_frame(const GstAV1FrameHeaderOBU *fh)
{
	u64 ts = 1000 * (frame_no + 1);
	int i, slot;

	fill_frame(fh);
	H.seq = &v4l2_sequence;
	H.frame = &v4l2_frame;
	H.tge = tge;
	H.num_tge = num_tge;
	H.film_grain = (v4l2_sequence.flags & V4L2_AV1_SEQUENCE_FLAG_FILM_GRAIN_PARAMS_PRESENT) ?
		       &v4l2_film_grain : NULL;
	H.src_dma = 0x20000000;
	H.src_len = bitstream_len;
	H.src_size = sizeof(bitstream);
	H.dst_luma = 0x30000000 + 0x1000000ull * (frame_no % 8);
	H.dst_chroma = H.dst_luma + (u64)(v4l2_frame.frame_width_minus_1 + 1) *
			(v4l2_frame.frame_height_minus_1 + 1);
	H.bit_depth = v4l2_sequence.bit_depth;

	slot = h713_av1_gen_slot(&H, ts);
	if (slot < 0) {
		fprintf(stderr, "frame %d: no free slot\n", frame_no);
		return;
	}
	/* the slot's private buffers: recognisable per-slot addresses */
	H.refs[slot].bufs.rec = 0x50000000 + 0x1000000ull * slot;
	H.refs[slot].bufs.hdr = H.refs[slot].bufs.rec + 0x800000;
	H.refs[slot].bufs.mv = H.refs[slot].bufs.rec + 0xc00000;
	if (h713_av1_gen_frame(&H))
		fprintf(stderr, "frame %d: gen failed\n", frame_no);

	dump("regs", H.regs, sizeof(H.regs));
	dump("tile.bin", H.b.tile_info.cpu, H.b.tile_info.size);
	dump("gm.bin", H.b.global_model.cpu, H.b.global_model.size);
	dump("prob.bin", H.b.prob.cpu, H.b.prob.size);
	dump("fg.bin", H.b.film_grain.cpu, H.b.film_grain.size);
	dump("pdec.bin", H.b.pdec.cpu, H.b.pdec.size);

	/* "hardware done": outputs are zero, as in the vendor emulation */
	memset(H.b.prob_out.cpu, 0, H.b.prob_out.size);
	h713_av1_gen_done(&H);

	for (i = 0; i < 8; i++)
		if (v4l2_frame.refresh_frame_flags & (1 << i))
			ref_ts[i] = ts;
	printf("frame %3d: type %d show %d %dx%d q %3d tiles %dx%d refresh %#04x tge %u len %u\n",
	       frame_no, v4l2_frame.frame_type,
	       !!(v4l2_frame.flags & V4L2_AV1_FRAME_FLAG_SHOW_FRAME),
	       v4l2_frame.frame_width_minus_1 + 1, v4l2_frame.frame_height_minus_1 + 1,
	       v4l2_frame.quantization.base_q_idx, v4l2_frame.tile_info.tile_cols,
	       v4l2_frame.tile_info.tile_rows, v4l2_frame.refresh_frame_flags, num_tge,
	       bitstream_len);
	frame_no++;
}

static void add_tile_group(const GstAV1OBU *obu, const GstAV1TileGroupOBU *tg)
{
	u32 obu_offset = bitstream_len;
	int i;

	for (i = tg->tg_start; i <= tg->tg_end; i++) {
		tge[num_tge++] = (struct v4l2_ctrl_av1_tile_group_entry) {
			.tile_offset = tg->entry[i].tile_offset + obu_offset,
			.tile_size = tg->entry[i].tile_size,
			.tile_row = tg->entry[i].tile_row,
			.tile_col = tg->entry[i].tile_col,
		};
	}
	memcpy(bitstream + bitstream_len, obu->data, obu->obu_size);
	bitstream_len += obu->obu_size;
}

int main(int argc, char **argv)
{
	GstAV1Parser *parser;
	GstAV1FrameHeaderOBU fh;
	GstAV1SequenceHeaderOBU seq;
	int max_frames = argc > 3 ? atoi(argv[3]) : 1000;
	FILE *f;
	u8 hdr[32], fhdr[12];
	static u8 tu[4 << 20];
	bool have_fh = false;

	if (argc < 3) {
		fprintf(stderr, "usage: rig stream.ivf OUTDIR [max_frames]\n");
		return 2;
	}
	outdir = argv[2];
	mkdir(outdir, 0755);
	f = fopen(argv[1], "rb");
	if (!f || fread(hdr, 1, 32, f) != 32 || memcmp(hdr, "DKIF", 4)) {
		fprintf(stderr, "not an IVF file\n");
		return 1;
	}

	H.cdf = calloc(1, sizeof(*H.cdf));
	dma(&H.b.tile_info, H713_AV1_TILE_INFO_SIZE);
	dma(&H.b.global_model, H713_AV1_GLOBAL_MODEL_SIZE);
	dma(&H.b.prob, H713_AV1_PROB_SIZE);
	dma(&H.b.prob_out, H713_AV1_PROB_SIZE);
	dma(&H.b.film_grain, H713_AV1_FILM_GRAIN_SIZE);
	dma(&H.b.pdec, H713_AV1_PDEC_SIZE);
	dma(&H.b.scratch, H713_AV1_SCRATCH_SIZE);
	dma(&H.b.filter_ctrl, H713_AV1_FILTER_CTRL_SIZE);
	dma(&H.b.fg_colbuf, H713_AV1_FG_COLBUF_SIZE);
	dma(&H.b.cdef_colbuf, H713_AV1_CDEF_COLBUF_SIZE);
	dma(&H.b.rec_sindex, H713_AV1_REC_SINDEX_SIZE);
	dma(&H.b.sec_colbuf, H713_AV1_SEC_COLBUF_SIZE);
	h713_av1_gen_init(&H);

	parser = gst_av1_parser_new();
	while (frame_no < max_frames && fread(fhdr, 1, 12, f) == 12) {
		u32 size = fhdr[0] | fhdr[1] << 8 | fhdr[2] << 16 | (u32)fhdr[3] << 24;
		u32 pos = 0, consumed;
		GstAV1OBU obu;

		if (size > sizeof(tu) || fread(tu, 1, size, f) != size)
			break;
		while (pos < size) {
			if (gst_av1_parser_identify_one_obu(parser, tu + pos, size - pos, &obu,
							    &consumed) != GST_AV1_PARSER_OK)
				break;
			pos += consumed;
			switch (obu.obu_type) {
			case GST_AV1_OBU_SEQUENCE_HEADER:
				if (gst_av1_parser_parse_sequence_header_obu(parser, &obu, &seq) ==
				    GST_AV1_PARSER_OK)
					fill_sequence(&seq);
				break;
			case GST_AV1_OBU_FRAME: {
				GstAV1FrameOBU fo;

				if (gst_av1_parser_parse_frame_obu(parser, &obu, &fo) != GST_AV1_PARSER_OK)
					break;
				fh = fo.frame_header;
				num_tge = bitstream_len = 0;
				add_tile_group(&obu, &fo.tile_group);
				decode_frame(&fh);
				gst_av1_parser_reference_frame_update(parser, &fh);
				have_fh = false;
				break;
			}
			case GST_AV1_OBU_FRAME_HEADER:
				if (gst_av1_parser_parse_frame_header_obu(parser, &obu, &fh) !=
				    GST_AV1_PARSER_OK)
					break;
				if (fh.show_existing_frame)
					break;	/* nothing to decode */
				num_tge = bitstream_len = 0;
				have_fh = true;
				break;
			case GST_AV1_OBU_TILE_GROUP: {
				GstAV1TileGroupOBU tg;

				if (!have_fh || gst_av1_parser_parse_tile_group_obu(parser, &obu, &tg) !=
				    GST_AV1_PARSER_OK)
					break;
				add_tile_group(&obu, &tg);
				if (tg.tg_end == tg.num_tiles - 1) {
					decode_frame(&fh);
					gst_av1_parser_reference_frame_update(parser, &fh);
					have_fh = false;
				}
				break;
			}
			default:
				break;
			}
		}
	}
	printf("%d frame(s) generated\n", frame_no);
	return 0;
}
