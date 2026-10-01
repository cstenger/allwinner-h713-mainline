// SPDX-License-Identifier: GPL-2.0
/*
 * Put one P010 frame on the H713 video plane (EXPERIMENT, kernel patches 0149
 * and 0150) and say which 10-bit layout the display fetched.
 *
 * The firmware's VideoInfo codes name two 10-bit layouts: 14 =
 * p010_low_10bits_component, 15 = p010_high_10bits_component (resolver ->
 * AFBD fmt 7 and 6). Standard DRM P010 is the HIGH one (sample << 6); the
 * AV1 core's high-bit-depth output is believed to be the LOW one.
 *
 * The frame is built so that one look decides it:
 *
 *   top half     75% colour bars, HIGH-aligned (v << 6)
 *   bottom half  the same bars,   LOW-aligned  (v)
 *   each half ends in a 10-bit grey ramp, 64..940 across the width
 *
 * Read with the low layout, the bottom half is correct and the top is noise
 * (v & 0xf) << 6. Read with the high layout, the top is correct and the
 * bottom collapses to near-black with strongly green chroma (512 >> 6 = 8).
 * Correct bars in BOTH halves means the format was ignored; a half-height
 * picture or doubled bars means 8-bit NV12 fetching through a 2x stride.
 *
 * The framebuffer picks the fetch format, as a real client's would: FILL=lsb
 * adds it as P010 with DRM_FORMAT_MOD_ALLWINNER_LSB10 (driver -> fmt 7);
 * FILL=msb and FILL=split add plain P010 (fmt 6). The plane's IN_FORMATS
 * pairs for P010 are printed first. After the commit, AFBD 0x05600010 is
 * read: bits 15:8 are the fetch format the driver programmed (0 NV12,
 * 6 P010, 7 P010 LSB10).
 *
 * Build on the target:
 *   cc -O2 -Wall -o kms-p010-plane-test kms-p010-plane-test.c \
 *      $(pkg-config --cflags --libs libdrm)
 * Run with an observer at the panel:
 *   [FILL=split|msb|lsb] ARMED=yes kms-p010-plane-test [dwell-seconds]
 *
 * Result 2026-09-30: fmt 6 is standard (MSB-aligned) P010 and fmt 7 is the
 * same layout LSB-aligned, both full-frame correct. An early run had fmt 7
 * stop after 360 lines; that was the fetch budget (the high halves of
 * +0x30/+0x48/+0x4c) still at NV12's values, not the layout.
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

#define W 1280u
#define H 720u
#define PITCH (2 * W)
#define AFBD_PHYS 0x05600000UL

#ifndef DRM_FORMAT_MOD_ALLWINNER_LSB10
#define DRM_FORMAT_MOD_ALLWINNER_LSB10 fourcc_mod_code(ALLWINNER, 2)
#endif

/* BT.709 limited-range 75% bars, 8-bit Y, Cb, Cr; scaled to 10 bits below. */
static const uint8_t bars[8][3] = {
	{ 180, 128, 128 },	/* white */
	{ 168,  44, 136 },	/* yellow */
	{ 145, 147,  44 },	/* cyan */
	{ 133,  63,  52 },	/* green */
	{  63, 193, 204 },	/* magenta */
	{  51, 109, 212 },	/* red */
	{  28, 212, 120 },	/* blue */
	{  16, 128, 128 },	/* black */
};

static volatile sig_atomic_t interrupted;

static void on_signal(int sig)
{
	(void)sig;
	interrupted = 1;
}

/* Y, Cb, Cr in 10 bits for pixel (x, y) of a block of h lines. */
static void sample(unsigned x, unsigned y, unsigned h, uint16_t *Y,
		   uint16_t *cb, uint16_t *cr)
{
	if (y < h * 7 / 9) {
		const uint8_t *b = bars[x * 8 / W];

		*Y = b[0] << 2;
		*cb = b[1] << 2;
		*cr = b[2] << 2;
	} else {
		*Y = 64 + x * (940 - 64) / (W - 1);
		*cb = 512;
		*cr = 512;
	}
}

/*
 * FILL=split (default): the two halves above. FILL=msb or FILL=lsb: one
 * alignment over the whole frame, bars down to line 560 and the ramp below,
 * so a fetch that stops early or repeats is visible as such.
 */
static void fill(uint8_t *base, const char *mode)
{
	uint16_t *luma = (uint16_t *)base;
	uint16_t *chroma = (uint16_t *)(base + PITCH * H);
	int split = !strcmp(mode, "split");
	unsigned block = split ? H / 2 : H;
	unsigned x, y;

	for (y = 0; y < H; y++) {
		unsigned shift = split ? (y < H / 2 ? 6 : 0) :
				 !strcmp(mode, "msb") ? 6 : 0;

		for (x = 0; x < W; x++) {
			uint16_t Y, cb, cr;

			sample(x, y % block, block, &Y, &cb, &cr);
			luma[y * W + x] = Y << shift;
			if (!(x & 1) && !(y & 1)) {
				chroma[(y / 2) * W + x] = cb << shift;
				chroma[(y / 2) * W + x + 1] = cr << shift;
			}
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

/* The plane's (P010, modifier) pairs, from IN_FORMATS. */
static void print_in_formats(int fd, uint32_t plane)
{
	drmModeObjectProperties *props;
	drmModeFormatModifierIterator iter = { 0 };
	drmModePropertyBlobRes *blob = NULL;
	uint32_t i;

	props = drmModeObjectGetProperties(fd, plane, DRM_MODE_OBJECT_PLANE);
	for (i = 0; props && i < props->count_props && !blob; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, props->props[i]);

		if (p && !strcmp(p->name, "IN_FORMATS"))
			blob = drmModeGetPropertyBlob(fd, props->prop_values[i]);
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	if (!blob) {
		printf("plane %u has no IN_FORMATS (no modifier support)\n", plane);
		return;
	}
	while (drmModeFormatModifierBlobIterNext(blob, &iter))
		if (iter.fmt == DRM_FORMAT_P010)
			printf("IN_FORMATS: P010 modifier 0x%016llx%s\n",
			       (unsigned long long)iter.mod,
			       iter.mod == DRM_FORMAT_MOD_ALLWINNER_LSB10 ? " (ALLWINNER_LSB10)" :
			       iter.mod == DRM_FORMAT_MOD_LINEAR ? " (LINEAR)" : "");
	drmModeFreePropertyBlob(blob);
}

static int plane_set(int fd, uint32_t plane, uint32_t crtc, uint32_t fb)
{
	static const char *const names[] = {
		"CRTC_ID", "FB_ID", "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H",
		"SRC_X", "SRC_Y", "SRC_W", "SRC_H",
	};
	uint64_t on[] = { crtc, fb, 0, 0, W, H, 0, 0,
			  (uint64_t)W << 16, (uint64_t)H << 16 };
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

static void dump_afbd(void)
{
	volatile uint32_t *r;
	unsigned i;
	int fd = open("/dev/mem", O_RDONLY | O_SYNC);

	if (fd < 0) {
		perror("/dev/mem");
		return;
	}
	r = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, AFBD_PHYS);
	close(fd);
	if (r == MAP_FAILED) {
		perror("mmap AFBD");
		return;
	}
	printf("AFBD 0x05600010 = 0x%08x  -> resolved fmt %u\n", r[0x10 / 4],
	       (r[0x10 / 4] >> 8) & 0xff);
	for (i = 0x10; i < 0xb0; i += 0x10)
		printf("AFBD +0x%03x: %08x %08x %08x %08x\n", i, r[i / 4],
		       r[i / 4 + 1], r[i / 4 + 2], r[i / 4 + 3]);
	munmap((void *)r, 4096);
}

int main(int argc, char **argv)
{
	struct drm_mode_create_dumb create = { .width = W, .height = H * 3 / 2,
					       .bpp = 16 };
	struct drm_mode_map_dumb map = { 0 };
	struct drm_mode_destroy_dumb destroy = { 0 };
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	uint64_t modifiers[4] = { 0 };
	uint32_t crtc = 0, plane = 0, fb = 0;
	drmModePlaneRes *pres = NULL;
	drmModeRes *res = NULL;
	unsigned dwell = argc > 1 ? (unsigned)atoi(argv[1]) : 20;
	const char *mode = getenv("FILL") ? getenv("FILL") : "split";
	char path[32];
	uint8_t *p;
	uint32_t i, f;
	int fd = -1, rc = 1;

	if (!getenv("ARMED") || strcmp(getenv("ARMED"), "yes") ||
	    (strcmp(mode, "split") && strcmp(mode, "msb") && strcmp(mode, "lsb"))) {
		fprintf(stderr, "usage: [FILL=split|msb|lsb] ARMED=yes %s [dwell-seconds]\n",
			argv[0]);
		return 2;
	}

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
			if (pl->formats[f] == DRM_FORMAT_P010)
				plane = pl->plane_id;
		drmModeFreePlane(pl);
	}
	if (!plane) {
		fprintf(stderr, "no plane advertises P010 -- is patch 0149 in this kernel?\n");
		goto out;
	}
	print_in_formats(fd, plane);

	if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create)) {
		perror("CREATE_DUMB");
		goto out;
	}
	if (create.pitch != PITCH) {
		fprintf(stderr, "dumb pitch %u, need %u\n", create.pitch, PITCH);
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
	fill(p, mode);
	munmap(p, create.size);

	handles[0] = handles[1] = create.handle;
	pitches[0] = pitches[1] = PITCH;
	offsets[1] = PITCH * H;
	if (!strcmp(mode, "lsb")) {
		modifiers[0] = modifiers[1] = DRM_FORMAT_MOD_ALLWINNER_LSB10;
		if (drmModeAddFB2WithModifiers(fd, W, H, DRM_FORMAT_P010, handles,
					       pitches, offsets, modifiers, &fb,
					       DRM_MODE_FB_MODIFIERS)) {
			perror("AddFB2 P010 + ALLWINNER_LSB10");
			goto out;
		}
	} else if (drmModeAddFB2(fd, W, H, DRM_FORMAT_P010, handles, pitches,
				 offsets, &fb, 0)) {
		perror("AddFB2 P010");
		goto out;
	}

	printf("WATCH THE PANEL: P010 on plane %u for %us, FILL=%s\n", plane,
	       dwell, mode);
	fflush(stdout);
	if (plane_set(fd, plane, crtc, fb)) {
		perror("atomic enable P010");
		goto out;
	}
	usleep(200000);
	dump_afbd();
	fflush(stdout);

	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);
	while (dwell && !interrupted)
		dwell = sleep(dwell);

	if (plane_set(fd, plane, 0, 0))
		fprintf(stderr, "atomic disable failed: %s\n", strerror(errno));
	else
		printf("P010 plane disabled; KMS RGB restored\n");
	rc = 0;
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
