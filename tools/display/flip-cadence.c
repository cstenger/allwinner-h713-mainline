// SPDX-License-Identifier: GPL-2.0
/*
 * flip-cadence -- measure how long each decoded frame is actually displayed.
 *
 * RUNS ON THE TARGET.  Build:  gcc -O2 -o flip-cadence flip-cadence.c
 *
 * Companion to latch-timing.  That tool established the flip is ATOMIC: the
 * plane-address publish at 0x0560006c retires on the frame boundary (uniform
 * 0..16.7 ms retirement under randomised phase, never microseconds), so a ring
 * rewrite cannot split a frame and there is no structural tearing.
 *
 * This measures the other half of "vsync-correct": CADENCE.  Atomic flips can
 * still judder if frames are held for the wrong number of vsyncs.  29.97 fps
 * content on a ~60 Hz panel wants each frame held for 2 vsyncs (33.4 ms); a
 * 1/3 alternation is visible judder even though every individual flip is clean.
 *
 * Method: poll the live Y address at 0x05600070 and timestamp every change.
 * Each distinct address is one displayed frame, and the interval between
 * changes is its on-screen dwell.  Report the dwell distribution in units of
 * the 16.67 ms frame period.
 *
 * Read-only: this tool writes nothing.
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define AFBD_BASE 0x05600000UL
#define AFBD_SIZE 0x1000UL
#define OFF_Y0    0x70

#define VSYNC_US  16667.0

static double now_us(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1e6 + ts.tv_nsec / 1e3;
}

int main(int argc, char **argv)
{
	double secs = argc > 1 ? atof(argv[1]) : 6.0;
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	volatile uint32_t *regs;
	uint32_t last = 0;
	double t_last = 0, t_end;
	int n = 0, hist[9] = { 0 }, i;
	double sum = 0, worst = 0;

	if (fd < 0) {
		perror("open /dev/mem");
		return 1;
	}
	regs = mmap(NULL, AFBD_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED,
		    fd, AFBD_BASE);
	if ((void *)regs == MAP_FAILED) {
		perror("mmap");
		return 1;
	}

	last = regs[OFF_Y0 / 4];
	t_last = now_us();
	t_end = t_last + secs * 1e6;

	while (now_us() < t_end) {
		uint32_t v = regs[OFF_Y0 / 4];

		if (v != last) {
			double t = now_us();
			double dwell = t - t_last;
			int k = (int)(dwell / VSYNC_US + 0.5);

			if (n) {   /* skip the first, its start is arbitrary */
				hist[k > 8 ? 8 : k]++;
				sum += dwell;
				if (dwell > worst)
					worst = dwell;
			}
			n++;
			last = v;
			t_last = t;
		}
		usleep(200);
	}

	if (n < 2) {
		printf("no flips seen in %.1f s (Y0 = 0x%08x) -- is a stream running?\n",
		       secs, last);
		return 2;
	}
	/*
	 * Rate over the ACTIVE span (first flip to last), not the sample window.
	 * The clip is short; if playback ends mid-window, dividing by the window
	 * reports a fraction of the real rate next to a correct per-frame dwell,
	 * which looks like a contradiction and is purely an artefact.
	 */
	printf("flips=%d, active span %.2f s  =>  %.2f fps displayed\n",
	       n, sum / 1e6, (n - 1) / (sum / 1e6));
	printf("(sample window was %.1f s; any idle tail is excluded)\n", secs);
	printf("mean dwell %.1f ms (%.2f vsyncs), worst %.1f ms\n",
	       sum / (n - 1) / 1000.0, sum / (n - 1) / VSYNC_US, worst / 1000.0);
	printf("dwell histogram, in whole vsyncs:\n");
	for (i = 0; i <= 8; i++)
		if (hist[i])
			printf("   %d vsync%s (%5.1f ms): %d\n",
			       i, i == 1 ? " " : "s", i * VSYNC_US / 1000.0, hist[i]);
	printf("\n29.97 fps content on a 60 Hz panel is correct at a steady 2 vsyncs.\n");
	printf("A 1/3 split is judder; a spread is dropped or late frames.\n");
	return 0;
}
