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

static void flip_to(unsigned long phys)
{
	wr(regs, AFBD_SRC, (uint32_t)phys);
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

#define CONV_THREADS 4

static void nv12_to_argb(const uint8_t *y, const uint8_t *uv, int w, int h,
			 int ystride, int uvstride, uint32_t *out, int bt709)
{
	pthread_t th[CONV_THREADS];
	struct conv_job jobs[CONV_THREADS];
	int started[CONV_THREADS];
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

static void fill_bar(volatile uint32_t *fb, int x0)
{
	int y, x;

	for (y = 0; y < H; y++) {
		volatile uint32_t *row = fb + (size_t)y * W;
		for (x = 0; x < W; x++) {
			int in = (x - x0 + W) % W < 64;
			row[x] = in ? 0xffff0000u : 0xff0000ffu;
		}
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
#define AFBD_DIRTY      0x6c

static volatile uint8_t *regs8;

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
		"  nv12 <file> [frames] present NV12 frames from a raw file\n"
		"  yuvtry <f.nv12> <code> [ms]  try one AFBD format code, then restore\n"
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

	if (!strcmp(argv[1], "regs"))
		return 0;

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

	if (!strcmp(argv[1], "bar")) {
		int frames = argc >= 3 ? atoi(argv[2]) : 600;
		int n, timeouts = 0;
		double fill_tot = 0, wait_tot = 0, t0 = now_ms();

		for (n = 0; n < frames; n++) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a = now_ms(), b, us;

			fill_bar(target, (n * 16) % W);
			b = now_ms();
			flip_to(phys);
			us = commit();
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
		fill_bar(fb_front, ((frames - 1) * 16) % W);
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
		uint8_t *buf = malloc(fsz);
		uint32_t *stage = aligned_alloc(64, FB_BYTES);
		int vfd = open(argv[2], O_RDONLY);
		int n = 0, timeouts = 0;
		double read_tot = 0, conv_tot = 0, blit_tot = 0, wait_tot = 0;
		double t0 = now_ms();

		if (vfd < 0 || !buf || !stage) { perror("nv12 setup"); return 1; }
		/*
		 * Raw read() in frame-sized gulps, NOT stdio. fread() on a FILE*
		 * uses a 4 KB buffer, so a 1.38 MB frame became ~337 blocking
		 * reads that ping-pong with the writer -- measured at 31.7 ms
		 * per frame, which dwarfed decode (268 fps) and conversion
		 * (11 ms) combined. Enlarging the pipe cuts the round trips
		 * further; failure is harmless, so it is not checked.
		 */
		fcntl(vfd, F_SETPIPE_SZ, 4 << 20);
		while (n < frames) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double a, b, c, d, us;
			size_t got = 0;

			a = now_ms();
			while (got < fsz) {
				ssize_t r = read(vfd, buf + got, fsz - got);
				if (r <= 0)
					break;
				got += (size_t)r;
			}
			if (got != fsz)
				break;
			b = now_ms();
			nv12_to_argb(buf, buf + (size_t)W * H, W, H, W, W, stage, 1);
			c = now_ms();
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
