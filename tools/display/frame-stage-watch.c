/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Persist the H713 MIPS frame trace and composition registers without relying
 * on a shell being scheduled after a risky DECD submit.
 *
 * Build for the target:
 *
 *   clang --target=aarch64-linux-gnu -nostdlib -static -ffreestanding -Os \
 *         -fno-stack-protector -fuse-ld=lld -Wl,-e,_start \
 *         -o frame-stage-watch frame-stage-watch.c
 *
 * The program snapshots stage 0 immediately, then busy-polls the persistent
 * trace marker at 0x4e340040. Every changed stage is appended to an O_SYNC
 * file and fsync'd. Stage 0x6103 includes the complete 0x05000000 page. Run it
 * under chrt/taskset before submitting a frame; it exits after stage 0x6103.
 */
typedef unsigned int u32;
typedef unsigned long u64;
typedef unsigned long usize;

#define SYS_openat 56
#define SYS_close  57
#define SYS_write  64
#define SYS_fsync  82
#define SYS_mmap   222
#define SYS_exit   93

#define AT_FDCWD   -100
#define O_RDONLY   0
#define O_WRONLY   1
#define O_CREAT    0100
#define O_TRUNC    01000
#define O_SYNC     0x101000
#define PROT_READ  1
#define MAP_SHARED 1
#define PAGE       4096UL

#define TRACE_PHYS 0x4e340000UL
#define ROUTE_PHYS 0x05000000UL
#define AFBD_PHYS  0x05600000UL
#define INFO_PHYS  0x6c8f1000UL
#define FINAL_STAGE 0x00006103U

static char buffer[32768];
static usize used;

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

static char hex_digit(u32 value)
{
	return value < 10 ? '0' + value : 'A' + value - 10;
}

static void append_char(char c)
{
	if (used < sizeof(buffer))
		buffer[used++] = c;
}

static void append_string(const char *s)
{
	while (*s)
		append_char(*s++);
}

static void append_hex(u32 value)
{
	int i;

	for (i = 7; i >= 0; --i)
		append_char(hex_digit(value >> (i * 4) & 0xf));
}

static void append_register(u32 address, u32 value)
{
	append_hex(address);
	append_string(" 0x");
	append_hex(value);
	append_char('\n');
}

static void write_all(int fd, const char *data, usize size)
{
	while (size) {
		long done = sys(SYS_write, fd, (long)data, size, 0, 0, 0);

		if (done <= 0)
			return;
		data += done;
		size -= done;
	}
}

static volatile u32 *map_page(int memfd, u32 address)
{
	u64 map = (u64)sys(SYS_mmap, 0, PAGE, PROT_READ, MAP_SHARED,
			   memfd, address);

	if ((long)map < 0 && (long)map > -4096)
		return (volatile u32 *)0;
	return (volatile u32 *)map;
}

static void snapshot(int outfd, volatile u32 *trace, volatile u32 *route,
		     volatile u32 *afbd, volatile u32 *info, u32 stage)
{
	u32 i;

	used = 0;
	append_string("STAGE 0x");
	append_hex(stage);
	append_char('\n');

	for (i = 0x40 / 4; i <= 0x54 / 4; ++i)
		append_register(TRACE_PHYS + i * 4, trace[i]);

	/* A full page is cheap enough and avoids guessing which composition word
	 * matters. The previous shell watcher covered only through +0x87c. */
	for (i = 0; i < PAGE / 4; ++i)
		append_register(ROUTE_PHYS + i * 4, route[i]);

	for (i = 0; i < 0x80 / 4; ++i)
		append_register(AFBD_PHYS + i * 4, afbd[i]);

	for (i = 0x6c / 4; i <= 0x8c / 4; ++i)
		append_register(INFO_PHYS + i * 4, info[i]);

	append_char('\n');
	write_all(outfd, buffer, used);
	sys(SYS_fsync, outfd, 0, 0, 0, 0, 0);
}

__attribute__((used, noinline)) int run(void)
{
	static const char mem_path[] = "/dev/mem";
	static const char out_path[] = "/root/frame-stage-watch.txt";
	static const char done[] = "FRAME_STAGE_WATCH_DONE\n";
	volatile u32 *trace, *route, *afbd, *info;
	u32 last, stage;
	int memfd, outfd;

	memfd = sys(SYS_openat, AT_FDCWD, (long)mem_path,
		    O_RDONLY | O_SYNC, 0, 0, 0);
	if (memfd < 0)
		return 1;
	outfd = sys(SYS_openat, AT_FDCWD, (long)out_path,
		    O_WRONLY | O_CREAT | O_TRUNC | O_SYNC, 0644, 0, 0);
	if (outfd < 0)
		return 2;

	trace = map_page(memfd, TRACE_PHYS);
	route = map_page(memfd, ROUTE_PHYS);
	afbd = map_page(memfd, AFBD_PHYS);
	info = map_page(memfd, INFO_PHYS);
	if (!trace || !route || !afbd || !info)
		return 3;

	last = trace[0x40 / 4];
	snapshot(outfd, trace, route, afbd, info, last);
	for (;;) {
		stage = trace[0x40 / 4];
		if (stage == last)
			continue;
		snapshot(outfd, trace, route, afbd, info, stage);
		last = stage;
		if (stage == FINAL_STAGE)
			break;
	}

	write_all(1, done, sizeof(done) - 1);
	sys(SYS_close, outfd, 0, 0, 0, 0, 0);
	sys(SYS_close, memfd, 0, 0, 0, 0, 0);
	return 0;
}

__attribute__((naked, noreturn)) void _start(void)
{
	__asm__ volatile(
		"bl run\n"
		"mov x8, #93\n"
		"svc #0\n");
}
