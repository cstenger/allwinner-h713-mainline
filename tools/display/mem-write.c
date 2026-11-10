// SPDX-License-Identifier: GPL-2.0
/*
 * Write a file into physical memory through /dev/mem.
 *
 * mem-fill.c writes a pattern; this writes real content, which is what a video
 * plane test needs -- a flat fill is ambiguous on this hardware, because a
 * broken fetch also produces a flat colour (all-zero reads look green, all-ones
 * look magenta). Only a recognisable picture distinguishes "the plane is
 * fetching our frame" from "the plane is fetching nothing".
 *
 * MUST use mmap, not write(). On arm64 a write() to /dev/mem targeting a no-map
 * reserved region fails with EFAULT, because the kernel's write path needs a
 * linear-map pointer and no-map memory has none. mmap installs its own mapping
 * and works. `dd of=/dev/mem` therefore cannot be used for the carveout.
 *
 * Only reserved no-map regions are reachable at all: CONFIG_STRICT_DEVMEM
 * blocks system RAM, which is why a CMA-backed buffer cannot be written this
 * way but the U-Boot scanout carveout can.
 *
 *   mem-write FILE PHYS_ADDR
 *   mem-write frame60.nv12 0x6c500000
 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	unsigned long phys, page, off;
	size_t len, span;
	struct stat st;
	void *map;
	int ffd, mfd;
	ssize_t got;
	char *buf;

	if (argc != 3) {
		fprintf(stderr, "usage: mem-write FILE PHYS_ADDR\n");
		return 2;
	}
	phys = strtoul(argv[2], NULL, 0);

	ffd = open(argv[1], O_RDONLY);
	if (ffd < 0 || fstat(ffd, &st)) {
		perror(argv[1]);
		return 1;
	}
	len = st.st_size;

	buf = malloc(len);
	if (!buf) {
		perror("malloc");
		return 1;
	}
	for (off = 0; off < len; off += got) {
		got = read(ffd, buf + off, len - off);
		if (got <= 0) {
			perror("read");
			return 1;
		}
	}
	close(ffd);

	mfd = open("/dev/mem", O_RDWR | O_SYNC);
	if (mfd < 0) {
		perror("open /dev/mem (run as root)");
		return 1;
	}

	/* mmap needs a page-aligned offset; keep the remainder as a bias. */
	page = phys & ~(unsigned long)(sysconf(_SC_PAGESIZE) - 1);
	off = phys - page;
	span = len + off;

	map = mmap(NULL, span, PROT_READ | PROT_WRITE, MAP_SHARED, mfd, page);
	if (map == MAP_FAILED) {
		perror("mmap /dev/mem");
		fprintf(stderr,
			"is 0x%lx inside a reserved no-map region? system RAM is blocked\n",
			phys);
		return 1;
	}

	memcpy((char *)map + off, buf, len);
	msync(map, span, MS_SYNC);
	munmap(map, span);
	close(mfd);

	printf("wrote %zu bytes of %s to 0x%lx\n", len, argv[1], phys);
	return 0;
}
