/*
 * Write AFBD registers on the H713 under our arm64 Linux, then put them back.
 *
 * The arm64 counterpart of tools/display/hidtvreg-poke.c, which does the same
 * job on stock Android through /dev/hidtvreg.  Here it is /dev/mem, and mmap
 * rather than read()/write(): on arm64 the /dev/mem read path is gated by
 * valid_phys_addr_range() and MMIO is not memory.
 *
 * WHY THIS EXISTS.  The 2026-08-29 black-state sweep found that every
 * difference outside AFBD is byte-identical between our black state and our
 * *working* idle state, so the fault is inside AFBD.  The standout there is a
 * mirror image:
 *
 *     register     stock          ours (black)
 *     0x05600100   0x83001901     0x00010000     enabled+configured vs empty
 *     0x05600104   0x00000001     0x00000000     commit latch set   vs clear
 *     0x05600108   0x008000FF     0x00000000
 *     0x0560010c   0x00FF0080     0x00000000
 *     0x05600140   0x83001900     0x03001901     bit 0 CLEAR        vs SET
 *
 * Stock services channel 0x05600100 and leaves 0x140 disabled; we do the
 * opposite.  The model that fits: source 0 is the video producer and these
 * channels are the consumers.  Stock enables 0x100 to consume the video; we
 * enable 0x140 for our OSD framebuffer -- which is why our logo and console
 * render -- and leave 0x100 disabled, so source 0's output is configured,
 * latched, generating, and composited by nobody.
 *
 * Every phase restores the values it read at run time and re-pulses the latch,
 * so a phase that blanks the panel recovers by itself.  It also polls rather
 * than sleeps, because on this block an uncommitted write reads back
 * convincingly and does nothing -- readback alone proves nothing here.
 *
 *   clang --target=aarch64-linux-gnu -nostdlib -static -ffreestanding -Os \
 *         -fno-stack-protector -fuse-ld=lld -Wl,-e,_start \
 *         -o mmio-poke mmio-poke.c
 *
 *   mmio-poke 1   configure + enable channel 0x100 as stock has it, latch it
 *   mmio-poke 2   phase 1, and also clear 0x140's enable so it matches stock
 *   mmio-poke 3   phase 2, then exit immediately -- no hold, no restore
 *
 * Phase 3 exists because this state hard-locks the SoC within seconds to tens
 * of seconds (MIPS alive + DECD submitting), so every second spent holding is a
 * second the run can die in. A power cycle is the reset regardless, which makes
 * restoring pure cost here. Configure, exit, submit the frame from the caller.
 *
 * Run with a DECD frame in flight, or there is nothing for the channel to
 * consume. Root.
 *
 * RESULT 2026-08-29: the model above is REFUTED. Stock's 0x100 configuration was
 * written verbatim with 0x140 disabled, latched, and held 1000/1000 samples over
 * twenty seconds with readback confirming every write. The panel did not change,
 * and clearing 0x140's enable did not even blank it.
 *
 * Before using this again, establish that the panel is live: in that run it did
 * not respond to disabling the channel supposedly feeding it, so the image may
 * have been frozen, which would make any result here unfalsifiable. Boot with
 * 'h713_disp auto 0x34 logo' so a known image is on the panel and confirm it is
 * visible first. Do NOT read 0x05600058/0x0560005c as a liveness check -- they
 * are source-0 counters and read zero on a working display.
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
#define PAGE       4096UL

#define AFBD_PAGE  0x05600000
#define CH1_CTRL   0x100
#define CH1_LATCH  0x104
#define CH1_CFG_A  0x108
#define CH1_CFG_B  0x10c
#define CH2_CTRL   0x140
#define CH2_LATCH  0x144

#ifndef HOLD_SECONDS
#define HOLD_SECONDS 20
#endif
#define MAX_TARGETS 4

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

static char hex_lower(u32 v) { return v < 10 ? '0' + v : 'a' + v - 10; }
static char hex_upper(u32 v) { return v < 10 ? '0' + v : 'A' + v - 10; }

static void output_register(u32 address, u32 value)
{
	char line[20];
	int i;

	for (i = 0; i < 8; ++i)
		line[i] = hex_lower(address >> (28 - 4 * i) & 0xf);
	line[8] = ' ';
	line[9] = '0';
	line[10] = 'x';
	for (i = 0; i < 8; ++i)
		line[11 + i] = hex_upper(value >> (28 - 4 * i) & 0xf);
	line[19] = '\n';
	output(line, sizeof(line));
}

static void sleep_ns(long sec, long nsec)
{
	long spec[2];

	spec[0] = sec;
	spec[1] = nsec;
	sys(SYS_nanosleep, (long)spec, 0, 0, 0, 0, 0);
}

/* -nostdlib: no __aeabi/compiler-rt division helper is linked, and these counts
 * are in the hundreds, so repeated subtraction beats pulling one in. */
static u32 div10(u32 v, u32 *rem)
{
	u32 q = 0;

	while (v >= 10) {
		v -= 10;
		++q;
	}
	*rem = v;
	return q;
}

static void output_decimal(u32 v)
{
	char d[10];
	int n = 0;

	if (!v) {
		output("0", 1);
		return;
	}
	while (v) {
		u32 r;

		v = div10(v, &r);
		d[n++] = '0' + r;
	}
	while (n)
		output(&d[--n], 1);
}

__attribute__((used, noinline)) int run(long *stack)
{
	static const char device[] = "/dev/mem";
	long argc = stack[0];
	const char *arg = argc > 1 ? (const char *)stack[2] : 0;
	volatile u32 *r;
	u32 off[MAX_TARGETS], want[MAX_TARGETS], saved[MAX_TARGETS];
	u32 samples, held, first_revert, i;
	int targets = 0, clear_ch2 = 0, no_restore = 0;
	u64 map;
	int fd;

	if (!arg || arg[1] || (arg[0] < '1' || arg[0] > '3')) {
		output_string("usage: mmio-poke 1|2|3\n");
		return 2;
	}
	clear_ch2 = arg[0] == '2' || arg[0] == '3';
	no_restore = arg[0] == '3';

	fd = sys(SYS_openat, AT_FDCWD, (long)device, O_RDWR | O_SYNC, 0, 0, 0);
	if (fd < 0) {
		output_string("ERROR open /dev/mem -- run as root\n");
		return 1;
	}
	/* arm64 sys_mmap takes a page-aligned BYTE offset, not a page count. */
	map = (u64)sys(SYS_mmap, 0, PAGE, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
		       AFBD_PAGE);
	if ((long)map < 0 && (long)map > -4096) {
		output_string("ERROR mmap\n");
		return 1;
	}
	r = (volatile u32 *)map;

	/* Stock's channel-0x100 configuration, verbatim from the sweep. */
	off[0] = CH1_CTRL;  want[0] = 0x83001901u;
	off[1] = CH1_CFG_A; want[1] = 0x008000FFu;
	off[2] = CH1_CFG_B; want[2] = 0x00FF0080u;
	targets = 3;
	if (clear_ch2) {
		off[3] = CH2_CTRL;
		want[3] = 0;	/* filled from the live value below */
		targets = 4;
	}

	output_string("before\n");
	for (i = 0; i < (u32)targets; ++i) {
		saved[i] = r[off[i] / 4];
		output_register(AFBD_PAGE + off[i], saved[i]);
	}
	if (clear_ch2)
		want[3] = saved[3] & ~1u;	/* clear enable, keep the rest */

	for (i = 0; i < (u32)targets; ++i)
		r[off[i] / 4] = want[i];

	/* Latch. Without this the writes above are inert on this block. */
	r[CH1_LATCH / 4] = 1;
	if (clear_ch2)
		r[CH2_LATCH / 4] = 1;

	output_string("written + latched\n");
	for (i = 0; i < (u32)targets; ++i)
		output_register(AFBD_PAGE + off[i], r[off[i] / 4]);
	output_register(AFBD_PAGE + CH1_LATCH, r[CH1_LATCH / 4]);

	if (no_restore) {
		output_string("left in place (no restore); power-cycle to reset\n");
		sys(SYS_close, fd, 0, 0, 0, 0, 0);
		return 0;
	}

	samples = HOLD_SECONDS * 50;
	held = 0;
	first_revert = samples;
	for (i = 0; i < samples; ++i) {
		int ok = 1;
		u32 t;

		for (t = 0; t < (u32)targets; ++t)
			if (r[off[t] / 4] != want[t])
				ok = 0;
		if (ok)
			++held;
		else if (first_revert == samples)
			first_revert = i;
		sleep_ns(0, 20000000);
	}

	output_string("held at target in ");
	output_decimal(held);
	output_string("/");
	output_decimal(samples);
	output_string(" samples; first revert at ");
	if (first_revert == samples) {
		output_string("never\n");
	} else {
		output_decimal(first_revert * 20);
		output_string(" ms\n");
	}

	for (i = 0; i < (u32)targets; ++i)
		r[off[i] / 4] = saved[i];
	r[CH1_LATCH / 4] = 1;
	if (clear_ch2)
		r[CH2_LATCH / 4] = 1;

	output_string("restored\n");
	for (i = 0; i < (u32)targets; ++i)
		output_register(AFBD_PAGE + off[i], r[off[i] / 4]);

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
