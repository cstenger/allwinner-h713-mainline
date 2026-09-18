// SPDX-License-Identifier: GPL-2.0-only
/* Bounded H713 SCP test with fixed read-only and reversible EDID trial modes. */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/slab.h>
#include "edid-trial-code.h"

#define SRAM_BASE 0x00100000
#define SRAM_SIZE 0x5000
#define A2_OFFSET 0x4000
#define PAGE_BYTES 0x1000
#define VECTOR_COUNT 14
#define TRAP_BASE 0x4c00
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
static bool edid_trial;
module_param(edid_trial, bool, 0400);
MODULE_PARM_DESC(edid_trial, "Ten-second EDID/HPD trial with saved peripheral restoration");
static bool stock_io;
module_param(stock_io, bool, 0400);
MODULE_PARM_DESC(stock_io, "Trial-only saved/restored stock HPD timing/control setup");
static bool edid_backup;
module_param(edid_backup, bool, 0400);
MODULE_PARM_DESC(edid_backup, "Read-only full EDID/configuration backup");
static bool peripheral_restored;
module_param(peripheral_restored, bool, 0400);
static uint edid_mismatch;
module_param(edid_mismatch, uint, 0400);
static uint pre_data[5];
module_param_array(pre_data, uint, NULL, 0400);
static uint active_io[4];
module_param_array(active_io, uint, NULL, 0400);
static uint active_config[7];
module_param_array(active_config, uint, NULL, 0400);
static uint original_edid[192];
module_param_array(original_edid, uint, NULL, 0400);
static uint original_config[4];
module_param_array(original_config, uint, NULL, 0400);
static bool edid_snapshot;
module_param(edid_snapshot, bool, 0400);
MODULE_PARM_DESC(edid_snapshot, "Read fixed DDC configuration and first EDID word per port via SCP");
static uint edid_values[11];
module_param_array(edid_values, uint, NULL, 0400);
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

/* Fixed non-destructive DDC register/EDID header snapshot. */
static const u32 edid_snapshot_code[] = {
	0x18000000,
	0xa8604f00,
	0x18804844,
	0xa8844d49,
	0xd4032000,
	0x18a00709,
	0xa8a51014,
	0x84c50000,
	0xd4033004,
	0x18a00709,
	0xa8a51b00,
	0x84c50000,
	0xd4033010,
	0x18a00709,
	0xa8a51b04,
	0x84c50000,
	0xd4033014,
	0x18a00709,
	0xa8a51b08,
	0x84c50000,
	0xd4033018,
	0x18a00709,
	0xa8a51c00,
	0x84c50000,
	0xd403301c,
	0x18a00709,
	0xa8a51d00,
	0x84c50000,
	0xd4033020,
	0x18a00709,
	0xa8a51e00,
	0x84c50000,
	0xd4033024,
	0x18a00709,
	0xa8a51018,
	0x84c50000,
	0xd4033028,
	0x18a00709,
	0xa8a51020,
	0x84c50000,
	0xd403302c,
	0x18a00709,
	0xa8a51030,
	0x84c50000,
	0xd4033030,
	0x18a00709,
	0xa8a51034,
	0x84c50000,
	0xd4033034,
	0x18a00709,
	0xa8a51038,
	0x84c50000,
	0xd4033038,
	0xd4032008,
	0x00000000,
	0x15000000,
};

static int __init h713_scp_probe_init(void)
{
	void __iomem *sram = NULL, *reset = NULL;
	u8 *backup;
	u32 original = 0, vectors[VECTOR_COUNT];
	bool reset_owned = false, saved = false;
	int i, ret = -EBUSY;
	const bool trial_program = edid_trial || edid_backup;
	const int code_offset = trial_program ? 0x4000 : CODE_OFFSET;
	u8 payload_readback[sizeof(edid_trial_data)];
	const u32 *code = trial_program ? edid_trial_code :
		edid_snapshot ? edid_snapshot_code :
		hpd_read ? hpd_code : heartbeat_code;
	int code_words = trial_program ? ARRAY_SIZE(edid_trial_code) :
		edid_snapshot ? ARRAY_SIZE(edid_snapshot_code) :
		hpd_read ? ARRAY_SIZE(hpd_code) : ARRAY_SIZE(heartbeat_code);
	u32 trap_code[8] = {
		0x18000000, 0xa8604f00, 0xa8e00000, 0xd403380c,
		0x00000000, 0x15000000, 0x15000000, 0x15000000,
	};
	int j;

	if (edid_snapshot || trial_program)
		hpd_read = true;
	if (stock_io && !edid_trial)
		return -EINVAL;
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
		u32 offset = TRAP_BASE + 0x20 * (i - 1);
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
		writeq((u64)code[i + 1] << 32 | code[i], sram + code_offset + 4 * i);
	writel((code_offset - 0x100) / 4, sram + 0x100);
	for (i = 0; i < 128; i += 8)
		writeq(0, sram + MARKER_OFFSET + i);
	if (trial_program) {
		for (i = 0; i < sizeof(edid_trial_data); i += 8) {
			u64 word;
			memcpy(&word, edid_trial_data + i, 8);
			writeq(word, sram + EDID_PAYLOAD_OFFSET + i);
			word = readq(sram + EDID_PAYLOAD_OFFSET + i);
			memcpy(payload_readback + i, &word, 8);
		}
		if (memcmp(payload_readback, edid_trial_data, sizeof(payload_readback))) {
			ret = -EIO;
			goto restore;
		}
		writeq(edid_trial ? 1 : 0, sram + MARKER_OFFSET + 32);
		writeq(stock_io ? 1 : 0, sram + MARKER_OFFSET + 64);
	}
	wmb();
	/* Validate all vectors and full instruction pairs before releasing reset. */
	for (i = 0; i < VECTOR_COUNT; i++) {
		u32 expected = i ? (TRAP_BASE + 0x20 * (i - 1) - 0x100 * (i + 1)) / 4 :
			(code_offset - 0x100) / 4;
		if (readl(sram + 0x100 * (i + 1)) != expected ||
		    readl(sram + 0x100 * (i + 1) + 4) != 0x15000000) {
			ret = -EIO;
			goto restore;
		}
	}
	for (i = 0; i < code_words; i += 2) {
		u64 expected = (u64)code[i + 1] << 32 | code[i];
		u64 actual = readq(sram + code_offset + 4 * i);
		if (actual != expected) {
			pr_err("h713-scp-probe: pair readback offset=%x expected=%016llx actual=%016llx\n",
				code_offset + 4 * i, expected, actual);
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
	if (edid_snapshot && completed)
		for (i = 0; i < ARRAY_SIZE(edid_values); i++)
			edid_values[i] = readl(sram + MARKER_OFFSET + 16 + 4 * i);
	if (trial_program) {
		for (i = 0; i < ARRAY_SIZE(pre_data); i++)
			pre_data[i] = readl(sram + MARKER_OFFSET + 84 + 4 * i);
		if (edid_trial)
			pr_info("h713-scp-probe: payload=%08x,%08x pre-enable EDID=%08x,%08x,%08x\n",
				pre_data[0], pre_data[1], pre_data[2], pre_data[3], pre_data[4]);
		if (readl(sram + MARKER_OFFSET + 20) == MARKER) {
			for (i = 0; i < ARRAY_SIZE(original_config); i++)
				original_config[i] = readl(sram + EDID_META_OFFSET + 4 * i);
			for (i = 0; i < ARRAY_SIZE(original_edid); i++)
				original_edid[i] = readl(sram + EDID_BACKUP_OFFSET + 4 * i);
		}
		if (edid_trial) {
			if (completed) {
				for (i = 0; i < ARRAY_SIZE(active_config); i++)
					active_config[i] = readl(sram + MARKER_OFFSET + 36 + 4 * i);
				pr_info("h713-scp-probe: active HPD=%08x b00=%08x b04=%08x b08=%08x headers=%08x,%08x,%08x\n",
					active_config[0], active_config[1], active_config[2], active_config[3],
					active_config[4], active_config[5], active_config[6]);
				for (i = 0; i < ARRAY_SIZE(active_io); i++)
					active_io[i] = readl(sram + MARKER_OFFSET + 68 + 4 * i);
				pr_info("h713-scp-probe: active IO 1020=%08x 1030=%08x 1034=%08x 1038=%08x\n",
					active_io[0], active_io[1], active_io[2], active_io[3]);
				pr_info("h713-scp-probe: EDID trial ready; holding HPD asserted for ten seconds\n");
				msleep(10000);
			}
			writel(1, sram + MARKER_OFFSET + 16);
			readl(sram + MARKER_OFFSET + 16);
			for (i = 0; i < 100; i++) {
				if (readl(sram + MARKER_OFFSET + 28) == MARKER)
					break;
				usleep_range(1000, 1500);
			}
		}
		peripheral_restored = readl(sram + MARKER_OFFSET + 28) == MARKER;
		edid_mismatch = readl(sram + MARKER_OFFSET + 24);
	}
	ret = exception ? -EIO : (marker == MARKER && completed) ? 0 : -ETIMEDOUT;
	if (trial_program && (!peripheral_restored || edid_mismatch))
		ret = -EIO;
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
	if (edid_snapshot && completed)
		pr_info("h713-scp-probe: DDC b00=%08x b04=%08x b08=%08x EDID c00=%08x d00=%08x e00=%08x\n",
			edid_values[0], edid_values[1], edid_values[2],
			edid_values[3], edid_values[4], edid_values[5]);
	if (edid_snapshot && completed)
		pr_info("h713-scp-probe: IO 1018=%08x 1020=%08x 1030=%08x 1034=%08x 1038=%08x\n",
			edid_values[6], edid_values[7], edid_values[8], edid_values[9], edid_values[10]);
	if (trial_program)
		pr_info("h713-scp-probe: edid_trial=%d peripheral_restored=%d mismatch=%u initial HPD=%08x b00=%08x b04=%08x b08=%08x\n",
			edid_trial, peripheral_restored, edid_mismatch, original_config[0],
			original_config[1], original_config[2], original_config[3]);
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
MODULE_DESCRIPTION("Bounded H713 SCP diagnostics and reversible EDID/HPD trial");
