/*
 * Stock-Android probe: which AFBD control bits are load-bearing for the panel?
 *
 * The stock playback capture shows 0x05600100 = 0x83001901 and
 * 0x05600140 = 0x83001900, both with bit 31 set, in idle and during playback
 * alike -- while our Linux configured-but-black state has 0x00010000 and
 * 0x03001900, bit 31 clear.  Rather than rebuild a kernel to set the bit on the
 * black side, clear it on the working side and watch the panel.  A working
 * system that breaks when you remove one bit tells you more than a broken
 * system that stays broken when you add it.
 *
 * Every phase clears its bits, polls for six seconds to prove they STAYED
 * cleared, then restores the values it read at run time.  The restore is
 * unconditional, so a phase that blanks the panel recovers by itself.
 *
 *   arm-linux-gnueabi-gcc -Os -nostdlib -static -fno-builtin \
 *       -Wl,-e,_start -o hidtvreg-poke hidtvreg-poke.c
 *
 *   hidtvreg-poke 1     bit 31 on 0x05600100                  (no commit)
 *   hidtvreg-poke 2     bit 31 on 0x05600140                  (no commit)
 *   hidtvreg-poke 3     bit 31 on both                        (no commit)
 *   hidtvreg-poke 4     bit 0, the channel ENABLE, on 0x05600100 (no commit)
 *   hidtvreg-poke 5     bits 1:0, the source ENABLE, on 0x05600010 (no commit)
 *   hidtvreg-poke 6     phase 5, committed
 *   hidtvreg-poke 7     bit 31 on 0x05600100, committed
 *   hidtvreg-poke 8     bit 31 on 0x05600140, committed
 *   hidtvreg-poke 9     bit 31 on both, committed
 *
 * THE RULE, established 2026-08-28: a write to this block does nothing until
 * the per-register commit latch is pulsed -- control at +0x00, latch at +0x04.
 * Phases 1-5 are kept only as the demonstration of it.  Every one of them held
 * its cleared value for 300/300 samples across six seconds and changed nothing
 * on the panel; phase 6 is the identical write to phase 5 with the latch pulsed
 * and it replaced the playing video with solid green.  An uncommitted write
 * reads back convincingly and is inert, so readback proves nothing here.
 *
 * Green, not black, is the signature of a YUV source with no data: Y=0, Cb=0,
 * Cr=0 is about RGB(0,135,0).  So AFBD source 0 really is the live video path
 * to the panel, and phase 6 is the positive control the others lacked.
 *
 * Result for the question this file was written to answer: bit 31 is NOT
 * load-bearing.  Phases 7, 8 and 9 clear it with the latch pulsed, individually
 * and together, during verified-motion playback, and the video is unaffected.
 *
 * Phase 4 was originally read as evidence that the Android UI is not composited
 * through this block.  That inference was wrong -- phase 4 simply was not
 * committed, so it never reached hardware.  It remains untested.
 */
typedef unsigned int u32;
typedef unsigned long usize;

#define PROT_READ  1
#define PROT_WRITE 2
#define MAP_SHARED 1
#define O_RDWR     2

#define AFBD_PAGE  0x05600000
#define SRC_CTRL   0x010
#define SRC_COMMIT 0x014
#define CH1_CTRL   0x100
#define CH2_CTRL   0x140
#define BIT31      0x80000000u

#define HOLD_SECONDS 6
#define SAMPLE_NS    20000000  /* 20 ms */
#define MAX_TARGETS  2

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

static void sleep_ns(long seconds, long nanoseconds)
{
	long spec[2];

	spec[0] = seconds;
	spec[1] = nanoseconds;
	syscall2(162, (long)spec, 0); /* nanosleep */
}

/*
 * -nostdlib means no __aeabi_uidivmod, so "value % 10" does not link. These
 * counts are in the hundreds, so repeated subtraction is cheaper than pulling
 * in libgcc for one call site.
 */
static u32 divide_by_ten(u32 value, u32 *remainder)
{
	u32 quotient = 0;

	while (value >= 10) {
		value -= 10;
		++quotient;
	}
	*remainder = value;
	return quotient;
}

static void output_decimal(u32 value)
{
	char digits[10];
	int n = 0;

	if (!value) {
		output("0", 1);
		return;
	}
	while (value) {
		u32 remainder;

		value = divide_by_ten(value, &remainder);
		digits[n++] = '0' + remainder;
	}
	while (n)
		output(&digits[--n], 1);
}

__attribute__((used, noinline)) int run(long *stack)
{
	static const char device[] = "/dev/hidtvreg";
	long argc = stack[0];
	const char *arg = argc > 1 ? (const char *)stack[2] : 0;
	volatile u32 *registers;
	u32 offset[MAX_TARGETS];
	u32 mask[MAX_TARGETS];
	u32 saved[MAX_TARGETS];
	u32 samples, held, first_revert, i;
	int targets = 0;
	int commit = 0;
	long result;
	int fd;

	if (!arg || arg[0] < '1' || arg[0] > '9' || arg[1]) {
		output_string("usage: hidtvreg-poke 1|2|3|4|5|6|7|8|9\n");
		return 2;
	}

	switch (arg[0]) {
	case '1':
		offset[0] = CH1_CTRL; mask[0] = BIT31; targets = 1;
		break;
	case '2':
		offset[0] = CH2_CTRL; mask[0] = BIT31; targets = 1;
		break;
	case '3':
		offset[0] = CH1_CTRL; mask[0] = BIT31;
		offset[1] = CH2_CTRL; mask[1] = BIT31; targets = 2;
		break;
	case '4':
		/* Channel enable. Intended as the positive control for 1-3;
		 * failed on the idle UI, which is what identified the UI as not
		 * being composited through this block. */
		offset[0] = CH1_CTRL; mask[0] = 1u; targets = 1;
		break;
	case '5':
		/* Source enable, bits 1:0 of 0x05600010, which the capture
		 * shows as 3 during playback. The real positive control for
		 * this block -- run it only while a clip is playing. */
		offset[0] = SRC_CTRL; mask[0] = 3u; targets = 1;
		break;
	case '6':
		/*
		 * Phase 5 with the commit latch pulsed afterwards. Phase 5 held
		 * the source enable at 0 for six seconds during verified-motion
		 * playback and the video was untouched, so the write reaches the
		 * register but not the hardware's behaviour. A shadow bank fits
		 * every observation: the write lands in shadow and reads back
		 * from shadow while the committed value keeps driving the panel.
		 * 0x05600014 is the documented latch for source 0 -- written 1,
		 * reads back 0. If pulsing it makes the video stop, that is the
		 * mechanism, and it explains why ARM-side register writes have
		 * never taken effect.
		 */
		offset[0] = SRC_CTRL; mask[0] = 3u; targets = 1;
		commit = 1;
		break;
	case '7':
		/* The original question, now asked properly. Phases 1-3 cleared
		 * bit 31 without committing, so they never reached hardware. */
		offset[0] = CH1_CTRL; mask[0] = BIT31; targets = 1;
		commit = 1;
		break;
	case '8':
		offset[0] = CH2_CTRL; mask[0] = BIT31; targets = 1;
		commit = 1;
		break;
	case '9':
		offset[0] = CH1_CTRL; mask[0] = BIT31;
		offset[1] = CH2_CTRL; mask[1] = BIT31; targets = 2;
		commit = 1;
		break;
	}

	fd = syscall3(5, (long)device, O_RDWR, 0); /* open */
	if (fd < 0) {
		output_string("ERROR open /dev/hidtvreg read-write\n");
		return 1;
	}

	result = syscall6(192, 0, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd,
			  AFBD_PAGE >> 12); /* mmap2, offset in pages */
	if ((unsigned long)result >= (unsigned long)-4095) {
		output_string("ERROR mmap AFBD read-write\n");
		return 1;
	}
	registers = (volatile u32 *)result;

	output_string("before\n");
	for (i = 0; i < (u32)targets; ++i) {
		saved[i] = registers[offset[i] / 4];
		output_register(AFBD_PAGE + offset[i], saved[i]);
	}

	for (i = 0; i < (u32)targets; ++i)
		registers[offset[i] / 4] = saved[i] & ~mask[i];

	if (commit) {
		for (i = 0; i < (u32)targets; ++i) {
			registers[(offset[i] + 4) / 4] = 1;
			output_string("commit latch pulsed; reads back ");
			output_register(AFBD_PAGE + offset[i] + 4,
					registers[(offset[i] + 4) / 4]);
		}
	}

	output_string("cleared, holding\n");
	for (i = 0; i < (u32)targets; ++i)
		output_register(AFBD_PAGE + offset[i],
				registers[offset[i] / 4]);

	/*
	 * Poll rather than just sleep. Confirming the write landed says nothing
	 * about whether it PERSISTED: if the firmware rewrites the register
	 * within a frame the bit is back before the panel could show anything,
	 * and "nothing changed" would mean only that the write was reverted.
	 */
	samples = HOLD_SECONDS * 50;
	held = 0;
	first_revert = samples;
	for (i = 0; i < samples; ++i) {
		int cleared = 1;
		u32 t;

		for (t = 0; t < (u32)targets; ++t)
			if (registers[offset[t] / 4] & mask[t])
				cleared = 0;
		if (cleared)
			++held;
		else if (first_revert == samples)
			first_revert = i;
		sleep_ns(0, SAMPLE_NS);
	}

	output_string("held cleared in ");
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
		registers[offset[i] / 4] = saved[i];
	if (commit)
		for (i = 0; i < (u32)targets; ++i)
			registers[(offset[i] + 4) / 4] = 1;

	output_string("restored\n");
	for (i = 0; i < (u32)targets; ++i)
		output_register(AFBD_PAGE + offset[i],
				registers[offset[i] / 4]);

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
