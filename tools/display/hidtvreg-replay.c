/*
 * Stock-Android probe: replay a captured register state onto the live system.
 *
 * hidtvreg-fill.c writes one constant across a range, which answers "is this
 * range load-bearing". This one writes a *list* of address/value pairs, which
 * answers the question that actually matters after a stock-versus-ours diff:
 * force OUR values onto the working system and see whether the video breaks.
 *
 * Input is a file in exactly the format hidtvreg-read.c and mmio-read.c emit --
 * "aaaaaaaa 0xVVVVVVVV" per line -- so the "ours" column of a diff can be fed
 * straight in without reformatting. Lines that are blank or unparseable are a
 * hard error rather than skipped, because a silently ignored line means part of
 * the state under test never got applied and the null that follows is a lie.
 *
 *   arm-linux-gnueabi-gcc -Wall -Wextra -Os -nostdlib -static -fno-builtin \
 *       -fno-stack-protector -Wl,-e,_start -o hidtvreg-replay hidtvreg-replay.c
 *
 *   hidtvreg-replay /data/local/tmp/ours.txt f
 *
 * Writes every pair, holds 15 seconds, then restores every register to the
 * value it read at run time. The restore is unconditional on the normal path,
 * so a replay that blanks the panel recovers by itself. Keep holds short and do
 * not background it: nothing recovers if the process is killed mid-hold.
 *
 * Registers may span pages; each access maps its own page, which is slower than
 * caching but cannot get the wrong page for an address.
 */
typedef unsigned int u32;
typedef unsigned long usize;

#define PROT_READ  1
#define PROT_WRITE 2
#define MAP_SHARED 1
#define O_RDONLY   0
#define O_RDWR     2

#define MAX_PAIRS  512u
#define BUF_SIZE   32768u

static long syscall1(long number, long a0)
{
	register long r0 __asm__("r0") = a0;
	register long r7 __asm__("r7") = number;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r7) : "memory");
	return r0;
}

static long syscall2(long number, long a0, long a1)
{
	register long r0 __asm__("r0") = a0;
	register long r1 __asm__("r1") = a1;
	register long r7 __asm__("r7") = number;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r7) : "memory");
	return r0;
}

static long syscall3(long number, long a0, long a1, long a2)
{
	register long r0 __asm__("r0") = a0;
	register long r1 __asm__("r1") = a1;
	register long r2 __asm__("r2") = a2;
	register long r7 __asm__("r7") = number;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7)
			 : "memory");
	return r0;
}

static long syscall6(long number, long a0, long a1, long a2, long a3,
		     long a4, long a5)
{
	register long r0 __asm__("r0") = a0;
	register long r1 __asm__("r1") = a1;
	register long r2 __asm__("r2") = a2;
	register long r3 __asm__("r3") = a3;
	register long r4 __asm__("r4") = a4;
	register long r5 __asm__("r5") = a5;
	register long r7 __asm__("r7") = number;
	__asm__ volatile("svc 0" : "+r"(r0)
			 : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r5), "r"(r7)
			 : "memory");
	return r0;
}

static usize string_length(const char *s)
{
	usize n = 0;
	while (s[n])
		++n;
	return n;
}

static void output(const char *s, usize n)
{
	while (n) {
		long done = syscall3(4, 1, (long)s, n); /* write */
		if (done <= 0)
			return;
		s += done;
		n -= done;
	}
}

static void output_string(const char *s)
{
	output(s, string_length(s));
}

static char hex_digit_lower(u32 v) { return v < 10 ? '0' + v : 'a' + v - 10; }
static char hex_digit_upper(u32 v) { return v < 10 ? '0' + v : 'A' + v - 10; }

static void output_register(u32 address, u32 value)
{
	char line[20];
	int i;

	for (i = 0; i < 8; ++i)
		line[i] = hex_digit_lower(address >> (28 - 4 * i) & 0xf);
	line[8] = ' ';
	line[9] = '0';
	line[10] = 'x';
	for (i = 0; i < 8; ++i)
		line[11 + i] = hex_digit_upper(value >> (28 - 4 * i) & 0xf);
	line[19] = '\n';
	output(line, sizeof(line));
}

static int hex_value(char c, u32 *out)
{
	if (c >= '0' && c <= '9') { *out = c - '0'; return 1; }
	if (c >= 'a' && c <= 'f') { *out = c - 'a' + 10; return 1; }
	if (c >= 'A' && c <= 'F') { *out = c - 'A' + 10; return 1; }
	return 0;
}

static void sleep_seconds(u32 seconds)
{
	long spec[2];

	spec[0] = seconds;
	spec[1] = 0;
	syscall2(162, (long)spec, 0); /* nanosleep */
}

/* Map the page holding `address` and return a pointer to that word, or 0. */
static volatile u32 *map_word(int fd, u32 address, int writable)
{
	long result = syscall6(192, 0, 4096,
			       writable ? (PROT_READ | PROT_WRITE) : PROT_READ,
			       MAP_SHARED, fd, (address & ~0xfffu) >> 12);

	if ((unsigned long)result >= (unsigned long)-4095)
		return 0;
	return (volatile u32 *)(result + (address & 0xfffu));
}

__attribute__((used, noinline)) int run(long *stack)
{
	static const char device[] = "/dev/hidtvreg";
	static char buf[BUF_SIZE];
	static u32 addrs[MAX_PAIRS], wants[MAX_PAIRS], saved[MAX_PAIRS];
	long argc = stack[0];
	const char *path = argc > 1 ? (const char *)stack[2] : 0;
	const char *arg_seconds = argc > 2 ? (const char *)stack[3] : 0;
	u32 seconds = 15, n = 0, i, d;
	long len;
	int fd, ffd;
	usize p = 0;

	if (!path) {
		output_string("usage: hidtvreg-replay <file> [hex-seconds]\n");
		return 2;
	}
	if (arg_seconds) {
		u32 v = 0;
		const char *s = arg_seconds;

		if (!*s) return 2;
		while (*s) {
			if (!hex_value(*s++, &d)) {
				output_string("bad seconds\n");
				return 2;
			}
			v = (v << 4) | d;
		}
		seconds = v;
	}

	ffd = syscall3(5, (long)path, O_RDONLY, 0);
	if (ffd < 0) {
		output_string("ERROR open input file\n");
		return 1;
	}
	len = syscall3(3, ffd, (long)buf, BUF_SIZE - 1); /* read */
	syscall1(6, ffd);
	if (len <= 0) {
		output_string("ERROR empty input file\n");
		return 1;
	}
	buf[len] = 0;

	/* Parse "aaaaaaaa 0xVVVVVVVV" lines. An unparseable line is fatal: a
	 * skipped one would mean the state under test was never fully applied,
	 * and the resulting null would be meaningless. */
	while (buf[p] && n < MAX_PAIRS) {
		u32 a = 0, v = 0;
		int got = 0;

		while (buf[p] == ' ' || buf[p] == '\n' || buf[p] == '\r')
			++p;
		if (!buf[p])
			break;
		while (hex_value(buf[p], &d)) { a = (a << 4) | d; ++p; ++got; }
		if (!got) { output_string("ERROR bad address in input\n"); return 1; }
		while (buf[p] == ' ') ++p;
		if (buf[p] == '0' && (buf[p + 1] == 'x' || buf[p + 1] == 'X'))
			p += 2;
		got = 0;
		while (hex_value(buf[p], &d)) { v = (v << 4) | d; ++p; ++got; }
		if (!got) { output_string("ERROR bad value in input\n"); return 1; }
		addrs[n] = a;
		wants[n] = v;
		++n;
		while (buf[p] && buf[p] != '\n')
			++p;
	}
	if (!n) {
		output_string("ERROR no pairs parsed\n");
		return 1;
	}

	fd = syscall3(5, (long)device, O_RDWR, 0);
	if (fd < 0) {
		output_string("ERROR open /dev/hidtvreg O_RDWR\n");
		return 1;
	}

	output_string("--- before ---\n");
	for (i = 0; i < n; ++i) {
		volatile u32 *w = map_word(fd, addrs[i], 1);

		if (!w) { output_string("ERROR mmap\n"); return 1; }
		saved[i] = *w;
		output_register(addrs[i], saved[i]);
	}

	for (i = 0; i < n; ++i) {
		volatile u32 *w = map_word(fd, addrs[i], 1);

		if (w)
			*w = wants[i];
	}

	output_string("--- replayed, holding ---\n");
	for (i = 0; i < n; ++i) {
		volatile u32 *w = map_word(fd, addrs[i], 1);

		if (w)
			output_register(addrs[i], *w);
	}

	sleep_seconds(seconds);

	for (i = 0; i < n; ++i) {
		volatile u32 *w = map_word(fd, addrs[i], 1);

		if (w)
			*w = saved[i];
	}

	output_string("--- restored ---\n");
	for (i = 0; i < n; ++i) {
		volatile u32 *w = map_word(fd, addrs[i], 1);

		if (w)
			output_register(addrs[i], *w);
	}

	syscall1(6, fd);
	return 0;
}

__attribute__((naked, noreturn)) void _start(void)
{
	__asm__ volatile(
		"mov r0, sp\n"
		"bl run\n"
		"mov r7, #1\n" /* exit */
		"svc 0\n");
}
