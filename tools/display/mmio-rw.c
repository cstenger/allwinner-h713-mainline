// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * General 32-bit MMIO read/write over /dev/mem.
 *
 * The existing helpers here are read-only (devmem32, mmio-read) or bound to
 * a fixed sequence (mmio-poke), which is fine for their jobs but leaves no
 * way to poke one register during bring-up. Compile on the board:
 *
 *     cc -O2 -o mmio-rw mmio-rw.c
 *     mmio-rw r 3003124            # read
 *     mmio-rw w 3003124 ffffffff   # write
 *     mmio-rw d 3003100 10         # dump N words
 *
 * Addresses are hex, no 0x prefix, matching mmio-read.
 */

#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define PAGE 4096UL

static volatile uint32_t *map_reg(int fd, unsigned long addr, void **mapping)
{
	unsigned long base = addr & ~(PAGE - 1);
	unsigned long off = addr & (PAGE - 1);
	void *m = mmap(NULL, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
		       (off_t)base);

	if (m == MAP_FAILED)
		return NULL;
	*mapping = m;
	return (volatile uint32_t *)((char *)m + off);
}

int main(int argc, char **argv)
{
	unsigned long addr, count = 1;
	volatile uint32_t *p;
	void *mapping;
	uint32_t val;
	int fd, i;

	if (argc < 3) {
		fprintf(stderr, "usage: mmio-rw r|w|d <hex-addr> [hex-value|count]\n");
		return 2;
	}

	addr = strtoul(argv[2], NULL, 16);

	fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("open /dev/mem");
		return 2;
	}

	switch (argv[1][0]) {
	case 'r':
		p = map_reg(fd, addr, &mapping);
		if (!p) { perror("mmap"); return 2; }
		printf("%08lx 0x%08X\n", addr, *p);
		break;

	case 'w':
		if (argc < 4) {
			fprintf(stderr, "w needs a value\n");
			return 2;
		}
		val = (uint32_t)strtoul(argv[3], NULL, 16);
		p = map_reg(fd, addr, &mapping);
		if (!p) { perror("mmap"); return 2; }
		*p = val;
		printf("%08lx <- 0x%08X, reads back 0x%08X\n", addr, val, *p);
		break;

	case 'd':
		if (argc >= 4)
			count = strtoul(argv[3], NULL, 16);
		for (i = 0; i < (int)count; i++) {
			unsigned long a = addr + 4UL * i;

			p = map_reg(fd, a, &mapping);
			if (!p) { perror("mmap"); return 2; }
			printf("%08lx 0x%08X\n", a, *p);
			munmap(mapping, PAGE);
		}
		break;

	default:
		fprintf(stderr, "unknown op '%s'\n", argv[1]);
		return 2;
	}

	close(fd);
	return 0;
}
