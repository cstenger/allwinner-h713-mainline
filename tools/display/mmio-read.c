/*
 * Read MMIO ranges on the H713 under our arm64 Linux, in the exact output
 * format of tools/display/hidtvreg-read.c.
 *
 * This is the Linux-side counterpart of hidtvreg-read: same arguments, same
 * output, different device.  Stock reaches registers through the vendor's
 * /dev/hidtvreg; here it is /dev/mem.
 *
 * The format matters more than it looks.  These captures exist to be diffed
 * against docs/reference/stock-android-block-sweep-2026-08-28.txt, and the
 * first stock capture of this project emitted upper-case addresses against a
 * lower-case reference -- 90 of 150 lines came back as changed on formatting
 * alone.  Address lower-case, value upper-case, one space, "0x" on the value
 * only.  Do not tidy it.
 *
 * devmem32.c already reads registers here but prints "0x<addr>  <value>", which
 * does not line up, and it takes individual addresses rather than ranges.
 *
 * Why mmap and not read(): on arm64 /dev/mem's read() path is gated by
 * valid_phys_addr_range() -> memblock_is_map_memory(), and MMIO is not memory,
 * so every read returns -EFAULT on a perfectly healthy board.  Only mmap works,
 * and CONFIG_STRICT_DEVMEM permits exactly that.
 *
 *   clang --target=aarch64-linux-gnu -nostdlib -static -ffreestanding -Os \
 *         -fno-stack-protector -fuse-ld=lld -Wl,-e,_start \
 *         -o mmio-read mmio-read.c
 *
 *   mmio-read 05600000 80      128 words from 0x05600000
 *
 * Root, and the count is clamped so the read stays inside the mapped page.
 */
typedef unsigned int u32;
typedef unsigned long u64;
typedef unsigned long usize;

#define SYS_openat 56
#define SYS_close  57
#define SYS_write  64
#define SYS_mmap   222
#define SYS_exit   93

#define AT_FDCWD   -100
#define O_RDONLY   0
#define O_SYNC     0x101000
#define PROT_READ  1
#define MAP_SHARED 1
#define PAGE       4096UL

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
		long done = sys(SYS_write, 1, (long)s, n, 0, 0, 0);
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

/* Byte-identical to hidtvreg-read.c's output_register. */
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
	static const char device[] = "/dev/mem";
	long argc = stack[0];
	const char *arg_address = argc > 1 ? (const char *)stack[2] : 0;
	const char *arg_count = argc > 2 ? (const char *)stack[3] : 0;
	volatile u32 *registers;
	u32 address, count = 16, page, offset, limit, i;
	u64 map;
	int fd;

	if (!parse_hex(arg_address, &address)) {
		output_string("usage: mmio-read <hex-address> [hex-word-count]\n");
		return 2;
	}
	if (arg_count && !parse_hex(arg_count, &count)) {
		output_string("bad word count\n");
		return 2;
	}

	page = address & ~(u32)(PAGE - 1);
	offset = address & (u32)(PAGE - 1);
	limit = (PAGE - offset) / 4;
	if (count > limit)
		count = limit; /* keep the read inside the mapped page */
	if (!count) {
		output_string("nothing to read\n");
		return 2;
	}

	fd = sys(SYS_openat, AT_FDCWD, (long)device, O_RDONLY | O_SYNC, 0, 0, 0);
	if (fd < 0) {
		output_string("ERROR open /dev/mem -- run as root\n");
		return 1;
	}

	/* arm64's sys_mmap takes a BYTE offset, page-aligned -- not the page
	 * count that arm32's mmap2 wants. */
	map = (u64)sys(SYS_mmap, 0, PAGE, PROT_READ, MAP_SHARED, fd, (long)page);
	if ((long)map < 0 && (long)map > -4096) {
		output_string("ERROR mmap\n");
		return 1;
	}
	registers = (volatile u32 *)(map + offset);

	for (i = 0; i < count; ++i)
		output_register(address + i * 4, registers[i]);

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
