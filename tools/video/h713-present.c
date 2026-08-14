// SPDX-License-Identifier: GPL-2.0
/*
 * h713-present -- put frames on the H713 panel from Linux, through the AFBD
 * scanout path U-Boot already proved.
 *
 * Runs ON THE TARGET. Build with: gcc -O2 -o h713-present h713-present.c
 *
 * This is the Linux-side twin of h713_disp's fb-anim / fb-anim-db. It writes
 * a frame into the reserved scanout buffer, points the AFBD source register at
 * it, and commits using the exact order recovered from the stock ge2d_dev.ko:
 *
 *     clear the write-one-to-clear IRQ status  (+0x168)
 *     set bit 0 of the channel control         (+0x140)
 *     write literal 1 to the channel ready     (+0x144)
 *     poll for the completion bit              (+0x168 BIT(1))
 *
 * The `bar` mode is deliberately synthetic and decoder-independent: it is the
 * controlled reference that a decoder fault cannot masquerade as. Get `bar`
 * working before believing anything about a decoded frame.
 *
 * WHY THIS WORKS WITHOUT A KERNEL DRIVER: CONFIG_STRICT_DEVMEM=y blocks
 * /dev/mem on System RAM, but uboot-scanout@6c100000 is a `no-map` reservation,
 * so it is carved out of System RAM and appears as a top-level /proc/iomem
 * entry. page_is_ram() is false for it, and devmem_is_allowed() therefore
 * permits the mapping.
 *
 * CONSEQUENCE, and it matters for M3: because pfn_is_map_memory() is false,
 * arm64's phys_mem_access_prot() maps it pgprot_noncached -- Device-nGnRnE, not
 * write-combining. Bulk stores to it are slow and do not burst. `--time`
 * reports the achieved fill bandwidth so this is measured, not assumed.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define W               1280
#define H               720
#define FB_BYTES        (W * H * 4)             /* ARGB8888 */
#define FB_FRONT        0x6c100000UL
#define FB_BACK         0x6c500000UL
#define FB_WINDOW       0x800000UL              /* both buffers, per patch 0024 */

#define AFBD_BASE       0x05600000UL
#define AFBD_CTRL       0x140
#define AFBD_READY      0x144
#define AFBD_STATUS     0x168
#define AFBD_STRIDE     0x170
#define AFBD_SRC        0x178
#define AFBD_DIRTY      0x6c

/*
 * The real vblank signal, from the vendor's dec_irq_query() (patch 0013,
 * decd_hw.c). Its base is regs->workaround = afbd + 0x60, and it reads +96 and
 * +100, so 0x056000c0 and 0x056000c4; it requires bit 0 in BOTH, then acks by
 * writing bit 0 back to +0xc0. A register dump taken while the panel was live
 * showed 0x056000c0 = 0x00000001, so the bit is real and set.
 *
 * This matters because the vendor swaps buffers INSIDE the vsync interrupt --
 * dec_vsync_handler -> dec_frame_manager_handle_vsync -> sync_cb, which is
 * dec_sync_frame_to_hardware -- rather than by polling a completion bit the way
 * this tool has been doing. AFBD_STATUS bit 1 was assumed to be vsync and never
 * verified. If it is not, every swap lands at an arbitrary point in the scan,
 * which is exactly the shape of the measured tearing and explains why waiting
 * an extra frame (EXTRA_VSYNC, verified to halve the frame rate) did not help:
 * more waiting on the wrong signal is still the wrong phase.
 */
#define AFBD_IRQ_ST0    0xc0
#define AFBD_IRQ_ST1    0xc4

/*
 * CCU, always clocked, so reading it is safe from any state. Bit 31 is the
 * AFBD clock gate. The display blocks wedge the interconnect when read while
 * gated, so this is the precondition check that keeps a cold run from hanging
 * the board -- the same reason h713_disp's scanrate/regscan refuse cold.
 */
#define CCU_AFBD_CLK    0x02001dc0UL

static volatile uint32_t *regs, *ccu;
static volatile uint32_t *fb_front, *fb_back;

static uint32_t rd(volatile uint32_t *base, unsigned off) { return base[off / 4]; }
static void wr(volatile uint32_t *base, unsigned off, uint32_t v) { base[off / 4] = v; }

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

/* Returns wait time in us, or -1 if the completion bit never arrived. */
static double commit(void)
{
	uint32_t pending = rd(regs, AFBD_STATUS);
	uint32_t ctrl;
	double t0;

	if (pending)
		wr(regs, AFBD_STATUS, pending);         /* write-one-to-clear */

	ctrl = rd(regs, AFBD_CTRL);
	wr(regs, AFBD_CTRL, ctrl | 1u);
	wr(regs, AFBD_READY, 1);

	t0 = now_ms();
	while (now_ms() - t0 < 50.0) {
		if (rd(regs, AFBD_STATUS) & 2u)
			return (now_ms() - t0) * 1000.0;
		usleep(100);
	}
	return -1.0;
}

/*
 * Barrier before the flip, and it is not paranoia.
 *
 * leak-test proved writes to the OFF-SCREEN buffer never reach the panel:
 * 1799 full-screen repaints at ~450/s while the other buffer was live, and the
 * capture is solid green for the whole 8 s window. So the tearing is not our
 * writes landing on a live surface.
 *
 * What leak-test never does is SWAP to the buffer it just wrote -- which is
 * exactly what every torn run does. That isolates the remaining candidate: the
 * fill's stores may not have drained to DRAM when the AFBD_SRC write reaches
 * the display block. The framebuffer is written through a plain (non-volatile)
 * pointer so the compiler can vectorise it, while the register goes through a
 * volatile one to a different peripheral; nothing orders the two. If the
 * display starts reading the new buffer while the tail of the fill is still in
 * flight, the raster sees a half-written surface -- which is precisely the
 * "rows with no bar" signal, and it would be immune to every timing fix tried
 * so far, because the problem is not WHEN we flip.
 *
 * BARRIER=0 disables it so the A/B can be measured rather than assumed.
 */
static int use_barrier = 1;

static void flip_to(unsigned long phys)
{
	if (use_barrier)
		__sync_synchronize();           /* dsb: drain the fill first */
	wr(regs, AFBD_SRC, (uint32_t)phys);
}

/*
 * Poll the vendor's vsync condition and ack it, mirroring dec_irq_query().
 * Returns the wait in ms, or -1 on timeout. Reading a byte register through the
 * 32-bit accessor would straddle neighbours, so use the byte view.
 */
static double wait_vblank(void)
{
	volatile uint8_t *b = (volatile uint8_t *)regs;
	double t0 = now_ms();

	/*
	 * 0xc0 ONLY, not the vendor's 0xc0 && 0xc4.
	 *
	 * dec_irq_query() requires bit 0 in both. 0xc4 is the HARDWARE
	 * INTERRUPT ENABLE: dec_reg_enable() writes it via
	 * `regs->workaround + 100`, and workaround is afbd + 0x60, so
	 * 0x60 + 100 = 0xc4. Nothing in this tool ever calls that, so the bit
	 * stays 0, the AND is never true, and every wait timed out (300 misses
	 * out of 300). The vendor's condition is simply "status set AND
	 * interrupt enabled" -- correct for a handler, wrong for a poller.
	 *
	 * Polling 0xc0 alone is right here precisely BECAUSE we never enable
	 * the interrupt: the status bit ticks either way.
	 *
	 * 0xc0 bit 0 on its own is MEASURED to be the vblank event: acked and
	 * re-polled 20 times it fires at 16.74 ms intervals, 19 of them
	 * identical, against the panel's computed 16.75 ms period (0.06%).
	 * That is the real vsync this tool has been missing -- AFBD_STATUS
	 * bit 1 was only ever assumed to be one.
	 */
	while (now_ms() - t0 < 50.0) {
		if (b[AFBD_IRQ_ST0] & 1u) {
			b[AFBD_IRQ_ST0] = b[AFBD_IRQ_ST0] | 1u;   /* ack */
			return now_ms() - t0;
		}
	}
	return -1.0;
}

/*
 * BT.709 for >=720p, BT.601 below it. Integer math, limited range in.
 *
 * PERFORMANCE, learned the hard way (2026-08-09): the destination MUST NOT be
 * `volatile`. The first version wrote straight into the mmap'd framebuffer
 * through a volatile pointer, which forbids the compiler from vectorising or
 * merging stores -- one scalar store per pixel, 921600 times. That measured
 * 84 ms/frame, i.e. 11.95 fps on a 30 fps clip.
 *
 * Converting into an ordinary cached staging buffer lets the compiler
 * autovectorise, and a single bulk copy then moves it to the framebuffer at the
 * ~307 MB/s the `bar` fill demonstrates. Splitting rows across cores is nearly
 * free on top: three of the four A53s are idle during playback.
 */
struct conv_job {
	const uint8_t *y, *uv;
	uint32_t *out;
	int w, ystride, uvstride, bt709, row0, row1;
};

static void *conv_worker(void *arg)
{
	const struct conv_job *j = arg;
	const int kr = j->bt709 ? 459 : 409;    /* 1.793 / 1.596 in Q8 */
	const int kb = j->bt709 ? 541 : 516;    /* 2.115 / 2.017 */
	const int kgu = j->bt709 ? 55 : 100;
	const int kgv = j->bt709 ? 136 : 208;
	int x, row;

	for (row = j->row0; row < j->row1; row++) {
		const uint8_t *yr = j->y + (size_t)row * j->ystride;
		const uint8_t *cr = j->uv + (size_t)(row >> 1) * j->uvstride;
		uint32_t *o = j->out + (size_t)row * W;

		for (x = 0; x < j->w; x++) {
			int c = yr[x] - 16;
			int d = cr[(x & ~1)] - 128;
			int e = cr[(x & ~1) + 1] - 128;
			int r = (298 * c + kr * e + 128) >> 8;
			int g = (298 * c - kgu * d - kgv * e + 128) >> 8;
			int b = (298 * c + kb * d + 128) >> 8;

			r = r < 0 ? 0 : (r > 255 ? 255 : r);
			g = g < 0 ? 0 : (g > 255 ? 255 : g);
			b = b < 0 ? 0 : (b > 255 ? 255 : b);
			o[x] = 0xff000000u | (r << 16) | (g << 8) | b;
		}
	}
	return NULL;
}

/*
 * Tunable because the obvious value is not the best one. With 4 threads the
 * conversion saturates all four A53s and starves the decoder feeding our pipe:
 * a reader thread added on top moved 2 ms out of "read" and straight into
 * "convert" for no net gain (28.33 -> 28.14 fps). Leaving a core for GStreamer
 * may beat using every core for pixels. Set CONV_THREADS=n to sweep it.
 */
#define CONV_THREADS_MAX 4
static int conv_threads = CONV_THREADS_MAX;
static int extra_vsync;
/*
 * Bar step in px/frame, default 16. BAR_STEP=0 gives a MOVING-BAR-FREE
 * control that still does the identical per-frame work: same two-phase
 * fill, same buffer alternation, same vblank swap, same rate -- only the
 * motion is removed.
 *
 * This exists because the negative control used so far was a STATIC panel
 * with nothing running (0.74%), while every test run had a bar sweeping at
 * ~955 px/s. An LCD's pixel response smears a moving bar, and the metric
 * needs redness > 40 over a contiguous run, so motion alone can drop rows
 * below threshold. If BAR_STEP=0 also reads ~26%, the tearing figure is a
 * motion artefact and the presentation path is fine.
 */
static int bar_step = 16;

static void conv_threads_init(void)
{
	const char *e = getenv("CONV_THREADS");
	int v = e ? atoi(e) : 0;

	if (v >= 1 && v <= CONV_THREADS_MAX)
		conv_threads = v;
}

static void nv12_to_argb(const uint8_t *y, const uint8_t *uv, int w, int h,
			 int ystride, int uvstride, uint32_t *out, int bt709)
{
	pthread_t th[CONV_THREADS_MAX];
	struct conv_job jobs[CONV_THREADS_MAX];
	int started[CONV_THREADS_MAX];
	const int CONV_THREADS = conv_threads;
	int n, rows = h / CONV_THREADS;

	for (n = 0; n < CONV_THREADS; n++) {
		jobs[n] = (struct conv_job){
			.y = y, .uv = uv, .out = out, .w = w,
			.ystride = ystride, .uvstride = uvstride, .bt709 = bt709,
			.row0 = n * rows,
			.row1 = (n == CONV_THREADS - 1) ? h : (n + 1) * rows,
		};
		/*
		 * Splitting at any row is safe, even an odd one: every row
		 * derives its own chroma row as uv + (row >> 1) * uvstride, so
		 * the halves of a chroma pair never share mutable state.
		 */
		started[n] = (pthread_create(&th[n], NULL, conv_worker, &jobs[n]) == 0);
		if (!started[n])
			conv_worker(&jobs[n]);      /* degrade to inline */
	}
	for (n = 0; n < CONV_THREADS; n++)
		if (started[n])
			pthread_join(th[n], NULL);
}

/*
 * Frame reader, on its own thread.
 *
 * Reading was the single largest per-frame cost once the conversion was fixed
 * (14.8 ms of a ~35 ms frame) and it is pure waiting -- the decoder filling a
 * pipe. Overlapping it with convert/blit/commit hides nearly all of it. The VE
 * decodes this content at 268 fps, so the reader is never the limit; it just
 * has to run ahead.
 *
 * A short ring rather than a single handoff, so a hiccup in either stage does
 * not immediately stall the other.
 */
#define RING_SLOTS 3

struct reader {
	int fd;
	size_t fsz;
	uint8_t *slot[RING_SLOTS];
	int filled[RING_SLOTS];
	int head, tail;                 /* producer writes head, consumer takes tail */
	int eof, stop;
	pthread_mutex_t m;
	pthread_cond_t space, item;
};

static void *reader_thread(void *arg)
{
	struct reader *r = arg;

	for (;;) {
		size_t got = 0;
		int slot;

		pthread_mutex_lock(&r->m);
		while (r->filled[r->head] && !r->stop)
			pthread_cond_wait(&r->space, &r->m);
		if (r->stop) { pthread_mutex_unlock(&r->m); return NULL; }
		slot = r->head;
		pthread_mutex_unlock(&r->m);

		while (got < r->fsz) {
			ssize_t k = read(r->fd, r->slot[slot] + got, r->fsz - got);
			if (k <= 0)
				break;
			got += (size_t)k;
		}

		pthread_mutex_lock(&r->m);
		if (got != r->fsz) {
			r->eof = 1;
			pthread_cond_broadcast(&r->item);
			pthread_mutex_unlock(&r->m);
			return NULL;
		}
		r->filled[slot] = 1;
		r->head = (r->head + 1) % RING_SLOTS;
		pthread_cond_signal(&r->item);
		pthread_mutex_unlock(&r->m);
	}
}

/* Returns the next frame buffer, or NULL at end of stream. */
static uint8_t *reader_get(struct reader *r)
{
	uint8_t *p;

	pthread_mutex_lock(&r->m);
	while (!r->filled[r->tail] && !r->eof)
		pthread_cond_wait(&r->item, &r->m);
	if (!r->filled[r->tail]) { pthread_mutex_unlock(&r->m); return NULL; }
	p = r->slot[r->tail];
	pthread_mutex_unlock(&r->m);
	return p;
}

static void reader_release(struct reader *r)
{
	pthread_mutex_lock(&r->m);
	r->filled[r->tail] = 0;
	r->tail = (r->tail + 1) % RING_SLOTS;
	pthread_cond_signal(&r->space);
	pthread_mutex_unlock(&r->m);
}

/*
 * TWO PHASE, and it must stay that way: blue the whole surface, THEN draw the
 * bar. tools/display/tear-measure.py scores "rows with no bar at all", which
 * only exists as a signal because of this ordering -- a raster passing through
 * mid-fill finds a surface that has been blued but not yet barred.
 *
 * A single-pass fill (bar-or-blue per pixel, which this was originally) leaves
 * every row carrying a bar at either the old or the new position, so the metric
 * reads 0% whether or not the panel tears. That is a meaningless pass, not a
 * clean one.
 *
 * Rolling shutter can shift the bar but can never delete it, which is why this
 * metric is specific to single-buffered corruption and the step size is not.
 */
static void fill_bar(volatile uint32_t *fb, int x0)
{
	uint32_t *p = (uint32_t *)fb;           /* non-volatile: let it vectorise */
	int y, k;
	size_t i;

	for (i = 0; i < (size_t)W * H; i++)
		p[i] = 0xff0000ffu;                     /* phase 1: all blue */

	for (y = 0; y < H; y++) {
		uint32_t *row = p + (size_t)y * W;
		for (k = 0; k < 64; k++)                /* phase 2: the bar */
			row[(x0 + k) % W] = 0xffff0000u;
	}
}

/*
 * AFBD global config, from the vendor sunxi_decd driver (patch 0013,
 * dec_reg_video_channel_attr_config), whose `base` is the AFBD block base:
 *
 *   +0x10 bit 4  clear = AFBC-compressed source, set = linear
 *   +0x11        format selector. Vendor writes 1 (compressed), 6 (10-bit
 *                YUV420 linear), 7 (AV1 10-bit linear). Ours runs 0 for the
 *                ARGB8888 path that works today.
 *   +0x13        0x03 on the linear path
 *   +0x40/+0x44  plane strides   +0x48/+0x4c  luma / chroma plane geometry
 *
 * The 8-bit NV12 code is NOT derivable from that driver: its only
 * format-to-register function handles the two 10-bit modes and has no caller
 * in the port. Hence this sweep.
 */
#define AFBD_G_FLAGS    0x10
#define AFBD_G_FORMAT   0x11
#define AFBD_G_LINEAR   0x13
#define AFBD_G_STRIDE0  0x40
#define AFBD_G_STRIDE1  0x44
/*
 * The latch. The vendor's regs->workaround is afbd + 0x60, and
 * dec_reg_set_dirty() writes workaround + 12 -- so afbd + 0x6c. Every vendor
 * config change is followed by writing 1 here; dec_reg_bypass_config() does it
 * inline after touching a single byte.
 *
 * Without it the format byte at +0x11 sits in a shadow register and never
 * reaches the hardware. Measured: setting format+stride without the latch left
 * the fetch at 4 bytes/pixel while the stride change DID take, so four source
 * rows packed into each display row -- the picture repeated 4x horizontally in
 * greyscale (test_39/IMG_0659.jpeg).
 */


static volatile uint8_t *regs8;

/*
 * dump_channel -- the video-channel half of the block, which the one-line `regs`
 * dump does not cover.
 *
 * It exists because sunxi-decd and this tool program DIFFERENT halves of the
 * same registers. The driver writes the plane addresses (0x70/0x84, via its
 * regs->workaround = afbd + 0x60) and the dirty latch, and nothing else: its
 * only format-programming function, dec_reg_video_channel_attr_config(), has no
 * caller anywhere in the port, and it handles only the two 10-bit modes even if
 * one were added. So after a DECD FRAME_SUBMIT the plane registers should carry
 * the submitted addresses while the format byte still carries whatever U-Boot's
 * logo left behind. Printing both halves is what tells those two apart, and it
 * settles by readout what would otherwise be a question about what the panel
 * looked like.
 */
static void dump_channel(void)
{
	static const unsigned y_off[] = { 0x70, 0x74, 0x78, 0x7c };
	static const unsigned c_off[] = { 0x84, 0x88, 0x8c, 0x90 };
	unsigned i;

	printf("AFBD cfg   flags=%08x fmt=%u linear=%02x stride0=%08x stride1=%08x\n",
	       rd(regs, AFBD_G_FLAGS), regs8[AFBD_G_FORMAT], regs8[AFBD_G_LINEAR],
	       rd(regs, AFBD_G_STRIDE0), rd(regs, AFBD_G_STRIDE1));
	printf("AFBD ch    enable=%02x mux=%02x dirty=%08x irq=%08x/%08x\n",
	       regs8[0x60], regs8[0x68], rd(regs, AFBD_DIRTY),
	       rd(regs, AFBD_IRQ_ST0), rd(regs, AFBD_IRQ_ST1));
	for (i = 0; i < 4; i++)
		printf("AFBD plane%u Y=%08x C=%08x info=%08x\n", i,
		       rd(regs, y_off[i]), rd(regs, c_off[i]),
		       rd(regs, 0x98 + 4 * i));
}

/*
 * fmt -- program ONLY the format and strides, then latch and commit.
 *
 * This is the bridge, and more importantly the isolating control, for the DECD
 * test: sunxi-decd supplies the plane addresses via FRAME_SUBMIT and this
 * supplies the format the driver never programs. It deliberately does NOT touch
 * 0x70/0x84, so if the panel comes up after this and only after this, the gap is
 * named exactly -- the driver's half worked and the format byte was the whole
 * of what was missing.
 *
 * Same register set yuv2 writes minus the plane addresses, because yuv2 is the
 * configuration known to put NV12 on this panel; a minimal delta can come later,
 * once something works.
 *
 * dwell 0 means set and exit WITHOUT restoring -- for leaving the format in
 * place while something else runs. Any other dwell restores, on the yuvtry
 * principle that a wrong code must not outlive the run that tried it.
 */
static int fmt_bridge(unsigned code, unsigned stride, unsigned dwell_ms)
{
	uint32_t s_10, s_s0, s_s1, s_str;
	double us;

	s_10 = rd(regs, AFBD_G_FLAGS);          /* covers bytes 0x10..0x13 */
	s_s0 = rd(regs, AFBD_G_STRIDE0);
	s_s1 = rd(regs, AFBD_G_STRIDE1);
	s_str = rd(regs, AFBD_STRIDE);
	printf("saved: 0x10=%08x s0=%08x s1=%08x stride=%08x\n",
	       s_10, s_s0, s_s1, s_str);

	regs8[AFBD_G_FORMAT] = (uint8_t)code;
	wr(regs, AFBD_G_STRIDE0, stride);
	wr(regs, AFBD_G_STRIDE1, stride);
	wr(regs, AFBD_STRIDE, stride);
	wr(regs, AFBD_DIRTY, 1);
	us = commit();
	printf("fmt %u stride %u: commit %s %.0f us\n", code, stride,
	       us < 0 ? "TIMEOUT" : "ok", us < 0 ? 0 : us);
	dump_channel();

	if (!dwell_ms) {
		printf("left in place (dwell 0) -- restore with a reboot or 'fmt %u %u 1'\n",
		       (unsigned)(s_10 >> 8) & 0xff, s_s0);
		return us < 0 ? 1 : 0;
	}

	printf("holding %u ms -- look at the panel\n", dwell_ms);
	usleep(dwell_ms * 1000);

	wr(regs, AFBD_G_STRIDE0, s_s0);
	wr(regs, AFBD_G_STRIDE1, s_s1);
	wr(regs, AFBD_STRIDE, s_str);
	wr(regs, AFBD_G_FLAGS, s_10);
	wr(regs, AFBD_DIRTY, 1);
	commit();
	printf("restored\n");
	return us < 0 ? 1 : 0;
}

/*
 * info -- rewrite the four per-slot video-info-page addresses, latch, commit.
 *
 * This is a single-variable probe against sunxi-decd. Its linear path computes
 * the info address as video_info_buffer_init() = y_phys + 4096, which for our
 * y_phys lands 4 KB INSIDE the luma plane -- the "info page" the hardware reads
 * is pixel data. Measured on hardware: info=6c101000 with Y=6c100000.
 *
 * That is the only non-zero register DECD writes that the working userspace path
 * (yuv2) never wrote: yuv2 left these at 0 and got colour, DECD sets them and we
 * get the 4x-repeat greyscale of the old test_43 failure. Zeroing them isolates
 * it. The offsets are dec_reg_set_address()'s info table, workaround + {56, 60,
 * 64, 68} with workaround = afbd + 0x60.
 */
static int info_probe(uint32_t val, unsigned dwell_ms)
{
	static const unsigned off[] = { 0x98, 0x9c, 0xa0, 0xa4 };
	uint32_t save[4];
	unsigned i;
	double us;

	for (i = 0; i < 4; i++)
		save[i] = rd(regs, off[i]);
	printf("saved info: %08x %08x %08x %08x\n",
	       save[0], save[1], save[2], save[3]);

	for (i = 0; i < 4; i++)
		wr(regs, off[i], val);
	wr(regs, AFBD_DIRTY, 1);
	us = commit();
	printf("info <- %08x: commit %s %.0f us\n", val,
	       us < 0 ? "TIMEOUT" : "ok", us < 0 ? 0 : us);
	dump_channel();

	if (!dwell_ms)
		return us < 0 ? 1 : 0;

	printf("holding %u ms -- look at the panel\n", dwell_ms);
	usleep(dwell_ms * 1000);
	for (i = 0; i < 4; i++)
		wr(regs, off[i], save[i]);
	wr(regs, AFBD_DIRTY, 1);
	commit();
	printf("restored\n");
	return us < 0 ? 1 : 0;
}

/*
 * load -- copy a raw NV12 frame into the scanout buffer and exit, touching no
 * registers at all.
 *
 * The sweep for the real format field needs the pixels in place while the
 * registers stay exactly as the vendor's DE-block replay left them, so that a
 * following `poke` changes ONE field against an otherwise untouched vendor
 * configuration. Neither yuv2 nor fmt can do that: both program format, strides
 * and (for yuv2) plane addresses as a package, which is three variables at once
 * and is how this file talked itself into a false positive before.
 *
 * With the vendor's stride of 5120 still in place a 1280x720 NV12 frame covers
 * the top 270 rows as ARGB garbage -- the test_53 picture. That is the expected
 * starting point, not a fault.
 */
static int load_raw_frame(const char *path)
{
	size_t fsz = (size_t)W * H * 3 / 2;
	uint8_t *buf;
	size_t got = 0;
	int fd2;

	if (fsz > FB_WINDOW) {
		fprintf(stderr, "frame larger than the mapped window\n");
		return 1;
	}
	buf = malloc(fsz);
	fd2 = open(path, O_RDONLY);
	if (fd2 < 0 || !buf) {
		perror("load");
		free(buf);
		if (fd2 >= 0)
			close(fd2);
		return 1;
	}
	while (got < fsz) {
		ssize_t r = read(fd2, buf + got, fsz - got);

		if (r <= 0)
			break;
		got += (size_t)r;
	}
	close(fd2);
	if (got != fsz) {
		fprintf(stderr, "short frame: %zu of %zu\n", got, fsz);
		free(buf);
		return 1;
	}

	memcpy((void *)fb_front, buf, fsz);
	__sync_synchronize();
	free(buf);
	printf("loaded %s: %zu bytes -> %#lx, registers untouched\n",
	       path, fsz, FB_FRONT);
	dump_channel();
	return 0;
}

/*
 * poke -- one 32-bit write into the AFBD window, latched and committed.
 *
 * For bisecting the rest of what DECD writes and userspace does not (the aux
 * bytes at +0x80/+0x94, the field bytes at +0xa8). Restores unless dwell is 0.
 */
static int poke(unsigned off, uint32_t val, unsigned dwell_ms)
{
	uint32_t save;
	double us;

	if (off > 0xffc || (off & 3)) {
		fprintf(stderr, "offset must be 32-bit aligned and < 0x1000\n");
		return 2;
	}
	save = rd(regs, off);
	wr(regs, off, val);
	wr(regs, AFBD_DIRTY, 1);
	us = commit();
	printf("poke +%#05x: %08x -> %08x, commit %s %.0f us\n", off, save, val,
	       us < 0 ? "TIMEOUT" : "ok", us < 0 ? 0 : us);
	dump_channel();

	if (!dwell_ms)
		return us < 0 ? 1 : 0;

	printf("holding %u ms -- look at the panel\n", dwell_ms);
	usleep(dwell_ms * 1000);
	wr(regs, off, save);
	wr(regs, AFBD_DIRTY, 1);
	commit();
	printf("restored +%#05x = %08x\n", off, save);
	return us < 0 ? 1 : 0;
}

/*
 * Try one candidate format code with a real NV12 frame, then put every register
 * back exactly as found. Self-restoring on purpose: a wrong code shows garbage,
 * and without the restore the panel would stay broken until a U-Boot reboot.
 */
static int yuvtry(const char *path, unsigned code, unsigned dwell_ms)
{
	uint32_t save_10, save_stride, save_src, save_s0, save_s1;
	size_t fsz = (size_t)W * H * 3 / 2;
	uint8_t *buf = malloc(fsz);
	int fd2 = open(path, O_RDONLY);
	size_t got = 0;
	double us;

	if (fd2 < 0 || !buf) { perror("yuvtry"); return 1; }
	while (got < fsz) {
		ssize_t r = read(fd2, buf + got, fsz - got);
		if (r <= 0) break;
		got += (size_t)r;
	}
	close(fd2);
	if (got != fsz) { fprintf(stderr, "short frame\n"); return 1; }

	save_10 = rd(regs, AFBD_G_FLAGS);
	save_stride = rd(regs, AFBD_STRIDE);
	save_src = rd(regs, AFBD_SRC);
	save_s0 = rd(regs, AFBD_G_STRIDE0);
	save_s1 = rd(regs, AFBD_G_STRIDE1);
	printf("saved: +0x10=%08x stride=%08x src=%08x s0=%08x s1=%08x\n",
	       save_10, save_stride, save_src, save_s0, save_s1);

	/* NV12 into the front buffer: Y plane then interleaved chroma. */
	memcpy((void *)fb_front, buf, fsz);

	regs8[AFBD_G_FORMAT] = (uint8_t)code;
	/*
	 * BOTH stride registers. The channel stride at +0x170 is not the only
	 * one: the global plane strides at +0x40/+0x44 came up holding 1920,
	 * and at that pitch a 1280-wide 8-bit luma plane consumes 720 * 1920 =
	 * 1382400 bytes -- the whole NV12 frame -- so the lower part of the
	 * picture is chroma being read as luma. Setting only +0x170 produced
	 * exactly that: correct at the bottom, a grey band, black above.
	 */
	wr(regs, AFBD_STRIDE, W);                  /* luma stride, 1 byte/px */
	wr(regs, AFBD_G_STRIDE0, W);
	wr(regs, AFBD_G_STRIDE1, W);               /* NV12 chroma pitch == luma */
	wr(regs, AFBD_DIRTY, 1);                   /* latch the shadow config */
	flip_to(FB_FRONT);
	us = commit();
	printf("code %2u: +0x10=%08x stride=%08x s0=%08x s1=%08x commit %s %.0f us\n",
	       code, rd(regs, AFBD_G_FLAGS), rd(regs, AFBD_STRIDE),
	       rd(regs, AFBD_G_STRIDE0), rd(regs, AFBD_G_STRIDE1),
	       us < 0 ? "TIMEOUT" : "ok", us < 0 ? 0 : us);

	usleep(dwell_ms * 1000);

	wr(regs, AFBD_G_FLAGS, save_10);
	wr(regs, AFBD_STRIDE, save_stride);
	wr(regs, AFBD_SRC, save_src);
	wr(regs, AFBD_G_STRIDE0, save_s0);
	wr(regs, AFBD_G_STRIDE1, save_s1);
	wr(regs, AFBD_DIRTY, 1);                   /* latch the restore too */
	commit();
	printf("restored\n");
	free(buf);
	return 0;
}

static void usage(void)
{
	fprintf(stderr,
		"usage: h713-present <mode> [args]\n"
		"  regs                 dump the AFBD registers (safe once display is up)\n"
		"  fill <0xAARRGGBB>    solid fill of the front buffer, then commit\n"
		"  bar [frames]         moving red bar on blue, double-buffered (default 600)\n"
		"  bar-sb [frames]      same bar, SINGLE-buffered — the tearing positive control\n"
		"  nv12 <file> [frames] present NV12 frames from a raw file\n"
		"  yuvtry <f.nv12> <code> [ms]  try one AFBD format code, then restore\n"
		"  fmt <code> [stride] [ms]  set ONLY format+strides, latch, commit,\n"
		"                       then restore (ms=0 leaves it set). The plane\n"
		"                       addresses are left alone -- pair with DECD's\n"
		"                       FRAME_SUBMIT, which programs those and nothing else\n"
		"  load <file.nv12>     copy a frame into the scanout buffer, touch NO\n"
		"                       registers -- the base state for a poke sweep\n"
		"  info <val> [ms]      rewrite the 4 video-info-page addresses, latch,\n"
		"                       commit. 'info 0' undoes DECD's y_phys+4096 bug\n"
		"  poke <off> <val> [ms]  one 32-bit write into the AFBD window + commit\n"
		"\nThe display must already be up (h713_disp in U-Boot). This refuses to\n"
		"touch the display blocks otherwise -- reading them gated hangs the board.\n");
}

int main(int argc, char **argv)
{
	int fd;
	uint32_t gate;

	if (argc < 2) { usage(); return 2; }

	fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) { perror("open /dev/mem"); return 1; }

	ccu = mmap(NULL, 0x1000, PROT_READ, MAP_SHARED, fd, CCU_AFBD_CLK & ~0xfffUL);
	if (ccu == MAP_FAILED) { perror("mmap ccu"); return 1; }

	gate = ccu[(CCU_AFBD_CLK & 0xfff) / 4];
	if (!(gate & (1u << 31))) {
		fprintf(stderr,
			"refusing: AFBD clock gate is closed (0x%08x at 0x%08lx).\n"
			"The display is not up. Run 'h713_disp auto 0x34 logo' (or a\n"
			"panel-test) in U-Boot before booting, then retry.\n",
			gate, CCU_AFBD_CLK);
		return 1;
	}

	regs = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, AFBD_BASE);
	if (regs == MAP_FAILED) { perror("mmap afbd"); return 1; }

	fb_front = mmap(NULL, FB_WINDOW, PROT_READ | PROT_WRITE, MAP_SHARED, fd, FB_FRONT);
	if (fb_front == MAP_FAILED) {
		perror("mmap scanout");
		fprintf(stderr, "If this is EPERM, CONFIG_STRICT_DEVMEM rejected the\n"
				"range -- check /proc/iomem shows uboot-scanout as a\n"
				"TOP-LEVEL entry, not a child of System RAM.\n");
		return 1;
	}
	fb_back = fb_front + (FB_BACK - FB_FRONT) / 4;

	printf("AFBD ctrl=%08x ready=%08x status=%08x stride=%08x src=%08x\n",
	       rd(regs, AFBD_CTRL), rd(regs, AFBD_READY), rd(regs, AFBD_STATUS),
	       rd(regs, AFBD_STRIDE), rd(regs, AFBD_SRC));

	regs8 = (volatile uint8_t *)regs;
	conv_threads_init();
	extra_vsync = getenv("EXTRA_VSYNC") && atoi(getenv("EXTRA_VSYNC"));
	if (getenv("BARRIER"))
		use_barrier = atoi(getenv("BARRIER"));
	if (getenv("BAR_STEP"))
		bar_step = atoi(getenv("BAR_STEP"));

	if (!strcmp(argv[1], "regs")) {
		dump_channel();
		return 0;
	}

	if (!strcmp(argv[1], "fmt") && argc >= 3)
		return fmt_bridge(strtoul(argv[2], NULL, 0),
				  argc >= 4 ? strtoul(argv[3], NULL, 0) : W,
				  argc >= 5 ? strtoul(argv[4], NULL, 0) : 8000);

	if (!strcmp(argv[1], "load") && argc >= 3)
		return load_raw_frame(argv[2]);

	if (!strcmp(argv[1], "info") && argc >= 3)
		return info_probe(strtoul(argv[2], NULL, 0),
				  argc >= 4 ? strtoul(argv[3], NULL, 0) : 0);

	if (!strcmp(argv[1], "poke") && argc >= 4)
		return poke(strtoul(argv[2], NULL, 0), strtoul(argv[3], NULL, 0),
			    argc >= 5 ? strtoul(argv[4], NULL, 0) : 0);

	if (!strcmp(argv[1], "yuvtry") && argc >= 4)
		return yuvtry(argv[2], strtoul(argv[3], NULL, 0),
			      argc >= 5 ? strtoul(argv[4], NULL, 0) : 4000);

	if (!strcmp(argv[1], "fill") && argc >= 3) {
		uint32_t v = strtoul(argv[2], NULL, 0);
		double t0 = now_ms(), t1, us;
		size_t i;

		for (i = 0; i < FB_BYTES / 4; i++)
			fb_front[i] = v;
		t1 = now_ms();
		flip_to(FB_FRONT);
		us = commit();
		printf("fill %08x: %.1f ms (%.1f MB/s), commit %s %.0f us\n",
		       v, t1 - t0, FB_BYTES / 1024.0 / 1024.0 / ((t1 - t0) / 1000.0),
		       us < 0 ? "TIMEOUT" : "ok", us < 0 ? 0 : us);
		return us < 0 ? 1 : 0;
	}

	/*
	 * bar-sb is the POSITIVE CONTROL for the tearing measurement, not a
	 * leftover. It writes into the buffer the hardware is scanning, so the
	 * raster can catch the surface blued-but-not-yet-barred. Without a run
	 * that the metric is known to flag, a 0% double-buffered result cannot
	 * be told apart from a metric that does not work.
	 *
	 * Expected magnitude is predicted, not guessed: rows with no bar should
	 * be about (phase-1 fill time / frame period). The console prints the
	 * fill time, so the prediction can be checked against the measurement.
	 */
	/*
	 * Does writing AFBD_SRC actually move the scanout? Everything in the
	 * double-buffered path assumes it does, and the tearing measurement
	 * says otherwise: 25.65% of rows lose the bar when it should be ~0%,
	 * which is about half the single-buffered rate -- exactly what you get
	 * if the flip is ignored and only the frames landing in fb_front are
	 * visible.
	 *
	 * Two solid colours, no motion, no metric: if the panel does not go
	 * red -> green -> red, the flip is not working and double buffering is
	 * an illusion.
	 */
	if (!strcmp(argv[1], "flip-test")) {
		unsigned dwell = argc >= 3 ? strtoul(argv[2], NULL, 0) : 5000;
		size_t i;

		for (i = 0; i < FB_BYTES / 4; i++) {
			((uint32_t *)fb_front)[i] = 0xffff0000u;   /* red  */
			((uint32_t *)fb_back)[i]  = 0xff00ff00u;   /* green */
		}

		flip_to(FB_FRONT); commit();
		printf("FRONT: expect RED    src=%08x\n", rd(regs, AFBD_SRC));
		usleep(dwell * 1000);

		flip_to(FB_BACK); commit();
		printf("BACK:  expect GREEN  src=%08x\n", rd(regs, AFBD_SRC));
		usleep(dwell * 1000);

		flip_to(FB_FRONT); commit();
		printf("FRONT: expect RED    src=%08x\n", rd(regs, AFBD_SRC));
		return 0;
	}

	/*
	 * bar-noflip isolates WHICH activity corrupts the picture.
	 *
	 * It does the full per-frame workload -- fill a buffer, commit, at the
	 * panel rate -- but always fills fb_back and always leaves scanout
	 * pointed at fb_front, which is written once at the start and then
	 * never touched. The displayed surface is therefore static by
	 * construction, exactly like the `bar 1` negative control that
	 * measured 0.74%.
	 *
	 * Reads ~0.74%  -> writing the OTHER buffer is harmless, and the
	 *                  corruption comes from presenting a freshly filled
	 *                  buffer (a latch/coherency problem at the flip).
	 * Reads ~25%    -> the corruption is caused by the commit/scanout
	 *                  activity itself, independent of what we write, and
	 *                  the double-buffering model is not the issue at all.
	 *
	 * Either answer eliminates half the search space; the current evidence
	 * cannot distinguish them, which is why guessing again would be wrong.
	 */
	/*
	 * bar-vs swaps the way the vendor does: wait for the real vblank
	 * (dec_irq_query's condition), THEN write the address, THEN latch it
	 * with the dirty bit -- rather than writing the address whenever the
	 * fill happens to finish and polling AFBD_STATUS bit 1.
	 *
	 * If this drops rows-with-no-bar from 25.65% toward the 0.74% floor,
	 * the defect was swapping at an arbitrary point in the scan, and the
	 * fix is to keep the address write inside vblank.
	 */
	/*
	 * Is 0x056000c0 bit 0 a per-vblank event, or just a static bit?
	 *
	 * bar-vs measured 300 vblank misses out of 300 because dec_irq_query()
	 * ANDs +0xc0 with +0xc4, and a live dump shows 0xc4 = 0 -- the vendor's
	 * second condition is not enabled in our configuration. Before relaxing
	 * the condition to 0xc0 alone, find out what 0xc0 actually does:
	 * ack it, time how long until it sets again, repeat.
	 *
	 * ~16.75 ms intervals  -> it is vblank, and we have the signal we need.
	 * instant re-set        -> it is a level/static bit, useless as an event.
	 * never re-sets         -> acking clears it for good; not an event either.
	 */
	/*
	 * How many vblanks after the flip does scanout ACTUALLY switch?
	 *
	 * Four tearing hypotheses have been eliminated and every one of them
	 * assumed an answer to this. It is measurable without reading the panel,
	 * by using the fill as the probe: flip to the other buffer, then
	 * immediately repaint the OLD buffer white. If white ever reaches the
	 * screen, the old buffer was still live when we wrote it -- which is
	 * precisely the corruption the tearing metric keeps reporting.
	 *
	 *   stays GREEN            -> the flip is effective immediately; writing
	 *                             the other buffer is safe, and the tearing
	 *                             comes from somewhere else entirely.
	 *   flashes WHITE then GREEN -> the flip lands late; the count of frames
	 *                             painted before it takes tells us how late.
	 *   stays WHITE            -> the flip never took effect at 60 Hz
	 *                             timescales at all, despite flip-test
	 *                             working across 5-second dwells.
	 */
	/*
	 * leak-test amplifies latency-probe so a transient cannot hide.
	 *
	 * latency-probe repaints the off-screen buffer white ONCE. If the front
	 * were live for a single frame that is one 16.74 ms flash -- easy for an
	 * eye to miss, and a 30 fps camera samples every 33 ms so it can fall
	 * between samples too.
	 *
	 * Here BACK (green) is made live and then FRONT is hammered between
	 * white and red continuously for several seconds. The panel must stay
	 * SOLID GREEN. Any flicker of white or red means the front buffer is
	 * reaching the screen while we write it, and at this repetition rate a
	 * leak becomes a visible strobe rather than a single missable frame.
	 */
	/*
	 * yuv2 -- direct YUV the way the VENDOR does it, with the plane
	 * addresses, not just the format byte.
	 *
	 * The earlier attempt (yuvtry) set the format at +0x11 and the strides
	 * and kept feeding the single packed source at +0x178. That is the RGB
	 * data path. dec_sync_frame_to_hardware() shows the vendor writes TWO
	 * plane addresses instead, via dec_reg_set_address() with
	 * base = afbd + 0x60:
	 *
	 *     Y: base + {16,20,24,28}[idx]   -> 0x05600070 for idx 0
	 *     C: base + {36,40,44,48}[idx]   -> 0x05600084 for idx 0
	 *
	 * and they come from item->y_addr / item->c_addr -- the decoder's own
	 * buffers, submitted by DECD_IOC_FRAME_SUBMIT. The CPU never reads the
	 * frame. Our register dump showed both plane registers reading zero,
	 * which was noted and then dismissed as "a parallel mechanism we do not
	 * use"; it is in fact what makes YUV work.
	 *
	 * usage: yuv2 <file.nv12> <format-code> <idx> [dwell-ms]
	 */
	if (!strcmp(argv[1], "yuv2") && argc >= 5) {
		unsigned code = strtoul(argv[3], NULL, 0);
		unsigned idx = strtoul(argv[4], NULL, 0);
		unsigned dwell = argc >= 6 ? strtoul(argv[5], NULL, 0) : 8000;
		static const unsigned y_off[] = { 0x70, 0x74, 0x78, 0x7c };
		static const unsigned c_off[] = { 0x84, 0x88, 0x8c, 0x90 };
		size_t fsz = (size_t)W * H * 3 / 2;
		uint8_t *buf = malloc(fsz);
		int fd2 = open(argv[2], O_RDONLY);
		uint32_t s_flags, s_str, s_src, s_s0, s_s1, s_y, s_c;
		unsigned long y_phys = FB_FRONT, c_phys = FB_FRONT + (unsigned long)W * H;
		size_t got = 0;
		double us;

		if (idx > 3) { fprintf(stderr, "idx must be 0..3\n"); return 2; }
		if (fd2 < 0 || !buf) { perror("yuv2"); return 1; }
		while (got < fsz) {
			ssize_t r = read(fd2, buf + got, fsz - got);
			if (r <= 0) break;
			got += (size_t)r;
		}
		close(fd2);
		if (got != fsz) { fprintf(stderr, "short frame\n"); return 1; }

		s_flags = rd(regs, AFBD_G_FLAGS);
		s_str = rd(regs, AFBD_STRIDE);
		s_src = rd(regs, AFBD_SRC);
		s_s0 = rd(regs, AFBD_G_STRIDE0);
		s_s1 = rd(regs, AFBD_G_STRIDE1);
		s_y = rd(regs, y_off[idx]);
		s_c = rd(regs, c_off[idx]);
		printf("saved: flags=%08x stride=%08x src=%08x s0=%08x s1=%08x "
		       "Y[%u]=%08x C[%u]=%08x\n",
		       s_flags, s_str, s_src, s_s0, s_s1, idx, s_y, idx, s_c);

		/* NV12 laid out contiguously: Y plane, then interleaved chroma. */
		memcpy((void *)fb_front, buf, fsz);
		__sync_synchronize();

		regs8[AFBD_G_FORMAT] = (uint8_t)code;
		wr(regs, AFBD_G_STRIDE0, W);
		wr(regs, AFBD_G_STRIDE1, W);
		wr(regs, AFBD_STRIDE, W);
		wr(regs, y_off[idx], (uint32_t)y_phys);   /* the vendor's Y plane */
		wr(regs, c_off[idx], (uint32_t)c_phys);   /* the vendor's C plane */
		wr(regs, AFBD_DIRTY, 1);
		us = commit();
		printf("code %u idx %u: Y=%08x C=%08x flags=%08x commit %s %.0f us\n",
		       code, idx, rd(regs, y_off[idx]), rd(regs, c_off[idx]),
		       rd(regs, AFBD_G_FLAGS), us < 0 ? "TIMEOUT" : "ok",
		       us < 0 ? 0 : us);

		usleep(dwell * 1000);

		wr(regs, y_off[idx], s_y);
		wr(regs, c_off[idx], s_c);
		wr(regs, AFBD_G_FLAGS, s_flags);
		wr(regs, AFBD_G_STRIDE0, s_s0);
		wr(regs, AFBD_G_STRIDE1, s_s1);
		wr(regs, AFBD_STRIDE, s_str);
		wr(regs, AFBD_SRC, s_src);
		wr(regs, AFBD_DIRTY, 1);
		commit();
		printf("restored\n");
		free(buf);
		return 0;
	}

	/*
	 * yuv-stream: successive NV12 frames via the vendor's plane addresses.
	 *
	 * Still copies the frame into the scanout region (we cannot resolve a
	 * V4L2 buffer to a physical address from userspace -- that is exactly
	 * why the vendor has a kernel driver), but it does NO colour conversion
	 * and no ARGB blit. It answers whether direct YUV survives motion and
	 * what the per-frame cost becomes once convert+blit are gone.
	 *
	 * Two frame slots inside the 8 MiB reservation: an NV12 frame is
	 * 1.38 MB so both fit with room to spare.
	 */
	if (!strcmp(argv[1], "yuv-stream") && argc >= 3) {
		int frames = argc >= 4 ? atoi(argv[3]) : 1 << 30;
		static const unsigned y_off[] = { 0x70, 0x74, 0x78, 0x7c };
		static const unsigned c_off[] = { 0x84, 0x88, 0x8c, 0x90 };
		size_t fsz = (size_t)W * H * 3 / 2;
		uint8_t *buf = malloc(fsz);
		int vfd = open(argv[2], O_RDONLY);
		uint32_t s_flags = rd(regs, AFBD_G_FLAGS), s_str = rd(regs, AFBD_STRIDE);
		uint32_t s_src = rd(regs, AFBD_SRC), s_s0 = rd(regs, AFBD_G_STRIDE0);
		uint32_t s_s1 = rd(regs, AFBD_G_STRIDE1);
		uint32_t s_y = rd(regs, y_off[0]), s_c = rd(regs, c_off[0]);
		int n = 0, timeouts = 0;
		double copy_tot = 0, wait_tot = 0, t0;

		if (vfd < 0 || !buf) { perror("yuv-stream"); return 1; }
		fcntl(vfd, F_SETPIPE_SZ, 4 << 20);

		regs8[AFBD_G_FORMAT] = 3;               /* 8-bit YUV420 */
		wr(regs, AFBD_G_STRIDE0, W);
		wr(regs, AFBD_G_STRIDE1, W);
		wr(regs, AFBD_STRIDE, W);
		wr(regs, AFBD_DIRTY, 1);

		t0 = now_ms();
		while (n < frames) {
			unsigned long base = (n & 1) ? FB_BACK : FB_FRONT;
			double a, b, us;
			size_t got = 0;

			a = now_ms();
			while (got < fsz) {
				ssize_t r = read(vfd, buf + got, fsz - got);
				if (r <= 0) break;
				got += (size_t)r;
			}
			if (got != fsz) break;
			memcpy((void *)(uintptr_t)((char *)fb_front +
			       (base - FB_FRONT)), buf, fsz);
			__sync_synchronize();
			b = now_ms();

			wr(regs, y_off[0], (uint32_t)base);
			wr(regs, c_off[0], (uint32_t)(base + (unsigned long)W * H));
			wr(regs, AFBD_DIRTY, 1);
			us = commit();
			if (us < 0) timeouts++;
			copy_tot += b - a;
			wait_tot += us < 0 ? 0 : us / 1000.0;
			n++;
		}
		close(vfd);

		wr(regs, y_off[0], s_y);
		wr(regs, c_off[0], s_c);
		wr(regs, AFBD_G_FLAGS, s_flags);
		wr(regs, AFBD_G_STRIDE0, s_s0);
		wr(regs, AFBD_G_STRIDE1, s_s1);
		wr(regs, AFBD_STRIDE, s_str);
		wr(regs, AFBD_SRC, s_src);
		wr(regs, AFBD_DIRTY, 1);
		commit();

		if (n)
			printf("yuv-stream: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
			       "            mean read+copy %.2f ms, commit wait %.2f ms\n",
			       n, now_ms() - t0, n / ((now_ms() - t0) / 1000.0),
			       timeouts, copy_tot / n, wait_tot / n);
		return n ? 0 : 1;
	}

	if (!strcmp(argv[1], "leak-test")) {
		unsigned secs = argc >= 3 ? strtoul(argv[2], NULL, 0) : 8;
		double t0;
		size_t i;
		unsigned long cycles = 0;

		for (i = 0; i < FB_BYTES / 4; i++) {
			((uint32_t *)fb_front)[i] = 0xffff0000u;   /* red   */
			((uint32_t *)fb_back)[i]  = 0xff00ff00u;   /* green */
		}
		wait_vblank();
		flip_to(FB_BACK);
		wr(regs, AFBD_DIRTY, 1);
		commit();
		wait_vblank();

		printf("BACK (green) is live; hammering FRONT white<->red for %u s.\n"
		       "  SOLID GREEN      = front writes never reach the panel\n"
		       "  ANY white/red    = front is live while being written\n",
		       secs);

		t0 = now_ms();
		while (now_ms() - t0 < secs * 1000.0) {
			for (i = 0; i < FB_BYTES / 4; i++)
				((uint32_t *)fb_front)[i] = 0xffffffffu;
			for (i = 0; i < FB_BYTES / 4; i++)
				((uint32_t *)fb_front)[i] = 0xffff0000u;
			cycles++;
		}
		printf("%lu white/red cycles in %u s; src=%08x\n",
		       cycles, secs, rd(regs, AFBD_SRC));

		for (i = 0; i < FB_BYTES / 4; i++)
			((uint32_t *)fb_front)[i] = 0xffff0000u;
		wait_vblank();
		flip_to(FB_FRONT);
		wr(regs, AFBD_DIRTY, 1);
		commit();
		return 0;
	}

	if (!strcmp(argv[1], "latency-probe")) {
		unsigned dwell = argc >= 3 ? strtoul(argv[2], NULL, 0) : 4000;
		size_t i;

		for (i = 0; i < FB_BYTES / 4; i++) {
			((uint32_t *)fb_front)[i] = 0xffff0000u;   /* red   */
			((uint32_t *)fb_back)[i]  = 0xff00ff00u;   /* green */
		}
		flip_to(FB_FRONT);
		wr(regs, AFBD_DIRTY, 1);
		commit();
		printf("phase 1: panel should be RED (front live), %u ms\n", dwell);
		usleep(dwell * 1000);

		wait_vblank();
		flip_to(FB_BACK);
		wr(regs, AFBD_DIRTY, 1);
		commit();
		/* No pause: repaint the buffer we just flipped AWAY from. */
		for (i = 0; i < FB_BYTES / 4; i++)
			((uint32_t *)fb_front)[i] = 0xffffffffu;  /* white */
		printf("phase 2: flipped to BACK, then repainted FRONT white.\n"
		       "         GREEN  = flip effective, front write invisible\n"
		       "         WHITE  = front still live when written (the bug)\n");
		usleep(dwell * 1000);

		for (i = 0; i < FB_BYTES / 4; i++)
			((uint32_t *)fb_front)[i] = 0xffff0000u;
		flip_to(FB_FRONT);
		wr(regs, AFBD_DIRTY, 1);
		commit();
		printf("phase 3: back to RED. src=%08x\n", rd(regs, AFBD_SRC));
		return 0;
	}

	if (!strcmp(argv[1], "vbprobe")) {
		volatile uint8_t *b = (volatile uint8_t *)regs;
		int i, hits = 0;
		double last;

		printf("initial: 0xc0=%02x 0xc4=%02x  (status %08x)\n",
		       b[AFBD_IRQ_ST0], b[AFBD_IRQ_ST1], rd(regs, AFBD_STATUS));

		b[AFBD_IRQ_ST0] = b[AFBD_IRQ_ST0] | 1u;         /* ack */
		last = now_ms();
		for (i = 0; i < 20; i++) {
			double t0 = now_ms();

			while (!(b[AFBD_IRQ_ST0] & 1u) && now_ms() - t0 < 100.0)
				;
			if (b[AFBD_IRQ_ST0] & 1u) {
				printf("  event %2d after %6.2f ms  (0xc4=%02x)\n",
				       i, now_ms() - last, b[AFBD_IRQ_ST1]);
				hits++;
				b[AFBD_IRQ_ST0] = b[AFBD_IRQ_ST0] | 1u; /* ack */
				last = now_ms();
			} else {
				printf("  event %2d TIMEOUT after 100 ms\n", i);
				last = now_ms();
			}
		}
		printf("%d/20 events; a 59.7 Hz panel would give ~16.75 ms\n", hits);
		return 0;
	}

	if (!strcmp(argv[1], "bar-vs")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0, vmiss = 0;
		double fill_tot = 0, vb_tot = 0, t0 = now_ms();

		for (n = 0; n < frames; n++) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a = now_ms(), b, vb, us;

			fill_bar(target, (n * bar_step) % W);
			b = now_ms();

			vb = wait_vblank();
			if (vb < 0) vmiss++;
			flip_to(phys);
			wr(regs, AFBD_DIRTY, 1);        /* latch, as the vendor does */
			us = commit();
			if (us < 0) timeouts++;
			/*
			 * BAR_LATCH_WAIT=1 waits for the vblank AFTER the flip,
			 * so the new address has actually taken effect before we
			 * touch the other buffer.
			 *
			 * The zero-motion control (BAR_STEP=0) reads 30.46%
			 * against 0.74% for an idle panel, so the raster really
			 * is catching a half-filled surface -- with identical
			 * content every frame, motion cannot explain it. The
			 * remaining candidate is a one-frame flip latency: if
			 * the address written after vblank N only takes effect
			 * at vblank N+1, then with just two buffers the one we
			 * fill is still the one being scanned, every frame.
			 *
			 * If this drops the metric toward 0.74% (at half the
			 * frame rate), that is the mechanism, and the real fix
			 * is a third buffer -- which needs a bigger
			 * uboot-scanout reservation, i.e. a kernel change.
			 */
			if (getenv("BAR_LATCH_WAIT"))
				wait_vblank();

			fill_tot += b - a;
			vb_tot += vb < 0 ? 0 : vb;
		}
		fill_bar(fb_front, ((frames - 1) * bar_step) % W);
		flip_to(FB_FRONT);
		wr(regs, AFBD_DIRTY, 1);
		commit();

		printf("bar-vs: %d frames in %.0f ms (%.2f fps), %d timeouts, "
		       "%d vblank misses\n"
		       "        fill mean %.2f ms, vblank wait mean %.2f ms\n",
		       frames, now_ms() - t0, frames / ((now_ms() - t0) / 1000.0),
		       timeouts, vmiss, fill_tot / frames, vb_tot / frames);
		return timeouts ? 1 : 0;
	}

	if (!strcmp(argv[1], "bar-noflip")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0;
		double t0;

		fill_bar(fb_front, 0);                  /* the one visible frame */
		flip_to(FB_FRONT);
		commit();

		t0 = now_ms();
		for (n = 0; n < frames; n++) {
			double us;

			fill_bar(fb_back, (n * bar_step) % W);   /* never displayed */
			flip_to(FB_FRONT);                 /* scanout stays put */
			us = commit();
			if (us < 0) timeouts++;
		}
		printf("bar-noflip: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
		       "            panel shows a STATIC bar; expect the 0.74%% floor\n"
		       "            unless commit/scanout activity is itself the cause\n",
		       frames, now_ms() - t0, frames / ((now_ms() - t0) / 1000.0),
		       timeouts);
		return timeouts ? 1 : 0;
	}

	if (!strcmp(argv[1], "bar-sb")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0;
		double fill_tot = 0, wait_tot = 0, t0 = now_ms();

		flip_to(FB_FRONT);
		for (n = 0; n < frames; n++) {
			double a = now_ms(), b, us;

			fill_bar(fb_front, (n * bar_step) % W);   /* the live surface */
			b = now_ms();
			us = commit();
			if (us < 0) timeouts++;
			fill_tot += b - a;
			wait_tot += us < 0 ? 0 : us / 1000.0;
		}
		printf("bar-sb: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
		       "        fill mean %.2f ms, commit wait mean %.2f ms\n"
		       "        predicted rows-with-no-bar ~%.1f%% "
		       "(fill / 16.75 ms frame)\n",
		       frames, now_ms() - t0, frames / ((now_ms() - t0) / 1000.0),
		       timeouts, fill_tot / frames, wait_tot / frames,
		       100.0 * (fill_tot / frames) / 16.75);
		return timeouts ? 1 : 0;
	}

	if (!strcmp(argv[1], "bar")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0;
		double fill_tot = 0, wait_tot = 0, t0 = now_ms();

		for (n = 0; n < frames; n++) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a = now_ms(), b, us;

			fill_bar(target, (n * bar_step) % W);
			b = now_ms();
			flip_to(phys);
			us = commit();
			/*
			 * EXTRA_VSYNC=1 burns one more frame before the next
			 * fill begins. It is a diagnostic for the 25.65%
			 * rows-with-no-bar that double buffering should have
			 * removed: the flip itself is proven working
			 * (flip-test alternates the panel red/green and src
			 * reads back correctly), so what remains is when the
			 * new address is LATCHED relative to the raster. The
			 * fill takes 12.07 ms of a 16.75 ms frame, leaving
			 * ~4.7 ms of margin; if the latch lands a frame later
			 * than assumed we overwrite the live surface every
			 * time. If this halves the frame rate AND drops the
			 * metric to ~0, that is the answer.
			 */
			if (extra_vsync)
				commit();
			if (us < 0) { timeouts++; if (timeouts == 1)
				printf("first commit timeout at frame %d\n", n); }
			fill_tot += b - a;
			wait_tot += us < 0 ? 0 : us / 1000.0;
		}
		/*
		 * Always finish on the front buffer: every other consumer of this
		 * path writes 0x6c100000 and none of them touch the source
		 * register, so leaving the hardware reading the back buffer would
		 * silently break whatever runs next.
		 */
		fill_bar(fb_front, ((frames - 1) * bar_step) % W);
		flip_to(FB_FRONT);
		commit();

		printf("bar: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
		       "     fill mean %.2f ms, commit wait mean %.2f ms\n",
		       frames, now_ms() - t0, frames / ((now_ms() - t0) / 1000.0),
		       timeouts, fill_tot / frames, wait_tot / frames);
		return timeouts ? 1 : 0;
	}

	if (!strcmp(argv[1], "nv12") && argc >= 3) {
		int frames = argc >= 4 ? atoi(argv[3]) : 1 << 30;
		size_t fsz = (size_t)W * H * 3 / 2;
		uint32_t *stage = aligned_alloc(64, FB_BYTES);
		int vfd = open(argv[2], O_RDONLY);
		int n = 0, timeouts = 0, i;
		double read_tot = 0, conv_tot = 0, blit_tot = 0, wait_tot = 0;
		double t0;
		struct reader rd_ctx = { 0 };
		pthread_t rd_th;

		if (vfd < 0 || !stage) { perror("nv12 setup"); return 1; }
		/*
		 * Raw read() in frame-sized gulps, NOT stdio. fread() on a FILE*
		 * uses a 4 KB buffer, so a 1.38 MB frame became ~337 blocking
		 * reads that ping-pong with the writer -- measured at 31.7 ms
		 * per frame, which dwarfed decode (268 fps) and conversion
		 * (11 ms) combined. Enlarging the pipe cuts the round trips
		 * further; failure is harmless, so it is not checked.
		 */
		/*
		 * Verify, do not assume. F_SETPIPE_SZ is capped by
		 * /proc/sys/fs/pipe-max-size (1 MB by default) and silently
		 * clamps; a 64 KB pipe needs ~22 fill/drain round trips per
		 * 1.38 MB frame, each waiting on the writer to be scheduled,
		 * which is the right order to explain a 12-15 ms "read" that
		 * should take 2-3 ms.
		 */
		if (fcntl(vfd, F_SETPIPE_SZ, 4 << 20) < 0)
			fcntl(vfd, F_SETPIPE_SZ, 1 << 20);
		{
			int got = fcntl(vfd, F_GETPIPE_SZ);
			if (got > 0)
				printf("pipe size: %d bytes (%.2f frames)\n",
				       got, got / (double)fsz);
			else
				printf("pipe size: not a pipe (regular file)\n");
		}

		rd_ctx.fd = vfd;
		rd_ctx.fsz = fsz;
		for (i = 0; i < RING_SLOTS; i++) {
			rd_ctx.slot[i] = malloc(fsz);
			if (!rd_ctx.slot[i]) { perror("ring"); return 1; }
		}
		pthread_mutex_init(&rd_ctx.m, NULL);
		pthread_cond_init(&rd_ctx.space, NULL);
		pthread_cond_init(&rd_ctx.item, NULL);
		if (pthread_create(&rd_th, NULL, reader_thread, &rd_ctx)) {
			perror("reader thread");
			return 1;
		}

		t0 = now_ms();
		while (n < frames) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a, b, c, d, us;
			uint8_t *buf;

			a = now_ms();
			buf = reader_get(&rd_ctx);
			if (!buf)
				break;
			b = now_ms();
			nv12_to_argb(buf, buf + (size_t)W * H, W, H, W, W, stage, 1);
			c = now_ms();
			/* buf is consumed once converted -- hand the slot back
			 * before the blit so the reader can run further ahead. */
			reader_release(&rd_ctx);
			/*
			 * One bulk copy rather than per-pixel volatile stores.
			 * The cast is deliberate: the framebuffer is only
			 * volatile to stop the compiler caching the register
			 * window, and memcpy to it is exactly what we want.
			 */
			memcpy((void *)target, stage, FB_BYTES);
			d = now_ms();
			flip_to(phys);
			us = commit();
			if (us < 0) timeouts++;

			read_tot += b - a; conv_tot += c - b;
			blit_tot += d - c; wait_tot += us < 0 ? 0 : us / 1000.0;
			n++;
		}
		pthread_mutex_lock(&rd_ctx.m);
		rd_ctx.stop = 1;
		pthread_cond_broadcast(&rd_ctx.space);
		pthread_mutex_unlock(&rd_ctx.m);
		pthread_join(rd_th, NULL);
		close(vfd);
		flip_to(FB_FRONT);
		if (n)
			printf("nv12: %d frames in %.0f ms (%.2f fps), %d timeouts\n"
			       "      mean read %.2f  convert %.2f  blit %.2f  "
			       "commit-wait %.2f ms\n",
			       n, now_ms() - t0, n / ((now_ms() - t0) / 1000.0),
			       timeouts, read_tot / n, conv_tot / n,
			       blit_tot / n, wait_tot / n);
		return n ? 0 : 1;
	}

	usage();
	return 2;
}
