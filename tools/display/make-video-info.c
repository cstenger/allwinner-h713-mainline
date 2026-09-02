// SPDX-License-Identifier: GPL-2.0
/*
 * Generate the 4 KiB VideoInfo page used by a direct AFBD ring test.
 *
 * The reconstructed DECD driver normally copies the 0x104-byte payload from
 * offset 0x1000 of a userspace dma-buf into its reserved page, then patches two
 * embedded physical pointers.  A KMS-owned test has no DECD driver, so this
 * tool produces that final reserved-page representation directly.
 *
 *   make-video-info OUTPUT PHYS_ADDR
 *   make-video-info f60.videoinfo 0x4d941000
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define PAGE_SIZE 4096
#define VIDEO_COORD_W 1920u
#define VIDEO_COORD_H 1080u

static int write_all(int fd, const void *buf, size_t len)
{
	const uint8_t *p = buf;

	while (len) {
		ssize_t n = write(fd, p, len);

		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return -1;
		p += n;
		len -= (size_t)n;
	}
	return 0;
}

int main(int argc, char **argv)
{
	uint8_t page[PAGE_SIZE] = { 0 };
	uint32_t *v = (uint32_t *)page;
	unsigned long phys;
	char *end;
	int fd;

	if (argc != 3) {
		fprintf(stderr, "usage: make-video-info OUTPUT PHYS_ADDR\n");
		return 2;
	}

	errno = 0;
	phys = strtoul(argv[2], &end, 0);
	if (errno || *end || phys > UINT32_MAX || (phys & 3)) {
		fprintf(stderr, "invalid 32-bit physical address: %s\n", argv[2]);
		return 2;
	}

	/* VideoInfo constructor plus the setters used for linear 1280x720 SDR. */
	v[0x00 / 4] = 0x61770000;
	v[0x04 / 4] = 2;
	v[0x08 / 4] = 1280;
	v[0x0c / 4] = 720;
	v[0x10 / 4] = 1280;
	v[0x14 / 4] = 720;
	v[0x18 / 4] = 0;
	v[0x1c / 4] = 720;
	v[0x20 / 4] = 0;
	v[0x24 / 4] = 1280;
	v[0x34 / 4] = 30000;
	v[0x38 / 4] = 30000;
	v[0x3c / 4] = 0;
	v[0x40 / 4] = 0;          /* VideoInfo selector 0 -> AFBD format 0 */
	v[0x44 / 4] = 1;          /* stock VideoTunnel colourspace */
	v[0x48 / 4] = 0;          /* limited range */
	v[0x4c / 4] = 0xffff0000;
	v[0x50 / 4] = 1;
	v[0x54 / 4] = 0xffff0000;
	v[0x58 / 4] = 1280;
	v[0x5c / 4] = 0;          /* uncompressed */
	v[0x60 / 4] = 0;
	/* Pointers patched by video_info_buffer_init_dmabuf(). */
	v[0x64 / 4] = (uint32_t)phys + 144;
	v[0x68 / 4] = (uint32_t)phys + 172;
	v[0x6c / 4] = 0;
	v[0x70 / 4] = VIDEO_COORD_W << 4;
	v[0x74 / 4] = 0;
	v[0x78 / 4] = VIDEO_COORD_H << 4;
	v[0x7c / 4] = 0;
	v[0x80 / 4] = VIDEO_COORD_W << 4;
	v[0x84 / 4] = 0;
	v[0x88 / 4] = VIDEO_COORD_H << 4;
	v[0x8c / 4] = 2;

	fd = open(argv[1], O_WRONLY | O_CREAT | O_TRUNC, 0644);
	if (fd < 0) {
		perror(argv[1]);
		return 1;
	}
	if (write_all(fd, page, sizeof(page)) || close(fd)) {
		perror("write VideoInfo");
		return 1;
	}

	printf("wrote %u-byte VideoInfo for %#lx to %s\n",
	       PAGE_SIZE, phys, argv[1]);
	return 0;
}
