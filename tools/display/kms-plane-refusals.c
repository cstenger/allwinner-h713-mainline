// SPDX-License-Identifier: GPL-2.0
/*
 * Letterbox Phase 4: does the video plane refuse, IN CHECK, every geometry
 * the hardware cannot show -- and accept the ones it can? RUNS ON THE TARGET,
 * as root, with nothing else holding DRM master (no kmssink, no mpv).
 *
 *   cc -O2 -Wall -o kms-plane-refusals kms-plane-refusals.c \
 *      $(pkg-config --cflags --libs libdrm)
 *   kms-plane-refusals
 *
 * Every case is one DRM_MODE_ATOMIC_TEST_ONLY commit of the video plane, so
 * nothing reaches the hardware and the panel is untouched. Each prints
 *
 *   PASS|FAIL  name  expect=accept|refuse  got=0|-errno  geometry
 *
 * and the last line is `REFUSALS pass=N fail=M`; exit status 1 on any FAIL.
 *
 * WHY THE ACCEPT CASES. A suite of refusals alone passes whenever the commit
 * fails for any reason -- no master, a wrong property id, an inactive CRTC.
 * The accept cases (native, unity placement, every magnification the Phase 3
 * gate showed on the glass) are the positive controls: if they fail, the
 * refusals prove nothing, and the summary says so.
 *
 * The geometry rules are the kernel's (0161 h713_lb_check, 0163 scaling):
 * NV12 only below native; even source sizes from 64 up; no source crop;
 * magnify 1x..4x per axis, never shrink; destination fully on the panel;
 * pitch a multiple of 16 covering ALIGN(w, 16); the buffer must cover the
 * whole 16-row blocks AFBD fetches (-ERANGE, not -EINVAL). Odd destination
 * x/width/height are rounded down to even and ACCEPTED (kmssink centres
 * 852x480 as 1278x720 at x = 1).
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>

#define PANEL_W 1280
#define PANEL_H 720

static int fd;
static uint32_t plane_id, crtc_id;
static uint32_t p_fb, p_crtc, p_sx, p_sy, p_sw, p_sh, p_cx, p_cy, p_cw, p_ch;

static uint32_t prop_id(uint32_t obj, uint32_t type, const char *name)
{
	drmModeObjectProperties *pr = drmModeObjectGetProperties(fd, obj, type);
	uint32_t id = 0;

	for (uint32_t i = 0; pr && i < pr->count_props; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, pr->props[i]);

		if (p && !strcmp(p->name, name))
			id = p->prop_id;
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(pr);
	if (!id) {
		fprintf(stderr, "no property %s on object %u\n", name, obj);
		exit(2);
	}
	return id;
}

/* The plane that takes NV12 is the video plane; the active CRTC drives it. */
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
		fprintf(stderr, "no NV12 plane (%u) or active CRTC (%u)\n",
			plane_id, crtc_id);
		exit(2);
	}
	p_fb = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "FB_ID");
	p_crtc = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_ID");
	p_sx = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "SRC_X");
	p_sy = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "SRC_Y");
	p_sw = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "SRC_W");
	p_sh = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "SRC_H");
	p_cx = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_X");
	p_cy = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_Y");
	p_cw = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_W");
	p_ch = prop_id(plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_H");
	drmModeFreePlaneResources(pr);
	drmModeFreeResources(res);
}

/* One dumb buffer, `pitch` bytes wide and `rows` lines (the driver adds
 * 16 lines of slack, so the object is pitch x (rows + 16)). */
static uint32_t dumb(uint32_t pitch, uint32_t rows, uint64_t *size)
{
	struct drm_mode_create_dumb c = { .width = pitch, .height = rows, .bpp = 8 };

	if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &c)) {
		perror("CREATE_DUMB");
		exit(2);
	}
	*size = c.size;
	return c.handle;
}

/* A framebuffer of fourcc `fmt` over one object; returns 0 if AddFB2
 * itself refuses (then the case is a harness error, not a plane result). */
static uint32_t fb(uint32_t handle, uint32_t fmt, uint64_t mod, uint32_t w,
		   uint32_t h, uint32_t pitch, uint32_t c_off)
{
	uint32_t hs[4] = { handle, handle }, ps[4] = { pitch, pitch };
	uint32_t os[4] = { 0, c_off }, id = 0;
	uint64_t ms[4] = { mod, mod };

	if (drmModeAddFB2WithModifiers(fd, w, h, fmt, hs, ps, os,
				       mod != DRM_FORMAT_MOD_LINEAR ? ms : NULL,
				       &id, mod != DRM_FORMAT_MOD_LINEAR ?
				       DRM_MODE_FB_MODIFIERS : 0)) {
		fprintf(stderr, "AddFB2 %ux%u pitch %u c_off %u: %s\n",
			w, h, pitch, c_off, strerror(errno));
		return 0;
	}
	return id;
}

static int pass, fail;

static void test(const char *name, int expect_ok, uint32_t fb_id,
		 int sx, int sy, int sw, int sh, int cx, int cy, int cw, int ch)
{
	drmModeAtomicReq *r = drmModeAtomicAlloc();
	int ret, ok;

	if (!fb_id) {
		printf("FAIL  %-28s harness: no framebuffer\n", name);
		fail++;
		return;
	}
	drmModeAtomicAddProperty(r, plane_id, p_fb, fb_id);
	drmModeAtomicAddProperty(r, plane_id, p_crtc, crtc_id);
	drmModeAtomicAddProperty(r, plane_id, p_sx, (uint64_t)sx << 16);
	drmModeAtomicAddProperty(r, plane_id, p_sy, (uint64_t)sy << 16);
	drmModeAtomicAddProperty(r, plane_id, p_sw, (uint64_t)sw << 16);
	drmModeAtomicAddProperty(r, plane_id, p_sh, (uint64_t)sh << 16);
	drmModeAtomicAddProperty(r, plane_id, p_cx, (uint64_t)(int64_t)cx);
	drmModeAtomicAddProperty(r, plane_id, p_cy, (uint64_t)(int64_t)cy);
	drmModeAtomicAddProperty(r, plane_id, p_cw, cw);
	drmModeAtomicAddProperty(r, plane_id, p_ch, ch);
	ret = drmModeAtomicCommit(fd, r, DRM_MODE_ATOMIC_TEST_ONLY, NULL) ? -errno : 0;
	drmModeAtomicFree(r);

	ok = expect_ok ? ret == 0 : ret != 0;
	printf("%s  %-28s expect=%-6s got=%-4d src %dx%d+%d+%d -> %dx%d at (%d,%d)\n",
	       ok ? "PASS" : "FAIL", name, expect_ok ? "accept" : "refuse", ret,
	       sw, sh, sx, sy, cw, ch, cx, cy);
	ok ? pass++ : fail++;
}

#define ACCEPT(n, ...) test(n, 1, __VA_ARGS__)
#define REFUSE(n, ...) test(n, 0, __VA_ARGS__)

int main(void)
{
	uint64_t sz;
	uint32_t h, native, p010, lb536, c852, s640, s352, s720, s160;
	uint32_t tight, p856, p010s;
	int ctl_fail;

	fd = drmOpen("sun50i-h713-afbd", NULL);
	if (fd < 0) {
		perror("drmOpen sun50i-h713-afbd");
		return 2;
	}
	if (drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) ||
	    drmSetClientCap(fd, DRM_CLIENT_CAP_ATOMIC, 1)) {
		perror("client caps");
		return 2;
	}
	if (drmSetMaster(fd)) {
		perror("drmSetMaster (is a player running?)");
		return 2;
	}
	find_plane();
	printf("REFUSALS plane=%u crtc=%u\n", plane_id, crtc_id);

	/* Buffers: NV12 is pitch x (rows + rows/2); dumb adds 16 slack rows. */
	h = dumb(1280, 768 + 384, &sz);
	native = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 1280, 720, 1280, 1280 * 768);
	h = dumb(2560, 768 + 384, &sz);
	p010 = fb(h, DRM_FORMAT_P010, DRM_FORMAT_MOD_LINEAR, 1280, 720, 2560, 2560 * 768);
	p010s = fb(h, DRM_FORMAT_P010, DRM_FORMAT_MOD_LINEAR, 640, 360, 2560, 2560 * 768);
	h = dumb(1280, 544 + 272, &sz);
	lb536 = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 1280, 536, 1280, 1280 * 544);
	h = dumb(864, 480 + 240, &sz);
	c852 = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 852, 480, 864, 864 * 480);
	h = dumb(640, 368 + 184, &sz);
	s640 = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 640, 360, 640, 640 * 368);
	h = dumb(352, 288 + 144, &sz);
	s352 = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 352, 288, 352, 352 * 288);
	h = dumb(720, 576 + 288, &sz);
	s720 = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 720, 576, 720, 720 * 576);
	h = dumb(160, 96 + 48, &sz);
	s160 = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 160, 90, 160, 160 * 96);
	/*
	 * TIGHT: 1280x536 whose chroma plane starts right after 536 luma rows.
	 * The object is 1280 x (788 + 16) = 536 + 268 rows: enough for AddFB2
	 * (536 + 268) but not for AFBD's whole blocks (chroma 272 rows) --
	 * exactly the fetch that would run off the end and fault the IOMMU.
	 */
	h = dumb(1280, 536 + 268 - 16, &sz);
	tight = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 1280, 536, 1280, 1280 * 536);
	/* PITCH 856: a multiple of 8, not 16 -- AFBD would shear. */
	h = dumb(1024, 480 + 240, &sz);
	p856 = fb(h, DRM_FORMAT_NV12, DRM_FORMAT_MOD_LINEAR, 852, 480, 856, 856 * 480);

	/* Positive controls: what the Phase 2/3 gates showed on the glass. */
	ACCEPT("native 1280x720", native, 0, 0, 1280, 720, 0, 0, 1280, 720);
	ACCEPT("p010 native", p010, 0, 0, 1280, 720, 0, 0, 1280, 720);
	ACCEPT("unity scope 1280x536", lb536, 0, 0, 1280, 536, 0, 92, 1280, 536);
	ACCEPT("unity 852x480 centred", c852, 0, 0, 852, 480, 214, 120, 852, 480);
	ACCEPT("unity at origin", c852, 0, 0, 852, 480, 0, 0, 852, 480);
	ACCEPT("unity bottom-right corner", c852, 0, 0, 852, 480, 428, 240, 852, 480);
	ACCEPT("2x 640x360", s640, 0, 0, 640, 360, 0, 0, 1280, 720);
	ACCEPT("1.5x 852x480", c852, 0, 0, 852, 480, 2, 0, 1278, 720);
	ACCEPT("2.5x 352x288 pillarbox", s352, 0, 0, 352, 288, 200, 0, 880, 720);
	ACCEPT("unequal 720x576 -> 960x720", s720, 0, 0, 720, 576, 160, 0, 960, 720);
	ACCEPT("4x exactly 160x90", s160, 0, 0, 160, 90, 0, 0, 640, 360);
	ACCEPT("odd dst x (kmssink 1278@1)", c852, 0, 0, 852, 480, 1, 0, 1278, 720);
	ACCEPT("odd dst y", c852, 0, 0, 852, 480, 0, 121, 852, 480);
	ctl_fail = fail;

	/* Refusals. */
	REFUSE("buffer short of 16-row blocks", tight, 0, 0, 1280, 536, 0, 92, 1280, 536);
	REFUSE("pitch not multiple of 16", p856, 0, 0, 852, 480, 214, 120, 852, 480);
	REFUSE("odd source width", c852, 0, 0, 851, 480, 214, 120, 851, 480);
	REFUSE("odd source height", c852, 0, 0, 852, 479, 214, 120, 852, 479);
	REFUSE("source below 64x64", c852, 0, 0, 62, 62, 0, 0, 62, 62);
	REFUSE("source crop x", c852, 2, 0, 640, 480, 0, 0, 640, 480);
	REFUSE("source crop y", c852, 0, 2, 852, 400, 0, 0, 852, 400);
	REFUSE("off panel right", c852, 0, 0, 852, 480, 430, 120, 852, 480);
	REFUSE("off panel bottom", c852, 0, 0, 852, 480, 214, 242, 852, 480);
	REFUSE("negative x", c852, 0, 0, 852, 480, -2, 120, 852, 480);
	REFUSE("negative y", c852, 0, 0, 852, 480, 214, -2, 852, 480);
	REFUSE("dst larger than panel", s640, 0, 0, 640, 360, 0, 0, 1284, 722);
	REFUSE("downscale 1280x720 -> 640x360", native, 0, 0, 1280, 720, 0, 0, 640, 360);
	REFUSE("shrink one axis", s640, 0, 0, 640, 360, 0, 0, 1280, 180);
	REFUSE("magnify beyond 4x", s160, 0, 0, 160, 90, 0, 0, 1280, 720);
	REFUSE("p010 below native", p010s, 0, 0, 640, 360, 0, 0, 640, 360);
	REFUSE("p010 magnified", p010s, 0, 0, 640, 360, 0, 0, 1280, 720);
	REFUSE("p010 sub-panel window", p010, 0, 0, 1280, 536, 0, 92, 1280, 536);

	if (ctl_fail)
		printf("REFUSALS INVALID: %d positive control(s) failed, so the refusals prove nothing\n",
		       ctl_fail);
	printf("REFUSALS pass=%d fail=%d\n", pass, fail);
	return fail ? 1 : 0;
}
