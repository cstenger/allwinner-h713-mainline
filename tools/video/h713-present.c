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

/* BT.709 for >=720p, BT.601 below it. Integer math, limited range in. */
static void nv12_to_argb(const uint8_t *y, const uint8_t *uv, int w, int h,
			 int ystride, int uvstride, volatile uint32_t *out, int bt709)
{
	const int kr = bt709 ? 459 : 409;       /* 1.793 / 1.596 in Q8 */
	const int kb = bt709 ? 541 : 516;       /* 2.115 / 2.017 */
	const int kgu = bt709 ? 55 : 100;
	const int kgv = bt709 ? 136 : 208;
	int i, j;

	for (j = 0; j < h; j++) {
		const uint8_t *yr = y + (size_t)j * ystride;
		const uint8_t *cr = uv + (size_t)(j / 2) * uvstride;
		volatile uint32_t *o = out + (size_t)j * W;

		for (i = 0; i < w; i++) {
			int c = yr[i] - 16;
			int d = cr[(i / 2) * 2] - 128;
			int e = cr[(i / 2) * 2 + 1] - 128;
			int r = (298 * c + kr * e + 128) >> 8;
			int g = (298 * c - kgu * d - kgv * e + 128) >> 8;
			int b = (298 * c + kb * d + 128) >> 8;

			r = r < 0 ? 0 : (r > 255 ? 255 : r);
			g = g < 0 ? 0 : (g > 255 ? 255 : g);
			b = b < 0 ? 0 : (b > 255 ? 255 : b);
			o[i] = 0xff000000u | (r << 16) | (g << 8) | b;
		}
	}
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

static void usage(void)
{
	fprintf(stderr,
		"usage: h713-present <mode> [args]\n"
		"  regs                 dump the AFBD registers (safe once display is up)\n"
		"  fill <0xAARRGGBB>    solid fill of the front buffer, then commit\n"
		"  bar [frames]         moving red bar on blue, double-buffered (default 600)\n"
		"  nv12 <file> [frames] present NV12 frames from a raw file\n"
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

	if (!strcmp(argv[1], "regs"))
		return 0;

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
		FILE *f = fopen(argv[2], "rb");
		int n = 0, timeouts = 0;
		double t0 = now_ms();

		if (!f || !buf) { perror("open nv12"); return 1; }
		while (n < frames && fread(buf, 1, fsz, f) == fsz) {
			volatile uint32_t *target = (n & 1) ? fb_back : fb_front;
			unsigned long phys = (n & 1) ? FB_BACK : FB_FRONT;
			double us;

			nv12_to_argb(buf, buf + (size_t)W * H, W, H, W, W, target, 1);
			flip_to(phys);
			us = commit();
			if (us < 0) timeouts++;
			n++;
		}
		fclose(f);
		flip_to(FB_FRONT);
		printf("nv12: %d frames in %.0f ms (%.2f fps), %d timeouts\n",
		       n, now_ms() - t0, n / ((now_ms() - t0) / 1000.0), timeouts);
		return n ? 0 : 1;
	}

	usage();
	return 2;
}
