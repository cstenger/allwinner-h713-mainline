// SPDX-License-Identifier: GPL-2.0
/*
 * decd-client -- vendor-faithful synthetic NV12 submission to /dev/decd.
 *
 * Runs on the H713 target. Build:
 *   gcc -O2 -Wall -Wextra -o decd-client decd-client.c
 *
 * Stock Android HWC submits an exact 112-byte descriptor containing two
 * dma-buf FDs: one for the image and one for a 32 KiB VideoInfo allocation
 * whose 0x104-byte payload starts at offset 4096. This mirrors that shape.
 * The local scanout-dmabuf exporter supplies contiguous test dma-bufs.
 *
 * WARNING: PM off asserts the shared display reset on the reconstructed Linux
 * driver and blanks the panel until reboot. `show` deliberately leaves DECD on.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define DECD_IOC_PM_HINT           0x40046401u
#define DECD_IOC_STOP_VIDEO_STREAM 0x40046408u
#define DECD_IOC_FRAME_SUBMIT      0x40706400u
#define DECD_IOC_GET_VSYNC_TS      0x8008640au
#define SCANOUT_IOC_GET_FD _IOWR('S', 1, struct scanout_req)

struct scanout_req {
	uint64_t phys;
	uint64_t size;
	int32_t fd;
	uint32_t pad;
};

struct dec_ioctl_header {
	uint64_t user_ptr;
	uint64_t user_ptr2;
	uint32_t repeat;          /* stock wrapper offset +0x10 */
	uint32_t reserved14;
	uint32_t reserved18;
	uint32_t reserved1c;
};

struct dec_frame_submit_desc {
	uint8_t compressed;       /* +0x00 */
	uint8_t blue_en;          /* +0x01: nonzero skips frame creation */
	uint8_t reserved02[2];
	int32_t image_fd;         /* +0x04 */
	uint32_t format;          /* +0x08 */
	uint32_t reserved0c[7];
	uint32_t width;           /* +0x28 */
	uint32_t height;          /* +0x2c */
	uint32_t chroma_width;    /* +0x30 */
	uint32_t chroma_height;   /* +0x34 */
	uint32_t chroma_width2;   /* +0x38 */
	uint32_t chroma_height2;  /* +0x3c */
	uint32_t stride_align;    /* +0x40 */
	uint32_t stride_align2;   /* +0x44 */
	uint32_t stride_align3;   /* +0x48 */
	int32_t info_fd;          /* +0x4c */
	uint32_t info_size;       /* +0x50 */
	uint32_t info_align;      /* +0x54 */
	uint32_t legacy_info_phys;/* +0x58 */
	uint32_t reserved5c;
	uint8_t split_fields;     /* +0x60 */
	uint8_t reserved61[3];
	uint32_t field_select;    /* +0x64 */
	uint8_t legacy_direct;    /* +0x68: zero in stock HWC */
	uint8_t reserved69[7];
};

_Static_assert(sizeof(struct dec_ioctl_header) == 32, "ioctl wrapper ABI");
_Static_assert(sizeof(struct dec_frame_submit_desc) == 112, "frame ABI");
_Static_assert(offsetof(struct dec_frame_submit_desc, info_fd) == 0x4c,
	       "info_fd ABI");
_Static_assert(offsetof(struct dec_frame_submit_desc, legacy_direct) == 0x68,
	       "legacy flag ABI");

#define W 1280u
#define H 720u
#define NV12_SIZE ((size_t)W * H * 3 / 2)
#define IMAGE_PHYS 0x6c500000ULL
#define INFO_PHYS  0x6c8f0000ULL
#define INFO_SIZE  0x8000u
#define DEC_FORMAT_NV12_CANDIDATE 6u

static size_t page_align(size_t n)
{
	long p = sysconf(_SC_PAGESIZE);
	return (n + (size_t)p - 1) & ~((size_t)p - 1);
}

static double now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

static int export_buffer(int ctl_fd, uint64_t phys, size_t size)
{
	struct scanout_req req = { .phys = phys, .size = size, .fd = -1 };

	if (ioctl(ctl_fd, SCANOUT_IOC_GET_FD, &req) < 0) {
		perror("SCANOUT_IOC_GET_FD");
		return -1;
	}
	return req.fd;
}

static int copy_file_to_fd(const char *path, int fd)
{
	uint8_t *dst;
	int in;
	size_t got = 0, map_size = page_align(NV12_SIZE);

	in = open(path, O_RDONLY);
	if (in < 0) {
		perror("open NV12");
		return -1;
	}
	dst = mmap(NULL, map_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	if (dst == MAP_FAILED) {
		perror("mmap image dma-buf");
		close(in);
		return -1;
	}
	while (got < NV12_SIZE) {
		ssize_t n = read(in, dst + got, NV12_SIZE - got);
		if (n <= 0)
			break;
		got += (size_t)n;
	}
	close(in);
	if (got != NV12_SIZE)
		fprintf(stderr, "short NV12 frame: %zu of %zu bytes\n",
			got, NV12_SIZE);
	__sync_synchronize();
	msync(dst, map_size, MS_SYNC);
	munmap(dst, map_size);
	return got == NV12_SIZE ? 0 : -1;
}

/*
 * The VideoInfo format selector, overridable for sweeping the firmware's
 * mapping table on hardware. Default 0, which the table maps to AFBD fmt 0 --
 * the value stock plays at.
 */
static uint32_t video_info_format(void)
{
	const char *s = getenv("DECD_FMT");
	unsigned long v;

	if (!s || !*s)
		return 0;
	v = strtoul(s, NULL, 0);
	if (v > 15) {
		fprintf(stderr, "DECD_FMT=%lu out of range, using 0\n", v);
		return 0;
	}
	printf("VideoInfo format selector overridden to %lu\n", v);
	return (uint32_t)v;
}

/* Reproduce the constructor and setters used by VideoTunnel for SDR video. */
static int fill_video_info(int fd)
{
	uint8_t *map = mmap(NULL, INFO_SIZE, PROT_READ | PROT_WRITE,
			    MAP_SHARED, fd, 0);
	uint32_t *v;

	if (map == MAP_FAILED) {
		perror("mmap info dma-buf");
		return -1;
	}
	memset(map, 0, INFO_SIZE);
	v = (uint32_t *)(map + 0x1000);
	v[0x00 / 4] = 0x61770000; /* stock decd.ko check at 0x4c18 */
	v[0x04 / 4] = 2;
	v[0x08 / 4] = W;
	v[0x0c / 4] = H;
	v[0x10 / 4] = W;
	v[0x14 / 4] = H;
	v[0x18 / 4] = 0;         /* setOutputWindow(0, 0, W, H) */
	v[0x1c / 4] = H;
	v[0x20 / 4] = 0;
	v[0x24 / 4] = W;
	v[0x34 / 4] = 30000;     /* setFps(30) */
	v[0x38 / 4] = 30000;
	v[0x3c / 4] = 0;         /* progressive */
	/*
	 * The firmware's format selector. This is the input to the resolver at
	 * MIPS 0x8b1a31e8, a bounds-checked jump table through 16 entries at
	 * 0x8b2078a4; the arm it selects stores the byte the firmware then
	 * writes into 0x05600010[15:8]. Recovered 2026-08-30, see
	 * docs/reference/firmware-format-mapping-2026-08-30.md.
	 *
	 *     input   0 -> fmt 0      8 -> fmt 4     14 -> fmt 7
	 *             2 -> fmt 1      9 -> fmt 5     15 -> fmt 6
	 *             4 -> fmt 2     11 -> fmt 4
	 *             6 -> fmt 3     12 -> fmt 5
	 *     1,3,5,10,13 take a default arm that logs an error and writes 0.
	 *     7 stores nothing at all, leaving the firmware's stack byte.
	 *
	 * This was 11, which the table maps to fmt 4 -- and fmt 4 is measured
	 * wrong for NV12: forced onto stock during playback it gave a
	 * 2x-repeated, half-height, colour-shifted picture, because the fetch
	 * eats about two source lines per output line. Stock plays at fmt 0,
	 * and 0 is the only input that reaches fmt 0 without going through the
	 * error-logging default.
	 *
	 * That 11 -> 4 is what the table predicts is also why it is trusted: it
	 * reproduces the measured 0x05600010 = 0x03000413 exactly.
	 *
	 * DECD_FMT overrides it, so the table can be swept on hardware without
	 * a rebuild. Note the resolver's input is 0x5c($s0) in the firmware's
	 * frame object; that it is this field rests on the 11 -> 4
	 * correspondence rather than a traced data path, so if setting 0 does
	 * not move 0x05600010, this field is not the input and the descriptor's
	 * own format at +0x08 is the next candidate.
	 */
	v[0x40 / 4] = video_info_format();
	v[0x44 / 4] = 1;         /* stock VideoTunnel colorspace */
	v[0x48 / 4] = 0;         /* limited range constructor default */
	v[0x4c / 4] = 0xffff0000;/* retained VideoInfo constructor sentinel */
	v[0x50 / 4] = 1;         /* setDataspace(0), no HDR metadata */
	v[0x54 / 4] = 0xffff0000;/* retained VideoInfo constructor sentinel */
	v[0x58 / 4] = W;
	v[0x5c / 4] = 0;         /* uncompressed */
	v[0x60 / 4] = 0;
	/* +0x64/+0x68 are patched to reserved physical pointers by decd.ko. */
	v[0x6c / 4] = 0;
	/*
	 * Source crop and display frame, each a {x, width, y, height} struct in
	 * 1/16-pixel fixed point.
	 *
	 * The layout and the units are not guesses: the same four-word encoding
	 * was recovered from the MIPS firmware on 2026-08-30, where
	 * THal_Vp_Wce_GetActiveWindow returns {0, 0x5000, 0, 0x2d00} and 0x5000/16
	 * = 1280, 0x2d00/16 = 720 -- exactly this panel. See
	 * docs/reference/cpu-comm-call-table.md.
	 *
	 * These were 0x7800/0x4380 (1920x1080) while W/H are 1280x720, so the
	 * block labelled "identity" was not one. 0x7800/0x4380 is also the
	 * firmware's own linked-in default window, which is the likely source of
	 * the copy. Derive from W/H instead so the comment and the code agree and
	 * a resolution change cannot desynchronise them again.
	 *
	 * UNTESTED ON HARDWARE. Unlike the firmware globals -- which are inert,
	 * having no path to any register -- this struct is handed to the firmware
	 * on every submit, so it is live input and worth correcting on its own
	 * terms. But no stock VideoInfo capture exists to confirm the vendor also
	 * sends source-sized values here rather than always sending 1080p and
	 * letting the pipeline scale. If this regresses, that is the reason, and
	 * reverting is these four lines.
	 */
	v[0x70 / 4] = W << 4;    /* crop        x = 0, width  */
	v[0x74 / 4] = 0;
	v[0x78 / 4] = H << 4;    /*             y = 0, height */
	v[0x7c / 4] = 0;         /* identity setDisplayFrame() */
	v[0x80 / 4] = W << 4;
	v[0x84 / 4] = 0;
	v[0x88 / 4] = H << 4;
	v[0x8c / 4] = 2;         /* retained VideoInfo constructor default */
	__sync_synchronize();
	msync(map, INFO_SIZE, MS_SYNC);
	munmap(map, INFO_SIZE);
	return 0;
}

static int pm_hint(int fd, int on)
{
	struct dec_ioctl_header h = { .user_ptr = !!on };

	if (ioctl(fd, DECD_IOC_PM_HINT, &h) < 0) {
		perror("DECD_IOC_PM_HINT");
		return -1;
	}
	printf("PM_HINT %s ok\n", on ? "on" : "off");
	return 0;
}

static int submit_frame(int dec_fd, int image_fd, int info_fd)
{
	struct dec_frame_submit_desc d;
	struct dec_ioctl_header h;
	int fence_fd = -1;

	memset(&d, 0, sizeof(d));
	d.image_fd = image_fd;
	d.info_fd = info_fd;
	d.format = DEC_FORMAT_NV12_CANDIDATE;
	d.width = W;
	d.height = H;
	d.stride_align = d.stride_align2 = d.stride_align3 = 16;
	d.info_size = INFO_SIZE;
	d.info_align = 16;
	d.field_select = 1;

	memset(&h, 0, sizeof(h));
	h.user_ptr = (uintptr_t)&d;
	h.user_ptr2 = (uintptr_t)&fence_fd;
	h.repeat = 1;
	if (ioctl(dec_fd, DECD_IOC_FRAME_SUBMIT, &h) < 0) {
		perror("DECD_IOC_FRAME_SUBMIT");
		return -1;
	}
	printf("FRAME_SUBMIT format=%u desc=%zu repeat@+0x10=%u fence_fd=%d%s\n",
	       d.format, sizeof(d), h.repeat, fence_fd,
	       fence_fd < 0 ? " (not enqueued)" : "");
	if (fence_fd >= 0)
		close(fence_fd);
	return fence_fd >= 0 ? 0 : -1;
}

static int show_blue(int dec_fd, unsigned dwell_ms)
{
	struct dec_frame_submit_desc d;
	struct dec_ioctl_header h;
	int fence_fd = -1;

	memset(&d, 0, sizeof(d));
	d.blue_en = 1;
	memset(&h, 0, sizeof(h));
	h.user_ptr = (uintptr_t)&d;
	h.user_ptr2 = (uintptr_t)&fence_fd;
	h.repeat = 1;

	if (pm_hint(dec_fd, 1))
		return -1;
	if (ioctl(dec_fd, DECD_IOC_FRAME_SUBMIT, &h) < 0) {
		perror("DECD_IOC_FRAME_SUBMIT blue");
		return -1;
	}
	printf("BLUE_SUBMIT desc=%zu blue@+0x01=%u fence_fd=%d\n",
	       sizeof(d), d.blue_en, fence_fd);
	printf("holding %u ms; leaving DECD blue enabled\n", dwell_ms);
	usleep((useconds_t)dwell_ms * 1000);
	return 0;
}

static int show_frame(int dec_fd, const char *path, unsigned dwell_ms)
{
	int ctl = -1, image_fd = -1, info_fd = -1, ret = -1;

	ctl = open("/dev/scanout-dmabuf", O_RDWR);
	if (ctl < 0) {
		perror("open /dev/scanout-dmabuf");
		goto out;
	}
	image_fd = export_buffer(ctl, IMAGE_PHYS, page_align(NV12_SIZE));
	info_fd = export_buffer(ctl, INFO_PHYS, INFO_SIZE);
	if (image_fd < 0 || info_fd < 0)
		goto out;
	if (copy_file_to_fd(path, image_fd) || fill_video_info(info_fd))
		goto out;
	printf("prepared image dma-buf at %#llx and VideoInfo dma-buf at %#llx\n",
	       (unsigned long long)IMAGE_PHYS, (unsigned long long)INFO_PHYS);
	if (pm_hint(dec_fd, 1) || submit_frame(dec_fd, image_fd, info_fd))
		goto out;
	printf("holding %u ms; leaving DECD enabled to avoid shared display reset\n",
	       dwell_ms);
	usleep((useconds_t)dwell_ms * 1000);
	ret = 0;
out:
	if (info_fd >= 0)
		close(info_fd);
	if (image_fd >= 0)
		close(image_fd);
	if (ctl >= 0)
		close(ctl);
	return ret;
}

static void vsync_ts(int fd, int count)
{
	int i;

	for (i = 0; i < count; i++) {
		uint64_t ts = 0;
		struct dec_ioctl_header h = { .user_ptr = (uintptr_t)&ts };
		double start = now_ms();

		while (ioctl(fd, DECD_IOC_GET_VSYNC_TS, &h) < 0) {
			if (now_ms() - start > 200.0) {
				printf("vsync %d: timeout\n", i);
				break;
			}
		}
		if (ts)
			printf("vsync %d: %llu\n", i, (unsigned long long)ts);
	}
}

static void usage(const char *argv0)
{
	fprintf(stderr,
		"usage: %s show FRAME.nv12 [dwell-ms]\n"
		"       %s blue [dwell-ms]\n"
		"       %s pm on|off   # off resets the shared display block\n"
		"       %s vsync [count]\n"
		"       %s stop\n", argv0, argv0, argv0, argv0, argv0);
}

int main(int argc, char **argv)
{
	int fd, ret = 0;

	if (argc < 2) {
		usage(argv[0]);
		return 2;
	}
	fd = open("/dev/decd", O_RDWR);
	if (fd < 0) {
		perror("open /dev/decd");
		return 1;
	}
	if (!strcmp(argv[1], "show") && argc >= 3) {
		unsigned dwell = argc >= 4 ? strtoul(argv[3], NULL, 0) : 10000;
		ret = show_frame(fd, argv[2], dwell);
	} else if (!strcmp(argv[1], "blue")) {
		unsigned dwell = argc >= 3 ? strtoul(argv[2], NULL, 0) : 10000;
		ret = show_blue(fd, dwell);
	} else if (!strcmp(argv[1], "pm") && argc >= 3) {
		ret = pm_hint(fd, !strcmp(argv[2], "on"));
	} else if (!strcmp(argv[1], "vsync")) {
		vsync_ts(fd, argc >= 3 ? atoi(argv[2]) : 10);
	} else if (!strcmp(argv[1], "stop")) {
		struct dec_ioctl_header h = { 0 };
		ret = ioctl(fd, DECD_IOC_STOP_VIDEO_STREAM, &h);
	} else {
		usage(argv[0]);
		ret = 2;
	}
	close(fd);
	return ret ? 1 : 0;
}
