/*
 * Stock-Android probe: write a value across a register range, hold it, restore.
 *
 * hidtvreg-poke.c is the same idea but its phases are hardcoded to the AFBD
 * channel-control question it was written for. This one takes the range and the
 * value, so a new difference from a stock-versus-ours diff can be forced onto
 * the working system without a rebuild.
 *
 * The method it exists to serve: a working system that breaks when you remove
 * something tells you more than a broken system that stays broken when you add
 * it. Force OUR value onto STOCK during playback and watch the panel.
 *
 *   arm-linux-gnueabi-gcc -Wall -Wextra -Os -nostdlib -static -fno-builtin \
 *       -fno-stack-protector -Wl,-e,_start -o hidtvreg-fill hidtvreg-fill.c
 *
 *   hidtvreg-fill 05000108 c FFFFFFFF f
 *
 * ...writes 0xFFFFFFFF to 12 words from 0x05000108, holds 15 seconds, then
 * restores every word to what it read at run time. All arguments are hex, no
 * 0x prefix, matching hidtvreg-read.
 *
 * The restore is unconditional and happens on the normal path, so a fill that
 * blanks the panel recovers by itself after the hold. It is NOT proof against
 * the process being killed mid-hold -- keep holds short and do not background
 * this.
 *
 * The count is clamped to stay inside the mapped page, and to 256 words so a
 * typo cannot rewrite a whole page from the saved-value buffer.
 */
typedef unsigned int u32;
typedef unsigned long usize;

#define PROT_READ  1
#define PROT_WRITE 2
#define MAP_SHARED 1
#define O_RDWR     2

#define MAX_WORDS  256u

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

static char hex_digit_lower(u32 value)
{
	return value < 10 ? '0' + value : 'a' + value - 10;
}

static char hex_digit_upper(u32 value)
{
	return value < 10 ? '0' + value : 'A' + value - 10;
}

/* Byte-identical to hidtvreg-read.c's output_register, so a fill's before and
 * after lines diff against a capture without reformatting. */
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

/* Returns 0 on a bad digit, so an unparseable argument cannot silently become
 * address 0 or value 0 and be mistaken for a deliberate write. */
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
	*out = value;
	return digits > 0;
}

static void sleep_seconds(u32 seconds)
{
	long spec[2];

	spec[0] = seconds;
	spec[1] = 0;
	syscall2(162, (long)spec, 0); /* nanosleep */
}

__attribute__((used, noinline)) int run(long *stack)
{
	static const char device[] = "/dev/hidtvreg";
	long argc = stack[0];
	const char *arg_address = argc > 1 ? (const char *)stack[2] : 0;
	const char *arg_count   = argc > 2 ? (const char *)stack[3] : 0;
	const char *arg_value   = argc > 3 ? (const char *)stack[4] : 0;
	const char *arg_seconds = argc > 4 ? (const char *)stack[5] : 0;
	volatile u32 *registers;
	u32 saved[MAX_WORDS];
	u32 address, count, value, seconds, page, offset, limit, i;
	long result;
	int fd;

	if (!parse_hex(arg_address, &address) || !parse_hex(arg_count, &count) ||
	    !parse_hex(arg_value, &value) || !parse_hex(arg_seconds, &seconds)) {
		output_string("usage: hidtvreg-fill <hex-addr> <hex-count> "
			      "<hex-value> <hex-seconds>\n");
		return 2;
	}

	page = address & ~0xfffu;
	offset = address & 0xfffu;
	limit = (4096 - offset) / 4;
	if (count > limit)
		count = limit;
	if (count > MAX_WORDS)
		count = MAX_WORDS;
	if (!count) {
		output_string("nothing to write\n");
		return 2;
	}

	fd = syscall3(5, (long)device, O_RDWR, 0); /* open */
	if (fd < 0) {
		output_string("ERROR open /dev/hidtvreg O_RDWR\n");
		return 1;
	}

	result = syscall6(192, 0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
			  page >> 12);
	if ((unsigned long)result >= (unsigned long)-4095) {
		output_string("ERROR mmap -- window not reachable writable\n");
		return 1;
	}
	registers = (volatile u32 *)result;

	output_string("--- before ---\n");
	for (i = 0; i < count; ++i) {
		saved[i] = registers[(offset / 4) + i];
		output_register(address + i * 4, saved[i]);
	}

	for (i = 0; i < count; ++i)
		registers[(offset / 4) + i] = value;

	output_string("--- written, holding ---\n");
	for (i = 0; i < count; ++i)
		output_register(address + i * 4, registers[(offset / 4) + i]);

	sleep_seconds(seconds);

	for (i = 0; i < count; ++i)
		registers[(offset / 4) + i] = saved[i];

	output_string("--- restored ---\n");
	for (i = 0; i < count; ++i)
		output_register(address + i * 4, registers[(offset / 4) + i]);

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
