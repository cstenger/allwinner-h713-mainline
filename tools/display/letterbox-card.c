// SPDX-License-Identifier: GPL-2.0
/*
 * Hold a 1280x720 NV12 control card on the H713 video plane, with the
 * letterbox Phase 1 cards pre-rendered in the same buffer object.
 * RUNS ON THE TARGET.
 *
 *   cc -O2 -Wall -o letterbox-card letterbox-card.c $(pkg-config --cflags --libs libdrm)
 *   ARMED=yes letterbox-card [dwell-seconds]        # default 3600
 *
 * WHY ONE BUFFER. The plane's atomic_check takes only a 1280x720, pitch-1280
 * framebuffer, so a sub-panel card cannot be committed through KMS. Instead
 * one dumb buffer holds every card at its own offset; the framebuffer covers
 * the native control card only. letterbox-apply.py then points AFBD's slot
 * registers at a step card's region, with the geometry from the recipe, and
 * points them back afterwards. The whole object is mapped for the display
 * (GEM DMA allocates it on the display device), so every region is fetchable,
 * and no KMS commit happens between the native card and a step.
 *
 * Regions (all plane starts 64 KiB aligned):
 *
 *   native  1280x720  stride 1280, 768 rows allocated  -- the framebuffer
 *   ab      1280x536  stride 1280, 544 rows (ALIGN16)  -- steps a and b
 *   c        852x480  stride  864, 480 rows            -- step c
 *
 * The layout, with the slot addresses AFBD reads for the native card, goes to
 * /tmp/letterbox-card.layout once the card is on the plane. Nothing else is
 * written to hardware here; the KMS driver programs AFBD for the native card.
 *
 * THE CARD. Mid grey, so black bars are distinguishable from the picture:
 *   - a 2-px white frame on the picture's own edge, a 2-px black ring inside;
 *   - ruler ticks every 16 px (short) and 64 px (long) on all four edges;
 *   - a centred circle (radius 0.4 x min(W, H)) and four corner circles --
 *     round means unscaled, an ellipse means an axis is wrong;
 *   - both diagonals, which break into steps under any line shear;
 *   - a centre cross;
 *   - chroma patches near the corners: TL red, TR green, BL blue, BR yellow,
 *     which show orientation and whether chroma lines up with luma.
 * Padding (columns stride-W, rows past H) is MAGENTA: if any appears on the
 * panel, the display is showing the aligned fetch, not the picture.
 */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#define PANEL_W 1280u
#define PANEL_H 720u
#define AFBD_PHYS 0x05600000UL
#define LAYOUT "/tmp/letterbox-card.layout"
#define ALIGN(x, a) (((x) + (a) - 1) / (a) * (a))
#define REGION_ALIGN 0x10000u

struct region {
	const char *name;
	unsigned w, h, stride, rows;	/* rows: luma rows allocated */
	size_t y_off, c_off;
};

static struct region regions[] = {
	{ "native", 1280, 720, 1280, 768, 0, 0 },
	{ "ab",     1280, 536, 1280, 544, 0, 0 },
	{ "c",       852, 480,  864, 480, 0, 0 },
};
#define NREG (sizeof(regions) / sizeof(regions[0]))

static volatile sig_atomic_t interrupted;

static void on_signal(int sig)
{
	(void)sig;
	interrupted = 1;
}

/* BT.601 limited range. */
enum { GREY, WHITE, BLACK, RED, GREEN, BLUE, YELLOW, PAD };
static const uint8_t ycc[][3] = {
	[GREY]   = { 100, 128, 128 },
	[WHITE]  = { 235, 128, 128 },
	[BLACK]  = {  16, 128, 128 },
	[RED]    = {  81,  90, 240 },
	[GREEN]  = { 145,  54,  34 },
	[BLUE]   = {  41, 240, 110 },
	[YELLOW] = { 210,  16, 146 },
	[PAD]    = { 105, 212, 234 },	/* magenta */
};

static int near_circle(long x, long y, long cx, long cy, long r, long t)
{
	long d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy);

	return d2 >= (r - t) * (r - t) && d2 <= r * r;
}

static int colour_at(unsigned x, unsigned y, unsigned w, unsigned h)
{
	unsigned m = w < h ? w : h;
	long r = m * 2 / 5, rc = m / 10;
	long lx = x, ly = y, lw = w, lh = h;

	if (x < 2 || y < 2 || x >= w - 2 || y >= h - 2)
		return WHITE;
	if (x < 4 || y < 4 || x >= w - 4 || y >= h - 4)
		return BLACK;
	/* ruler ticks, 2 px wide, measured from the picture's own origin */
	if ((x % 64 < 2 && (y < 28 || y >= h - 28)) ||
	    (x % 16 < 2 && (y < 14 || y >= h - 14)) ||
	    (y % 64 < 2 && (x < 28 || x >= w - 28)) ||
	    (y % 16 < 2 && (x < 14 || x >= w - 14)))
		return WHITE;
	/* chroma patches, 48x48, inset 40 */
	if (y >= 40 && y < 88) {
		if (x >= 40 && x < 88)
			return RED;
		if (x >= w - 88 && x < w - 40)
			return GREEN;
	}
	if (y >= h - 88 && y < h - 40) {
		if (x >= 40 && x < 88)
			return BLUE;
		if (x >= w - 88 && x < w - 40)
			return YELLOW;
	}
	if (near_circle(lx, ly, lw / 2, lh / 2, r, 3) ||
	    near_circle(lx, ly, rc + 100, rc + 100, rc, 2) ||
	    near_circle(lx, ly, lw - rc - 100, rc + 100, rc, 2) ||
	    near_circle(lx, ly, rc + 100, lh - rc - 100, rc, 2) ||
	    near_circle(lx, ly, lw - rc - 100, lh - rc - 100, rc, 2))
		return WHITE;
	/* diagonals: |x*h - y*w| < w*1.5 is about 1.5 px thick along x */
	if (labs(lx * lh - ly * lw) < lw * 3 / 2 ||
	    labs((lw - 1 - lx) * lh - ly * lw) < lw * 3 / 2)
		return WHITE;
	if (x == w / 2 || x == w / 2 - 1 || y == h / 2 || y == h / 2 - 1)
		return WHITE;
	return GREY;
}

static void render(uint8_t *bo, const struct region *rg)
{
	uint8_t *luma = bo + rg->y_off, *chroma = bo + rg->c_off;
	unsigned x, y;

	for (y = 0; y < rg->rows; y++)
		for (x = 0; x < rg->stride; x++) {
			int c = (x < rg->w && y < rg->h) ?
				colour_at(x, y, rg->w, rg->h) : PAD;

			luma[(size_t)y * rg->stride + x] = ycc[c][0];
			if (!(x & 1) && !(y & 1)) {
				uint8_t *uv = chroma + (size_t)(y / 2) * rg->stride + x;

				uv[0] = ycc[c][1];
				uv[1] = ycc[c][2];
			}
		}
}

static uint32_t find_prop(int fd, uint32_t obj, const char *name)
{
	drmModeObjectProperties *props;
	uint32_t i, id = 0;

	props = drmModeObjectGetProperties(fd, obj, DRM_MODE_OBJECT_PLANE);
	for (i = 0; props && i < props->count_props && !id; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, props->props[i]);

		if (p && !strcmp(p->name, name))
			id = p->prop_id;
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	if (!id)
		fprintf(stderr, "plane has no %s property\n", name);
	return id;
}

static int plane_set(int fd, uint32_t plane, uint32_t crtc, uint32_t fb)
{
	static const char *const names[] = {
		"CRTC_ID", "FB_ID", "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H",
		"SRC_X", "SRC_Y", "SRC_W", "SRC_H",
	};
	uint64_t on[] = { crtc, fb, 0, 0, PANEL_W, PANEL_H, 0, 0,
			  (uint64_t)PANEL_W << 16, (uint64_t)PANEL_H << 16 };
	unsigned i, n = fb ? 10 : 2;
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	int ret;

	for (i = 0; i < n; i++) {
		uint32_t id = find_prop(fd, plane, names[i]);

		if (!id || drmModeAtomicAddProperty(req, plane, id, on[i]) < 0) {
			drmModeAtomicFree(req);
			return -1;
		}
	}
	ret = drmModeAtomicCommit(fd, req, DRM_MODE_ATOMIC_ALLOW_MODESET, NULL);
	drmModeAtomicFree(req);
	return ret;
}

/* The slot addresses AFBD is actually fetching, after the driver's commit. */
static int read_slots(uint32_t *y, uint32_t *c, uint32_t *ctrl)
{
	volatile uint32_t *r;
	int fd = open("/dev/mem", O_RDONLY | O_SYNC);

	if (fd < 0)
		return -1;
	r = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, AFBD_PHYS);
	close(fd);
	if (r == MAP_FAILED)
		return -1;
	*ctrl = r[0x010 / 4];
	*y = r[0x070 / 4];
	*c = r[0x084 / 4];
	munmap((void *)r, 4096);
	return 0;
}

static int write_layout(size_t bo_size, uint32_t y, uint32_t c)
{
	FILE *f = fopen(LAYOUT ".tmp", "w");
	unsigned i;

	if (!f)
		return -1;
	fprintf(f, "bo_size %zu\n", bo_size);
	fprintf(f, "slot_y 0x%08x\nslot_c 0x%08x\n", y, c);
	for (i = 0; i < NREG; i++)
		fprintf(f, "region %s %u %u %u %u %zu %zu\n", regions[i].name,
			regions[i].w, regions[i].h, regions[i].stride,
			regions[i].rows, regions[i].y_off, regions[i].c_off);
	if (fclose(f))
		return -1;
	return rename(LAYOUT ".tmp", LAYOUT);
}

int main(int argc, char **argv)
{
	struct drm_mode_create_dumb create = { .width = PANEL_W, .bpp = 8 };
	struct drm_mode_map_dumb map = { 0 };
	struct drm_mode_destroy_dumb destroy = { 0 };
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	uint32_t crtc = 0, plane = 0, fb = 0, sy, sc, ctrl;
	drmModePlaneRes *pres = NULL;
	drmModeRes *res = NULL;
	unsigned dwell = argc > 1 ? (unsigned)atoi(argv[1]) : 3600;
	size_t end = 0;
	char path[32];
	uint8_t *p;
	uint32_t i, f;
	int fd = -1, rc = 1;

	if (!getenv("ARMED") || strcmp(getenv("ARMED"), "yes")) {
		fprintf(stderr, "usage: ARMED=yes %s [dwell-seconds]\n", argv[0]);
		return 2;
	}
	unlink(LAYOUT);

	for (i = 0; i < NREG; i++) {
		struct region *rg = &regions[i];

		rg->y_off = ALIGN(end, REGION_ALIGN);
		rg->c_off = ALIGN(rg->y_off + (size_t)rg->stride * rg->rows,
				  REGION_ALIGN);
		end = rg->c_off + (size_t)rg->stride * rg->rows / 2;
	}
	/* The framebuffer's chroma must sit where the driver will look for it. */
	if (regions[0].y_off != 0) {
		fprintf(stderr, "native region must start at 0\n");
		return 1;
	}
	create.height = ALIGN(end, PANEL_W) / PANEL_W;

	for (i = 0; i < 16 && !crtc; i++) {
		snprintf(path, sizeof(path), "/dev/dri/card%u", i);
		fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0)
			continue;
		res = drmModeGetResources(fd);
		if (res && res->count_crtcs == 1 && res->count_connectors)
			crtc = res->crtcs[0];
		else {
			drmModeFreeResources(res);
			res = NULL;
			close(fd);
			fd = -1;
		}
	}
	if (!crtc) {
		fprintf(stderr, "no single-CRTC KMS card\n");
		return 1;
	}
	if (drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) ||
	    drmSetClientCap(fd, DRM_CLIENT_CAP_ATOMIC, 1)) {
		perror("client caps");
		goto out;
	}
	pres = drmModeGetPlaneResources(fd);
	for (i = 0; pres && i < pres->count_planes && !plane; i++) {
		drmModePlane *pl = drmModeGetPlane(fd, pres->planes[i]);

		for (f = 0; pl && f < pl->count_formats; f++)
			if (pl->formats[f] == DRM_FORMAT_NV12)
				plane = pl->plane_id;
		drmModeFreePlane(pl);
	}
	if (!plane) {
		fprintf(stderr, "no plane advertises NV12\n");
		goto out;
	}

	if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create)) {
		perror("CREATE_DUMB");
		goto out;
	}
	if (create.pitch != PANEL_W || create.size < end) {
		fprintf(stderr, "dumb pitch %u size %llu, need %u and %zu\n",
			create.pitch, (unsigned long long)create.size, PANEL_W, end);
		goto out;
	}
	map.handle = create.handle;
	if (drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map)) {
		perror("MAP_DUMB");
		goto out;
	}
	p = mmap(NULL, create.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
		 map.offset);
	if (p == MAP_FAILED) {
		perror("mmap dumb");
		goto out;
	}
	memset(p, 0, create.size);
	for (i = 0; i < NREG; i++) {
		render(p, &regions[i]);
		printf("region %-6s %4ux%-4u stride %4u rows %3u  Y +0x%06zx  C +0x%06zx\n",
		       regions[i].name, regions[i].w, regions[i].h,
		       regions[i].stride, regions[i].rows, regions[i].y_off,
		       regions[i].c_off);
	}
	munmap(p, create.size);

	handles[0] = handles[1] = create.handle;
	pitches[0] = pitches[1] = PANEL_W;
	offsets[1] = regions[0].c_off;
	if (drmModeAddFB2(fd, PANEL_W, PANEL_H, DRM_FORMAT_NV12, handles,
			  pitches, offsets, &fb, 0)) {
		perror("AddFB2 NV12");
		goto out;
	}
	printf("WATCH THE PANEL: native 1280x720 control card on plane %u for %us\n",
	       plane, dwell);
	fflush(stdout);
	if (plane_set(fd, plane, crtc, fb)) {
		perror("atomic enable");
		goto out;
	}
	usleep(200000);
	if (read_slots(&sy, &sc, &ctrl)) {
		perror("read AFBD slots");
		goto off;
	}
	printf("AFBD ctrl 0x%08x  slot Y 0x%08x  slot C 0x%08x  (C - Y = 0x%x)\n",
	       ctrl, sy, sc, sc - sy);
	if (sc - sy != regions[0].c_off) {
		fprintf(stderr, "slot C - slot Y = 0x%x, expected 0x%zx: refusing to "
			"publish a layout the executor could misuse\n",
			sc - sy, regions[0].c_off);
		goto off;
	}
	if (write_layout(create.size, sy, sc)) {
		perror("write " LAYOUT);
		goto off;
	}
	printf("layout in " LAYOUT "\n");
	fflush(stdout);

	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);
	signal(SIGHUP, on_signal);
	while (dwell && !interrupted)
		dwell = sleep(dwell);
	rc = 0;
off:
	unlink(LAYOUT);
	if (plane_set(fd, plane, 0, 0))
		fprintf(stderr, "atomic disable failed: %s\n", strerror(errno));
	else
		printf("video plane disabled; KMS RGB restored\n");
out:
	if (fb)
		drmModeRmFB(fd, fb);
	if (create.handle) {
		destroy.handle = create.handle;
		drmIoctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &destroy);
	}
	drmModeFreePlaneResources(pres);
	drmModeFreeResources(res);
	close(fd);
	return rc;
}
