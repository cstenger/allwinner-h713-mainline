// SPDX-License-Identifier: GPL-2.0-only
/* Bounded H713 SCP test; optional fixed SCP-side HPD read, no HPD writes. */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/slab.h>

#define SRAM_BASE 0x00100000
#define SRAM_SIZE 0x5000
#define A2_OFFSET 0x4000
#define PAGE_BYTES 0x1000
#define VECTOR_COUNT 14
#define RESET_REG 0x07000400
#define CODE_OFFSET 0x4100
#define MARKER_OFFSET 0x4f00
#define MARKER 0x48444d49

static bool run;
module_param(run, bool, 0400);
MODULE_PARM_DESC(run, "Explicitly run the bounded SCP test");
static bool hpd_read;
module_param(hpd_read, bool, 0400);
MODULE_PARM_DESC(hpd_read, "Also perform the fixed SCP-side HPD register read");
static uint exception;
module_param(exception, uint, 0400);
static uint hpd_value;
module_param(hpd_value, uint, 0400);
static bool completed;
module_param(completed, bool, 0400);
static uint marker;
module_param(marker, uint, 0400);
static bool restored;
module_param(restored, bool, 0400);

static const u32 heartbeat_code[] = {
	0x18000000, /* l.movhi r0, 0 */
	0xa8604f00, /* l.ori r3, r0, 0x4f00 */
	0x18804844, /* l.movhi r4, 0x4844 */
	0xa8844d49, /* l.ori r4, r4, 0x4d49 */
	0xd4032000, /* l.sw 0(r3), r4 */
	0x00000000, /* l.j self */
	0x15000000, /* delay slot: l.nop */
	0x15000000, /* pad to an eight-byte pair */
};

/* Fixed read-only HPD probe. ARM never accesses 0x07091014. */
static const u32 hpd_code[] = {
	0x18000000, /* l.movhi r0, 0 */
	0xa8604f00, /* l.ori r3, r0, 0x4f00 */
	0x18804844, /* l.movhi r4, 0x4844 */
	0xa8844d49, /* l.ori r4, r4, 0x4d49 */
	0xd4032000, /* l.sw 0(r3), r4: startup marker */
	0x18a00709, /* l.movhi r5, 0x0709 */
	0xa8a51014, /* l.ori r5, r5, 0x1014 */
	0x84c50000, /* l.lwz r6, 0(r5): HPD snapshot */
	0xd4033004, /* l.sw 4(r3), r6: snapshot to SRAM */
	0xd4032008, /* l.sw 8(r3), r4: completion marker */
	0x00000000, /* l.j self */
	0x15000000, /* delay slot: l.nop */
};

static int __init h713_scp_probe_init(void)
{
	void __iomem *sram = NULL, *reset = NULL;
	u8 *backup;
	u32 original = 0, vectors[VECTOR_COUNT];
	bool reset_owned = false, saved = false;
	int i, ret = -EBUSY;
	const u32 *code = hpd_read ? hpd_code : heartbeat_code;
	int code_words = hpd_read ? ARRAY_SIZE(hpd_code) : ARRAY_SIZE(heartbeat_code);
	u32 trap_code[8] = {
		0x18000000, 0xa8604f00, 0xa8e00000, 0xd403380c,
		0x00000000, 0x15000000, 0x15000000, 0x15000000,
	};
	int j;

	if (!run)
		return -EINVAL;
	if (!of_machine_is_compatible("allwinner,sun50i-h713"))
		return -ENODEV;
	backup = kmalloc(PAGE_BYTES, GFP_KERNEL);
	if (!backup)
		return -ENOMEM;
	if (!request_mem_region(SRAM_BASE, SRAM_SIZE, "h713-scp-probe"))
		goto free_backup;
	if (!request_mem_region(RESET_REG, 4, "h713-scp-probe"))
		goto release_sram;
	reset_owned = true;
	sram = ioremap(SRAM_BASE, SRAM_SIZE);
	reset = ioremap(RESET_REG, 4);
	if (!sram || !reset) {
		ret = -ENOMEM;
		goto cleanup;
	}
	original = readl(reset);
	if (original & BIT(0)) {
		pr_err("h713-scp-probe: SCP is already running; refusing\n");
		goto cleanup;
	}
	memcpy_fromio(backup, sram + A2_OFFSET, PAGE_BYTES);
	for (i = 0; i < VECTOR_COUNT; i++)
		vectors[i] = readl(sram + 0x100 * (i + 1));
	saved = true;
	/* The first region exposes sparse jump/NOP vector stubs, not code RAM. */
	for (i = 1; i < VECTOR_COUNT; i++) {
		u32 offset = 0x4200 + 0x20 * (i - 1);
		trap_code[2] = 0xa8e00000 | (i + 1); /* l.ori r7,r0,vector */
		for (j = 0; j < ARRAY_SIZE(trap_code); j += 2)
			writeq((u64)trap_code[j + 1] << 32 | trap_code[j], sram + offset + 4 * j);
		for (j = 0; j < ARRAY_SIZE(trap_code); j += 2)
			if (readq(sram + offset + 4 * j) !=
			    ((u64)trap_code[j + 1] << 32 | trap_code[j])) {
				ret = -EIO;
				goto restore;
			}
		writel((offset - 0x100 * (i + 1)) / 4, sram + 0x100 * (i + 1));
	}
	for (i = 0; i < code_words; i += 2)
		writeq((u64)code[i + 1] << 32 | code[i], sram + CODE_OFFSET + 4 * i);
	writel((CODE_OFFSET - 0x100) / 4, sram + 0x100);
	writeq(0, sram + MARKER_OFFSET);
	writeq(0, sram + MARKER_OFFSET + 8);
	wmb();
	/* Validate all vectors and full instruction pairs before releasing reset. */
	for (i = 0; i < VECTOR_COUNT; i++) {
		u32 expected = i ? (0x4200 + 0x20 * (i - 1) - 0x100 * (i + 1)) / 4 :
			(CODE_OFFSET - 0x100) / 4;
		if (readl(sram + 0x100 * (i + 1)) != expected ||
		    readl(sram + 0x100 * (i + 1) + 4) != 0x15000000) {
			ret = -EIO;
			goto restore;
		}
	}
	for (i = 0; i < code_words; i += 2) {
		u64 expected = (u64)code[i + 1] << 32 | code[i];
		u64 actual = readq(sram + CODE_OFFSET + 4 * i);
		if (actual != expected) {
			pr_err("h713-scp-probe: pair readback offset=%x expected=%016llx actual=%016llx\n",
				CODE_OFFSET + 4 * i, expected, actual);
			ret = -EIO;
			goto restore;
		}
	}
	writel(original | BIT(0), reset);
	readl(reset);
	for (i = 0; i < 100; i++) {
		marker = readl(sram + MARKER_OFFSET);
		exception = readl(sram + MARKER_OFFSET + 12);
		if (exception)
			break;
		completed = marker == MARKER &&
			(!hpd_read || readl(sram + MARKER_OFFSET + 8) == MARKER);
		if (marker && completed)
			break;
		usleep_range(1000, 1500);
	}
	if (hpd_read && completed)
		hpd_value = readl(sram + MARKER_OFFSET + 4);
	ret = exception ? -EIO : (marker == MARKER && completed) ? 0 : -ETIMEDOUT;
restore:
	/* Stop the core before restoring its vectors/data, including on failure. */
	writel(original & ~BIT(0), reset);
	readl(reset);
	udelay(10);
	memcpy_toio(sram + A2_OFFSET, backup, PAGE_BYTES);
	for (i = 0; i < VECTOR_COUNT; i++)
		writel(vectors[i], sram + 0x100 * (i + 1));
	wmb();
	restored = true;
	for (i = 0; i < PAGE_BYTES; i += 8)
		if (readq(sram + A2_OFFSET + i) != *(u64 *)(backup + i)) {
			restored = false;
			ret = -EIO;
			break;
		}
	for (i = 0; i < VECTOR_COUNT; i++)
		if (readl(sram + 0x100 * (i + 1)) != vectors[i]) {
			restored = false;
			ret = -EIO;
		}
	pr_info("h713-scp-probe: hpd_read=%d marker=%08x completed=%d hpd=%08x exception=%u restored=%d reset=%08x result=%d\n",
		hpd_read, marker, completed, hpd_value, exception, restored, readl(reset), ret);
cleanup:
	/* A saved page always goes through restore before reaching cleanup. */
	WARN_ON(saved && !restored);
	if (reset)
		iounmap(reset);
	if (sram)
		iounmap(sram);
	if (reset_owned)
		release_mem_region(RESET_REG, 4);
release_sram:
	release_mem_region(SRAM_BASE, SRAM_SIZE);
free_backup:
	kfree(backup);
	return ret;
}

static void __exit h713_scp_probe_exit(void) {}
module_init(h713_scp_probe_init);
module_exit(h713_scp_probe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded H713 SCP execution and optional read-only HPD probe");
