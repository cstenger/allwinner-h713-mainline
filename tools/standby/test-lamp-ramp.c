/* Exercise the real helper with a clock and sysfs model; no hardware access. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static long long model_time;
static int enabled, writes, highs, lows, fail_write, fail_lock;
static int initial_off = 1;
static int mock_open(const char *p, int flags, ...)
{ (void)flags; assert(!strcmp(p, "/sys/class/backlight/lamp/bl_power")); return 77; }
static int mock_close(int fd) { assert(fd == 77); return 0; }
static ssize_t mock_read(int fd, void *buf, size_t n)
{ assert(fd == 77 && n >= 2); memcpy(buf, initial_off ? "4\n" : "0\n", 2); return 2; }
static off_t mock_seek(int fd, off_t off, int whence)
{ assert(fd == 77 && off == 0 && whence == SEEK_SET); return 0; }
static ssize_t mock_write(int fd, const void *buf, size_t n)
{
	assert(fd == 77 && n == 2);
	if (++writes == fail_write) { errno = EIO; return -1; }
	enabled = !memcmp(buf, "0\n", 2);
	if (enabled) highs++; else { assert(!memcmp(buf, "4\n", 2)); lows++; }
	return 2;
}
static int mock_clock(clockid_t id, struct timespec *ts)
{
	assert(id == CLOCK_MONOTONIC);
	model_time += 10000;
	ts->tv_sec = model_time / 1000000000LL;
	ts->tv_nsec = model_time % 1000000000LL;
	return 0;
}
static int mock_sleep(clockid_t id, int flags, const struct timespec *ts,
		      struct timespec *remain)
{
	assert(id == CLOCK_MONOTONIC && flags == TIMER_ABSTIME && !remain);
	long long end = ts->tv_sec * 1000000000LL + ts->tv_nsec;
	if (end > model_time) model_time = end;
	return 0;
}
static int mock_lock(int flags) { (void)flags; return fail_lock; }
static int mock_sched(pid_t pid, int policy, const struct sched_param *sp)
{ assert(!pid && policy == SCHED_FIFO && sp->sched_priority == 1); return 0; }

#define open mock_open
#define close mock_close
#define read mock_read
#define write mock_write
#define lseek mock_seek
#define clock_gettime mock_clock
#define clock_nanosleep mock_sleep
#define mlockall mock_lock
#define sched_setscheduler mock_sched
#define main ramp_main
#include "h713-lamp-ramp.c"
#undef main

static void reset(void)
{
	model_time = 0;
	enabled = writes = highs = lows = fail_write = fail_lock = interrupted = 0;
	initial_off = 1;
}

int main(void)
{
	char *args[] = { "lamp-ramp", "--enable", NULL };
	reset();
	assert(ramp_main(2, args) == 0);
	assert(enabled && highs == 250 && lows == 249);
	assert(model_time >= 500000000 && model_time < 510000000);
	reset(); fail_write = 7;
	assert(ramp_main(2, args) == 1);
	assert(!enabled && writes == 8 && model_time < 10000000);
	reset(); initial_off = 0;
	assert(ramp_main(2, args) == 0 && !writes);
	reset(); fail_lock = -1;
	assert(ramp_main(2, args) == 1 && !writes);
	reset();
	assert(ramp_main(1, args) == 2 && !writes);
	puts("PASS bounded ramp, final state, write failure, preconditions");
	return 0;
}
