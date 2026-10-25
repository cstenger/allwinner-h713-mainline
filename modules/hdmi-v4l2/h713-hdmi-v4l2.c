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
#include <linux/string.h>
#include <linux/workqueue.h>

#include <asm/cacheflush.h>

#include <media/v4l2-device.h>
#include <linux/v4l2-dv-timings.h>
#include <media/v4l2-dv-timings.h>
#include <media/v4l2-event.h>
#include <media/v4l2-fh.h>
#include <media/v4l2-ioctl.h>
#include <media/videobuf2-dma-contig.h>
#include <media/videobuf2-v4l2.h>
#include <media/videobuf2-vmalloc.h>

#include "h713-nv12.h"

#include "h713-signal.h"

#define H713_CARVEOUT 0x4bf41000ULL
#define H713_CARVEOUT_SIZE (26 * 1024 * 1024)
#define H713_FIRST_PLANE 0x4c3ef000ULL
#define H713_PLANE_STEP 0x1ff000
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
/*
 * MIPS DRAM below the capture carve-out, where the firmware's device manager
 * and HDMI port objects live (read-mips-port-cache.py). Mapped separately
 * from the ring so the two never alias with different attributes.
 */
#define H713_MIPS_WINDOW 0x4b100000ULL
#define H713_MIPS_WINDOW_END 0x4bf41000ULL
#define H713_MIPS_PHYS_DELTA 0x40000000U	/* MIPS 0x8bxxxxxx = ARM 0x4bxxxxxx */
#define H713_PORT_ROOT 0x4bac1a70ULL
#define H713_MANAGER_VPTR 0x8b201d24
#define H713_HDMIRX_VPTR 0x8b1f5390
#define H713_PORT_LINK_BASE 0x06840000
#define H713_SIG_PERIOD_MS 20
#define H713_BACKSTOP_MS 1000		/* NO_SIGNAL while streaming: EIO after this */
#define H713_MISMATCH_MS 2000		/* locked at another size while streaming */

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
	unsigned int width;
	unsigned int height;
	unsigned int plane_size;
	unsigned int frame_size;
	u32 fourcc;	/* V4L2_PIX_FMT_NV16 (the ring, copied) or _NV12 (converted) */
	struct v4l2_dv_timings timings;	/* configured (G/S_DV_TIMINGS) */
	unsigned int stream_width;	/* geometry the running stream was set up with */
	unsigned int stream_height;
	/* signal state (HDMI panel-source design 10.26) */
	u8 *mips;
	struct delayed_work sig_work;
	spinlock_t sig_lock;
	struct h713_sig sig;
	struct h713_sig_config sig_cfg;
	int sig_last_pair;
	bool sig_moving;
	bool sig_published;		/* video node registered: uevents allowed */
	ktime_t sig_last;
};

static struct h713_capture *h713_cap;

/*
 * A worker that gives up (no completed frame) must not return before
 * kthread_stop(): stop_streaming would then stop an exited, possibly freed,
 * task. Wait for the stop instead.
 */
static void h713_park_until_stopped(void)
{
	while (!kthread_should_stop())
		schedule_timeout_interruptible(HZ / 10);
}
/*
 * -1 (auto): full verification in hook mode; in pair mode the pair re-read
 * after the copy is the guard, because re-reading the whole uncached vb2
 * buffer takes longer than a frame (10.25.5).
 */
static int verify_full = -1;
module_param(verify_full, int, 0444);
MODULE_PARM_DESC(verify_full,
	"Compare full source planes after each copy: 1 yes, 0 sparse probes only, -1 auto (default; off in pair mode)");
static bool phase_from_hash = true;
module_param(phase_from_hash, bool, 0444);
MODULE_PARM_DESC(phase_from_hash,
	"Allow ring-content phase learning (default true); false validates AFBD bootstrap alone");
static bool source_cached = true;
module_param(source_cached, bool, 0444);
MODULE_PARM_DESC(source_cached,
	"Map the firmware frame ring cacheable with explicit invalidation (default true)");
static bool use_vmalloc;
module_param(use_vmalloc, bool, 0444);
MODULE_PARM_DESC(use_vmalloc,
	"Use cached vmalloc capture buffers (default false); false uses DMA-contiguous buffers");
/*
 * Completion source (HDMI panel-source design 10.25, route B). "hook": the
 * VIncap completion trampoline's VDE counter in the trace mailbox (needs the
 * bench U-Boot that installs it). "pair": AFBD +0x320/+0x324, which the
 * capture hardware advances by one slot per frame, so no firmware patching
 * is needed. The pair names the slot being captured, not the finished one:
 * slot k is still written for most of the period after the pair reaches k
 * and k+1 starts within a millisecond, while k-1 holds still for the whole
 * period (ring-timeline, 10.25.5). "auto": hook when its words are present,
 * otherwise pair.
 */
static char *completion = "auto";
module_param(completion, charp, 0444);
MODULE_PARM_DESC(completion, "Frame completion source: auto (default), hook or pair");
static bool pair_mode;
static unsigned int width = 1280;
module_param(width, uint, 0444);
MODULE_PARM_DESC(width, "Geometry before the first lock: 640 or 1280 (default 1280)");
static unsigned int height = 720;
module_param(height, uint, 0444);
MODULE_PARM_DESC(height, "Geometry before the first lock: 480 or 720 (default 720)");
static unsigned int lock_ms = 200;
module_param(lock_ms, uint, 0444);
MODULE_PARM_DESC(lock_ms, "Live at one size this long before LOCKED (default 200)");
static unsigned int hold_ms = 100;
module_param(hold_ms, uint, 0444);
MODULE_PARM_DESC(hold_ms, "LOCKED -> HOLD after this long without the locked signal (default 100)");
static unsigned int grace_ms = 1500;
module_param(grace_ms, uint, 0444);
MODULE_PARM_DESC(grace_ms, "HOLD -> no signal after this long (default 1500)");
static bool allow_480p;
module_param(allow_480p, bool, 0444);
MODULE_PARM_DESC(allow_480p, "Lock and show 640x480 (default false: unsupported, console stays)");
static unsigned long sig_transitions;
static unsigned long sig_bad_guard;
module_param(sig_transitions, ulong, 0444);
module_param(sig_bad_guard, ulong, 0444);
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

static void h713_invalidate_plane(struct h713_capture *cap,
				  unsigned int index)
{
	unsigned long start;

	if (!source_cached)
		return;
	start = (unsigned long)h713_plane(cap, index);
	dcache_inval_poc(start, start + cap->plane_size);
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
	unsigned int offset;

	h713_invalidate_plane(cap, index);
	for (offset = 0x10000; offset < cap->plane_size; offset += 0x20000)
		crc = crc32_le(crc, plane + offset,
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

/*
 * Copy (NV16) or convert (NV12) ring slot `pair` into dst. The source planes
 * are hashed before and after; full verification re-reads the source. Returns
 * 0, or -EAGAIN when the slot changed under the copy.
 */
static int h713_copy_frame(struct h713_capture *cap, u8 *dst,
			   unsigned int pair)
{
	const u8 *y = h713_plane(cap, pair), *c = h713_plane(cap, pair + 3);
	u32 before_y = h713_hash_plane(cap, pair);
	u32 before_uv = h713_hash_plane(cap, pair + 3);
	bool nv12 = cap->fourcc == V4L2_PIX_FMT_NV12;

	if (nv12) {
		h713_nv16_to_nv12(dst, y, c, cap->width, cap->height);
	} else {
		memcpy(dst, y, cap->plane_size);
		memcpy(dst + cap->plane_size, c, cap->plane_size);
	}
	if (before_y != h713_hash_plane(cap, pair) ||
	    before_uv != h713_hash_plane(cap, pair + 3))
		return -EAGAIN;
	if (!verify_full || (verify_full < 0 && pair_mode))
		return 0;
	if (nv12)
		return h713_nv12_matches(dst, y, c, cap->width, cap->height) ?
		       0 : -EAGAIN;
	return memcmp(dst, y, cap->plane_size) ||
	       memcmp(dst + cap->plane_size, c, cap->plane_size) ? -EAGAIN : 0;
}

/*
 * HDMI port 1 as the firmware publishes it, read with the same guards as
 * tools/hdmi/read-mips-port-cache.py: every pointer must be aligned and inside
 * the mapped MIPS window, and the device manager, receiver and port must carry
 * the expected vptrs, port id and link base. Any miss is an invalid sample,
 * which the state machine treats as no signal.
 */
static bool h713_mips_word(struct h713_capture *cap, u32 mips_addr, u32 *val)
{
	u64 phys = (u64)mips_addr - H713_MIPS_PHYS_DELTA;

	if (mips_addr & 3 || mips_addr < H713_MIPS_PHYS_DELTA ||
	    phys < H713_MIPS_WINDOW || phys + 4 > H713_MIPS_WINDOW_END)
		return false;
	*val = le32_to_cpu(READ_ONCE(*(__le32 *)(cap->mips + (phys - H713_MIPS_WINDOW))));
	return true;
}

static bool h713_read_port(struct h713_capture *cap, struct h713_sig_sample *s)
{
	u32 manager, hdmi, port, v, size_w, size_h;

	manager = le32_to_cpu(READ_ONCE(*(__le32 *)(cap->mips +
					(H713_PORT_ROOT - H713_MIPS_WINDOW))));
	if (!manager || !h713_mips_word(cap, manager, &v) || v != H713_MANAGER_VPTR)
		return false;
	/* +0x18 is the real THDMIRx; +0x1c is THDMIDummy. */
	if (!h713_mips_word(cap, manager + 0x18, &hdmi) || !hdmi ||
	    !h713_mips_word(cap, hdmi, &v) || v != H713_HDMIRX_VPTR)
		return false;
	if (!h713_mips_word(cap, hdmi + 0xec, &port) || !port ||
	    !h713_mips_word(cap, port + 0x530, &v))	/* whole object in the window */
		return false;
	if (!h713_mips_word(cap, port + 0x518, &v) || ((v >> 24) & 0xff) != 1)
		return false;	/* port id byte at +0x51b */
	if (!h713_mips_word(cap, port + 0x520, &v) || v != H713_PORT_LINK_BASE)
		return false;
	if (!h713_mips_word(cap, port + 0xc0, &s->port_state) ||
	    !h713_mips_word(cap, port + 0x4c, &size_w) ||	/* hactive at +0x4e */
	    !h713_mips_word(cap, port + 0x48, &size_h))		/* vactive at +0x48 */
		return false;
	s->width = size_w >> 16;
	s->height = size_h & 0xffff;
	return true;
}

static const struct v4l2_dv_timings h713_timings_720p = V4L2_DV_BT_CEA_1280X720P60;
static const struct v4l2_dv_timings h713_timings_480p = V4L2_DV_BT_DMT_640X480P60;

static const struct v4l2_dv_timings *h713_mode_timings(unsigned int w,
							unsigned int h)
{
	if (w == 1280 && h == 720)
		return &h713_timings_720p;
	if (w == 640 && h == 480)
		return &h713_timings_480p;
	return NULL;
}

static unsigned int h713_frame_size(struct h713_capture *cap, u32 fourcc);

/* Caller holds cap->lock and the queue is idle. */
static void h713_set_geometry(struct h713_capture *cap, unsigned int w,
			      unsigned int h)
{
	cap->timings = *h713_mode_timings(w, h);
	cap->width = w;
	cap->height = h;
	cap->plane_size = w * h;
	cap->frame_size = h713_frame_size(cap, cap->fourcc);
}

static void h713_sig_snapshot(struct h713_capture *cap, struct h713_sig *out)
{
	unsigned long flags;

	spin_lock_irqsave(&cap->sig_lock, flags);
	*out = cap->sig;
	spin_unlock_irqrestore(&cap->sig_lock, flags);
}

static int h713_sig_format(const struct h713_sig *sig, char *buf, size_t len)
{
	if (sig->state == H713_SIG_NONE || sig->state == H713_SIG_ACQUIRING)
		return scnprintf(buf, len, "%s\n", h713_sig_name(sig->state));
	return scnprintf(buf, len, "%s %ux%u\n", h713_sig_name(sig->state),
			 sig->width, sig->height);
}

static ssize_t signal_show(struct device *dev, struct device_attribute *attr,
			   char *buf)
{
	struct h713_capture *cap = dev_get_drvdata(dev);
	struct h713_sig sig;

	if (!cap)
		return -ENODEV;
	h713_sig_snapshot(cap, &sig);
	return h713_sig_format(&sig, buf, PAGE_SIZE);
}
static DEVICE_ATTR_RO(signal);

static struct attribute *h713_attrs[] = {
	&dev_attr_signal.attr,
	NULL,
};
ATTRIBUTE_GROUPS(h713);

/* One sample: port object + ring motion, then a state-machine step. */
static unsigned int h713_sig_sample_step(struct h713_capture *cap)
{
	struct h713_sig_sample s = { 0 };
	ktime_t now = ktime_get();
	unsigned int dt = clamp_t(s64, ktime_ms_delta(now, cap->sig_last), 1, 200);
	unsigned long flags;
	unsigned int ev;
	int idx;

	cap->sig_last = now;
	s.valid = h713_read_port(cap, &s);
	if (!s.valid)
		sig_bad_guard++;
	idx = h713_afbd_pair_index(cap);
	if (idx >= 0) {	/* a torn read keeps the previous answer */
		cap->sig_moving = cap->sig_last_pair >= 0 && idx != cap->sig_last_pair;
		cap->sig_last_pair = idx;
	}
	s.moving = cap->sig_moving;
	spin_lock_irqsave(&cap->sig_lock, flags);
	ev = h713_sig_step(&cap->sig, &cap->sig_cfg, &s, dt);
	spin_unlock_irqrestore(&cap->sig_lock, flags);
	return ev;
}

static void h713_sig_publish(struct h713_capture *cap, unsigned int ev)
{
	struct h713_sig sig;
	char state[48], mode[32], *envp[] = { state, mode, NULL };

	h713_sig_snapshot(cap, &sig);
	sig_transitions++;
	/* A new lock moves the format while nobody streams (G_FMT follows). */
	if (sig.state == H713_SIG_LOCKED && h713_mode_timings(sig.width, sig.height)) {
		mutex_lock(&cap->lock);
		if (!vb2_is_busy(&cap->queue))
			h713_set_geometry(cap, sig.width, sig.height);
		mutex_unlock(&cap->lock);
	}
	if (ev & H713_SIG_EV_SOURCE) {
		static const struct v4l2_event src_ev = {
			.type = V4L2_EVENT_SOURCE_CHANGE,
			.u.src_change.changes = V4L2_EVENT_SRC_CH_RESOLUTION,
		};

		v4l2_event_queue(&cap->vdev, &src_ev);
	}
	pr_info("h713-hdmi-v4l2: signal %s %ux%u%s\n", h713_sig_name(sig.state),
		sig.width, sig.height,
		ev & H713_SIG_EV_SOURCE ? " (source change)" : "");
	snprintf(state, sizeof(state), "H713_HDMI_SIGNAL=%s", h713_sig_name(sig.state));
	snprintf(mode, sizeof(mode), "H713_HDMI_MODE=%ux%u", sig.width, sig.height);
	kobject_uevent_env(&cap->vdev.dev.kobj, KOBJ_CHANGE, envp);
}

static void h713_sig_work(struct work_struct *work)
{
	struct h713_capture *cap = container_of(to_delayed_work(work),
						 struct h713_capture, sig_work);
	unsigned int ev = h713_sig_sample_step(cap);

	if (ev && cap->sig_published)
		h713_sig_publish(cap, ev);
	schedule_delayed_work(&cap->sig_work, msecs_to_jiffies(H713_SIG_PERIOD_MS));
}

/*
 * Coldplug: sample synchronously before the video node exists, so its "add"
 * uevent already carries a settled state (design 4). Stops early once the
 * state can no longer be ACQUIRING-in-progress.
 */
static void h713_sig_settle(struct h713_capture *cap)
{
	unsigned int i, limit = (lock_ms + hold_ms) / H713_SIG_PERIOD_MS + 4;
	struct h713_sig sig;

	cap->sig_last = ktime_get();
	for (i = 0; i < limit; i++) {
		msleep(H713_SIG_PERIOD_MS);
		h713_sig_sample_step(cap);
		h713_sig_snapshot(cap, &sig);
		if (sig.state == H713_SIG_LOCKED || sig.state == H713_SIG_UNSUPPORTED)
			break;
	}
	if (sig.state == H713_SIG_LOCKED)
		h713_set_geometry(cap, sig.width, sig.height);
	pr_info("h713-hdmi-v4l2: initial signal %s %ux%u after %u samples\n",
		h713_sig_name(sig.state), sig.width, sig.height, i + 1);
}

static void h713_fill_black(struct h713_capture *cap, u8 *dst)
{
	unsigned int chroma = cap->fourcc == V4L2_PIX_FMT_NV12 ?
			      cap->plane_size / 2 : cap->plane_size;

	memset(dst, 16, cap->plane_size);
	memset(dst + cap->plane_size, 128, chroma);
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
		if (h713_copy_frame(cap, dst, pair)) {
			copy_ns += ktime_get_ns() - tick;
			unstable++;
			frames_rejected++;
			continue;
		}
		copy_ns += ktime_get_ns() - tick;

		vb2_set_plane_payload(&buf->vb.vb2_buf, 0, cap->frame_size);
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
	h713_park_until_stopped();
	return 0;
}

/*
 * Pair-driven capture: the AFBD capture pair names the slot the capture
 * hardware completed last. A change means a new complete frame; it is copied
 * while capture writes the next slot, and the hash bracketing in
 * h713_copy_frame rejects a copy the writer reached. A torn pair read
 * (Y and C from different slots) is treated as no change.
 */
/*
 * Route B stream thread. Follows the signal state:
 *   LOCKED at the stream's size: copy each finished ring slot;
 *   HOLD, or LOCKED at another size (the consumer has a SOURCE_CHANGE to
 *   act on): black frames at about 60 Hz, so the panel shows black, not a
 *   frozen frame, and the pipeline stays up;
 *   anything else for H713_BACKSTOP_MS (or another size for
 *   H713_MISMATCH_MS): vb2_queue_error(), so a consumer that missed the
 *   systemd stop gets EIO (design 3).
 */
static int h713_capture_thread_pair(void *arg)
{
	struct h713_capture *cap = arg;
	struct h713_buffer *buf = NULL;
	unsigned int polls = 0, completion_events = 0, no_buffer = 0;
	unsigned int copies = 0, unstable = 0, delivered = 0, black = 0;
	u64 copy_ns = 0, tick, completion_ns, last_black = 0;
	unsigned long bad_since = 0, mismatch_since = 0;
	int last = h713_afbd_pair_index(cap), idx;
	struct h713_sig sig;
	bool at_size, ok;
	u8 *dst;

	while (!kthread_should_stop()) {
		if (!buf)
			buf = h713_take_buffer(cap);
		usleep_range(500, 1000);
		polls++;
		h713_sig_snapshot(cap, &sig);
		at_size = sig.width == cap->stream_width &&
			  sig.height == cap->stream_height;
		ok = sig.state == H713_SIG_LOCKED && at_size;
		if (sig.state != H713_SIG_LOCKED && sig.state != H713_SIG_HOLD) {
			if (!bad_since)
				bad_since = jiffies;
		} else {
			bad_since = 0;
		}
		if (sig.state == H713_SIG_LOCKED && !at_size) {
			if (!mismatch_since)
				mismatch_since = jiffies;
		} else {
			mismatch_since = 0;
		}
		if ((bad_since && time_after(jiffies, bad_since +
				msecs_to_jiffies(H713_BACKSTOP_MS))) ||
		    (mismatch_since && time_after(jiffies, mismatch_since +
				msecs_to_jiffies(H713_MISMATCH_MS)))) {
			pr_warn("h713-hdmi-v4l2: signal %s %ux%u while streaming %ux%u; ending the stream\n",
				h713_sig_name(sig.state), sig.width, sig.height,
				cap->stream_width, cap->stream_height);
			if (buf) {
				vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_ERROR);
				buf = NULL;
			}
			vb2_queue_error(&cap->queue);
			h713_return_buffers(cap, VB2_BUF_STATE_ERROR);
			break;
		}
		if (!ok) {
			/* Track the pair so the first frame after HOLD is a fresh one. */
			idx = h713_afbd_pair_index(cap);
			if (idx >= 0)
				last = idx;
			if (bad_since || !buf)
				continue;
			completion_ns = ktime_get_ns();
			if (completion_ns - last_black < 16666667)
				continue;
			last_black = completion_ns;
			dst = vb2_plane_vaddr(&buf->vb.vb2_buf, 0);
			if (!dst)
				continue;
			h713_fill_black(cap, dst);
			black++;
			goto deliver;
		}
		idx = h713_afbd_pair_index(cap);
		if (idx < 0 || idx == last)
			continue;
		last = idx;
		completion_ns = ktime_get_ns();
		completion_events++;
		frames_produced++;
		if (!buf) {
			no_buffer++;
			frames_overwritten++;
			cap->sequence++;
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
		/*
		 * The finished frame is the slot before the one being captured.
		 * It holds still until the pair moves on, so a copy that ends
		 * with the pair unchanged is whole.
		 */
		if (h713_copy_frame(cap, dst, (idx + 2) % 3) ||
		    h713_afbd_pair_index(cap) != idx) {
			copy_ns += ktime_get_ns() - tick;
			unstable++;
			frames_rejected++;
			cap->sequence++;
			continue;
		}
		copy_ns += ktime_get_ns() - tick;
deliver:
		vb2_set_plane_payload(&buf->vb.vb2_buf, 0, cap->frame_size);
		buf->vb.vb2_buf.timestamp = completion_ns;
		buf->vb.sequence = cap->sequence++;
		buf->vb.field = V4L2_FIELD_NONE;
		vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_DONE);
		buf = NULL;
		delivered++;
		frames_delivered++;
	}
	if (buf)
		vb2_buffer_done(&buf->vb.vb2_buf, VB2_BUF_STATE_ERROR);
	pr_info("h713-hdmi-v4l2: pair stream polls=%u completions=%u no_buffer=%u copies=%u unstable=%u delivered=%u black=%u copy_us=%llu\n",
		polls, completion_events, no_buffer, copies, unstable, delivered,
		black, (unsigned long long)div_u64(copy_ns, 1000));
	h713_park_until_stopped();
	return 0;
}

static int h713_queue_setup(struct vb2_queue *q, unsigned int *nbuffers,
			    unsigned int *nplanes, unsigned int sizes[],
			    struct device *alloc_devs[])
{
	struct h713_capture *cap = vb2_get_drv_priv(q);

	if (*nplanes)
		return sizes[0] < cap->frame_size ? -EINVAL : 0;
	*nplanes = 1;
	sizes[0] = cap->frame_size;
	return 0;
}

static int h713_buf_prepare(struct vb2_buffer *vb)
{
	struct h713_capture *cap = vb2_get_drv_priv(vb->vb2_queue);

	if (vb2_plane_size(vb, 0) < cap->frame_size)
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
	struct h713_sig sig;
	int ret;

	h713_sig_snapshot(cap, &sig);
	if (sig.state != H713_SIG_LOCKED || sig.width != cap->width ||
	    sig.height != cap->height) {
		h713_return_buffers(cap, VB2_BUF_STATE_QUEUED);
		return -ENOLINK;
	}
	cap->stream_width = cap->width;
	cap->stream_height = cap->height;
	cap->sequence = 0;
	frames_produced = 0;
	frames_delivered = 0;
	frames_overwritten = 0;
	frames_rejected = 0;
	cap->worker = kthread_run(pair_mode ? h713_capture_thread_pair :
				  h713_capture_thread, cap, "h713-hdmi-v4l2");
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

static unsigned int h713_frame_size(struct h713_capture *cap, u32 fourcc)
{
	return fourcc == V4L2_PIX_FMT_NV12 ? cap->plane_size * 3 / 2 :
					     cap->plane_size * 2;
}

/* NV16 is the ring itself; NV12 is converted (copy Y, average CbCr pairs). */
static void h713_fixed_format(struct h713_capture *cap, struct v4l2_format *f)
{
	u32 fourcc = f->fmt.pix.pixelformat == V4L2_PIX_FMT_NV12 ||
		     f->fmt.pix.pixelformat == V4L2_PIX_FMT_NV16 ?
		     f->fmt.pix.pixelformat : cap->fourcc;

	memset(&f->fmt.pix, 0, sizeof(f->fmt.pix));
	f->fmt.pix.width = cap->width;
	f->fmt.pix.height = cap->height;
	f->fmt.pix.pixelformat = fourcc;
	f->fmt.pix.field = V4L2_FIELD_NONE;
	f->fmt.pix.bytesperline = cap->width;
	f->fmt.pix.sizeimage = h713_frame_size(cap, fourcc);
	f->fmt.pix.colorspace = cap->height == 720 ? V4L2_COLORSPACE_REC709 :
		V4L2_COLORSPACE_SMPTE170M;
	f->fmt.pix.ycbcr_enc = V4L2_YCBCR_ENC_DEFAULT;
	f->fmt.pix.quantization = V4L2_QUANTIZATION_LIM_RANGE;
	f->fmt.pix.xfer_func = V4L2_XFER_FUNC_DEFAULT;
}

static int h713_querycap(struct file *file, void *priv,
			 struct v4l2_capability *cap)
{
	strscpy(cap->driver, "h713-hdmi-ring", sizeof(cap->driver));
	strscpy(cap->card, "H713 HDMI-in", sizeof(cap->card));
	strscpy(cap->bus_info, "platform:h713-hdmi-ring", sizeof(cap->bus_info));
	return 0;
}

static int h713_enum_fmt(struct file *file, void *priv,
			 struct v4l2_fmtdesc *f)
{
	if (f->index > 1)
		return -EINVAL;
	f->pixelformat = f->index ? V4L2_PIX_FMT_NV12 : V4L2_PIX_FMT_NV16;
	strscpy(f->description, f->index ? "NV12 4:2:0 (converted)" :
		"NV16 4:2:2", sizeof(f->description));
	return 0;
}

static int h713_enum_framesizes(struct file *file, void *priv,
				struct v4l2_frmsizeenum *f)
{
	struct h713_capture *cap = video_drvdata(file);

	if (f->index || (f->pixel_format != V4L2_PIX_FMT_NV16 &&
			 f->pixel_format != V4L2_PIX_FMT_NV12))
		return -EINVAL;
	f->type = V4L2_FRMSIZE_TYPE_DISCRETE;
	f->discrete.width = cap->width;
	f->discrete.height = cap->height;
	return 0;
}

static int h713_enum_frameintervals(struct file *file, void *priv,
				    struct v4l2_frmivalenum *f)
{
	struct h713_capture *cap = video_drvdata(file);

	if (f->index || (f->pixel_format != V4L2_PIX_FMT_NV16 &&
			 f->pixel_format != V4L2_PIX_FMT_NV12) ||
	    f->width != cap->width || f->height != cap->height)
		return -EINVAL;
	f->type = V4L2_FRMIVAL_TYPE_DISCRETE;
	f->discrete = v4l2_calc_timeperframe(&cap->timings);
	return 0;
}

static int h713_g_parm(struct file *file, void *priv,
		       struct v4l2_streamparm *parm)
{
	struct h713_capture *cap = video_drvdata(file);

	if (parm->type != V4L2_BUF_TYPE_VIDEO_CAPTURE)
		return -EINVAL;
	memset(&parm->parm.capture, 0, sizeof(parm->parm.capture));
	parm->parm.capture.capability = V4L2_CAP_TIMEPERFRAME;
	parm->parm.capture.timeperframe = v4l2_calc_timeperframe(&cap->timings);
	parm->parm.capture.readbuffers = 2;
	return 0;
}

static int h713_s_parm(struct file *file, void *priv,
		       struct v4l2_streamparm *parm)
{
	/* The source sets the interval; report it back to callers. */
	return h713_g_parm(file, priv, parm);
}

static int h713_enum_input(struct file *file, void *priv,
			   struct v4l2_input *input)
{
	struct h713_capture *cap = video_drvdata(file);
	struct h713_sig sig;

	if (input->index)
		return -EINVAL;
	memset(input, 0, sizeof(*input));
	strscpy(input->name, "HDMI1", sizeof(input->name));
	input->type = V4L2_INPUT_TYPE_CAMERA;
	input->capabilities = V4L2_IN_CAP_DV_TIMINGS;
	h713_sig_snapshot(cap, &sig);
	if (sig.state == H713_SIG_NONE)
		input->status = V4L2_IN_ST_NO_SIGNAL;
	else if (sig.state == H713_SIG_ACQUIRING || sig.state == H713_SIG_UNSUPPORTED)
		input->status = V4L2_IN_ST_NO_SYNC;
	return 0;
}

/* -ENOLINK no signal, -ENOLCK acquiring, -ERANGE a size the route can't show. */
static int h713_query_dv_timings(struct file *file, void *priv,
				 struct v4l2_dv_timings *timings)
{
	struct h713_capture *cap = video_drvdata(file);
	const struct v4l2_dv_timings *t;
	struct h713_sig sig;

	h713_sig_snapshot(cap, &sig);
	switch (sig.state) {
	case H713_SIG_NONE:
		return -ENOLINK;
	case H713_SIG_ACQUIRING:
		return -ENOLCK;
	case H713_SIG_UNSUPPORTED:
		return -ERANGE;
	default:
		break;
	}
	t = h713_mode_timings(sig.width, sig.height);
	if (!t)
		return -ERANGE;
	*timings = *t;
	return 0;
}

static int h713_g_dv_timings(struct file *file, void *priv,
			     struct v4l2_dv_timings *timings)
{
	struct h713_capture *cap = video_drvdata(file);

	*timings = cap->timings;
	return 0;
}

static bool h713_timings_allowed(const struct v4l2_dv_timings *t)
{
	return v4l2_match_dv_timings(t, &h713_timings_720p, 0, false) ||
	       (allow_480p && v4l2_match_dv_timings(t, &h713_timings_480p, 0, false));
}

static int h713_s_dv_timings(struct file *file, void *priv,
			     struct v4l2_dv_timings *timings)
{
	struct h713_capture *cap = video_drvdata(file);

	if (!h713_timings_allowed(timings))
		return -EINVAL;
	if (v4l2_match_dv_timings(timings, &cap->timings, 0, false))
		return 0;
	if (vb2_is_busy(&cap->queue))
		return -EBUSY;
	h713_set_geometry(cap, timings->bt.width, timings->bt.height);
	return 0;
}

static int h713_enum_dv_timings(struct file *file, void *priv,
				struct v4l2_enum_dv_timings *timings)
{
	if (timings->pad)
		return -EINVAL;
	if (timings->index == 0)
		timings->timings = h713_timings_720p;
	else if (timings->index == 1 && allow_480p)
		timings->timings = h713_timings_480p;
	else
		return -EINVAL;
	return 0;
}

static int h713_dv_timings_cap(struct file *file, void *priv,
			       struct v4l2_dv_timings_cap *dv_cap)
{
	if (dv_cap->pad)
		return -EINVAL;
	memset(dv_cap->reserved, 0, sizeof(dv_cap->reserved));
	dv_cap->type = V4L2_DV_BT_656_1120;
	dv_cap->bt.min_width = allow_480p ? 640 : 1280;
	dv_cap->bt.max_width = 1280;
	dv_cap->bt.min_height = allow_480p ? 480 : 720;
	dv_cap->bt.max_height = 720;
	dv_cap->bt.min_pixelclock = allow_480p ? 25175000 : 74250000;
	dv_cap->bt.max_pixelclock = 74250000;
	dv_cap->bt.standards = V4L2_DV_BT_STD_CEA861 | V4L2_DV_BT_STD_DMT;
	dv_cap->bt.capabilities = V4L2_DV_BT_CAP_PROGRESSIVE;
	return 0;
}

static int h713_subscribe_event(struct v4l2_fh *fh,
				const struct v4l2_event_subscription *sub)
{
	if (sub->type == V4L2_EVENT_SOURCE_CHANGE)
		return v4l2_src_change_event_subscribe(fh, sub);
	return -EINVAL;
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
	struct h713_capture *cap = video_drvdata(file);

	f->fmt.pix.pixelformat = cap->fourcc;
	h713_fixed_format(cap, f);
	return 0;
}

static int h713_try_fmt(struct file *file, void *priv, struct v4l2_format *f)
{
	struct h713_capture *cap = video_drvdata(file);

	h713_fixed_format(cap, f);
	return 0;
}

static int h713_s_fmt(struct file *file, void *priv, struct v4l2_format *f)
{
	struct h713_capture *cap = video_drvdata(file);

	if (vb2_is_busy(&cap->queue))
		return -EBUSY;
	h713_fixed_format(cap, f);
	cap->fourcc = f->fmt.pix.pixelformat;
	cap->frame_size = f->fmt.pix.sizeimage;
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
	.vidioc_expbuf = vb2_ioctl_expbuf,
	.vidioc_query_dv_timings = h713_query_dv_timings,
	.vidioc_g_dv_timings = h713_g_dv_timings,
	.vidioc_s_dv_timings = h713_s_dv_timings,
	.vidioc_enum_dv_timings = h713_enum_dv_timings,
	.vidioc_dv_timings_cap = h713_dv_timings_cap,
	.vidioc_subscribe_event = h713_subscribe_event,
	.vidioc_unsubscribe_event = v4l2_event_unsubscribe,
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
	u32 hook0, hook1, hook2, hook3;
	int ret;

	if (!of_machine_is_compatible("cstenger,hy200-qz713df-a1"))
		return -ENODEV;
	if (!((width == 640 && height == 480) ||
	      (width == 1280 && height == 720))) {
		pr_err("h713-hdmi-v4l2: supported sizes are 640x480 and 1280x720\n");
		return -EINVAL;
	}

	cap = kzalloc(sizeof(*cap), GFP_KERNEL);
	if (!cap)
		return -ENOMEM;
	/*
	 * The "signal" attribute lives on this platform device, the video
	 * node's parent, and exists before the node's "add" uevent (udev reads
	 * it through ATTRS{signal}).
	 */
	cap->pdev = platform_device_alloc("h713-hdmi-ring", -1);
	if (!cap->pdev) {
		ret = -ENOMEM;
		goto free_cap;
	}
	cap->pdev->dev.groups = h713_groups;
	platform_set_drvdata(cap->pdev, cap);
	spin_lock_init(&cap->sig_lock);
	h713_sig_init(&cap->sig);
	cap->sig_cfg = (struct h713_sig_config){ lock_ms, hold_ms, grace_ms, allow_480p };
	cap->sig_last_pair = -1;
	INIT_DELAYED_WORK(&cap->sig_work, h713_sig_work);
	ret = platform_device_add(cap->pdev);
	if (ret) {
		platform_device_put(cap->pdev);
		goto free_cap;
	}
	cap->fourcc = V4L2_PIX_FMT_NV16;
	h713_set_geometry(cap, width, height);
	ret = dma_coerce_mask_and_coherent(&cap->pdev->dev, DMA_BIT_MASK(32));
	if (ret)
		goto unregister_pdev;
	cap->ring = memremap(H713_CARVEOUT, H713_CARVEOUT_SIZE,
			     source_cached ? MEMREMAP_WB : MEMREMAP_WC);
	if (!cap->ring) {
		ret = -ENOMEM;
		goto unregister_pdev;
	}
	cap->trace = memremap(H713_TRACE, H713_TRACE_SIZE, MEMREMAP_WC);
	if (!cap->trace) {
		ret = -ENOMEM;
		goto unmap_ring;
	}
	cap->mips = memremap(H713_MIPS_WINDOW, H713_MIPS_WINDOW_END - H713_MIPS_WINDOW,
			     MEMREMAP_WC);
	if (!cap->mips) {
		ret = -ENOMEM;
		goto unmap_trace;
	}
	if (strcmp(completion, "auto") && strcmp(completion, "hook") &&
	    strcmp(completion, "pair")) {
		pr_err("h713-hdmi-v4l2: completion must be auto, hook or pair\n");
		ret = -EINVAL;
		goto unmap_mips;
	}
	pair_mode = !strcmp(completion, "pair");
	if (!pair_mode) {
		bool hook_ok;

		firmware = memremap(H713_MIPS_IMAGE, H713_MIPS_VERIFY_SIZE,
				    MEMREMAP_WC);
		if (!firmware) {
			ret = -ENOMEM;
			goto unmap_mips;
		}
		hook0 = le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x0ba0)));
		hook1 = le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x0bac)));
		hook2 = le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x0c08)));
		hook3 = le32_to_cpu(READ_ONCE(*(__le32 *)(firmware + 0x863a4)));
		memunmap(firmware);
		hook_ok = hook0 == 0x27bdfff8 && hook1 == 0x3c18ad98 &&
			  hook2 == 0x0ac618eb && hook3 == 0x0ac402e8 &&
			  h713_trace_word(cap, 4) == H713_TRACE_MAGIC &&
			  h713_trace_word(cap, 0x80) == H713_TRACE_CANARY &&
			  h713_trace_word(cap, 0xffc) == H713_TRACE_CANARY;
		if (!hook_ok && !strcmp(completion, "hook")) {
			pr_err("h713-hdmi-v4l2: guarded VIncap completion hook absent: %08x/%08x/%08x/%08x\n",
			       hook0, hook1, hook2, hook3);
			ret = -ENODEV;
			goto unmap_mips;
		}
		pair_mode = !hook_ok;
	}
	cap->afbd_pair = ioremap(H713_AFBD_PAIR, H713_AFBD_PAIR_SIZE);
	if (!cap->afbd_pair) {
		pr_err("h713-hdmi-v4l2: AFBD pair unavailable\n");
		ret = -ENOMEM;
		goto unmap_mips;
	}
	pr_info("h713-hdmi-v4l2: completion from the %s\n",
		pair_mode ? "AFBD capture pair" : "VIncap hook");
	/* This diagnostic platform device has no bound struct device_driver. */
	strscpy(cap->v4l2_dev.name, "h713-hdmi-ring",
		sizeof(cap->v4l2_dev.name));
	ret = v4l2_device_register(&cap->pdev->dev, &cap->v4l2_dev);
	if (ret)
		goto unmap_pair;

	mutex_init(&cap->lock);
	spin_lock_init(&cap->qlock);
	INIT_LIST_HEAD(&cap->buffers);
	cap->pair_offset = -1;
	q = &cap->queue;
	q->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	q->io_modes = VB2_MMAP | VB2_READ | VB2_DMABUF;
	q->drv_priv = cap;
	q->buf_struct_size = sizeof(struct h713_buffer);
	q->ops = &h713_queue_ops;
	q->mem_ops = use_vmalloc ? &vb2_vmalloc_memops :
		&vb2_dma_contig_memops;
	q->timestamp_flags = V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC;
	q->min_reqbufs_allocation = 2;
	q->lock = &cap->lock;
	q->dev = &cap->pdev->dev;
	ret = vb2_queue_init(q);
	if (ret)
		goto unregister_v4l2;
	pr_info("h713-hdmi-v4l2: using %s capture buffers\n",
		use_vmalloc ? "cached vmalloc" : "DMA-contiguous");
	strscpy(cap->vdev.name, "h713-hdmi-in", sizeof(cap->vdev.name));
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
	h713_sig_settle(cap);
	ret = video_register_device(&cap->vdev, VFL_TYPE_VIDEO, -1);
	if (ret)
		goto release_queue;
	cap->sig_published = true;
	schedule_delayed_work(&cap->sig_work, msecs_to_jiffies(H713_SIG_PERIOD_MS));
	if (!pair_mode) {
		cap->phase_worker = kthread_run(h713_phase_thread, cap,
						"h713-hdmi-phase");
		if (IS_ERR(cap->phase_worker)) {
			ret = PTR_ERR(cap->phase_worker);
			cap->phase_worker = NULL;
			goto unregister_video;
		}
	}
	h713_cap = cap;
	pr_info("h713-hdmi-v4l2: read-only %ux%u NV16/NV12 %s ring at /dev/video%d\n",
		cap->width, cap->height, source_cached ? "cacheable" :
		"write-combining", cap->vdev.num);
	return 0;

unregister_video:
	cancel_delayed_work_sync(&cap->sig_work);
	video_unregister_device(&cap->vdev);
release_queue:
	vb2_queue_release(q);
unregister_v4l2:
	v4l2_device_unregister(&cap->v4l2_dev);
unmap_pair:
	iounmap(cap->afbd_pair);
unmap_mips:
	memunmap(cap->mips);
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

	cancel_delayed_work_sync(&cap->sig_work);
	if (cap->phase_worker)
		kthread_stop(cap->phase_worker);
	pr_info("h713-hdmi-v4l2: AFBD telemetry samples=%lu invalid=%lu phase=%lu/%lu/%lu last=%08lx/%08lx\n",
		afbd_samples, afbd_invalid, afbd_phase0, afbd_phase1,
		afbd_phase2, afbd_y, afbd_uv);
	video_unregister_device(&cap->vdev);
	vb2_queue_release(&cap->queue);
	v4l2_device_unregister(&cap->v4l2_dev);
	if (cap->afbd_pair)
		iounmap(cap->afbd_pair);
	memunmap(cap->mips);
	memunmap(cap->trace);
	memunmap(cap->ring);
	platform_device_unregister(cap->pdev);
	kfree(cap);
}

module_init(h713_init);
module_exit(h713_exit);
MODULE_DESCRIPTION("Read-only V4L2 bridge for H713 HDMI firmware NV16 ring");
MODULE_LICENSE("GPL");
