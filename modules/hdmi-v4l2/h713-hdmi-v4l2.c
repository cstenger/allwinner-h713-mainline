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
	u8 *ring;
	u32 sequence;
};

static struct h713_capture *h713_cap;

static u8 *h713_plane(struct h713_capture *cap, unsigned int index)
{
	return cap->ring + H713_FIRST_PLANE - H713_CARVEOUT +
	       H713_PLANE_STEP * index;
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

static int h713_capture_thread(void *arg)
{
	struct h713_capture *cap = arg;
	struct h713_buffer *buf = NULL;
	u32 previous[6], observed[6];
	int last_pair = -1;
	unsigned int i, changed, active, pair;
	u32 before_y, before_uv;
	u8 *dst;
	unsigned long last_activity = jiffies;

	h713_hash_ring(cap, previous);
	while (!kthread_should_stop()) {
		if (!buf) {
			buf = h713_take_buffer(cap);
			if (buf)
				last_activity = jiffies;
		}
		msleep(2);
		h713_hash_ring(cap, observed);
		if (memcmp(previous, observed, sizeof(previous)))
			last_activity = jiffies;
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
		if (buf && time_after(jiffies, last_activity +
					msecs_to_jiffies(H713_NO_FRAME_MS))) {
			vb2_queue_error(&cap->queue);
			vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_ERROR);
			buf = NULL;
			h713_return_buffers(cap, VB2_BUF_STATE_ERROR);
			while (!kthread_should_stop())
				msleep(20);
			break;
		}
		if (!buf || changed != 1)
			continue;

		/* Once the next pair changes, its predecessor is complete. */
		pair = (active + 2) % 3;
		if (pair == last_pair)
			continue;
		dst = vb2_plane_vaddr(&buf->vb.vb2_buf, 0);
		if (!dst) {
			vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_ERROR);
			buf = NULL;
			continue;
		}

		before_y = h713_hash_plane(cap, pair);
		before_uv = h713_hash_plane(cap, pair + 3);
		memcpy(dst, h713_plane(cap, pair), H713_PLANE_SIZE);
		memcpy(dst + H713_PLANE_SIZE, h713_plane(cap, pair + 3),
		       H713_PLANE_SIZE);
		/* The second read must equal the first and leave probes unchanged. */
		if (memcmp(dst, h713_plane(cap, pair), H713_PLANE_SIZE) ||
		    memcmp(dst + H713_PLANE_SIZE, h713_plane(cap, pair + 3),
			   H713_PLANE_SIZE) ||
		    before_y != h713_hash_plane(cap, pair) ||
		    before_uv != h713_hash_plane(cap, pair + 3))
			continue;

		vb2_set_plane_payload(&buf->vb.vb2_buf, 0, H713_FRAME_SIZE);
		buf->vb.vb2_buf.timestamp = ktime_get_ns();
		buf->vb.sequence = cap->sequence++;
		buf->vb.field = V4L2_FIELD_NONE;
		vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_DONE);
		buf = NULL;
		last_pair = pair;
	}
	if (buf)
		vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_ERROR);
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
	.vidioc_enum_input = h713_enum_input,
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
	/* This diagnostic platform device has no bound struct device_driver. */
	strscpy(cap->v4l2_dev.name, "h713-hdmi-ring",
		sizeof(cap->v4l2_dev.name));
	ret = v4l2_device_register(&cap->pdev->dev, &cap->v4l2_dev);
	if (ret)
		goto unmap_ring;

	mutex_init(&cap->lock);
	spin_lock_init(&cap->qlock);
	INIT_LIST_HEAD(&cap->buffers);
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
	h713_cap = cap;
	pr_info("h713-hdmi-v4l2: read-only 640x480 NV16 ring at /dev/video%d\n",
		cap->vdev.num);
	return 0;

release_queue:
	vb2_queue_release(q);
unregister_v4l2:
	v4l2_device_unregister(&cap->v4l2_dev);
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

	video_unregister_device(&cap->vdev);
	vb2_queue_release(&cap->queue);
	v4l2_device_unregister(&cap->v4l2_dev);
	memunmap(cap->ring);
	platform_device_unregister(cap->pdev);
	kfree(cap);
}

module_init(h713_init);
module_exit(h713_exit);
MODULE_DESCRIPTION("Read-only V4L2 bridge for H713 HDMI firmware NV16 ring");
MODULE_LICENSE("GPL");
