// SPDX-License-Identifier: GPL-2.0
/*
 * Exercise the H713 fullscreen NV12 plane through DRM atomic KMS.
 *
 * Runs on the target and deliberately uses the scanout carveout exporter for
 * the first test: GEM DMA accepts that single contiguous PRIME mapping, while
 * fragmented Cedrus buffers remain blocked until the display IOMMU phase.
 *
 * Build on the target:
 *   cc -O2 -Wall -Wextra -Werror -o kms-nv12-plane-test \
 *      kms-nv12-plane-test.c $(pkg-config --cflags --libs libdrm)
 *
 * Run only with an observer watching:
 *   ARMED=yes kms-nv12-plane-test frame.nv12 [dwell-seconds]
 */
#define _GNU_SOURCE

#include <errno.h>
#include <math.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <gst/gst.h>
#include <gst/app/gstappsink.h>
#include <gst/allocators/gstdmabuf.h>

#include <drm_fourcc.h>
#include <xf86drm.h>
#include <xf86drmMode.h>

#define WIDTH 1280u
#define HEIGHT 720u
#define Y_SIZE (WIDTH * HEIGHT)
#define FRAME_SIZE (Y_SIZE + Y_SIZE / 2)
#define FRAME_PHYS 0x6c500000ULL
#define SCANOUT_IOC_GET_FD _IOWR('S', 1, struct scanout_req)

struct scanout_req {
	uint64_t phys;
	uint64_t size;
	int32_t fd;
	uint32_t pad;
};

static volatile sig_atomic_t interrupted;

static void on_signal(int sig)
{
	(void)sig;
	interrupted = 1;
}

static int open_kms(char *path_out, size_t path_len)
{
	unsigned int i;

	for (i = 0; i < 16; i++) {
		drmModeRes *res;
		char path[64];
		int fd;

		snprintf(path, sizeof(path), "/dev/dri/card%u", i);
		fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0)
			continue;
		res = drmModeGetResources(fd);
		if (res && res->count_crtcs == 1 && res->count_connectors) {
			drmModeFreeResources(res);
			snprintf(path_out, path_len, "%s", path);
			return fd;
		}
		drmModeFreeResources(res);
		close(fd);
	}

	errno = ENODEV;
	return -1;
}

static uint32_t find_prop(int fd, uint32_t object_id, uint32_t object_type,
			  const char *name)
{
	drmModeObjectProperties *props;
	uint32_t id = 0;
	uint32_t i;

	props = drmModeObjectGetProperties(fd, object_id, object_type);
	if (!props)
		return 0;
	for (i = 0; i < props->count_props; i++) {
		drmModePropertyRes *prop = drmModeGetProperty(fd,
							      props->props[i]);

		if (prop && !strcmp(prop->name, name))
			id = prop->prop_id;
		drmModeFreeProperty(prop);
		if (id)
			break;
	}
	drmModeFreeObjectProperties(props);
	return id;
}

static int add_prop(drmModeAtomicReq *req, uint32_t object_id,
			    uint32_t prop_id, uint64_t value,
			    const char *name)
{
	if (!prop_id) {
		fprintf(stderr, "plane has no %s property\n", name);
		return -1;
	}
	if (drmModeAtomicAddProperty(req, object_id, prop_id, value) < 0) {
		fprintf(stderr, "add %s: %s\n", name, strerror(errno));
		return -1;
	}
	return 0;
}

/*
 * dma-buf CPU-access bracketing.  msync() does NOT work here: a dma-buf mapping
 * has no writeback path, so msync(MS_SYNC) fails with EINVAL and the write is
 * never flushed.  DMA_BUF_IOCTL_SYNC is the only correct flush, and it is not
 * optional -- without it the CPU view is not guaranteed coherent with what the
 * device reads, and a stale cache line invents a display bug that is not there.
 * Same idiom as decd-play.c, in the write direction.
 */
struct kms_dma_buf_sync {
	uint64_t flags;
};
#define KMS_DMA_BUF_SYNC_WRITE (1ULL << 1)
#define KMS_DMA_BUF_SYNC_START (0ULL << 2)
#define KMS_DMA_BUF_SYNC_END   (1ULL << 2)
#define KMS_DMA_BUF_IOCTL_SYNC _IOW('b', 0, struct kms_dma_buf_sync)

static int dmabuf_sync(int dmabuf_fd, uint64_t flags, const char *what)
{
	struct kms_dma_buf_sync sync = { .flags = flags };

	if (ioctl(dmabuf_fd, KMS_DMA_BUF_IOCTL_SYNC, &sync) < 0) {
		perror(what);
		return -1;
	}
	return 0;
}

/*
 * Decode with Cedrus and return the dma-buf FD of a decoded frame, holding the
 * sample so the buffer stays alive for the caller.
 *
 * DECD_FREEZE_AT frames are discarded first, matching decd-play: frame 0 of the
 * diagnostic clip is black and useless as a visual result, frame 60 is the
 * known lit face. The pipeline is left PLAYING and the sample deliberately
 * leaked -- the process exits right after the test and a held CAPTURE buffer
 * must not be recycled while the plane is scanning it.
 */
static GstSample *held_sample;		/* on screen now */
static GstSample *prev_sample;		/* previous; freed one flip later */
static GstElement *held_pipeline;
static GstElement *held_sink;

/*
 * Page-flip event bookkeeping.
 *
 * A blocking commit tells you only that the ioctl returned; it says nothing
 * about when the flip actually reached the screen. The vblank timestamp does,
 * and it is the difference between "the loop ran at 59.71 fps" and "every frame
 * was presented on its own vsync" -- which is what drop-free and tear-free
 * actually mean. No camera can measure this as well: a phone at 120 fps beats
 * against 59.97 Hz and its rolling shutter mimics tearing.
 */
#define FLIP_PERIOD_US 16675.0		/* 59.97 Hz */
#define MAX_DELTAS 4096

static uint64_t flip_us;
static int flip_pending;

static void flip_handler(int fd, unsigned int seq, unsigned int tv_sec,
			 unsigned int tv_usec, unsigned int crtc_id, void *data)
{
	(void)fd; (void)seq; (void)crtc_id; (void)data;
	flip_us = (uint64_t)tv_sec * 1000000ull + tv_usec;
	flip_pending = 0;
}

/*
 * Report the distribution, not the mean. A mean of 16.7 ms is equally
 * consistent with every frame on its own vsync and with half the frames early
 * and half doubled; only the spread and the per-period histogram separate them.
 */
static void report_deltas(const double *d, unsigned n)
{
	unsigned i, drops = 0, h1 = 0, h2 = 0, h3 = 0;
	double lo = 1e9, hi = 0, sum = 0, var = 0, mean;

	if (!n) {
		printf("FLIP_TIMING no samples\n");
		return;
	}
	for (i = 0; i < n; i++) {
		unsigned periods = (unsigned)(d[i] / FLIP_PERIOD_US + 0.5);

		if (d[i] < lo)
			lo = d[i];
		if (d[i] > hi)
			hi = d[i];
		sum += d[i];
		if (periods <= 1)
			h1++;
		else if (periods == 2)
			h2++;
		else
			h3++;
		if (periods >= 2)
			drops += periods - 1;
	}
	mean = sum / n;
	for (i = 0; i < n; i++)
		var += (d[i] - mean) * (d[i] - mean);

	printf("FLIP_TIMING n=%u mean=%.2fms sd=%.2fms min=%.2f max=%.2f\n",
	       n, mean / 1000.0, sqrt(var / n) / 1000.0, lo / 1000.0,
	       hi / 1000.0);
	printf("FLIP_PERIODS 1x=%u 2x=%u 3x+=%u dropped=%u (%.2f%%)\n",
	       h1, h2, h3, drops, 100.0 * drops / n);
}

/*
 * Pull the next decoded frame and return its dma-buf FD.
 *
 * Two surfaces are held, not one: after committing frame N+1 the hardware may
 * still be scanning N until the flip retires, so N is released only once N+2
 * arrives. Keep this shallower than the decoder's CAPTURE pool -- the same
 * circular-wait that bit decd-play applies here, since a held surface is out of
 * the pool and the decoder blocks waiting for one.
 */
static int cedrus_next_frame(void)
{
	GstSample *s = gst_app_sink_pull_sample(GST_APP_SINK(held_sink));
	GstBuffer *buf;
	GstMemory *mem;

	if (!s)
		return -1;
	buf = gst_sample_get_buffer(s);
	if (gst_buffer_n_memory(buf) != 1)
		goto drop;
	mem = gst_buffer_peek_memory(buf, 0);
	if (!gst_is_dmabuf_memory(mem))
		goto drop;

	if (prev_sample)
		gst_sample_unref(prev_sample);
	prev_sample = held_sample;
	held_sample = s;
	return gst_dmabuf_memory_get_fd(mem);
drop:
	fprintf(stderr, "decoder gave an unusable buffer\n");
	gst_sample_unref(s);
	return -1;
}

static int cedrus_decode_frame(const char *path)
{
	unsigned want = 60, seen = 0;
	char desc[512];
	GstElement *sink;
	const char *env;
	int fd = -1;

	env = getenv("DECD_FREEZE_AT");
	if (env)
		want = (unsigned)strtoul(env, NULL, 0);

	gst_init(NULL, NULL);
	snprintf(desc, sizeof(desc),
		 "filesrc location=\"%s\" ! h264parse ! v4l2slh264dec ! "
		 "video/x-raw,format=NV12 ! "
		 "appsink name=out max-buffers=3 drop=false sync=false", path);
	held_pipeline = gst_parse_launch(desc, NULL);
	if (!held_pipeline) {
		fprintf(stderr, "cedrus pipeline will not build\n");
		return -1;
	}
	sink = gst_bin_get_by_name(GST_BIN(held_pipeline), "out");
	held_sink = sink;
	if (gst_element_set_state(held_pipeline, GST_STATE_PLAYING) ==
	    GST_STATE_CHANGE_FAILURE) {
		fprintf(stderr, "cedrus pipeline will not play\n");
		return -1;
	}

	for (;;) {
		GstSample *s = gst_app_sink_pull_sample(GST_APP_SINK(sink));
		GstBuffer *buf;
		GstMemory *mem;

		if (!s) {
			fprintf(stderr, "decode ended before frame %u\n", want);
			return -1;
		}
		if (seen++ < want) {
			gst_sample_unref(s);
			continue;
		}
		buf = gst_sample_get_buffer(s);
		if (gst_buffer_n_memory(buf) != 1) {
			fprintf(stderr, "need one dma-buf memory, got %u\n",
				gst_buffer_n_memory(buf));
			gst_sample_unref(s);
			return -1;
		}
		mem = gst_buffer_peek_memory(buf, 0);
		if (!gst_is_dmabuf_memory(mem)) {
			fprintf(stderr, "decoder did not give a dma-buf\n");
			gst_sample_unref(s);
			return -1;
		}
		fd = gst_dmabuf_memory_get_fd(mem);
		held_sample = s;	/* keep the surface out of the pool */
		printf("cedrus frame %u: dma-buf fd=%d\n", want, fd);
		return fd;
	}
}

static int stage_frame(const char *path, int dmabuf_fd, size_t map_len)
{
	struct stat st;
	uint8_t *map;
	size_t done = 0;
	int frame_fd;

	frame_fd = open(path, O_RDONLY | O_CLOEXEC);
	if (frame_fd < 0) {
		perror(path);
		return -1;
	}
	if (fstat(frame_fd, &st) || st.st_size != FRAME_SIZE) {
		fprintf(stderr, "%s must be exactly %u bytes\n", path,
			FRAME_SIZE);
		close(frame_fd);
		return -1;
	}

	map = mmap(NULL, map_len, PROT_READ | PROT_WRITE, MAP_SHARED,
		   dmabuf_fd, 0);
	if (map == MAP_FAILED) {
		perror("mmap scanout dma-buf");
		close(frame_fd);
		return -1;
	}
	if (dmabuf_sync(dmabuf_fd,
			KMS_DMA_BUF_SYNC_START | KMS_DMA_BUF_SYNC_WRITE,
			"dma-buf sync start")) {
		munmap(map, map_len);
		close(frame_fd);
		return -1;
	}
	while (done < FRAME_SIZE) {
		ssize_t n = read(frame_fd, map + done, FRAME_SIZE - done);

		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0) {
			perror("read frame");
			munmap(map, map_len);
			close(frame_fd);
			return -1;
		}
		done += (size_t)n;
	}
	if (dmabuf_sync(dmabuf_fd,
			KMS_DMA_BUF_SYNC_END | KMS_DMA_BUF_SYNC_WRITE,
			"dma-buf sync end")) {
		munmap(map, map_len);
		close(frame_fd);
		return -1;
	}
	munmap(map, map_len);
	close(frame_fd);
	return 0;
}

int main(int argc, char **argv)
{
	uint32_t handles[4] = { 0 }, pitches[4] = { 0 }, offsets[4] = { 0 };
	uint32_t crtc_id, plane_id = 0, fb_id = 0, gem_handle = 0;
	uint32_t p_crtc, p_fb, p_cx, p_cy, p_cw, p_ch;
	uint32_t p_sx, p_sy, p_sw, p_sh;
	drmModePlaneRes *plane_res = NULL;
	drmModeAtomicReq *atomic = NULL;
	drmModeRes *res = NULL;
	struct scanout_req scanout = { 0 };
	struct drm_gem_close gem_close = { 0 };
	struct sigaction sa = { 0 };
	size_t map_len = (FRAME_SIZE + 4095u) & ~4095u;
	char card[64];
	unsigned int dwell = 10;
	int scanout_ctl = -1, dmabuf_fd = -1, drm_fd = -1;
	int enabled = 0, rc = 1;
	uint32_t i;

	if (argc < 2 || argc > 3 || !getenv("ARMED") ||
	    strcmp(getenv("ARMED"), "yes")) {
		fprintf(stderr,
			"usage: ARMED=yes %s FRAME.nv12 [dwell-seconds]\n",
			argv[0]);
		return 2;
	}
	if (argc == 3) {
		char *end;
		unsigned long value = strtoul(argv[2], &end, 10);

		if (*end || !value || value > 300) {
			fprintf(stderr, "invalid dwell: %s\n", argv[2]);
			return 2;
		}
		dwell = (unsigned int)value;
	}

	drm_fd = open_kms(card, sizeof(card));
	if (drm_fd < 0) {
		perror("no KMS card");
		goto out;
	}
	if (drmSetClientCap(drm_fd, DRM_CLIENT_CAP_ATOMIC, 1)) {
		perror("DRM_CLIENT_CAP_ATOMIC");
		goto out;
	}
	res = drmModeGetResources(drm_fd);
	if (!res || res->count_crtcs != 1) {
		fprintf(stderr, "expected exactly one CRTC\n");
		goto out;
	}
	crtc_id = res->crtcs[0];

	plane_res = drmModeGetPlaneResources(drm_fd);
	if (!plane_res) {
		perror("drmModeGetPlaneResources");
		goto out;
	}
	for (i = 0; i < plane_res->count_planes && !plane_id; i++) {
		drmModePlane *plane = drmModeGetPlane(drm_fd,
						       plane_res->planes[i]);
		uint32_t f;

		if (!plane)
			continue;
		for (f = 0; f < plane->count_formats; f++) {
			if (plane->formats[f] == DRM_FORMAT_NV12 &&
			    plane->possible_crtcs & 1u && !plane->crtc_id &&
			    !plane->fb_id) {
				plane_id = plane->plane_id;
				break;
			}
		}
		drmModeFreePlane(plane);
	}
	if (!plane_id) {
		fprintf(stderr, "no disabled NV12 plane for CRTC %u\n", crtc_id);
		goto out;
	}

	p_crtc = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_ID");
	p_fb = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "FB_ID");
	p_cx = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_X");
	p_cy = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_Y");
	p_cw = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_W");
	p_ch = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_H");
	p_sx = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "SRC_X");
	p_sy = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "SRC_Y");
	p_sw = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "SRC_W");
	p_sh = find_prop(drm_fd, plane_id, DRM_MODE_OBJECT_PLANE, "SRC_H");

	/*
	 * CEDRUS=1 takes the buffer from the hardware decoder instead of the
	 * carveout. That is the whole point of the exercise: a Cedrus CAPTURE
	 * buffer is physically fragmented, and the carveout never was, so only
	 * this path exercises the IOMMU coalescing that
	 * drm_gem_dma_prime_import_sg_table() depends on. Buffer provenance is
	 * the single variable between the two modes.
	 */
	if (getenv("CEDRUS") && strcmp(getenv("CEDRUS"), "0")) {
		dmabuf_fd = cedrus_decode_frame(argv[1]);
		if (dmabuf_fd < 0)
			goto out;
	} else {
		scanout_ctl = open("/dev/scanout-dmabuf", O_RDWR | O_CLOEXEC);
		if (scanout_ctl < 0) {
			perror("/dev/scanout-dmabuf");
			goto out;
		}
		scanout.phys = FRAME_PHYS;
		scanout.size = map_len;
		scanout.fd = -1;
		if (ioctl(scanout_ctl, SCANOUT_IOC_GET_FD, &scanout)) {
			perror("SCANOUT_IOC_GET_FD");
			goto out;
		}
		dmabuf_fd = scanout.fd;
		if (stage_frame(argv[1], dmabuf_fd, map_len))
			goto out;
	}
	if (drmPrimeFDToHandle(drm_fd, dmabuf_fd, &gem_handle)) {
		perror("drmPrimeFDToHandle");
		goto out;
	}

	handles[0] = gem_handle;
	handles[1] = gem_handle;
	pitches[0] = WIDTH;
	pitches[1] = WIDTH;
	offsets[1] = Y_SIZE;
	if (drmModeAddFB2(drm_fd, WIDTH, HEIGHT, DRM_FORMAT_NV12, handles,
			  pitches, offsets, &fb_id, 0)) {
		perror("drmModeAddFB2 NV12");
		goto out;
	}

	atomic = drmModeAtomicAlloc();
	if (!atomic ||
	    add_prop(atomic, plane_id, p_crtc, crtc_id, "CRTC_ID") ||
	    add_prop(atomic, plane_id, p_fb, fb_id, "FB_ID") ||
	    add_prop(atomic, plane_id, p_cx, 0, "CRTC_X") ||
	    add_prop(atomic, plane_id, p_cy, 0, "CRTC_Y") ||
	    add_prop(atomic, plane_id, p_cw, WIDTH, "CRTC_W") ||
	    add_prop(atomic, plane_id, p_ch, HEIGHT, "CRTC_H") ||
	    add_prop(atomic, plane_id, p_sx, 0, "SRC_X") ||
	    add_prop(atomic, plane_id, p_sy, 0, "SRC_Y") ||
	    add_prop(atomic, plane_id, p_sw, (uint64_t)WIDTH << 16, "SRC_W") ||
	    add_prop(atomic, plane_id, p_sh, (uint64_t)HEIGHT << 16, "SRC_H"))
		goto out;

	printf("WATCH THE PANEL: %s plane %u on CRTC %u for %us\n",
	       card, plane_id, crtc_id, dwell);
	fflush(stdout);
	if (drmModeAtomicCommit(drm_fd, atomic, DRM_MODE_ATOMIC_ALLOW_MODESET,
				NULL)) {
		perror("atomic enable NV12");
		goto out;
	}
	enabled = 1;
	drmModeAtomicFree(atomic);
	atomic = NULL;

	sa.sa_handler = on_signal;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGINT, &sa, NULL);
	sigaction(SIGTERM, &sa, NULL);
	while (dwell && !interrupted)
		if (getenv("MOVING") && strcmp(getenv("MOVING"), "0")) {
			/*
			 * Flip loop. Everything validated before this was a
			 * static frame; page-flips, buffer rotation and the
			 * driver's per-commit register work are what this
			 * exercises. Report the achieved rate -- the panel is
			 * 59.97 Hz and DECD proved the hardware takes a frame
			 * every vsync, so anything far below that is the
			 * driver's per-flip cost, not the display.
			 */
			struct timespec t0, t1;
			uint32_t old_fb = fb_id, old_h = gem_handle;
			drmEventContext evctx = {
				.version = 3,
				.page_flip_handler2 = flip_handler,
			};
			static double deltas[MAX_DELTAS];
			uint64_t last_us = 0;
			unsigned ndelta = 0;
			unsigned flips = 0;
			double secs;

			clock_gettime(CLOCK_MONOTONIC, &t0);
			for (;;) {
				uint32_t nh = 0, nfb = 0;
				int nfd;

				clock_gettime(CLOCK_MONOTONIC, &t1);
				secs = (t1.tv_sec - t0.tv_sec) +
				       (t1.tv_nsec - t0.tv_nsec) / 1e9;
				if (secs >= (double)dwell)
					break;

				nfd = cedrus_next_frame();
				if (nfd < 0)
					break;
				if (drmPrimeFDToHandle(drm_fd, nfd, &nh)) {
					perror("drmPrimeFDToHandle");
					break;
				}
				handles[0] = nh;
				handles[1] = nh;
				if (drmModeAddFB2(drm_fd, WIDTH, HEIGHT,
						  DRM_FORMAT_NV12, handles,
						  pitches, offsets, &nfb, 0)) {
					perror("drmModeAddFB2");
					break;
				}
				drmModeAtomicFree(atomic);
				atomic = drmModeAtomicAlloc();
				flip_pending = 1;
				if (!atomic ||
				    add_prop(atomic, plane_id, p_fb, nfb, "FB_ID") ||
				    drmModeAtomicCommit(drm_fd, atomic,
							DRM_MODE_PAGE_FLIP_EVENT |
							DRM_MODE_ATOMIC_NONBLOCK,
							NULL)) {
					perror("atomic flip");
					break;
				}
				/*
				 * Bounded: a lost event must not hang the test
				 * with the plane still owning the panel.
				 */
				while (flip_pending) {
					struct pollfd pfd = {
						.fd = drm_fd,
						.events = POLLIN,
					};

					if (poll(&pfd, 1, 200) <= 0) {
						fprintf(stderr,
							"no page-flip event\n");
						flip_pending = 0;
						break;
					}
					if (drmHandleEvent(drm_fd, &evctx)) {
						perror("drmHandleEvent");
						flip_pending = 0;
						break;
					}
				}
				if (last_us && ndelta < MAX_DELTAS)
					deltas[ndelta++] = (double)(flip_us - last_us);
				last_us = flip_us;
				if (old_fb)
					drmModeRmFB(drm_fd, old_fb);
				if (old_h) {
					struct drm_gem_close gc = { .handle = old_h };

					drmIoctl(drm_fd, DRM_IOCTL_GEM_CLOSE, &gc);
				}
				old_fb = nfb;
				old_h = nh;
				flips++;
			}
			fb_id = old_fb;
			gem_handle = old_h;
			printf("FLIPS %u in %.2fs = %.2f fps\n", flips, secs,
			       secs > 0 ? flips / secs : 0.0);
			report_deltas(deltas, ndelta);
			dwell = 0;
		} else {
			dwell = sleep(dwell);
		}
	rc = 0;

out:
	if (enabled) {
		drmModeAtomicFree(atomic);
		atomic = drmModeAtomicAlloc();
		if (!atomic ||
		    add_prop(atomic, plane_id, p_fb, 0, "FB_ID") ||
		    add_prop(atomic, plane_id, p_crtc, 0, "CRTC_ID") ||
		    drmModeAtomicCommit(drm_fd, atomic,
					DRM_MODE_ATOMIC_ALLOW_MODESET, NULL)) {
			fprintf(stderr, "atomic disable NV12 failed: %s\n",
				strerror(errno));
			rc = 1;
		} else {
			printf("NV12 plane disabled; KMS RGB restored\n");
		}
	}
	drmModeAtomicFree(atomic);
	if (fb_id)
		drmModeRmFB(drm_fd, fb_id);
	if (gem_handle) {
		gem_close.handle = gem_handle;
		drmIoctl(drm_fd, DRM_IOCTL_GEM_CLOSE, &gem_close);
	}
	if (dmabuf_fd >= 0)
		close(dmabuf_fd);
	if (scanout_ctl >= 0)
		close(scanout_ctl);
	drmModeFreePlaneResources(plane_res);
	drmModeFreeResources(res);
	if (drm_fd >= 0)
		close(drm_fd);
	return rc;
}
