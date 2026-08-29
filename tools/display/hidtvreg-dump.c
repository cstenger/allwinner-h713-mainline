/*
 * Stock-Android H713 display register dump through /dev/hidtvreg.
 *
 * This is freestanding ARM EABI code so it can be built with the small
 * binutils-only cross toolchain used in the lab:
 *
 *   arm-linux-gnueabi-gcc -Os -nostdlib -static -fno-builtin \
 *       -Wl,-e,_start -o hidtvreg-dump hidtvreg-dump.c
 *
 * The program only mmaps registers read-only and writes their values to stdout.
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
			 : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r5),
			   "r"(r7)
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

/*
 * Match reference/decd-firmware-configured-black-2026-08-28.txt byte for byte.
 * That dump writes AFBD and mixer addresses bare and lower-case, TVTOP
 * addresses with an 0x prefix, and every value upper-case.  This output exists
 * only to be diffed against it, and a formatting difference is indistinguishable
 * from a register that changed -- the mixed conventions cost 90 of 150 lines.
 */
static void output_register(u32 address, u32 value, int prefix_address)
{
	char line[22];
	usize n = 0;
	int i;

	if (prefix_address) {
		line[n++] = '0';
		line[n++] = 'x';
	}
	for (i = 0; i < 8; ++i)
		line[n++] = hex_digit_lower(address >> (28 - 4 * i) & 0xf);
	line[n++] = ' ';
	line[n++] = '0';
	line[n++] = 'x';
	for (i = 0; i < 8; ++i)
		line[n++] = hex_digit_upper(value >> (28 - 4 * i) & 0xf);
	line[n++] = '\n';
	output(line, n);
}

static void output_value(u32 value)
{
	char line[11];
	int i;

	line[0] = '0';
	line[1] = 'x';
	for (i = 0; i < 8; ++i)
		line[2 + i] = hex_digit_upper(value >> (28 - 4 * i) & 0xf);
	line[10] = '\n';
	output(line, sizeof(line));
}

static volatile u32 *map_page(int fd, u32 address)
{
	/* ARM's mmap2 offset is in 4096-byte units. */
	long result = syscall6(192, 0, 4096, PROT_READ, MAP_SHARED, fd,
			       address >> 12);
	if ((unsigned long)result >= (unsigned long)-4095)
		return (volatile u32 *)0;
	return (volatile u32 *)result;
}

__attribute__((used, noinline)) int run(void)
{
	static const char device[] = "/dev/hidtvreg";
	static const u32 tvtop_offsets[] = { 0x00, 0x40, 0x44, 0x80, 0x84, 0x88 };
	volatile u32 *registers;
	int fd = syscall3(5, (long)device, O_RDONLY, 0); /* open */
	u32 i;

	if (fd < 0) {
		output_string("ERROR open /dev/hidtvreg\n");
		return 1;
	}

	/*
	 * A rejected window must not cost the whole capture: each section reports
	 * its own failure and the next one still runs.  Getting back onto stock
	 * Android with playback running is the expensive part, not the mmap.
	 */
	output_string("=== AFBD 0x05600000..0x056001ff ===\n");
	registers = map_page(fd, 0x05600000);
	if (!registers) {
		output_string("ERROR mmap AFBD\n");
	} else {
		for (i = 0; i < 0x200 / 4; ++i)
			output_register(0x05600000 + i * 4, registers[i], 0);
	}

	output_string("=== MIXER 0x0525c000..0x0525c03f ===\n");
	registers = map_page(fd, 0x0525c000);
	if (!registers) {
		output_string("ERROR mmap MIXER\n");
	} else {
		for (i = 0; i < 0x40 / 4; ++i)
			output_register(0x0525c000 + i * 4, registers[i], 0);
	}

	output_string("=== TVTOP ===\n");
	registers = map_page(fd, 0x05700000);
	if (!registers) {
		output_string("ERROR mmap TVTOP\n");
	} else {
		for (i = 0; i < sizeof(tvtop_offsets) / sizeof(tvtop_offsets[0]);
		     ++i)
			output_register(0x05700000 + tvtop_offsets[i],
					registers[tvtop_offsets[i] / 4], 1);
	}

	/* The reference dump's trailer: the MIPS run bit at 0x0306101c. */
	registers = map_page(fd, 0x03061000);
	if (!registers) {
		output_string("ERROR mmap MIPS\n");
	} else {
		output_string("MIPS=");
		output_value(registers[0x1c / 4]);
	}

	syscall1(6, fd); /* close */
	return 0;
}

__attribute__((naked, noreturn)) void _start(void)
{
	__asm__ volatile(
		"bl run\n"
		"mov r7, #1\n" /* exit */
		"svc 0\n");
}
