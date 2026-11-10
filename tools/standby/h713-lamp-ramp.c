/* Bounded PB5 soft start through its existing gpio-backlight owner.
 * PB5 also feeds the fan. This is a half-second startup ramp, never a
 * steady dimming mode. Failure leaves the lamp off and reports an error.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define LAMP "/sys/class/backlight/lamp/bl_power"
#define PERIOD_NS 2000000LL
#define CYCLES 250
static volatile sig_atomic_t interrupted;

static void interrupt_ramp(int sig) { (void)sig; interrupted = 1; }

static long long now_ns(void)
{
	struct timespec ts;
	if (clock_gettime(CLOCK_MONOTONIC, &ts)) return -1;
	return ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

static int power(int fd, int on)
{
	if (lseek(fd, 0, SEEK_SET) < 0) return -1;
	return write(fd, on ? "0\n" : "4\n", 2) == 2 ? 0 : -1;
}

static int wait_until(long long end, int busy)
{
	if (busy) {
		long long now;
		do {
			now = now_ns();
			if (now < 0 || interrupted) return -1;
		} while (now < end);
		return 0;
	}
	struct timespec ts = { .tv_sec = end / 1000000000LL,
		.tv_nsec = end % 1000000000LL };
	int ret;
	do ret = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL);
	while (ret == EINTR && !interrupted);
	return ret || interrupted ? -1 : 0;
}

int main(int argc, char **argv)
{
	char initial[8] = {0};
	if (argc != 2 || strcmp(argv[1], "--enable")) {
		fprintf(stderr, "usage: h713-lamp-ramp --enable\n");
		return 2;
	}
	int rd = open(LAMP, O_RDONLY | O_CLOEXEC);
	if (rd < 0 || read(rd, initial, sizeof(initial) - 1) <= 0) {
		perror("read lamp state");
		if (rd >= 0) close(rd);
		return 1;
	}
	close(rd);
	if (!strcmp(initial, "0\n")) {
		puts("lamp already on");
		return 0;
	}
	if (strcmp(initial, "4\n")) {
		fprintf(stderr, "lamp must be in standby before ramp\n");
		return 1;
	}
	int fd = open(LAMP, O_WRONLY | O_CLOEXEC);
	if (fd < 0) { perror("open lamp"); return 1; }
	struct sigaction sa = { .sa_handler = interrupt_ramp };
	sigemptyset(&sa.sa_mask);
	sigaction(SIGINT, &sa, NULL);
	sigaction(SIGTERM, &sa, NULL);
	/* Avoid a page fault or competing userspace task extending an early
	 * high pulse. Scheduling is used only for this bounded startup process. */
	struct sched_param sp = { .sched_priority = 1 };
	if (mlockall(MCL_CURRENT | MCL_FUTURE) ||
	    sched_setscheduler(0, SCHED_FIFO, &sp)) {
		perror("lock ramp timing"); close(fd); return 1;
	}
	for (int i = 0; i < CYCLES; ++i) {
		long long start = now_ns();
		/* Start at 1% duty, increase monotonically to 100%. */
		int duty = 1 + i * 99 / (CYCLES - 1);
		if (start < 0 || interrupted || power(fd, 1) ||
		    wait_until(start + PERIOD_NS * duty / 100, 1)) goto fail;
		if (duty < 100 && (power(fd, 0) ||
		    wait_until(start + PERIOD_NS, 0))) goto fail;
	}
	close(fd);
	puts("lamp startup ramp complete; PB5 held high");
	return 0;
fail:
	(void)power(fd, 0);
	close(fd);
	fputs("lamp startup ramp failed; left off\n", stderr);
	return 1;
}
