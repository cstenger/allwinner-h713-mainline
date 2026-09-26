// SPDX-License-Identifier: GPL-2.0
/* Read-only V4L2 bridge for the board-B firmware's HDMI NV16 frame ring. */

#include <linux/crc32.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/io.h>
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

#include <media/v4l2-device.h>
#include <media/v4l2-fh.h>
#include <media/v4l2-ioctl.h>
#include <media/videobuf2-dma-contig.h>
#include <media/videobuf2-v4l2.h>

#define H713_CARVEOUT 0x4bf41000ULL
#define H713_CARVEOUT_SIZE (26 * 1024 * 1024)
#define H713_FIRST_PLANE 0x4c3ef000ULL
#define H713_PLANE_STEP 0x1ff000
#define H713_WIDTH 640
#define H713_HEIGHT 480
#define H713_PLANE_SIZE (H713_WIDTH * H713_HEIGHT)
#define H713_FRAME_SIZE (2 * H713_PLANE_SIZE)
#define H713_PAGE_SIZE 4096
#define H713_NO_FRAME_MS 3000
#define H713_TRACE 0x4d980000ULL
#define H713_TRACE_SIZE 0x1000
#define H713_TRACE_MAGIC 0x434f4d4d
#define H713_TRACE_CANARY 0x43414e31
#define H713_MIPS_IMAGE 0x4b100000ULL
#define H713_MIPS_VERIFY_SIZE 0x87000
#define H713_AFBD_PAIR 0x05600320ULL
#define H713_AFBD_PAIR_SIZE 0x8
#define H713_AFBD_VOTE_WINDOW 12
#define H713_AFBD_VOTE_MIN 10

static const unsigned int h713_probe_pages[] = {
	0x10000, 0x20000, 0x30000, 0x40000,
};

struct h713_buffer {
	struct vb2_v4l2_buffer vb;
	struct list_head list;
};

struct h713_capture {
	struct platform_device *pdev;
	struct v4l2_device v4l2_dev;
	struct video_device vdev;
	struct vb2_queue queue;
	struct mutex lock;
	spinlock_t qlock;
	struct list_head buffers;
	struct task_struct *worker;
	struct task_struct *phase_worker;
	u8 *ring;
	u8 *trace;
	void __iomem *afbd_pair;
	u32 sequence;
	int pair_offset;
};

static struct h713_capture *h713_cap;
static bool verify_full = true;
module_param(verify_full, bool, 0444);
MODULE_PARM_DESC(verify_full,
	"Compare full source planes after each copy (default true); false uses sparse stability probes only");
static bool phase_from_hash = true;
module_param(phase_from_hash, bool, 0444);
MODULE_PARM_DESC(phase_from_hash,
	"Allow ring-content phase learning (default true); false validates AFBD bootstrap alone");
static unsigned long frames_produced;
static unsigned long frames_delivered;
static unsigned long frames_overwritten;
static unsigned long frames_rejected;
module_param(frames_produced, ulong, 0444);
module_param(frames_delivered, ulong, 0444);
module_param(frames_overwritten, ulong, 0444);
module_param(frames_rejected, ulong, 0444);
static unsigned long afbd_samples;
static unsigned long afbd_invalid;
static unsigned long afbd_phase0;
static unsigned long afbd_phase1;
static unsigned long afbd_phase2;
static unsigned long afbd_y;
static unsigned long afbd_uv;
module_param(afbd_samples, ulong, 0444);
module_param(afbd_invalid, ulong, 0444);
module_param(afbd_phase0, ulong, 0444);
module_param(afbd_phase1, ulong, 0444);
module_param(afbd_phase2, ulong, 0444);
module_param(afbd_y, ulong, 0444);
module_param(afbd_uv, ulong, 0444);

static u32 h713_trace_word(struct h713_capture *cap, unsigned int offset)
{
	return le32_to_cpu(READ_ONCE(*(__le32 *)(cap->trace + offset)));
}

static u8 *h713_plane(struct h713_capture *cap, unsigned int index)
{
	return cap->ring + H713_FIRST_PLANE - H713_CARVEOUT +
	       H713_PLANE_STEP * index;
}

/*
 * AFBD +0x320/+0x324 has held an exact Y/UV pair from this ring in every
 * retained register dump. Its latch can cross the VDE sampling read, so no
 * individual sample selects a buffer. Re-reading Y brackets C against a torn
 * pair; the phase thread accepts only a strongly dominant multi-event phase.
 */
static int h713_afbd_pair_index(struct h713_capture *cap)
{
	u32 y, y_again, uv;
	unsigned int i;

	if (!cap->afbd_pair)
		return -1;
	y = readl(cap->afbd_pair);
	uv = readl(cap->afbd_pair + 4);
	y_again = readl(cap->afbd_pair);
	afbd_y = y_again;
	afbd_uv = uv;
	if (y != y_again)
		return -1;
	for (i = 0; i < 3; i++) {
		if (y == H713_FIRST_PLANE + H713_PLANE_STEP * i &&
		    uv == H713_FIRST_PLANE + H713_PLANE_STEP * (i + 3))
			return i;
	}
	return -1;
}

static u32 h713_hash_plane(struct h713_capture *cap, unsigned int index)
{
	u8 *plane = h713_plane(cap, index);
	u32 crc = 0;
	unsigned int i;

	for (i = 0; i < ARRAY_SIZE(h713_probe_pages); i++)
		crc = crc32_le(crc, plane + h713_probe_pages[i],
			       H713_PAGE_SIZE);
	return crc;
}

static void h713_hash_ring(struct h713_capture *cap, u32 hashes[6])
{
	unsigned int i;

	for (i = 0; i < 6; i++)
		hashes[i] = h713_hash_plane(cap, i);
}

static struct h713_buffer *h713_take_buffer(struct h713_capture *cap)
{
	struct h713_buffer *buf = NULL;
	unsigned long flags;

	spin_lock_irqsave(&cap->qlock, flags);
	if (!list_empty(&cap->buffers)) {
		buf = list_first_entry(&cap->buffers, struct h713_buffer, list);
		list_del(&buf->list);
	}
	spin_unlock_irqrestore(&cap->qlock, flags);
	return buf;
}

static void h713_return_buffers(struct h713_capture *cap,
				enum vb2_buffer_state state)
{
	struct h713_buffer *buf;

	while ((buf = h713_take_buffer(cap)))
		vb2_buffer_done(&buf->vb.vb2_buf, state);
}

static int h713_phase_thread(void *arg)
{
	struct h713_capture *cap = arg;
	u32 previous[6], observed[6];
	u32 last_vde, vde, last_mode, mode;
	unsigned int i, changed, active, delta;
	int afbd_pair, afbd_offset;
	unsigned int afbd_votes[3] = { 0 };
	unsigned int afbd_vote_total = 0;
	unsigned long last_activity = jiffies;
	bool baseline = false;

	while (!kthread_should_stop()) {
		if (!baseline) {
			h713_hash_ring(cap, previous);
			last_vde = h713_trace_word(cap, 0x88);
			last_mode = h713_trace_word(cap, 0x90);
			last_activity = jiffies;
			baseline = true;
		}
		usleep_range(500, 1000);
		mode = h713_trace_word(cap, 0x90);
		if (mode != last_mode) {
			WRITE_ONCE(cap->pair_offset, -1);
			memset(afbd_votes, 0, sizeof(afbd_votes));
			afbd_vote_total = 0;
			baseline = false;
			continue;
		}
		vde = h713_trace_word(cap, 0x88);
		if (vde == last_vde) {
			if (READ_ONCE(cap->pair_offset) >= 0 &&
			    time_after(jiffies, last_activity +
				       msecs_to_jiffies(H713_NO_FRAME_MS))) {
				WRITE_ONCE(cap->pair_offset, -1);
				memset(afbd_votes, 0, sizeof(afbd_votes));
				afbd_vote_total = 0;
				baseline = false;
			}
			continue;
		}
		delta = vde - last_vde;
		last_vde = vde;
		last_activity = jiffies;
		if (delta == 1 && cap->afbd_pair) {
			afbd_samples++;
			afbd_pair = h713_afbd_pair_index(cap);
			if (afbd_pair < 0) {
				afbd_invalid++;
				memset(afbd_votes, 0, sizeof(afbd_votes));
				afbd_vote_total = 0;
			} else {
				afbd_offset = (afbd_pair + 3 - vde % 3) % 3;
				if (afbd_offset == 0)
					afbd_phase0++;
				else if (afbd_offset == 1)
					afbd_phase1++;
				else
					afbd_phase2++;
				if (READ_ONCE(cap->pair_offset) < 0) {
					afbd_votes[afbd_offset]++;
					afbd_vote_total++;
				}
			}
		} else if (delta != 1) {
			memset(afbd_votes, 0, sizeof(afbd_votes));
			afbd_vote_total = 0;
		}
		if (READ_ONCE(cap->pair_offset) < 0 &&
		    afbd_vote_total == H713_AFBD_VOTE_WINDOW) {
			for (i = 0; i < 3; i++) {
				if (afbd_votes[i] >= H713_AFBD_VOTE_MIN) {
					WRITE_ONCE(cap->pair_offset, i);
					pr_info("h713-hdmi-v4l2: learned completion phase offset=%u from AFBD votes %u/%u/%u\n",
						i, afbd_votes[0], afbd_votes[1],
						afbd_votes[2]);
					break;
				}
			}
			memset(afbd_votes, 0, sizeof(afbd_votes));
			afbd_vote_total = 0;
		}
		if (READ_ONCE(cap->pair_offset) >= 0)
			continue;
		if (!phase_from_hash)
			continue;
		h713_hash_ring(cap, observed);
		changed = 0;
		active = 0;
		for (i = 0; i < 3; i++) {
			if (observed[i] != previous[i] &&
			    observed[i + 3] != previous[i + 3]) {
				changed++;
				active = i;
			}
		}
		memcpy(previous, observed, sizeof(previous));
		if (delta == 1 && changed == 1) {
			int offset = (active + 3 - vde % 3) % 3;

			WRITE_ONCE(cap->pair_offset, offset);
			pr_info("h713-hdmi-v4l2: learned completion phase offset=%d at VDE=%u pair=%u\n",
				offset, vde, active);
		}
	}
	return 0;
}

static int h713_capture_thread(void *arg)
{
	struct h713_capture *cap = arg;
	struct h713_buffer *buf = NULL;
	u32 previous[6], observed[6];
	unsigned int i, changed, active, pair, delta;
	int pair_offset;
	u32 before_y, before_uv;
	u32 last_vde, vde, last_mode, mode, frame_sequence;
	u8 *dst;
	unsigned long last_activity = jiffies;
	u64 hash_ns = 0, copy_ns = 0, tick, completion_ns;
	unsigned int polls = 0, completion_events = 0, no_buffer = 0;
	unsigned int copies = 0, unstable = 0, delivered = 0;

	tick = ktime_get_ns();
	h713_hash_ring(cap, previous);
	hash_ns += ktime_get_ns() - tick;
	last_vde = h713_trace_word(cap, 0x88);
	last_mode = h713_trace_word(cap, 0x90);
	while (!kthread_should_stop()) {
		if (!buf) {
			buf = h713_take_buffer(cap);
		}
		usleep_range(500, 1000);
		polls++;
		mode = h713_trace_word(cap, 0x90);
		if (mode != last_mode) {
			frames_rejected++;
			WRITE_ONCE(cap->pair_offset, -1);
			pr_warn("h713-hdmi-v4l2: capture mode changed (%u -> %u)\n",
				last_mode, mode);
			if (buf) {
				vb2_buffer_done(&buf->vb.vb2_buf,
						VB2_BUF_STATE_ERROR);
				buf = NULL;
			}
			vb2_queue_error(&cap->queue);
			h713_return_buffers(cap, VB2_BUF_STATE_ERROR);
			break;
		}
		vde = h713_trace_word(cap, 0x88);
		if (vde == last_vde) {
			if (time_after(jiffies, last_activity +
				       msecs_to_jiffies(H713_NO_FRAME_MS))) {
				WRITE_ONCE(cap->pair_offset, -1);
				if (buf) {
					vb2_buffer_done(&buf->vb.vb2_buf,
							VB2_BUF_STATE_ERROR);
					buf = NULL;
				}
				vb2_queue_error(&cap->queue);
				h713_return_buffers(cap, VB2_BUF_STATE_ERROR);
				break;
			}
			continue;
		}
		delta = vde - last_vde;
		completion_ns = ktime_get_ns();
		last_vde = vde;
		last_activity = jiffies;
		completion_events++;
		frames_produced += delta;
		cap->sequence += delta;
		frame_sequence = cap->sequence - 1;
		if (delta > 1)
			frames_overwritten += delta - 1;
		tick = ktime_get_ns();
		h713_hash_ring(cap, observed);
		hash_ns += ktime_get_ns() - tick;
		changed = 0;
		active = 0;
		for (i = 0; i < 3; i++) {
			if (observed[i] != previous[i] &&
			    observed[i + 3] != previous[i + 3]) {
				changed++;
				active = i;
			}
		}
		memcpy(previous, observed, sizeof(previous));
		pair_offset = READ_ONCE(cap->pair_offset);
		if (pair_offset < 0) {
			frames_rejected++;
			continue;
		}
		pair = (vde + pair_offset) % 3;
		if (delta == 1 && changed == 1 && active != pair) {
			frames_rejected++;
			WRITE_ONCE(cap->pair_offset, -1);
			continue;
		}
		if (!buf) {
			no_buffer++;
			frames_overwritten++;
			continue;
		}
		dst = vb2_plane_vaddr(&buf->vb.vb2_buf, 0);
		if (!dst) {
			vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_ERROR);
			buf = NULL;
			continue;
		}

		copies++;
		tick = ktime_get_ns();
		before_y = h713_hash_plane(cap, pair);
		before_uv = h713_hash_plane(cap, pair + 3);
		memcpy(dst, h713_plane(cap, pair), H713_PLANE_SIZE);
		memcpy(dst + H713_PLANE_SIZE, h713_plane(cap, pair + 3),
		       H713_PLANE_SIZE);
		/* Full verification re-reads both planes; sparse mode checks probes. */
		if (before_y != h713_hash_plane(cap, pair) ||
		    before_uv != h713_hash_plane(cap, pair + 3) ||
		    (verify_full &&
		     (memcmp(dst, h713_plane(cap, pair), H713_PLANE_SIZE) ||
		      memcmp(dst + H713_PLANE_SIZE, h713_plane(cap, pair + 3),
			     H713_PLANE_SIZE)))) {
			copy_ns += ktime_get_ns() - tick;
			unstable++;
			frames_rejected++;
			continue;
		}
		copy_ns += ktime_get_ns() - tick;

		vb2_set_plane_payload(&buf->vb.vb2_buf, 0, H713_FRAME_SIZE);
		buf->vb.vb2_buf.timestamp = completion_ns;
		buf->vb.sequence = frame_sequence;
		buf->vb.field = V4L2_FIELD_NONE;
		vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_DONE);
		buf = NULL;
		delivered++;
		frames_delivered++;
	}
	if (buf)
		vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_ERROR);
	pr_info("h713-hdmi-v4l2: stream polls=%u completion_events=%u no_buffer=%u copies=%u unstable=%u delivered=%u produced=%lu overwritten=%lu rejected=%lu hash_us=%llu copy_us=%llu\n",
		polls, completion_events, no_buffer, copies, unstable, delivered,
		frames_produced, frames_overwritten, frames_rejected,
		(unsigned long long)div_u64(hash_ns, 1000),
		(unsigned long long)div_u64(copy_ns, 1000));
	return 0;
}

static int h713_queue_setup(struct vb2_queue *q, unsigned int *nbuffers,
			    unsigned int *nplanes, unsigned int sizes[],
			    struct device *alloc_devs[])
{
	if (*nplanes)
		return sizes[0] < H713_FRAME_SIZE ? -EINVAL : 0;
	*nplanes = 1;
	sizes[0] = H713_FRAME_SIZE;
	return 0;
}

static int h713_buf_prepare(struct vb2_buffer *vb)
{
	if (vb2_plane_size(vb, 0) < H713_FRAME_SIZE)
		return -EINVAL;
	return 0;
}

static void h713_buf_queue(struct vb2_buffer *vb)
{
	struct h713_capture *cap = vb2_get_drv_priv(vb->vb2_queue);
	struct h713_buffer *buf = container_of(vb, struct h713_buffer,
						  vb.vb2_buf);
	unsigned long flags;

	spin_lock_irqsave(&cap->qlock, flags);
	list_add_tail(&buf->list, &cap->buffers);
	spin_unlock_irqrestore(&cap->qlock, flags);
}

static int h713_start_streaming(struct vb2_queue *q, unsigned int count)
{
	struct h713_capture *cap = vb2_get_drv_priv(q);
	int ret;

	cap->sequence = 0;
	frames_produced = 0;
	frames_delivered = 0;
	frames_overwritten = 0;
	frames_rejected = 0;
	cap->worker = kthread_run(h713_capture_thread, cap, "h713-hdmi-v4l2");
	if (!IS_ERR(cap->worker))
		return 0;
	ret = PTR_ERR(cap->worker);
	cap->worker = NULL;
	h713_return_buffers(cap, VB2_BUF_STATE_QUEUED);
	return ret;
}

static void h713_stop_streaming(struct vb2_queue *q)
{
	struct h713_capture *cap = vb2_get_drv_priv(q);

	if (cap->worker) {
		kthread_stop(cap->worker);
		cap->worker = NULL;
	}
	h713_return_buffers(cap, VB2_BUF_STATE_ERROR);
}

static const struct vb2_ops h713_queue_ops = {
	.queue_setup = h713_queue_setup,
	.buf_prepare = h713_buf_prepare,
	.buf_queue = h713_buf_queue,
	.start_streaming = h713_start_streaming,
	.stop_streaming = h713_stop_streaming,
};

static void h713_fixed_format(struct v4l2_format *f)
{
	memset(&f->fmt.pix, 0, sizeof(f->fmt.pix));
	f->fmt.pix.width = H713_WIDTH;
	f->fmt.pix.height = H713_HEIGHT;
	f->fmt.pix.pixelformat = V4L2_PIX_FMT_NV16;
	f->fmt.pix.field = V4L2_FIELD_NONE;
	f->fmt.pix.bytesperline = H713_WIDTH;
	f->fmt.pix.sizeimage = H713_FRAME_SIZE;
	f->fmt.pix.colorspace = V4L2_COLORSPACE_SMPTE170M;
	f->fmt.pix.quantization = V4L2_QUANTIZATION_LIM_RANGE;
}

static int h713_querycap(struct file *file, void *priv,
			 struct v4l2_capability *cap)
{
	strscpy(cap->driver, "h713-hdmi-ring", sizeof(cap->driver));
	strscpy(cap->card, "H713 HDMI1 firmware ring", sizeof(cap->card));
	strscpy(cap->bus_info, "platform:h713-hdmi-ring", sizeof(cap->bus_info));
	return 0;
}

static int h713_enum_fmt(struct file *file, void *priv,
			 struct v4l2_fmtdesc *f)
{
	if (f->index)
		return -EINVAL;
	f->pixelformat = V4L2_PIX_FMT_NV16;
	strscpy(f->description, "NV16 4:2:2", sizeof(f->description));
	return 0;
}

static int h713_enum_framesizes(struct file *file, void *priv,
				struct v4l2_frmsizeenum *f)
{
	if (f->index || f->pixel_format != V4L2_PIX_FMT_NV16)
		return -EINVAL;
	f->type = V4L2_FRMSIZE_TYPE_DISCRETE;
	f->discrete.width = H713_WIDTH;
	f->discrete.height = H713_HEIGHT;
	return 0;
}

static int h713_enum_frameintervals(struct file *file, void *priv,
				    struct v4l2_frmivalenum *f)
{
	if (f->index || f->pixel_format != V4L2_PIX_FMT_NV16 ||
	    f->width != H713_WIDTH || f->height != H713_HEIGHT)
		return -EINVAL;
	f->type = V4L2_FRMIVAL_TYPE_DISCRETE;
	f->discrete.numerator = 1;
	f->discrete.denominator = 60;
	return 0;
}

static int h713_g_parm(struct file *file, void *priv,
		       struct v4l2_streamparm *parm)
{
	if (parm->type != V4L2_BUF_TYPE_VIDEO_CAPTURE)
		return -EINVAL;
	memset(&parm->parm.capture, 0, sizeof(parm->parm.capture));
	parm->parm.capture.capability = V4L2_CAP_TIMEPERFRAME;
	parm->parm.capture.timeperframe.numerator = 1;
	parm->parm.capture.timeperframe.denominator = 60;
	parm->parm.capture.readbuffers = 2;
	return 0;
}

static int h713_s_parm(struct file *file, void *priv,
		       struct v4l2_streamparm *parm)
{
	/* The firmware source interval is fixed; report it back to callers. */
	return h713_g_parm(file, priv, parm);
}

static int h713_enum_input(struct file *file, void *priv,
			   struct v4l2_input *input)
{
	if (input->index)
		return -EINVAL;
	memset(input, 0, sizeof(*input));
	strscpy(input->name, "HDMI1", sizeof(input->name));
	input->type = V4L2_INPUT_TYPE_CAMERA;
	return 0;
}

static int h713_g_input(struct file *file, void *priv, unsigned int *index)
{
	*index = 0;
	return 0;
}

static int h713_s_input(struct file *file, void *priv, unsigned int index)
{
	return index ? -EINVAL : 0;
}

static int h713_g_fmt(struct file *file, void *priv, struct v4l2_format *f)
{
	h713_fixed_format(f);
	return 0;
}

static int h713_try_fmt(struct file *file, void *priv, struct v4l2_format *f)
{
	h713_fixed_format(f);
	return 0;
}

static int h713_s_fmt(struct file *file, void *priv, struct v4l2_format *f)
{
	struct h713_capture *cap = video_drvdata(file);

	if (vb2_is_busy(&cap->queue))
		return -EBUSY;
	h713_fixed_format(f);
	return 0;
}

static const struct v4l2_ioctl_ops h713_ioctl_ops = {
	.vidioc_querycap = h713_querycap,
	.vidioc_enum_fmt_vid_cap = h713_enum_fmt,
	.vidioc_enum_framesizes = h713_enum_framesizes,
	.vidioc_enum_frameintervals = h713_enum_frameintervals,
	.vidioc_enum_input = h713_enum_input,
	.vidioc_g_parm = h713_g_parm,
	.vidioc_s_parm = h713_s_parm,
	.vidioc_g_input = h713_g_input,
	.vidioc_s_input = h713_s_input,
	.vidioc_g_fmt_vid_cap = h713_g_fmt,
	.vidioc_try_fmt_vid_cap = h713_try_fmt,
	.vidioc_s_fmt_vid_cap = h713_s_fmt,
	.vidioc_reqbufs = vb2_ioctl_reqbufs,
	.vidioc_querybuf = vb2_ioctl_querybuf,
	.vidioc_qbuf = vb2_ioctl_qbuf,
	.vidioc_dqbuf = vb2_ioctl_dqbuf,
	.vidioc_streamon = vb2_ioctl_streamon,
	.vidioc_streamoff = vb2_ioctl_streamoff,
};

static const struct v4l2_file_operations h713_fops = {
	.owner = THIS_MODULE,
	.open = v4l2_fh_open,
	.release = vb2_fop_release,
	.read = vb2_fop_read,
	.poll = vb2_fop_poll,
	.unlocked_ioctl = video_ioctl2,
	.mmap = vb2_fop_mmap,
};

static int __init h713_init(void)
{
	struct h713_capture *cap;
	struct vb2_queue *q;
	u8 *firmware;
	int ret;

	if (!of_machine_is_compatible("cstenger,hy200-qz713df-a1"))
		return -ENODEV;

	cap = kzalloc(sizeof(*cap), GFP_KERNEL);
	if (!cap)
		return -ENOMEM;
	cap->pdev = platform_device_register_simple("h713-hdmi-ring", -1,
					    NULL, 0);
	if (IS_ERR(cap->pdev)) {
		ret = PTR_ERR(cap->pdev);
		goto free_cap;
	}
	ret = dma_coerce_mask_and_coherent(&cap->pdev->dev, DMA_BIT_MASK(32));
	if (ret)
		goto unregister_pdev;
	cap->ring = memremap(H713_CARVEOUT, H713_CARVEOUT_SIZE, MEMREMAP_WC);
	if (!cap->ring) {
		ret = -ENOMEM;
		goto unregister_pdev;
	}
	cap->trace = memremap(H713_TRACE, H713_TRACE_SIZE, MEMREMAP_WC);
	if (!cap->trace) {
		ret = -ENOMEM;
		goto unmap_ring;
	}
	if (h713_trace_word(cap, 4) != H713_TRACE_MAGIC ||
	    h713_trace_word(cap, 0x80) != H713_TRACE_CANARY ||
	    h713_trace_word(cap, 0xffc) != H713_TRACE_CANARY) {
		pr_err("h713-hdmi-v4l2: guarded completion mailbox absent\n");
		ret = -ENODEV;
		goto unmap_trace;
	}
	firmware = memremap(H713_MIPS_IMAGE, H713_MIPS_VERIFY_SIZE,
			    MEMREMAP_WC);
	if (!firmware) {
		ret = -ENOMEM;
		goto unmap_trace;
	}
	if (le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x0ba0))) !=
			0x27bdfff8 ||
	    le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x0bac))) !=
			0x3c18ad98 ||
	    le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x0c08))) !=
			0x0ac618eb ||
	    le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x863a4))) !=
			0x0ac402e8) {
		pr_err("h713-hdmi-v4l2: guarded VIncap completion hook absent\n");
		memunmap(firmware);
		ret = -ENODEV;
		goto unmap_trace;
	}
	memunmap(firmware);
	/* This diagnostic platform device has no bound struct device_driver. */
	strscpy(cap->v4l2_dev.name, "h713-hdmi-ring",
		sizeof(cap->v4l2_dev.name));
	ret = v4l2_device_register(&cap->pdev->dev, &cap->v4l2_dev);
	if (ret)
		goto unmap_trace;

	mutex_init(&cap->lock);
	spin_lock_init(&cap->qlock);
	INIT_LIST_HEAD(&cap->buffers);
	cap->pair_offset = -1;
	q = &cap->queue;
	q->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	q->io_modes = VB2_MMAP | VB2_READ;
	q->drv_priv = cap;
	q->buf_struct_size = sizeof(struct h713_buffer);
	q->ops = &h713_queue_ops;
	q->mem_ops = &vb2_dma_contig_memops;
	q->timestamp_flags = V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC;
	q->min_reqbufs_allocation = 2;
	q->lock = &cap->lock;
	q->dev = &cap->pdev->dev;
	ret = vb2_queue_init(q);
	if (ret)
		goto unregister_v4l2;

	strscpy(cap->vdev.name, "H713 HDMI1 ring capture",
		sizeof(cap->vdev.name));
	cap->vdev.v4l2_dev = &cap->v4l2_dev;
	cap->vdev.fops = &h713_fops;
	cap->vdev.ioctl_ops = &h713_ioctl_ops;
	cap->vdev.release = video_device_release_empty;
	cap->vdev.lock = &cap->lock;
	cap->vdev.queue = q;
	cap->vdev.device_caps = V4L2_CAP_VIDEO_CAPTURE |
		V4L2_CAP_STREAMING | V4L2_CAP_READWRITE;
	cap->vdev.vfl_dir = VFL_DIR_RX;
	video_set_drvdata(&cap->vdev, cap);
	ret = video_register_device(&cap->vdev, VFL_TYPE_VIDEO, -1);
	if (ret)
		goto release_queue;
	cap->afbd_pair = ioremap(H713_AFBD_PAIR, H713_AFBD_PAIR_SIZE);
	if (!cap->afbd_pair)
		pr_warn("h713-hdmi-v4l2: AFBD pair telemetry unavailable\n");
	cap->phase_worker = kthread_run(h713_phase_thread, cap,
					"h713-hdmi-phase");
	if (IS_ERR(cap->phase_worker)) {
		ret = PTR_ERR(cap->phase_worker);
		cap->phase_worker = NULL;
		goto unregister_video;
	}
	h713_cap = cap;
	pr_info("h713-hdmi-v4l2: read-only 640x480 NV16 ring at /dev/video%d\n",
		cap->vdev.num);
	return 0;

unregister_video:
	if (cap->afbd_pair)
		iounmap(cap->afbd_pair);
	video_unregister_device(&cap->vdev);
release_queue:
	vb2_queue_release(q);
unregister_v4l2:
	v4l2_device_unregister(&cap->v4l2_dev);
unmap_trace:
	memunmap(cap->trace);
unmap_ring:
	memunmap(cap->ring);
unregister_pdev:
	platform_device_unregister(cap->pdev);
free_cap:
	kfree(cap);
	return ret;
}

static void __exit h713_exit(void)
{
	struct h713_capture *cap = h713_cap;

	if (cap->phase_worker)
		kthread_stop(cap->phase_worker);
	pr_info("h713-hdmi-v4l2: AFBD telemetry samples=%lu invalid=%lu phase=%lu/%lu/%lu last=%08lx/%08lx\n",
		afbd_samples, afbd_invalid, afbd_phase0, afbd_phase1,
		afbd_phase2, afbd_y, afbd_uv);
	if (cap->afbd_pair)
		iounmap(cap->afbd_pair);
	video_unregister_device(&cap->vdev);
	vb2_queue_release(&cap->queue);
	v4l2_device_unregister(&cap->v4l2_dev);
	memunmap(cap->trace);
	memunmap(cap->ring);
	platform_device_unregister(cap->pdev);
	kfree(cap);
}

module_init(h713_init);
module_exit(h713_exit);
MODULE_DESCRIPTION("Read-only V4L2 bridge for H713 HDMI firmware NV16 ring");
MODULE_LICENSE("GPL");
