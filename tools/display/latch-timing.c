// SPDX-License-Identifier: GPL-2.0
/*
 * latch-timing -- time how long the DECD latches take to retire.
 *
 * RUNS ON THE TARGET.  Build:  gcc -O2 -o latch-timing latch-timing.c
 *
 * Why this exists.  2026-09-08 established that the source-config commit at
 * 0x05600014 RETIRES ON VSYNC: written back to back from the kernel it does not
 * clear, and the hardware silently ignores the configuration while every
 * register still reads back correct.  That was found by accident.
 *
 * The same question decides whether frame flipping is already tear-free.
 * dec_frame_queue_sync() rewrites all four ring slots inside the vsync handler
 * and publishes with 0x0560006c.  If that publish also latches on the frame
 * boundary, the flip is atomic with respect to the raster and there is nothing
 * to fix.  If it takes effect immediately, a rewrite can land mid-scan and
 * tearing is structural.
 *
 * Method: write 1, then poll the register with a monotonic clock until it reads
 * 0, and report the distribution.  A latch that retires on vsync shows a spread
 * up to one frame period (16.7 ms at 60 Hz) and a mean near half of it.  One
 * that retires immediately shows microseconds.
 *
 * Read-only apart from writing the latch itself, which is what the driver and
 * every working recipe already do.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define AFBD_BASE   0x05600000UL
#define AFBD_SIZE   0x1000UL
#define OFF_COMMIT  0x14      /* source config commit */
#define OFF_PUBLISH 0x6c      /* two-plane address publish (AFBD_DIRTY) */

static volatile uint32_t *regs;

static double now_us(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1e6 + ts.tv_nsec / 1e3;
}

static int cmp(const void *a, const void *b)
{
	double x = *(const double *)a, y = *(const double *)b;

	return (x > y) - (x < y);
}

static void measure(const char *name, unsigned off, int n, double budget_us)
{
	double *s = calloc(n, sizeof(*s));
	int timeouts = 0, immediate = 0, i;
	double sum = 0;

	for (i = 0; i < n; i++) {
		double t0, el;

		regs[off / 4] = 1;
		t0 = now_us();
		for (;;) {
			if (!regs[off / 4]) {
				el = now_us() - t0;
				break;
			}
			el = now_us() - t0;
			if (el > budget_us) {
				timeouts++;
				break;
			}
		}
		if (el < 50.0)
			immediate++;
		s[i] = el;
		sum += el;
		/*
		 * RANDOMISE.  A fixed inter-sample delay phase-locks the sampler
		 * to the panel: a constant 3 ms plus a ~13.7 ms wait sums to one
		 * 16.7 ms frame, so every write lands at the same point in the
		 * frame and the spread collapses to a constant.  That reads like
		 * a fixed hardware latency and is an artefact of the sampler.
		 * A uniform 0..20 ms jitter puts the write at arbitrary phase, so
		 * a vsync-latched register shows a UNIFORM 0..16.7 ms spread.
		 */
		usleep(rand() % 20000);
	}

	qsort(s, n, sizeof(*s), cmp);
	printf("  %-22s n=%d  min=%.0f us  median=%.0f us  max=%.0f us  mean=%.0f us\n",
	       name, n, s[0], s[n / 2], s[n - 1], sum / n);
	printf("  %-22s under-50us=%d/%d   timeouts(>%.0f us)=%d\n",
	       "", immediate, n, budget_us, timeouts);
	{
		int b, hist[8] = { 0 };

		for (b = 0; b < n; b++) {
			int k = (int)(s[b] / (16667.0 / 8));

			hist[k > 7 ? 7 : k]++;
		}
		printf("  %-22s frame-phase histogram (eighths of 16.7 ms): ", "");
		for (b = 0; b < 8; b++)
			printf("%d ", hist[b]);
		printf("\n");
	}
	free(s);
}

int main(int argc, char **argv)
{
	int n = argc > 1 ? atoi(argv[1]) : 60;

	srand((unsigned)now_us());
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	void *map;

	if (fd < 0) {
		perror("open /dev/mem");
		return 1;
	}
	map = mmap(NULL, AFBD_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED,
		   fd, AFBD_BASE);
	if (map == MAP_FAILED) {
		perror("mmap AFBD");
		return 1;
	}
	regs = map;

	printf("DECD latch retirement timing (one vsync = 16667 us at 60 Hz)\n");
	printf("  ctrl=0x%08x  fmt_byte=0x%02x\n",
	       regs[0x10 / 4], (regs[0x10 / 4] >> 8) & 0xff);
	measure("commit  0x05600014", OFF_COMMIT, n, 50000.0);
	measure("publish 0x0560006c", OFF_PUBLISH, n, 50000.0);
	return 0;
}
