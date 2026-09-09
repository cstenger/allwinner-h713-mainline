// SPDX-License-Identifier: GPL-2.0
/*
 * decd-play -- submit Cedrus-decoded NV12 dma-bufs directly to H713 DECD.
 *
 * Runs ON THE TARGET. Build:
 *   gcc -O2 -Wall -Wextra -o decd-play decd-play.c $(pkg-config --cflags \
 *     --libs gstreamer-1.0 gstreamer-app-1.0 gstreamer-allocators-1.0 \
 *     gstreamer-video-1.0)
 *
 * This is deliberately strict.  It refuses system-memory fallback, multiple
 * dma-buf memories, non-NV12 output, non-zero GstMemory offsets, and layouts
 * whose stride/chroma offset cannot be represented by the stock 112-byte DECD
 * descriptor.  A quiet CPU copy would defeat the purpose of this test.
 *
 * The program owns only decoder submission.  It does not touch source enable,
 * source geometry, chroma gain, or the downstream plane selector; the guarded
 * decd-visible-sequence.sh diagnostic owns and restores that shared state.
 *
 * Surface retirement is driven by the release fence FRAME_SUBMIT returns.  A
 * capture surface goes back to Cedrus only once DECD has signalled that it is
 * finished scanning it out.  Requires the kernel fence-lifetime fix (patch
 * 0071): before it, the returned sync_file referenced a freed dma_fence, so the
 * FD had to be closed immediately and the retention depth guessed instead.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <gst/allocators/gstdmabuf.h>
#include <gst/app/gstappsink.h>
#include <gst/gst.h>
#include <gst/video/video.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define DECD_IOC_PM_HINT      0x40046401u
#define DECD_IOC_FRAME_SUBMIT 0x40706400u
#define SCANOUT_IOC_GET_FD _IOWR('S', 1, struct scanout_req)

#define INFO_PHYS 0x6c8f0000ULL
#define INFO_SIZE 0x8000u
#define VIDEO_COORD_W 1920u
#define VIDEO_COORD_H 1080u
#define DEC_FORMAT_NV12_CANDIDATE 6u

/*
 * How many submitted surfaces may be awaiting their release fence at once.
 *
 * DECD installs a frame in four hardware slots and retires it only when a
 * *later* frame displaces it, so a held surface cannot be released without
 * submitting a new one.  Holding too many is therefore not merely wasteful, it
 * is a circular wait: every free capture buffer is held pending a fence that
 * needs a new capture buffer to signal.  That is what starved the pool at eight.
 *
 * Keep the cap strictly below the decoder's capture-pool size, and remember
 * appsink holds max-buffers on top of this.
 */
#define DEFAULT_MAX_PENDING 4u
#define PENDING_CAP 32u
#define FENCE_POLL_SLICE_MS 100
#define FENCE_STALL_BUDGET_MS 2000
#define DRAIN_BUDGET_MS 1000

struct scanout_req {
	uint64_t phys;
	uint64_t size;
	int32_t fd;
	uint32_t pad;
};

struct dec_ioctl_header {
	uint64_t user_ptr;
	uint64_t user_ptr2;
	uint32_t repeat;
	uint32_t reserved14;
	uint32_t reserved18;
	uint32_t reserved1c;
};

struct dec_frame_submit_desc {
	uint8_t compressed;
	uint8_t blue_en;
	uint8_t reserved02[2];
	int32_t image_fd;
	uint32_t format;
	uint32_t reserved0c[7];
	uint32_t width;
	uint32_t height;
	uint32_t chroma_width;
	uint32_t chroma_height;
	uint32_t chroma_width2;
	uint32_t chroma_height2;
	uint32_t stride_align;
	uint32_t stride_align2;
	uint32_t stride_align3;
	int32_t info_fd;
	uint32_t info_size;
	uint32_t info_align;
	uint32_t legacy_info_phys;
	uint32_t reserved5c;
	uint8_t split_fields;
	uint8_t reserved61[3];
	uint32_t field_select;
	uint8_t legacy_direct;
	uint8_t reserved69[7];
};

_Static_assert(sizeof(struct dec_ioctl_header) == 32, "ioctl wrapper ABI");
_Static_assert(sizeof(struct dec_frame_submit_desc) == 112, "frame ABI");

/* Submitted surfaces, oldest first.  DECD retires in submission order. */
struct pending_frame {
	GstSample *sample;
	int fence_fd;
	unsigned seq;
};

static struct pending_frame pending[PENDING_CAP];
static unsigned pending_head;
static unsigned pending_count;
static unsigned pending_peak;
static unsigned retired_by_fence;
static unsigned stall_episodes;

/*
 * Where the wall clock goes, in milliseconds.  Added because a 29.95 -> 27.1 fps
 * regression across the fence-driven rewrite was attributed to nothing in
 * particular for a week: under a PTS-paced sink those numbers do not mean
 * "slower throughput", they mean deadlines are being missed, and guessing which
 * phase is responsible is exactly the sort of thing to measure instead.
 *
 * t_pull is the one to watch.  Holding surfaces until their fences signal keeps
 * them out of the decoder's CAPTURE pool, so if the hold is starving cedrus the
 * cost lands here -- inside the appsink pull, where the existing stall counter
 * cannot see it, because that only counts our own capacity waits.
 */
static double t_pull, t_submit, t_reap;

static double now_ms(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static void pending_push(GstSample *sample, int fence_fd, unsigned seq)
{
	unsigned slot = (pending_head + pending_count) % PENDING_CAP;

	pending[slot].sample = sample;
	pending[slot].fence_fd = fence_fd;
	pending[slot].seq = seq;
	pending_count++;
	if (pending_count > pending_peak)
		pending_peak = pending_count;
}

/* Release the oldest surface: close its fence, then hand the buffer back. */
static void pending_retire_head(void)
{
	struct pending_frame *p = &pending[pending_head];

	if (p->fence_fd >= 0)
		close(p->fence_fd);
	gst_sample_unref(p->sample);
	p->sample = NULL;
	p->fence_fd = -1;
	pending_head = (pending_head + 1) % PENDING_CAP;
	pending_count--;
}

/*
 * Retire every surface whose fence has signalled.  timeout_ms applies only to
 * the oldest one: pass 0 to sweep without blocking the decode loop, or a
 * positive value to wait for the head.  A signalled sync_file polls readable.
 */
static int reap_signaled(int timeout_ms)
{
	while (pending_count) {
		struct pollfd pfd = {
			.fd = pending[pending_head].fence_fd,
			.events = POLLIN,
		};
		int rc = poll(&pfd, 1, timeout_ms);

		if (rc < 0) {
			if (errno == EINTR)
				continue;
			perror("poll release fence");
			return -1;
		}
		if (rc == 0)
			break;
		pending_retire_head();
		retired_by_fence++;
		timeout_ms = 0;
	}
	return 0;
}

/*
 * Block until the hold drops below the cap.  Bounded, because the wait is
 * circular by construction: if the decoder cannot hand us another frame there
 * is nothing left to displace the one we are waiting on, and reporting that is
 * far more useful than silently reusing a surface DECD is still scanning.
 */
static int wait_for_capacity(unsigned max_pending)
{
	int waited = 0;

	if (pending_count < max_pending)
		return 0;
	stall_episodes++;
	while (pending_count >= max_pending) {
		if (reap_signaled(FENCE_POLL_SLICE_MS))
			return -1;
		if (pending_count < max_pending)
			return 0;
		waited += FENCE_POLL_SLICE_MS;
		if (waited >= FENCE_STALL_BUDGET_MS) {
			fprintf(stderr,
				"frame %u's release fence has not signalled in "
				"%d ms with %u held (cap %u); DECD retires a "
				"frame only when a later one displaces it, so "
				"the hold is too deep for this capture pool\n",
				pending[pending_head].seq, waited,
				pending_count, max_pending);
			return -1;
		}
	}
	return 0;
}

static unsigned max_pending_setting(void)
{
	const char *s = getenv("DECD_MAX_PENDING");
	unsigned long value;

	if (!s || !*s)
		return DEFAULT_MAX_PENDING;
	value = strtoul(s, NULL, 0);
	if (value < 1 || value >= PENDING_CAP) {
		fprintf(stderr, "DECD_MAX_PENDING=%lu out of range, using %u\n",
			value, DEFAULT_MAX_PENDING);
		return DEFAULT_MAX_PENDING;
	}
	return (unsigned)value;
}

/*
 * Report whether the decoder's buffer is physically contiguous, and where it
 * actually lives.
 *
 * This matters because DECD has no scatter-gather: dec_dma_map() keeps only
 * sg_dma_address(sgt->sgl) and the hardware scans from that one base with a
 * fixed stride, deriving the chroma address arithmetically. If the import is
 * segmented, everything past segment 0 is unrelated memory -- which looks
 * exactly like decoder corruption while the buffer itself is bit-exact.
 *
 * Compare the first PFN printed here against the Y base DECD is programmed
 * with at 0x05600070: equal means DECD is reading the real buffer, different
 * means it was handed an address valid only in someone else's address space.
 */
static void report_physical_layout(uint8_t *map, size_t size)
{
	long page = sysconf(_SC_PAGESIZE);
	size_t pages = (size + page - 1) / page;
	uint64_t first_pfn = 0, prev_pfn = 0;
	size_t breaks = 0, absent = 0, run = 0, longest = 0;
	int fd = open("/proc/self/pagemap", O_RDONLY);
	size_t i;

	if (fd < 0) {
		perror("open /proc/self/pagemap");
		return;
	}
	for (i = 0; i < pages; i++) {
		uint64_t entry, pfn;
		off_t at = (off_t)(((uintptr_t)map / page) + i) * 8;

		if (pread(fd, &entry, sizeof(entry), at) != sizeof(entry)) {
			perror("pread pagemap");
			break;
		}
		if (!(entry & (1ULL << 63))) {
			absent++;
			continue;
		}
		pfn = entry & ((1ULL << 55) - 1);
		if (!i)
			first_pfn = pfn;
		if (i && pfn != prev_pfn + 1) {
			breaks++;
			run = 0;
		}
		run++;
		if (run > longest)
			longest = run;
		prev_pfn = pfn;
	}
	close(fd);

	printf("PHYS pages=%zu first=0x%llx contiguous=%s breaks=%zu "
	       "longest-run=%zu(%zuKiB) absent=%zu\n",
	       pages, (unsigned long long)(first_pfn * (uint64_t)page),
	       breaks ? "NO" : "yes", breaks, longest,
	       longest * (size_t)page / 1024, absent);
	if (!first_pfn && !absent)
		printf("PHYS note: PFNs read as zero (mapping may be VM_PFNMAP, "
		       "or the read lacked privilege) -- treat as no answer\n");
}

/*
 * Declared locally rather than pulled from <linux/dma-buf.h>, which is not
 * reliably present in a target sysroot. Values are UAPI and fixed.
 */
struct decd_dma_buf_sync {
	uint64_t flags;
};
#define DECD_DMA_BUF_SYNC_READ  (1ULL << 0)
#define DECD_DMA_BUF_SYNC_START (0ULL << 2)
#define DECD_DMA_BUF_SYNC_END   (1ULL << 2)
#define DECD_DMA_BUF_IOCTL_SYNC _IOW('b', 0, struct decd_dma_buf_sync)

/*
 * Write the bytes DECD is about to be handed, exactly as they sit in the
 * decoder's buffer.  The point is to settle whether the decoder's output is
 * really the linear NV12 its GstVideoMeta claims: Cedrus natively emits
 * NV12_32L32 (32x32 tiled) and only produces linear when the caps force it, and
 * metadata claiming linear is not the same fact as the buffer being linear.
 *
 * The SYNC ioctls are not optional. Without them the CPU view of a dma-buf is
 * not guaranteed coherent with what the device wrote, and a stale-cache read
 * would look exactly like corrupt decoder output — inventing the very bug we
 * are trying to attribute.
 */
static int dump_frame(int image_fd, size_t size, const char *path)
{
	struct decd_dma_buf_sync sync;
	uint8_t *map;
	FILE *f;
	size_t written;

	map = mmap(NULL, size, PROT_READ, MAP_SHARED, image_fd, 0);
	if (map == MAP_FAILED) {
		perror("mmap decoded dma-buf");
		return -1;
	}
	sync.flags = DECD_DMA_BUF_SYNC_START | DECD_DMA_BUF_SYNC_READ;
	if (ioctl(image_fd, DECD_DMA_BUF_IOCTL_SYNC, &sync) < 0)
		perror("DMA_BUF_IOCTL_SYNC start");

	f = fopen(path, "wb");
	if (!f) {
		perror(path);
		munmap(map, size);
		return -1;
	}
	report_physical_layout(map, size);
	written = fwrite(map, 1, size, f);
	if (fclose(f) || written != size) {
		fprintf(stderr, "dump wrote %zu of %zu bytes\n", written, size);
		munmap(map, size);
		return -1;
	}

	sync.flags = DECD_DMA_BUF_SYNC_END | DECD_DMA_BUF_SYNC_READ;
	if (ioctl(image_fd, DECD_DMA_BUF_IOCTL_SYNC, &sync) < 0)
		perror("DMA_BUF_IOCTL_SYNC end");
	munmap(map, size);
	printf("DUMPED %zu bytes of frame 0 to %s\n", size, path);
	return 0;
}

/*
 * Copy a decoded frame into the fixed scanout carveout and submit that instead.
 *
 * Purely diagnostic -- it is a CPU copy, which is the thing this player exists
 * to avoid. It isolates the one variable that separates every working result
 * from every broken one: buffer provenance. Static carveout frames have always
 * displayed correctly; Cedrus frames never have. The carveout is a single
 * physically contiguous run, a Cedrus buffer is not.
 *
 * Same bytes, same route, same geometry -- only the memory differs. If this
 * displays, decoded content is fine and the remaining work is making the
 * decoder allocate contiguously. If it does not, decoded content differs from a
 * synthetic test card in some way nobody has identified yet.
 */
static int copy_to_carveout(int image_fd, int ctl_fd, size_t size,
			    uint64_t phys, int *out_fd)
{
	struct scanout_req req = { .phys = phys, .size = size, .fd = -1 };
	struct decd_dma_buf_sync sync;
	uint8_t *src = MAP_FAILED, *dst = MAP_FAILED;
	int ret = -1;

	if (ioctl(ctl_fd, SCANOUT_IOC_GET_FD, &req) < 0) {
		perror("SCANOUT_IOC_GET_FD carveout");
		return -1;
	}
	src = mmap(NULL, size, PROT_READ, MAP_SHARED, image_fd, 0);
	if (src == MAP_FAILED) {
		perror("mmap decoded buffer");
		goto out;
	}
	dst = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, req.fd, 0);
	if (dst == MAP_FAILED) {
		perror("mmap carveout");
		goto out;
	}
	sync.flags = DECD_DMA_BUF_SYNC_START | DECD_DMA_BUF_SYNC_READ;
	if (ioctl(image_fd, DECD_DMA_BUF_IOCTL_SYNC, &sync) < 0)
		perror("DMA_BUF_IOCTL_SYNC start");

	memcpy(dst, src, size);

	sync.flags = DECD_DMA_BUF_SYNC_END | DECD_DMA_BUF_SYNC_READ;
	if (ioctl(image_fd, DECD_DMA_BUF_IOCTL_SYNC, &sync) < 0)
		perror("DMA_BUF_IOCTL_SYNC end");
	msync(dst, size, MS_SYNC);
	__sync_synchronize();

	printf("CARVEOUT: copied %zu bytes of frame 0 to 0x%llx, submitting that\n",
	       size, (unsigned long long)phys);
	*out_fd = req.fd;
	req.fd = -1;
	ret = 0;
out:
	if (src != MAP_FAILED)
		munmap(src, size);
	if (dst != MAP_FAILED)
		munmap(dst, size);
	if (req.fd >= 0)
		close(req.fd);
	return ret;
}

static gboolean on_propose_allocation(GstElement *sink, GstQuery *query,
				      gpointer user_data)
{
	(void)sink;
	(void)user_data;
	gst_query_add_allocation_meta(query, GST_VIDEO_META_API_TYPE, NULL);
	return TRUE;
}

static int export_info_buffer(int ctl_fd)
{
	struct scanout_req req = {
		.phys = INFO_PHYS,
		.size = INFO_SIZE,
		.fd = -1,
	};

	if (ioctl(ctl_fd, SCANOUT_IOC_GET_FD, &req) < 0) {
		perror("SCANOUT_IOC_GET_FD info");
		return -1;
	}
	return req.fd;
}

static uint32_t video_info_format(void)
{
	const char *s = getenv("DECD_FMT");
	unsigned long value;

	if (!s || !*s)
		return 0;
	value = strtoul(s, NULL, 0);
	if (value > 15) {
		fprintf(stderr, "DECD_FMT=%lu out of range\n", value);
		return 0;
	}
	return (uint32_t)value;
}

static int fill_video_info(int fd, unsigned width, unsigned height,
			   unsigned fps_n, unsigned fps_d)
{
	uint8_t *map = mmap(NULL, INFO_SIZE, PROT_READ | PROT_WRITE,
			    MAP_SHARED, fd, 0);
	uint32_t *v;
	uint32_t format_selector = video_info_format();
	uint32_t fps_milli = fps_d ? (uint32_t)(((uint64_t)fps_n * 1000) / fps_d)
				    : 60000;

	if (map == MAP_FAILED) {
		perror("mmap info dma-buf");
		return -1;
	}
	memset(map, 0, INFO_SIZE);
	v = (uint32_t *)(map + 0x1000);
	v[0x00 / 4] = 0x61770000;
	v[0x04 / 4] = 2;
	v[0x08 / 4] = width;
	v[0x0c / 4] = height;
	v[0x10 / 4] = width;
	v[0x14 / 4] = height;
	v[0x18 / 4] = 0;
	v[0x1c / 4] = height;
	v[0x20 / 4] = 0;
	v[0x24 / 4] = width;
	v[0x34 / 4] = fps_milli;
	v[0x38 / 4] = fps_milli;
	v[0x3c / 4] = 0;
	v[0x40 / 4] = format_selector;
	v[0x44 / 4] = 1;
	v[0x48 / 4] = 0;
	v[0x4c / 4] = 0xffff0000;
	v[0x50 / 4] = 1;
	v[0x54 / 4] = 0xffff0000;
	v[0x58 / 4] = width;
	v[0x5c / 4] = 0;
	v[0x60 / 4] = 0;
	v[0x6c / 4] = 0;
	v[0x70 / 4] = VIDEO_COORD_W << 4;
	v[0x74 / 4] = 0;
	v[0x78 / 4] = VIDEO_COORD_H << 4;
	v[0x7c / 4] = 0;
	v[0x80 / 4] = VIDEO_COORD_W << 4;
	v[0x84 / 4] = 0;
	v[0x88 / 4] = VIDEO_COORD_H << 4;
	v[0x8c / 4] = 2;
	__sync_synchronize();
	msync(map, INFO_SIZE, MS_SYNC);
	munmap(map, INFO_SIZE);
	printf("VideoInfo: %ux%u, fps=%u.%03u, format selector=%u\n",
	       width, height, fps_milli / 1000, fps_milli % 1000,
	       format_selector);
	return 0;
}

static int pm_hint_on(int fd)
{
	struct dec_ioctl_header header = { .user_ptr = 1 };

	if (ioctl(fd, DECD_IOC_PM_HINT, &header) < 0) {
		perror("DECD_IOC_PM_HINT on");
		return -1;
	}
	printf("PM_HINT on ok\n");
	return 0;
}

/* Returns the release fence FD on success, -1 on failure.  Caller owns it. */
static int submit_frame(int dec_fd, int image_fd, int info_fd,
			unsigned width, unsigned height)
{
	struct dec_frame_submit_desc desc;
	struct dec_ioctl_header header;
	int fence_fd = -1;

	memset(&desc, 0, sizeof(desc));
	desc.image_fd = image_fd;
	desc.info_fd = info_fd;
	desc.format = DEC_FORMAT_NV12_CANDIDATE;
	desc.width = width;
	desc.height = height;
	desc.stride_align = 16;
	desc.stride_align2 = 16;
	desc.stride_align3 = 16;
	desc.info_size = INFO_SIZE;
	desc.info_align = 16;
	desc.field_select = 1;

	memset(&header, 0, sizeof(header));
	header.user_ptr = (uintptr_t)&desc;
	header.user_ptr2 = (uintptr_t)&fence_fd;
	header.repeat = 1;
	if (ioctl(dec_fd, DECD_IOC_FRAME_SUBMIT, &header) < 0) {
		perror("DECD_IOC_FRAME_SUBMIT");
		return -1;
	}
	if (fence_fd < 0) {
		fprintf(stderr,
			"FRAME_SUBMIT returned no release fence (%d); retirement "
			"cannot be synchronized, refusing to continue\n",
			fence_fd);
		return -1;
	}
	return fence_fd;
}

static void print_pipeline_error(GstElement *pipeline)
{
	GstMessage *message = gst_bus_pop_filtered(GST_ELEMENT_BUS(pipeline),
						   GST_MESSAGE_ERROR);

	if (message) {
		GError *error = NULL;
		gchar *debug = NULL;

		gst_message_parse_error(message, &error, &debug);
		fprintf(stderr, "pipeline error: %s\n%s\n",
			error ? error->message : "?", debug ? debug : "");
		g_clear_error(&error);
		g_free(debug);
		gst_message_unref(message);
	}
}

int main(int argc, char **argv)
{
	GstElement *pipeline = NULL, *sink = NULL;
	GstStateChangeReturn state_ret;
	GstVideoInfo info;
	char description[768];
	unsigned max_pending = max_pending_setting();
	int dec_fd = -1, ctl_fd = -1, info_fd = -1;
	int frames = 0, max_frames = 0, ret = 1;
	int freeze = getenv("DECD_FREEZE") && *getenv("DECD_FREEZE") != '0';
	int unpaced = getenv("DECD_UNPACED") && *getenv("DECD_UNPACED") != '0';
	const char *freeze_at_env = getenv("DECD_FREEZE_AT");
	unsigned freeze_at = freeze_at_env ? strtoul(freeze_at_env, NULL, 0) : 0;
	unsigned decoded_frames = 0;
	const char *dump_path = getenv("DECD_DUMP");
	const char *carveout_env = getenv("DECD_CARVEOUT");
	uint64_t carveout_phys = 0;
	int carveout_fd = -1, submit_fd;
	unsigned width = 0, height = 0;
	double started, drain_deadline;

	setvbuf(stdout, NULL, _IONBF, 0);
	if (argc < 2) {
		fprintf(stderr, "usage: decd-play FILE.h264 [max-frames]\n");
		return 2;
	}
	if (argc >= 3)
		max_frames = atoi(argv[2]);
	gst_init(&argc, &argv);
	gst_video_info_init(&info);

	dec_fd = open("/dev/decd", O_RDWR);
	if (dec_fd < 0) {
		perror("open /dev/decd");
		goto out;
	}
	ctl_fd = open("/dev/scanout-dmabuf", O_RDWR);
	if (ctl_fd < 0) {
		perror("open /dev/scanout-dmabuf");
		goto out;
	}
	info_fd = export_info_buffer(ctl_fd);
	if (info_fd < 0)
		goto out;

	/*
	 * sync=true paces the sink to each buffer's presentation timestamp, so a
	 * normal run can never exceed the clip's own frame rate no matter how
	 * fast the hardware is -- every "fps" this tool has ever printed was
	 * really a measurement of the fixture.  That is the right default for
	 * judging playback, and useless for finding the ceiling.
	 *
	 * DECD_UNPACED=1 removes the pacing and deepens the queue so the loop
	 * runs as fast as decode and DECD allow.  The number it prints is a
	 * throughput ceiling, not a playback result -- do not quote it as one.
	 */
	snprintf(description, sizeof(description),
		 "filesrc location=\"%s\" ! h264parse ! v4l2slh264dec ! "
		 "video/x-raw,format=NV12 ! "
		 "appsink name=out max-buffers=%d drop=false sync=%s",
		 argv[1], unpaced ? 8 : 3, unpaced ? "false" : "true");
	pipeline = gst_parse_launch(description, NULL);
	if (!pipeline) {
		fprintf(stderr, "pipeline build failed\n");
		goto out;
	}
	sink = gst_bin_get_by_name(GST_BIN(pipeline), "out");
	g_signal_connect(sink, "propose-allocation",
			 G_CALLBACK(on_propose_allocation), NULL);
	state_ret = gst_element_set_state(pipeline, GST_STATE_PLAYING);
	if (state_ret == GST_STATE_CHANGE_FAILURE) {
		fprintf(stderr, "pipeline will not play\n");
		goto out;
	}
	printf("fence-driven retirement, max %u surfaces held%s\n", max_pending,
	       freeze ? "; FREEZE mode, one buffer resubmitted" : "");

	started = now_ms();
	for (;;) {
		GstSample *sample;
		GstBuffer *buffer;
		GstMemory *memory;
		GstVideoMeta *meta;
		GstCaps *caps;
		gsize memory_offset = 0, max_size = 0, memory_size;
		unsigned stride, chroma_offset, expected_stride;
		int image_fd, fence_fd;
		double phase;

		if (max_frames > 0 && frames >= max_frames)
			break;

		/*
		 * Hand back whatever DECD has finished with, then make room.
		 * The non-blocking sweep first keeps the common case off the
		 * decode path entirely.
		 */
		phase = now_ms();
		if (reap_signaled(0) || wait_for_capacity(max_pending))
			goto out;
		t_reap += now_ms() - phase;

		phase = now_ms();
		sample = gst_app_sink_pull_sample(GST_APP_SINK(sink));
		t_pull += now_ms() - phase;
		if (!sample) {
			print_pipeline_error(pipeline);
			break;
		}
		buffer = gst_sample_get_buffer(sample);
		if (gst_buffer_n_memory(buffer) != 1) {
			fprintf(stderr, "frame %d: need one dma-buf memory, got %u\n",
				frames, gst_buffer_n_memory(buffer));
			gst_sample_unref(sample);
			goto out;
		}
		memory = gst_buffer_peek_memory(buffer, 0);
		if (!gst_is_dmabuf_memory(memory)) {
			fprintf(stderr, "frame %d: buffer is not dma-buf backed\n", frames);
			gst_sample_unref(sample);
			goto out;
		}
		image_fd = gst_dmabuf_memory_get_fd(memory);
		memory_size = gst_memory_get_sizes(memory, &memory_offset, &max_size);
		if (memory_offset) {
			fprintf(stderr, "frame %d: non-zero GstMemory offset %zu\n",
				frames, (size_t)memory_offset);
			gst_sample_unref(sample);
			goto out;
		}

		if (!decoded_frames) {
			caps = gst_sample_get_caps(sample);
			if (!gst_video_info_from_caps(&info, caps) ||
			    GST_VIDEO_INFO_FORMAT(&info) != GST_VIDEO_FORMAT_NV12) {
				fprintf(stderr, "first frame is not usable NV12\n");
				gst_sample_unref(sample);
				goto out;
			}
			width = GST_VIDEO_INFO_WIDTH(&info);
			height = GST_VIDEO_INFO_HEIGHT(&info);
			if (width != 1280 || height != 720) {
				fprintf(stderr,
					"this proven route is 1280x720 only, got %ux%u\n",
					width, height);
				gst_sample_unref(sample);
				goto out;
			}
		}

		meta = gst_buffer_get_video_meta(buffer);
		if (!meta) {
			fprintf(stderr, "frame %d: dma-buf has no GstVideoMeta\n", frames);
			gst_sample_unref(sample);
			goto out;
		}
		stride = meta->stride[0];
		chroma_offset = meta->offset[1];
		expected_stride = (width + 15) & ~15u;
		if (meta->n_planes != 2 || stride != expected_stride ||
		    meta->stride[1] != (int)stride ||
		    chroma_offset != stride * height ||
		    memory_size < chroma_offset + stride * (height / 2)) {
			fprintf(stderr,
				"frame %d: unrepresentable layout planes=%u stride=%u/%d "
				"chroma=%u memory=%zu max=%zu; expected stride=%u chroma=%u\n",
				frames, meta->n_planes, stride, meta->stride[1],
				chroma_offset, (size_t)memory_size, (size_t)max_size,
				expected_stride, expected_stride * height);
			gst_sample_unref(sample);
			goto out;
		}
		decoded_frames++;
		if (freeze && decoded_frames <= freeze_at) {
			printf("FREEZE_AT: discarding decoded frame %u of %u\n",
			       decoded_frames - 1, freeze_at);
			gst_sample_unref(sample);
			continue;
		}
		if (!frames) {
			printf("decoded %ux%u NV12: one dma-buf fd=%d, "
			       "stride=%u chroma-offset=%u size=%zu\n",
			       width, height, image_fd, stride, chroma_offset,
			       (size_t)memory_size);
			if (fill_video_info(info_fd, width, height,
					    GST_VIDEO_INFO_FPS_N(&info),
					    GST_VIDEO_INFO_FPS_D(&info)) ||
			    pm_hint_on(dec_fd)) {
				gst_sample_unref(sample);
				goto out;
			}
		}

		if (dump_path && frames == 0 &&
		    dump_frame(image_fd, memory_size, dump_path)) {
			gst_sample_unref(sample);
			goto out;
		}

		submit_fd = image_fd;
		if (carveout_env && frames == 0) {
			carveout_phys = strcmp(carveout_env, "1")
				? strtoull(carveout_env, NULL, 0) : 0x6c500000ULL;
			if (copy_to_carveout(image_fd, ctl_fd, memory_size,
					     carveout_phys, &carveout_fd)) {
				gst_sample_unref(sample);
				goto out;
			}
		}
		if (carveout_fd >= 0)
			submit_fd = carveout_fd;

		phase = now_ms();
		fence_fd = submit_frame(dec_fd, submit_fd, info_fd, width, height);
		t_submit += now_ms() - phase;
		if (fence_fd < 0) {
			gst_sample_unref(sample);
			goto out;
		}
		/*
		 * Hold the surface until this fence signals.  Returning it now
		 * would let Cedrus decode into a buffer DECD is still scanning
		 * out, which is what produced horizontal bands mixed from
		 * different pictures.
		 */
		pending_push(sample, fence_fd, (unsigned)frames);
		frames++;

		/*
		 * DECD_FREEZE: stop decoding and resubmit this one buffer.
		 *
		 * A static frame from the scanout carveout is already proven to
		 * display correctly, so the only variable left between that
		 * positive and corrupt playback is where the buffer came from.
		 * Here nothing is decoding, nothing is recycled and the sample
		 * is held, so the buffer is complete and quiescent: anything
		 * still wrong on the panel is wrong about how DECD *reads a
		 * decoder buffer*, and cannot be about timing.
		 */
		if (freeze) {
			printf("FREEZE: holding decoded frame %u, resubmitting %d times\n",
			       decoded_frames - 1,
			       max_frames > 1 ? max_frames - 1 : 0);
			while (max_frames <= 0 || frames < max_frames) {
				/*
				 * 33 ms is a deliberate ~30 fps cadence for
				 * watching a still, not a hardware limit.  It is
				 * also why a freeze run measures SLOWER than a
				 * moving one despite doing no decoding at all --
				 * which is the tell that these fps numbers were
				 * never measuring DECD.  DECD_UNPACED drops it.
				 */
				struct timespec tick = {
					.tv_nsec = 33 * 1000 * 1000,
				};
				int again = submit_frame(dec_fd, submit_fd,
							 info_fd, width, height);

				if (again < 0)
					goto out;
				close(again);
				frames++;
				if (!unpaced)
					nanosleep(&tick, NULL);
			}
			break;
		}
	}

	/*
	 * Drain.  The last submissions have nothing behind them to displace
	 * them from the display slots, so some fences will not signal here.
	 * Bounded wait, then release the rest: the pipeline is stopping and
	 * nothing will reuse these surfaces.
	 */
	drain_deadline = now_ms() + DRAIN_BUDGET_MS;
	while (pending_count && now_ms() < drain_deadline) {
		if (reap_signaled(FENCE_POLL_SLICE_MS))
			break;
	}

	if (frames) {
		double elapsed = now_ms() - started;

		printf("PLAY_COMPLETE frames=%d elapsed=%.0fms rate=%.2ffps\n",
		       frames, elapsed, frames / (elapsed / 1000.0));
		printf("PHASE_MS pull=%.0f submit=%.0f reap=%.0f other=%.0f"
		       " (per frame: pull=%.2f submit=%.2f reap=%.2f)\n",
		       t_pull, t_submit, t_reap,
		       elapsed - t_pull - t_submit - t_reap,
		       frames ? t_pull / frames : 0.0,
		       frames ? t_submit / frames : 0.0,
		       frames ? t_reap / frames : 0.0);
		printf("RETIRE_STATS fence-retired=%u unsignalled-at-exit=%u "
		       "peak-held=%u cap=%u stalls=%u\n",
		       retired_by_fence, pending_count, pending_peak,
		       max_pending, stall_episodes);
		ret = 0;
	}
out:
	if (pipeline)
		gst_element_set_state(pipeline, GST_STATE_NULL);
	while (pending_count)
		pending_retire_head();
	if (sink)
		gst_object_unref(sink);
	if (pipeline)
		gst_object_unref(pipeline);
	if (carveout_fd >= 0)
		close(carveout_fd);
	if (info_fd >= 0)
		close(info_fd);
	if (ctl_fd >= 0)
		close(ctl_fd);
	if (dec_fd >= 0)
		close(dec_fd);
	return ret;
}
