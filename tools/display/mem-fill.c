/*
 * Fill a physical memory range with a 32-bit pattern, on our arm64 Linux.
 *
 * A scanout liveness probe. Every consumer-side display experiment so far has
 * assumed the panel is being actively fetched; when a result comes back "no
 * visible change" that assumption is what makes it a result rather than a
 * non-event. On 2026-08-29 disabling the channel that should have been feeding
 * the panel changed nothing, which is equally consistent with "the write did not
 * matter" and with "the panel image is frozen and nothing is being fetched at
 * all". Those need separating before any further experiment means anything.
 *
 * So: write a known colour into the buffer being scanned out and look. If the
 * panel follows, scanout is live and a null result elsewhere is real. If it does
 * not, the panel is frozen and every consumer-side null is unfalsifiable.
 *
 * Read the live address from 0x05600178 rather than trusting the boot log: it
 * reports the adopted scanout as `source 6c100000`, but that is the address at
 * probe time. KMS then allocates its own framebuffer from CMA and repoints the
 * channel, so in the running system it is somewhere else entirely.
 *
 * That has a consequence. CONFIG_STRICT_DEVMEM blocks /dev/mem from mapping
 * system RAM, so once the channel points at CMA this tool cannot reach it --
 * mmap fails. It works on the U-Boot scanout carveout at 0x6c100000, which is a
 * `no-map` reserved region rather than RAM. To repaint a CMA framebuffer in the
 * working state, use /dev/fb0 instead.
 *
 *   mem-fill 6c100000 384000 00FF0000 10
 *
 * ...fills 0x384000 bytes (1280x720x4) with 0x00FF0000 and keeps rewriting for
 * 10 seconds. It rewrites rather than filling once because fbcon may redraw over
 * it in the working state, and a single fill could be overwritten before it can
 * be seen. Root.
 */
typedef unsigned int u32;
typedef unsigned long u64;
typedef unsigned long usize;

#define SYS_openat 56
#define SYS_close  57
#define SYS_write  64
#define SYS_mmap   222
#define SYS_nanosleep 101

#define AT_FDCWD   -100
#define O_RDWR     2
#define O_SYNC     0x101000
#define PROT_READ  1
#define PROT_WRITE 2
#define MAP_SHARED 1

static long sys(long n, long a, long b, long c, long d, long e, long f)
{
	register long x8 __asm__("x8") = n;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	register long x4 __asm__("x4") = e;
	register long x5 __asm__("x5") = f;

	__asm__ volatile("svc #0"
			 : "+r"(x0)
			 : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
			 : "memory");
	return x0;
}

static void sleep_50ms(void)
{
	long spec[2];

	spec[0] = 0;
	spec[1] = 50000000;
	sys(SYS_nanosleep, (long)spec, 0, 0, 0, 0, 0);
}

static usize string_length(const char *s)
{
	usize n = 0;
	while (s[n])
		++n;
	return n;
}

static void output_string(const char *s)
{
	usize n = string_length(s);

	while (n) {
		long done = sys(SYS_write, 1, (long)s, n, 0, 0, 0);
		if (done <= 0)
			return;
		s += done;
		n -= done;
	}
}

/* Returns 0 on a bad digit, so a mistyped argument cannot silently become 0 and
 * send a fill at physical address zero. */
static int parse_hex(const char *s, u32 *out)
{
	u32 v = 0;
	int digits = 0;

	if (!s)
		return 0;
	while (*s) {
		u32 d;

		if (*s >= '0' && *s <= '9')
			d = *s - '0';
		else if (*s >= 'a' && *s <= 'f')
			d = *s - 'a' + 10;
		else if (*s >= 'A' && *s <= 'F')
			d = *s - 'A' + 10;
		else
			return 0;
		v = (v << 4) | d;
		++digits;
		++s;
	}
	if (!digits || digits > 8)
		return 0;
	*out = v;
	return 1;
}

static int parse_dec(const char *s, u32 *out)
{
	u32 v = 0;
	int digits = 0;

	if (!s)
		return 0;
	while (*s) {
		if (*s < '0' || *s > '9')
			return 0;
		v = v * 10 + (u32)(*s - '0');
		++digits;
		++s;
	}
	if (!digits)
		return 0;
	*out = v;
	return 1;
}

__attribute__((used, noinline)) int run(long *stack)
{
	static const char device[] = "/dev/mem";
	long argc = stack[0];
	u32 addr, len, val, secs = 5, i, reps;
	volatile u32 *p;
	u64 map;
	int fd;

	if (argc < 4 ||
	    !parse_hex((const char *)stack[2], &addr) ||
	    !parse_hex((const char *)stack[3], &len) ||
	    !parse_hex((const char *)stack[4], &val)) {
		output_string("usage: mem-fill <hex-addr> <hex-len> <hex-value> [seconds]\n");
		return 2;
	}
	if (argc > 4 && !parse_dec((const char *)stack[5], &secs)) {
		output_string("bad seconds\n");
		return 2;
	}
	if (addr & 0xfff) {
		output_string("address must be page aligned\n");
		return 2;
	}
	if (!len || (len & 3)) {
		output_string("length must be non-zero and a multiple of 4\n");
		return 2;
	}

	fd = sys(SYS_openat, AT_FDCWD, (long)device, O_RDWR | O_SYNC, 0, 0, 0);
	if (fd < 0) {
		output_string("ERROR open /dev/mem -- run as root\n");
		return 1;
	}
	/* arm64 sys_mmap takes a page-aligned BYTE offset. */
	map = (u64)sys(SYS_mmap, 0, len, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
		       addr);
	if ((long)map < 0 && (long)map > -4096) {
		output_string("ERROR mmap\n");
		return 1;
	}
	p = (volatile u32 *)map;

	output_string("filling\n");
	/* Rewrite for the whole window: in the working state fbcon redraws over
	 * a single fill, and a pattern that vanishes before it can be seen is
	 * indistinguishable from one that never reached the panel. */
	for (reps = 0; reps < secs * 20; ++reps) {
		for (i = 0; i < len / 4; ++i)
			p[i] = val;
		sleep_50ms();
	}

	output_string("done\n");
	sys(SYS_close, fd, 0, 0, 0, 0, 0);
	return 0;
}

__attribute__((naked, noreturn)) void _start(void)
{
	__asm__ volatile(
		"mov x0, sp\n"
		"bl run\n"
		"mov x8, #93\n" /* exit */
		"svc #0\n");
}
