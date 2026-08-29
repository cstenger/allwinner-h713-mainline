/*
 * Read any MMIO page reachable through stock Android's /dev/hidtvreg.
 *
 * hidtvreg-dump.c is hardwired to the AFBD/mixer/TVTOP windows because it exists
 * to produce a diff against a saved reference.  This one takes an address, so a
 * new window can be inspected without a rebuild -- the IOMMU at 0x02010000, the
 * CCU, whatever the next question needs.  Read-only by construction: the fd is
 * opened O_RDONLY and the mapping is PROT_READ.
 *
 *   arm-linux-gnueabi-gcc -Wall -Wextra -Os -nostdlib -static -fno-builtin \
 *       -Wl,-e,_start -o hidtvreg-read hidtvreg-read.c
 *
 *   hidtvreg-read 02010000        16 words from 0x02010000
 *   hidtvreg-read 02010000 40     64 words
 *
 * The count is clamped so the read stays inside the mapped page.
 */
typedef unsigned int u32;
typedef unsigned long usize;

#define PROT_READ  1
#define MAP_SHARED 1
#define O_RDONLY   0

static long syscall1(long number, long a0)
{
	register long r0 __asm__("r0") = a0;
	register long r7 __asm__("r7") = number;
	__asm__ volatile("svc 0" : "+r"(r0) : "r"(r7) : "memory");
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

static char hex_digit_lower(u32 value)
{
	return value < 10 ? '0' + value : 'a' + value - 10;
}

static char hex_digit_upper(u32 value)
{
	return value < 10 ? '0' + value : 'A' + value - 10;
}

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

/* Returns 0 on a bad digit, so an unparseable argument cannot silently read
 * address 0 and be mistaken for a window full of zeroes. */
static int parse_hex(const char *s, u32 *out)
{
	u32 value = 0;
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
		value = (value << 4) | d;
		++digits;
		++s;
	}
	if (!digits || digits > 8)
		return 0;
	*out = value;
	return 1;
}

__attribute__((used, noinline)) int run(long *stack)
{
	static const char device[] = "/dev/hidtvreg";
	long argc = stack[0];
	const char *arg_address = argc > 1 ? (const char *)stack[2] : 0;
	const char *arg_count = argc > 2 ? (const char *)stack[3] : 0;
	volatile u32 *registers;
	u32 address, count = 16, page, offset, limit, i;
	long result;
	int fd;

	if (!parse_hex(arg_address, &address)) {
		output_string("usage: hidtvreg-read <hex-address> [hex-word-count]\n");
		return 2;
	}
	if (arg_count && !parse_hex(arg_count, &count)) {
		output_string("bad word count\n");
		return 2;
	}

	page = address & ~0xfffu;
	offset = address & 0xfffu;
	limit = (4096 - offset) / 4;
	if (count > limit)
		count = limit; /* keep the read inside the mapped page */
	if (!count) {
		output_string("nothing to read\n");
		return 2;
	}

	fd = syscall3(5, (long)device, O_RDONLY, 0); /* open */
	if (fd < 0) {
		output_string("ERROR open /dev/hidtvreg\n");
		return 1;
	}

	result = syscall6(192, 0, 4096, PROT_READ, MAP_SHARED, fd, page >> 12);
	if ((unsigned long)result >= (unsigned long)-4095) {
		output_string("ERROR mmap -- this window may not be reachable\n");
		return 1;
	}
	registers = (volatile u32 *)result;

	for (i = 0; i < count; ++i)
		output_register(address + i * 4,
				registers[(offset / 4) + i]);

	syscall1(6, fd); /* close */
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
