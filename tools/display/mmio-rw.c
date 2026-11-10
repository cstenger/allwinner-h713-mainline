// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * General MMIO read/write over /dev/mem, 32-bit and 8-bit.
 *
 * The existing helpers here are read-only (devmem32, mmio-read) or bound to
 * a fixed sequence (mmio-poke), which is fine for their jobs but leaves no
 * way to poke one register during bring-up. Compile on the board:
 *
 *     cc -O2 -o mmio-rw mmio-rw.c
 *     mmio-rw r 3003124            # read word
 *     mmio-rw w 3003124 ffffffff   # write word
 *     mmio-rw d 3003100 10         # dump N words
 *     mmio-rw rb 68008f1           # read byte
 *     mmio-rw wb 68008f1 01        # write byte
 *     mmio-rw db 68008f0 10        # dump N bytes
 *
 * Addresses are hex, no 0x prefix, matching mmio-read.
 *
 * The byte forms exist because some blocks here are byte-wide and silently
 * ignore word writes. The H713 HDMI-RX wrapper at 0x06800800/0x06840000 reads
 * back as each byte replicated across a word (0xc0c0c0c0, 0x33333333), the
 * vendor driver touches it only with writeb(), and a 32-bit write to
 * port-select at 0x068008f0 reads back zero while its neighbours plainly hold
 * values. Without an 8-bit path that hypothesis cannot be tested at all.
 */

#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define PAGE 4096UL

static void *map_any(int fd, unsigned long addr, void **mapping)
{
	unsigned long base = addr & ~(PAGE - 1);
	unsigned long off = addr & (PAGE - 1);
	void *m = mmap(NULL, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
		       (off_t)base);

	if (m == MAP_FAILED)
		return NULL;
	*mapping = m;
	return (char *)m + off;
}

static volatile uint32_t *map_reg(int fd, unsigned long addr, void **mapping)
{
	return (volatile uint32_t *)map_any(fd, addr, mapping);
}

static volatile uint8_t *map_byte(int fd, unsigned long addr, void **mapping)
{
	return (volatile uint8_t *)map_any(fd, addr, mapping);
}

int main(int argc, char **argv)
{
	unsigned long addr, count = 1;
	volatile uint32_t *p;
	volatile uint8_t *b;
	const char *op;
	void *mapping;
	uint32_t val;
	int fd, i;

	if (argc < 3) {
		fprintf(stderr,
			"usage: mmio-rw r|w|d|rb|wb|db <hex-addr> [hex-value|count]\n");
		return 2;
	}
	op = argv[1];

	addr = strtoul(argv[2], NULL, 16);

	fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("open /dev/mem");
		return 2;
	}

	if (!strcmp(op, "r")) {
		p = map_reg(fd, addr, &mapping);
		if (!p) { perror("mmap"); return 2; }
		printf("%08lx 0x%08X\n", addr, *p);
	} else if (!strcmp(op, "w")) {
		if (argc < 4) {
			fprintf(stderr, "w needs a value\n");
			return 2;
		}
		val = (uint32_t)strtoul(argv[3], NULL, 16);
		p = map_reg(fd, addr, &mapping);
		if (!p) { perror("mmap"); return 2; }
		*p = val;
		printf("%08lx <- 0x%08X, reads back 0x%08X\n", addr, val, *p);
	} else if (!strcmp(op, "d")) {
		if (argc >= 4)
			count = strtoul(argv[3], NULL, 16);
		for (i = 0; i < (int)count; i++) {
			unsigned long a = addr + 4UL * i;

			p = map_reg(fd, a, &mapping);
			if (!p) { perror("mmap"); return 2; }
			printf("%08lx 0x%08X\n", a, *p);
			munmap(mapping, PAGE);
		}
	} else if (!strcmp(op, "rb")) {
		b = map_byte(fd, addr, &mapping);
		if (!b) { perror("mmap"); return 2; }
		printf("%08lx 0x%02X\n", addr, *b);
	} else if (!strcmp(op, "wb")) {
		if (argc < 4) {
			fprintf(stderr, "wb needs a value\n");
			return 2;
		}
		val = (uint32_t)strtoul(argv[3], NULL, 16);
		b = map_byte(fd, addr, &mapping);
		if (!b) { perror("mmap"); return 2; }
		*b = (uint8_t)val;
		printf("%08lx <- 0x%02X, reads back 0x%02X\n", addr,
		       (uint8_t)val, *b);
	} else if (!strcmp(op, "db")) {
		if (argc >= 4)
			count = strtoul(argv[3], NULL, 16);
		for (i = 0; i < (int)count; i++) {
			unsigned long a = addr + (unsigned long)i;

			b = map_byte(fd, a, &mapping);
			if (!b) { perror("mmap"); return 2; }
			printf("%08lx 0x%02X\n", a, *b);
			munmap(mapping, PAGE);
		}
	} else {
		fprintf(stderr, "unknown op '%s'\n", op);
		return 2;
	}

	close(fd);
	return 0;
}
