// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Scan an MMIO range for regions that are actually backed.
 *
 * Written for the H713 HDMI-RX search, where the peer RE port's documented
 * EDID-RAM offset (THDMIRX+0x4424) turned out to be uniformly zero and to
 * refuse writes at both access widths, while other banks in the same window
 * plainly hold data. The question "which parts of this window are real?" is
 * not answerable one register at a time over ssh -- 256 round trips, and a
 * hang tells you nothing about where it happened.
 *
 *     cc -O2 -o mmio-scan mmio-scan.c
 *     mmio-scan 50c0000 10000          # scan 64 KiB, 256-byte blocks
 *     mmio-scan 50c0000 10000 40       # finer blocks
 *
 * Addresses, size and stride are hex with no 0x prefix, matching the other
 * tools here.
 *
 * TWO THINGS THIS DOES DELIBERATELY, both learned the hard way on this SoC:
 *
 *   - It prints a marker for every page BEFORE reading a byte of it, and
 *     flushes. An access to an unpowered or undecoded block here hangs the bus
 *     with no abort and no watchdog, taking the whole board down. When that
 *     happens the last line printed names the page that did it, instead of
 *     leaving a silent board and a guess.
 *
 *   - It reads BYTES, not words. Parts of this hardware are byte-wide and
 *     return zeros to 32-bit reads while byte reads of the same address return
 *     real data, so a word-based scan reports dead regions that are alive.
 */

#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define PAGE 4096UL

int main(int argc, char **argv)
{
	unsigned long base, size, stride = 0x100;
	unsigned long off, backed = 0, total = 0;
	int fd;

	if (argc < 3) {
		fprintf(stderr,
			"usage: mmio-scan <hex-base> <hex-size> [hex-stride]\n");
		return 2;
	}
	base = strtoul(argv[1], NULL, 16);
	size = strtoul(argv[2], NULL, 16);
	if (argc >= 4)
		stride = strtoul(argv[3], NULL, 16);
	if (!stride)
		stride = 0x100;

	fd = open("/dev/mem", O_RDONLY | O_SYNC);
	if (fd < 0) {
		perror("open /dev/mem");
		return 2;
	}

	for (off = 0; off < size; off += PAGE) {
		volatile uint8_t *p;
		void *m;
		unsigned long b;

		/* Named and flushed before the first access to this page. */
		printf("# page 0x%08lx\n", base + off);
		fflush(stdout);

		m = mmap(NULL, PAGE, PROT_READ, MAP_SHARED, fd,
			 (off_t)(base + off));
		if (m == MAP_FAILED) {
			printf("  mmap failed\n");
			continue;
		}
		p = (volatile uint8_t *)m;

		for (b = 0; b < PAGE && off + b < size; b += stride) {
			unsigned long i, lim = stride;
			int nz = 0;
			uint8_t first[8];

			if (off + b + lim > size)
				lim = size - off - b;
			if (b + lim > PAGE)
				lim = PAGE - b;

			for (i = 0; i < lim; i++) {
				uint8_t v = p[b + i];

				if (v) {
					if (nz < 8)
						first[nz] = v;
					nz++;
				}
			}
			total++;
			if (nz) {
				backed++;
				printf("  0x%08lx  %4d/%lu nonzero  first:",
				       base + off + b, nz, lim);
				for (i = 0; i < (unsigned long)(nz < 8 ? nz : 8); i++)
					printf(" %02x", first[i]);
				printf("\n");
			}
		}
		munmap(m, PAGE);
		fflush(stdout);
	}

	close(fd);
	printf("\n%lu of %lu blocks of 0x%lx bytes contain data\n",
	       backed, total, stride);
	return 0;
}
