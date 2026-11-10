/*
 * Copy a physical range to stdout as raw bytes, through stock Android's
 * /dev/hidtvreg.  The binary counterpart of hidtvreg-read.c.
 *
 * hidtvreg-read prints one page as "aaaaaaaa 0xVVVVVVVV" text, which is right
 * for registers and wrong for a 2 MiB DRAM log: 512 invocations and 10 MB of
 * text per sample.  This one exists for the MIPS firmware's elog ring
 * (0x4b270000 + 2 MiB) and for the firmware's copy of display_cfg.xml at
 * 0x4be01000 -- both DRAM, both parsed on the host.  Do not point it at
 * register blocks; use hidtvreg-read there, so captures diff line-for-line.
 *
 * Read-only by construction: the fd is opened O_RDONLY, each page is mapped
 * PROT_READ, and the copy is 32-bit word loads (what the device mapping is
 * proven to tolerate), one page at a time, unmapped before the next.
 *
 *   arm-linux-gnueabi-gcc -Wall -Wextra -Os -nostdlib -static -fno-builtin \
 *       -Wl,-e,_start -o hidtvreg-raw hidtvreg-raw.c
 *
 *   hidtvreg-raw 4b270000 200000 > elog.bin     2 MiB from 0x4b270000
 *
 * Address must be page-aligned and the byte count a multiple of 4, at most
 * 0x1000000 (16 MiB), so a typo cannot stream the whole of DRAM.
 */
typedef unsigned int u32;
typedef unsigned long usize;

#define PROT_READ  1
#define MAP_SHARED 1
#define O_RDONLY   0
#define PAGE       4096u
#define MAX_BYTES  0x1000000u

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

static int output(int fd, const void *buf, usize n)
{
	const char *s = buf;

	while (n) {
		long done = syscall3(4, fd, (long)s, n); /* write */
		if (done <= 0)
			return -1;
		s += done;
		n -= done;
	}
	return 0;
}

/* Diagnostics go to stderr: stdout is the payload. */
static void complain(const char *s)
{
	output(2, s, string_length(s));
}

/* Same contract as hidtvreg-read: 0 on a bad digit, so an unparseable
 * argument cannot silently read address 0. */
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

static u32 buffer[PAGE / 4];

__attribute__((used, noinline)) int run(long *stack)
{
	static const char device[] = "/dev/hidtvreg";
	long argc = stack[0];
	const char *arg_address = argc > 1 ? (const char *)stack[2] : 0;
	const char *arg_bytes = argc > 2 ? (const char *)stack[3] : 0;
	u32 address, bytes, done, i;
	long result;
	int fd;

	if (!parse_hex(arg_address, &address) || !parse_hex(arg_bytes, &bytes)) {
		complain("usage: hidtvreg-raw <hex-address> <hex-byte-count>\n");
		return 2;
	}
	if (address & (PAGE - 1)) {
		complain("address must be page-aligned\n");
		return 2;
	}
	if (!bytes || (bytes & 3) || bytes > MAX_BYTES) {
		complain("byte count must be a non-zero multiple of 4, <= 0x1000000\n");
		return 2;
	}

	fd = syscall3(5, (long)device, O_RDONLY, 0); /* open */
	if (fd < 0) {
		complain("ERROR open /dev/hidtvreg\n");
		return 1;
	}

	for (done = 0; done < bytes; done += PAGE) {
		volatile u32 *page;
		u32 chunk = bytes - done < PAGE ? bytes - done : PAGE;

		result = syscall6(192, 0, PAGE, PROT_READ, MAP_SHARED, fd,
				  (address + done) >> 12); /* mmap2 */
		if ((unsigned long)result >= (unsigned long)-4095) {
			complain("ERROR mmap -- this window may not be reachable\n");
			return 1;
		}
		page = (volatile u32 *)result;
		for (i = 0; i < chunk / 4; ++i)
			buffer[i] = page[i];
		syscall2(91, result, PAGE); /* munmap */

		if (output(1, buffer, chunk)) {
			complain("ERROR write\n");
			return 1;
		}
	}

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
