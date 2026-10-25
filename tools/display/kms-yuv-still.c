// SPDX-License-Identifier: GPL-2.0
/*
 * Show raw 1280x720 NV12 / NV16 stills on the H713 video plane, one after
 * another (HDMI panel-source design 10.25, Test 3).
 *
 * NV16 needs the EXPERIMENT kernel patch 0189 (AFBD format 2, chroma rows =
 * height). Each file is Y (1280x720) then interleaved CbCr (1280x360 for
 * NV12, 1280x720 for NV16); the extension (.nv12 / .nv16) picks the DRM
 * format. Every still goes into its own dumb buffer, is committed to the
 * video plane, held DWELL seconds, then the next replaces it; the plane is
 * disabled at the end and on SIGINT/SIGTERM. After each commit AFBD
 * 0x05600010 / 0x0560004c are read (/dev/mem, read-only) to show the format
 * byte and chroma rows the driver programmed.
 *
 * Build on the target:
 *   cc -O2 -Wall -Wextra -o kms-yuv-still kms-yuv-still.c $(pkg-config --cflags --libs libdrm)
 * Run with an observer watching:
 *   ARMED=yes kms-yuv-still DWELL a.nv12 b.nv16 ...
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#define W 1280u
#define H 720u
#define AFBD_PHYS 0x05600000
#define MAX_STILLS 8

static volatile sig_atomic_t interrupted;

static void on_signal(int sig)
{
	(void)sig;
	interrupted = 1;
}

static uint32_t find_prop(int fd, uint32_t obj, const char *name)
{
	drmModeObjectProperties *props = drmModeObjectGetProperties(fd, obj, DRM_MODE_OBJECT_PLANE);
	uint32_t id = 0, i;

	for (i = 0; props && i < props->count_props && !id; i++) {
		drmModePropertyRes *p = drmModeGetProperty(fd, props->props[i]);

		if (p && !strcmp(p->name, name))
			id = p->prop_id;
		drmModeFreeProperty(p);
	}
	drmModeFreeObjectProperties(props);
	return id;
}

static int plane_set(int fd, uint32_t plane, uint32_t crtc, uint32_t fb)
{
	static const char *const names[] = {
		"CRTC_ID", "FB_ID", "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H",
		"SRC_X", "SRC_Y", "SRC_W", "SRC_H",
	};
	uint64_t v[] = { crtc, fb, 0, 0, W, H, 0, 0, (uint64_t)W << 16, (uint64_t)H << 16 };
	unsigned i, n = fb ? 10 : 2;
	drmModeAtomicReq *req = drmModeAtomicAlloc();
	int ret;

	for (i = 0; i < n; i++) {
		uint32_t id = find_prop(fd, plane, names[i]);

		if (!id || drmModeAtomicAddProperty(req, plane, id, v[i]) < 0) {
			drmModeAtomicFree(req);
			return -1;
		}
	}
	ret = drmModeAtomicCommit(fd, req, DRM_MODE_ATOMIC_ALLOW_MODESET, NULL);
	drmModeAtomicFree(req);
	return ret;
}

static void dump_afbd(const char *label)
{
	volatile uint32_t *r;
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
	printf("%s: AFBD 0x10=%08x (fmt %u) 0x4c=%08x (chroma rows %u)\n", label,
	       r[0x10 / 4], (r[0x10 / 4] >> 8) & 0xff, r[0x4c / 4], r[0x4c / 4] >> 16);
	munmap((void *)r, 4096);
}

struct still {
	const char *path;
	uint32_t format, c_rows, handle, fb;
};

static int load(int fd, struct still *s)
{
	size_t len = strlen(s->path);
	struct drm_mode_create_dumb create = { .width = W, .bpp = 8 };
	struct drm_mode_map_dumb map = { 0 };
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	size_t want;
	struct stat st;
	uint8_t *p;
	int f;

	if (len > 5 && !strcmp(s->path + len - 5, ".nv12")) {
		s->format = DRM_FORMAT_NV12;
		s->c_rows = H / 2;
	} else if (len > 5 && !strcmp(s->path + len - 5, ".nv16")) {
		s->format = DRM_FORMAT_NV16;
		s->c_rows = H;
	} else {
		fprintf(stderr, "%s: extension must be .nv12 or .nv16\n", s->path);
		return -1;
	}
	want = (size_t)W * (H + s->c_rows);
	f = open(s->path, O_RDONLY | O_CLOEXEC);
	if (f < 0 || fstat(f, &st) || (size_t)st.st_size != want) {
		fprintf(stderr, "%s: need exactly %zu bytes\n", s->path, want);
		if (f >= 0)
			close(f);
		return -1;
	}
	create.height = H + s->c_rows;
	if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create)) {
		perror("CREATE_DUMB");
		close(f);
		return -1;
	}
	s->handle = create.handle;
	if (create.pitch != W) {
		fprintf(stderr, "dumb pitch %u, need %u\n", create.pitch, W);
		close(f);
		return -1;
	}
	map.handle = create.handle;
	if (drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map)) {
		perror("MAP_DUMB");
		close(f);
		return -1;
	}
	p = mmap(NULL, create.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
	if (p == MAP_FAILED || read(f, p, want) != (ssize_t)want) {
		perror("fill dumb");
		close(f);
		return -1;
	}
	munmap(p, create.size);
	close(f);
	handles[0] = handles[1] = s->handle;
	pitches[0] = pitches[1] = W;
	offsets[1] = W * H;
	if (drmModeAddFB2(fd, W, H, s->format, handles, pitches, offsets, &s->fb, 0)) {
		fprintf(stderr, "AddFB2 %s: %s\n", s->path, strerror(errno));
		return -1;
	}
	return 0;
}

int main(int argc, char **argv)
{
	struct still stills[MAX_STILLS] = { 0 };
	uint32_t crtc = 0, plane = 0, i, f;
	int nstill = argc - 2, fd = -1, rc = 1, has_nv16 = 0, shown = 0;
	unsigned dwell = argc > 1 ? (unsigned)atoi(argv[1]) : 0;
	drmModePlaneRes *pres = NULL;
	drmModeRes *res = NULL;
	char path[32];

	if (!getenv("ARMED") || strcmp(getenv("ARMED"), "yes") || nstill < 1 ||
	    nstill > MAX_STILLS || !dwell) {
		fprintf(stderr, "usage: ARMED=yes %s DWELL a.nv12 b.nv16 ...\n", argv[0]);
		return 2;
	}
	for (i = 0; i < 16 && !crtc; i++) {
		snprintf(path, sizeof(path), "/dev/dri/card%u", i);
		fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0)
			continue;
		res = drmModeGetResources(fd);
		if (res && res->count_crtcs == 1 && res->count_connectors) {
			crtc = res->crtcs[0];
		} else {
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
		int nv12 = 0, nv16 = 0;

		for (f = 0; pl && f < pl->count_formats; f++) {
			nv12 |= pl->formats[f] == DRM_FORMAT_NV12;
			nv16 |= pl->formats[f] == DRM_FORMAT_NV16;
		}
		if (nv12) {
			plane = pl->plane_id;
			has_nv16 = nv16;
		}
		drmModeFreePlane(pl);
	}
	if (!plane) {
		fprintf(stderr, "no video plane (no NV12)\n");
		goto out;
	}
	printf("video plane %u, NV16 %s\n", plane, has_nv16 ? "advertised" : "NOT advertised (no patch 0189)");
	for (i = 0; i < (uint32_t)nstill; i++) {
		stills[i].path = argv[i + 2];
		if (load(fd, &stills[i]))
			goto out;
		if (stills[i].format == DRM_FORMAT_NV16 && !has_nv16) {
			fprintf(stderr, "%s is NV16 but the plane lacks NV16\n", stills[i].path);
			goto out;
		}
	}
	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);
	for (i = 0; i < (uint32_t)nstill && !interrupted; i++) {
		unsigned left = dwell;

		if (plane_set(fd, plane, crtc, stills[i].fb)) {
			fprintf(stderr, "commit %s: %s\n", stills[i].path, strerror(errno));
			break;
		}
		shown = 1;
		usleep(200000);
		printf("STILL %u/%d %s (%s) for %us\n", i + 1, nstill, stills[i].path,
		       stills[i].format == DRM_FORMAT_NV16 ? "NV16" : "NV12", dwell);
		dump_afbd(stills[i].path);
		fflush(stdout);
		while (left && !interrupted)
			left = sleep(left);
	}
	rc = 0;
out:
	if (shown) {
		if (plane_set(fd, plane, 0, 0))
			fprintf(stderr, "disable failed: %s\n", strerror(errno));
		else
			printf("video plane disabled; console restored\n");
	}
	for (i = 0; i < MAX_STILLS; i++) {
		if (stills[i].fb)
			drmModeRmFB(fd, stills[i].fb);
		if (stills[i].handle) {
			struct drm_mode_destroy_dumb d = { .handle = stills[i].handle };

			drmIoctl(fd, DRM_IOCTL_MODE_DESTROY_DUMB, &d);
		}
	}
	drmModeFreePlaneResources(pres);
	drmModeFreeResources(res);
	if (fd >= 0)
		close(fd);
	return rc;
}
