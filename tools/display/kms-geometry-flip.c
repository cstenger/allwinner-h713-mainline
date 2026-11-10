// SPDX-License-Identifier: GPL-2.0
/*
 * Letterbox Phase 4: what does a geometry change cost the video plane, and
 * what does the panel show while it happens? RUNS ON THE TARGET, as root,
 * with nothing else holding DRM master.
 *
 *   cc -O2 -Wall -o kms-geometry-flip kms-geometry-flip.c \
 *      $(pkg-config --cflags --libs libdrm)
 *   kms-geometry-flip [--cover none|top|left] [CYCLES] [HOLD_FRAMES]
 *                                                   (defaults none, 20, 30)
 *
 * Cycles the plane through the geometries below, HOLD_FRAMES blocking
 * flips each (alternating two buffers of the same size, so the fb id keeps
 * changing), and times every atomic commit with CLOCK_MONOTONIC. A blocking
 * commit returns after the flip it asked for has latched, so a same-geometry
 * flip costs one vsync (~16.7 ms); the geometry commit's extra time is the
 * driver's source-off interval. Prints one line per geometry change and a
 * `GEOMFLIP same ms med/max  change ms med/max` summary.
 *
 * --cover (EXPERIMENT, Phase 4 green flash): just before each geometry
 * commit, write the vblender border overlay (0x05200000/04, WriteBorderOverlay1
 * layout) so its borders cover the whole panel -- top = 720 or left = 1280.
 * The driver's h713_lb_program then writes the new geometry's real borders
 * while the source is off. If the overlay latches on vsync with the source
 * stop, the off frame shows black instead of green; if it latches at once,
 * the new borders uncover the off frame early and green comes back. Either
 * way the glass answers which, with no kernel change.
 *
 * ON THE GLASS (operator look): every card is mid grey with a white frame on
 * its own edge, so the bars are black, the picture is grey, and anything
 * else at a transition -- a green flash, a frame of the wrong size, garbage
 * -- is the driver's doing. The decoder is not involved.
 *
 *   geometry                        what the window layer does
 *   1280x720 at (0,0)               native (letterbox registers restored)
 *   1280x536 at (0,92)              unity, letterboxed
 *   852x480 at (214,120)            unity, centred
 *   640x360 -> 1280x720             2x
 *   352x288 -> 880x720 at (200,0)   2.5x, pillarboxed
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>

struct geom {
	const char *name;
	int w, h, x, y, ow, oh;
	uint32_t fb[2];
};

static struct geom geoms[] = {
	{ "native 1280x720",  1280, 720,   0,   0, 1280, 720 },
	{ "unity 1280x536",   1280, 536,   0,  92, 1280, 536 },
	{ "unity 852x480",     852, 480, 214, 120,  852, 480 },
	{ "2x 640x360",        640, 360,   0,   0, 1280, 720 },
	{ "2.5x 352x288",      352, 288, 200,   0,  880, 720 },
};
#define NGEOM (sizeof(geoms) / sizeof(geoms[0]))

static int fd;
static volatile uint32_t *vblend;	/* /dev/mem map of 0x05200000, --cover only */
static uint32_t plane_id, crtc_id;
static uint32_t p_fb, p_crtc, p_sx, p_sy, p_sw, p_sh, p_cx, p_cy, p_cw, p_ch;

static uint32_t prop_id(uint32_t obj, const char *name)
{
	drmModeObjectProperties *pr =
		drmModeObjectGetProperties(fd, obj, DRM_MODE_OBJECT_PLANE);
	uint32_t id = 0;

	for (uint32_t i = 0; pr && i < pr->count_props; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, pr->props[i]);

		if (p && !strcmp(p->name, name))
			id = p->prop_id;
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(pr);
	if (!id) {
		fprintf(stderr, "no plane property %s\n", name);
		exit(2);
	}
	return id;
}

static void find_plane(void)
{
	drmModePlaneRes *pr = drmModeGetPlaneResources(fd);
	drmModeRes *res = drmModeGetResources(fd);

	for (uint32_t i = 0; pr && i < pr->count_planes && !plane_id; i++) {
		drmModePlane *p = drmModeGetPlane(fd, pr->planes[i]);

		for (uint32_t f = 0; p && f < p->count_formats; f++)
			if (p->formats[f] == DRM_FORMAT_NV12)
				plane_id = p->plane_id;
		drmModeFreePlane(p);
	}
	for (int i = 0; res && i < res->count_crtcs && !crtc_id; i++) {
		drmModeCrtc *c = drmModeGetCrtc(fd, res->crtcs[i]);

		if (c && c->mode_valid)
			crtc_id = c->crtc_id;
		drmModeFreeCrtc(c);
	}
	if (!plane_id || !crtc_id) {
		fprintf(stderr, "no NV12 plane or active CRTC\n");
		exit(2);
	}
	p_fb = prop_id(plane_id, "FB_ID");
	p_crtc = prop_id(plane_id, "CRTC_ID");
	p_sx = prop_id(plane_id, "SRC_X");
	p_sy = prop_id(plane_id, "SRC_Y");
	p_sw = prop_id(plane_id, "SRC_W");
	p_sh = prop_id(plane_id, "SRC_H");
	p_cx = prop_id(plane_id, "CRTC_X");
	p_cy = prop_id(plane_id, "CRTC_Y");
	p_cw = prop_id(plane_id, "CRTC_W");
	p_ch = prop_id(plane_id, "CRTC_H");
	drmModeFreePlaneResources(pr);
	drmModeFreeResources(res);
}

/* Mid-grey NV12 card, 2-px white frame on its edge; `alt` moves a small
 * white square so the two buffers of one geometry differ. */
static uint32_t card(int w, int h, int alt)
{
	uint32_t pitch = (w + 15) & ~15, rows = (h + 15) & ~15;
	struct drm_mode_create_dumb c = { .width = pitch, .height = rows * 3 / 2, .bpp = 8 };
	struct drm_mode_map_dumb m = { 0 };
	uint32_t hs[4], ps[4] = { pitch, pitch }, os[4] = { 0, pitch * rows }, id;
	uint8_t *p;

	if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &c)) {
		perror("CREATE_DUMB");
		exit(2);
	}
	m.handle = c.handle;
	if (drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &m)) {
		perror("MAP_DUMB");
		exit(2);
	}
	p = mmap(NULL, c.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, m.offset);
	if (p == MAP_FAILED) {
		perror("mmap");
		exit(2);
	}
	for (int y = 0; y < h; y++)
		for (int x = 0; x < w; x++) {
			int edge = x < 2 || y < 2 || x >= w - 2 || y >= h - 2;
			int sq = x >= w / 2 - 16 + (alt ? 64 : -64) && x < w / 2 + 16 + (alt ? 64 : -64) &&
				 y >= h / 2 - 16 && y < h / 2 + 16;

			p[y * pitch + x] = edge || sq ? 235 : 126;
		}
	memset(p + pitch * rows, 128, pitch * rows / 2);
	munmap(p, c.size);

	hs[0] = hs[1] = c.handle;
	if (drmModeAddFB2(fd, w, h, DRM_FORMAT_NV12, hs, ps, os, &id, 0)) {
		fprintf(stderr, "AddFB2 %dx%d: %s\n", w, h, strerror(errno));
		exit(2);
	}
	return id;
}

static double now_ms(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

/* Border overlay covering the whole panel; bit 30 (enable) and the bits
 * outside the fields are kept. */
static void cover(const char *how)
{
	uint32_t a = vblend[0], b = vblend[1];
	uint32_t top = 0, left = 0;

	if (!strcmp(how, "top"))
		top = 720;
	else
		left = 1280;
	a &= ~(0xfffu | 0xfu << 12 | 0xfffu << 16 | 0xfu << 28);
	b &= ~(0xfffu | 0xfu << 12);
	a |= (top & 0xf) << 12 | left << 16 | ((top >> 4) & 0xf) << 28;
	b |= ((top >> 8) & 0xf) << 12 | 1u << 30;
	vblend[0] = a;
	vblend[1] = b;
}

static double commit(const struct geom *g, uint32_t fb_id)
{
	drmModeAtomicReq *r = drmModeAtomicAlloc();
	double t0 = now_ms();
	int ret;

	drmModeAtomicAddProperty(r, plane_id, p_fb, fb_id);
	drmModeAtomicAddProperty(r, plane_id, p_crtc, crtc_id);
	drmModeAtomicAddProperty(r, plane_id, p_sx, 0);
	drmModeAtomicAddProperty(r, plane_id, p_sy, 0);
	drmModeAtomicAddProperty(r, plane_id, p_sw, (uint64_t)g->w << 16);
	drmModeAtomicAddProperty(r, plane_id, p_sh, (uint64_t)g->h << 16);
	drmModeAtomicAddProperty(r, plane_id, p_cx, g->x);
	drmModeAtomicAddProperty(r, plane_id, p_cy, g->y);
	drmModeAtomicAddProperty(r, plane_id, p_cw, g->ow);
	drmModeAtomicAddProperty(r, plane_id, p_ch, g->oh);
	ret = drmModeAtomicCommit(fd, r, 0, NULL);
	drmModeAtomicFree(r);
	if (ret) {
		fprintf(stderr, "commit %s: %s\n", g->name, strerror(errno));
		exit(1);
	}
	return now_ms() - t0;
}

static int cmpd(const void *a, const void *b)
{
	double x = *(const double *)a, y = *(const double *)b;

	return x < y ? -1 : x > y;
}

int main(int argc, char **argv)
{
	const char *how = "none";
	int cycles, hold;
	int nsame = 0, nchg = 0;
	double *same, *chg;

	if (argc > 2 && !strcmp(argv[1], "--cover")) {
		how = argv[2];
		argc -= 2;
		argv += 2;
	}
	cycles = argc > 1 ? atoi(argv[1]) : 20;
	hold = argc > 2 ? atoi(argv[2]) : 30;
	if (strcmp(how, "none")) {
		int mfd = open("/dev/mem", O_RDWR | O_SYNC);
		void *m;

		if (strcmp(how, "top") && strcmp(how, "left")) {
			fprintf(stderr, "--cover none|top|left\n");
			return 2;
		}
		m = mfd < 0 ? MAP_FAILED : mmap(NULL, 4096, PROT_READ | PROT_WRITE,
						MAP_SHARED, mfd, 0x05200000);
		if (m == MAP_FAILED) {
			perror("/dev/mem 0x05200000");
			return 2;
		}
		vblend = m;
	}
	printf("GEOMFLIP cover=%s cycles=%d hold=%d\n", how, cycles, hold);

	fd = drmOpen("sun50i-h713-afbd", NULL);
	if (fd < 0 || drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) ||
	    drmSetClientCap(fd, DRM_CLIENT_CAP_ATOMIC, 1) || drmSetMaster(fd)) {
		perror("open/caps/master (is a player running?)");
		return 2;
	}
	find_plane();
	for (unsigned i = 0; i < NGEOM; i++) {
		geoms[i].fb[0] = card(geoms[i].w, geoms[i].h, 0);
		geoms[i].fb[1] = card(geoms[i].w, geoms[i].h, 1);
	}
	same = calloc((size_t)cycles * NGEOM * hold, sizeof(*same));
	chg = calloc((size_t)cycles * NGEOM, sizeof(*chg));

	for (int c = 0; c < cycles; c++)
		for (unsigned i = 0; i < NGEOM; i++) {
			struct geom *g = &geoms[i];
			double t;

			if (vblend && (c || i))
				cover(how);
			t = commit(g, g->fb[0]);

			if (c || i) {
				chg[nchg++] = t;
				printf("GEOMFLIP change -> %-16s %6.1f ms\n", g->name, t);
			}
			for (int f = 1; f < hold; f++)
				same[nsame++] = commit(g, g->fb[f & 1]);
		}

	qsort(same, nsame, sizeof(*same), cmpd);
	qsort(chg, nchg, sizeof(*chg), cmpd);
	printf("GEOMFLIP same ms med %.1f max %.1f (n=%d)  change ms med %.1f max %.1f (n=%d)\n",
	       same[nsame / 2], same[nsame - 1], nsame,
	       chg[nchg / 2], chg[nchg - 1], nchg);
	/* Closing the fd releases the plane; the console comes back. */
	return 0;
}
