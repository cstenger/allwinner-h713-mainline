// SPDX-License-Identifier: GPL-2.0-only
/* Firmware-lifetime EDID/HPD owner. The proven SCP payload waits for an
 * explicit restore request; unlike the probe, ownership has no timer. */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/slab.h>
#include "edid-trial-code.h"
#ifndef EDID_CHECK_OFFSET
#error "regenerate edid-trial-code.h with make-edid-trial-code.py --verify-restore"
#endif

extern int h713_receiver_acquire(void);
extern void h713_receiver_release(void);
#define SRAM_BASE 0x00100000
#define SRAM_SIZE 0x5000
#define RESET_REG 0x07000400
#define SCP_PAGE_OFFSET 0x4000
#define PAGE_BYTES 0x1000
#define VECTOR_COUNT 14
#define TRAP_BASE 0x4c00
#define MARKER_OFFSET 0x4f00
#define MARKER 0x48444d49
/* HPD 1014, DDC 1b00/1b04/1b08, IO 1020/1030/1034/1038: originals at META,
 * the SCP's post-restore readback at CHECK, in the same order. */
#define RESTORED_REGS 8
static bool armed, ready, failed, restored, receiver_owned;
static void __iomem *sram, *reset;
static u8 *backup;
static u32 original, vectors[VECTOR_COUNT];
static DEFINE_MUTEX(signal_lock);
module_param(armed, bool, 0400);
module_param(ready, bool, 0444);
module_param(failed, bool, 0444);
module_param(restored, bool, 0444);

static void release_resources(void)
{
	iounmap(reset);iounmap(sram);
	reset = NULL;sram = NULL;
	release_mem_region(RESET_REG, 4);
	release_mem_region(SRAM_BASE, SRAM_SIZE);
	kfree(backup);backup = NULL;
	if (receiver_owned) {
		h713_receiver_release();receiver_owned = false;
	}
}

static int restore_sram(void)
{
	unsigned int i;

	writel(original & ~BIT(0), reset);
	if (readl(reset) != (original & ~BIT(0)))
		return -EIO;
	udelay(10);
	memcpy_toio(sram + SCP_PAGE_OFFSET, backup, PAGE_BYTES);
	for (i = 0; i < VECTOR_COUNT; i++)
		writel(vectors[i], sram + 0x100 * (i + 1));
	wmb();
	for (i = 0; i < PAGE_BYTES; i += 8)
		if (readq(sram + SCP_PAGE_OFFSET + i) != *(u64 *)(backup + i))
			return -EIO;
	for (i = 0; i < VECTOR_COUNT; i++)
		if (readl(sram + 0x100 * (i + 1)) != vectors[i])
			return -EIO;
	return 0;
}

/* The page restore erases the payload's evidence; log it first. Reads only
 * SCP SRAM, never receiver MMIO. */
static void report(const char *phase)
{
	u32 meta[RESTORED_REGS], check[RESTORED_REGS], active[11];
	unsigned int i;

	for (i = 0; i < RESTORED_REGS; i++) {
		meta[i] = readl(sram + EDID_META_OFFSET + 4 * i);
		check[i] = readl(sram + EDID_CHECK_OFFSET + 4 * i);
	}
	for (i = 0; i < ARRAY_SIZE(active); i++)
		active[i] = readl(sram + MARKER_OFFSET + 36 + 4 * (i < 7 ? i : i + 1));
	pr_info("h713-hdmi-signal: %s marker=%08x ready=%08x exception=%u error=%u done=%08x\n",
		phase, readl(sram + MARKER_OFFSET), readl(sram + MARKER_OFFSET + 8),
		readl(sram + MARKER_OFFSET + 12), readl(sram + MARKER_OFFSET + 24),
		readl(sram + MARKER_OFFSET + 28));
	pr_info("h713-hdmi-signal: %s original 1014=%08x 1b00=%08x 1b04=%08x 1b08=%08x 1020=%08x 1030=%08x 1034=%08x 1038=%08x\n",
		phase, meta[0], meta[1], meta[2], meta[3], meta[4], meta[5], meta[6], meta[7]);
	pr_info("h713-hdmi-signal: %s readback 1014=%08x 1b00=%08x 1b04=%08x 1b08=%08x 1020=%08x 1030=%08x 1034=%08x 1038=%08x\n",
		phase, check[0], check[1], check[2], check[3], check[4], check[5], check[6], check[7]);
	pr_info("h713-hdmi-signal: %s active 1014=%08x 1b00=%08x 1b04=%08x 1b08=%08x c00=%08x d00=%08x e00=%08x 1020=%08x 1030=%08x 1034=%08x 1038=%08x\n",
		phase, active[0], active[1], active[2], active[3], active[4], active[5],
		active[6], active[7], active[8], active[9], active[10]);
}

static int stop_signal(const char *value, const struct kernel_param *kp)
{
	bool stop;
	int i, ret = kstrtobool(value, &stop);

	if (ret || !stop)
		return -EINVAL;
	mutex_lock(&signal_lock);
	if (restored) {ret = 0;goto out;}
	if (!ready || failed) {ret = -EPERM;goto out;}
	failed = true; /* A failed restoration is terminal; retain every hold. */
	writel(1, sram + MARKER_OFFSET + 16);
	readl(sram + MARKER_OFFSET + 16);
	for (i = 0; i < 100; i++) {
		if (readl(sram + MARKER_OFFSET + 28) == MARKER)
			break;
		usleep_range(1000, 1500);
	}
	report("stop");
	ret = -EIO;
	if (i == 100 || readl(sram + MARKER_OFFSET + 24) ||
	    readl(sram + MARKER_OFFSET + 12))
		goto out;
	/* ARM must not read receiver MMIO; the SCP's readback is the proof. */
	for (i = 0; i < RESTORED_REGS; i++)
		if (readl(sram + EDID_CHECK_OFFSET + 4 * i) !=
		    readl(sram + EDID_META_OFFSET + 4 * i))
			goto out;
	ret = restore_sram();
	if (ret)
		goto out;
	ready = false;restored = true;failed = false;
	release_resources();
	pr_info("h713-hdmi-signal: peripheral readback, SRAM and vectors restored; SCP stopped; receiver client released\n");
	module_put(THIS_MODULE);
out:
	mutex_unlock(&signal_lock);
	return ret;
}
static const struct kernel_param_ops stop_ops = { .set = stop_signal };
module_param_cb(stop, &stop_ops, NULL, 0200);

static int __init signal_init(void)
{
	u32 trap[] = {0x18000000, 0xa8604f00, 0xa8e00000, 0xd403380c,
		0x00000000, 0x15000000, 0x15000000, 0x15000000};
	u8 readback[sizeof(edid_trial_data)];
	unsigned int i, j;
	int ret;

	if (!armed || !of_machine_is_compatible("allwinner,sun50i-h713"))
		return -EINVAL;
	ret = h713_receiver_acquire();
	if (ret)
		return ret;
	receiver_owned = true;
	backup = kmalloc(PAGE_BYTES, GFP_KERNEL);
	if (!backup) {ret = -ENOMEM;goto client;}
	if (!request_mem_region(SRAM_BASE, SRAM_SIZE, "h713-hdmi-signal")) {
		ret = -EBUSY;goto free;
	}
	if (!request_mem_region(RESET_REG, 4, "h713-hdmi-signal")) {
		ret = -EBUSY;goto region;
	}
	sram = ioremap(SRAM_BASE, SRAM_SIZE);reset = ioremap(RESET_REG, 4);
	if (!sram || !reset) {ret = -ENOMEM;goto resources;}
	original = readl(reset);
	if (original & BIT(0)) {ret = -EBUSY;goto resources;}
	memcpy_fromio(backup, sram + SCP_PAGE_OFFSET, PAGE_BYTES);
	for (i = 0; i < VECTOR_COUNT; i++)
		vectors[i] = readl(sram + 0x100 * (i + 1));
	for (i = 1; i < VECTOR_COUNT; i++) {
		u32 offset = TRAP_BASE + 0x20 * (i - 1);
		trap[2] = 0xa8e00000 | (i + 1);
		for (j = 0; j < ARRAY_SIZE(trap); j += 2) {
			u64 pair = (u64)trap[j + 1] << 32 | trap[j];
			writeq(pair, sram + offset + 4 * j);
			if (readq(sram + offset + 4 * j) != pair)
				goto before_launch_failed;
		}
		writel((offset - 0x100 * (i + 1)) / 4, sram + 0x100 * (i + 1));
	}
	for (i = 0; i < ARRAY_SIZE(edid_trial_code); i += 2)
		writeq((u64)edid_trial_code[i + 1] << 32 | edid_trial_code[i], sram + SCP_PAGE_OFFSET + 4 * i);
	writel((SCP_PAGE_OFFSET - 0x100) / 4, sram + 0x100);
	for (i = 0; i < 128; i += 8)
		writeq(0, sram + MARKER_OFFSET + i);
	/* Poison, not zero: zero is a legitimate original IO value. */
	for (i = 0; i < 4 * RESTORED_REGS; i += 8) {
		writeq(~0ULL, sram + EDID_CHECK_OFFSET + i);
		if (readq(sram + EDID_CHECK_OFFSET + i) != ~0ULL)
			goto before_launch_failed;
	}
	for (i = 0; i < sizeof(edid_trial_data); i += 8) {
		u64 word;
		memcpy(&word, edid_trial_data + i, 8);
		writeq(word, sram + EDID_PAYLOAD_OFFSET + i);
		word = readq(sram + EDID_PAYLOAD_OFFSET + i);
		memcpy(readback + i, &word, 8);
	}
	if (memcmp(readback, edid_trial_data, sizeof(readback)))
		goto before_launch_failed;
	writeq(1, sram + MARKER_OFFSET + 32);
	writeq(1, sram + MARKER_OFFSET + 64);
	wmb();
	for (i = 0; i < VECTOR_COUNT; i++) {
		u32 expected = i ? (TRAP_BASE + 0x20 * (i - 1) - 0x100 * (i + 1)) / 4 :
			(SCP_PAGE_OFFSET - 0x100) / 4;
		if (readl(sram + 0x100 * (i + 1)) != expected ||
		    readl(sram + 0x100 * (i + 1) + 4) != 0x15000000)
			goto before_launch_failed;
	}
	for (i = 0; i < ARRAY_SIZE(edid_trial_code); i += 2)
		if (readq(sram + SCP_PAGE_OFFSET + 4 * i) !=
		    ((u64)edid_trial_code[i + 1] << 32 | edid_trial_code[i]))
			goto before_launch_failed;
	/* From release onward, failures retain the module and every resource. */
	__module_get(THIS_MODULE);
	writel(original | BIT(0), reset);readl(reset);
	for (i = 0; i < 100; i++) {
		if (readl(sram + MARKER_OFFSET + 12))
			break;
		if (readl(sram + MARKER_OFFSET) == MARKER &&
		    readl(sram + MARKER_OFFSET + 8) == MARKER &&
		    !readl(sram + MARKER_OFFSET + 24)) {
			report("ready");
			mutex_lock(&signal_lock); /* stop is writable during init */
			ready = true;
			mutex_unlock(&signal_lock);
			pr_info("h713-hdmi-signal: EDID and HPD ready; explicit stop required, no timed expiry\n");
			return 0;
		}
		usleep_range(1000, 1500);
	}
	report("setup");
	mutex_lock(&signal_lock);
	failed = true;
	mutex_unlock(&signal_lock);
	pr_err("h713-hdmi-signal: setup failed; holds retained, physical cold boot required\n");
	return 0;
before_launch_failed:
	ret = restore_sram();
	if (ret) {
		failed = true;__module_get(THIS_MODULE);
		return 0; /* Partial SRAM restoration must not lose ownership. */
	}
	ret = -EIO;
resources:
	release_resources();return ret;
region:
	release_mem_region(SRAM_BASE, SRAM_SIZE);
free:
	kfree(backup);backup = NULL;
client:
	h713_receiver_release();receiver_owned = false;return ret;
}
static void __exit signal_exit(void) { WARN_ON(!restored); }
module_init(signal_init);
module_exit(signal_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 managed HDMI EDID/HPD firmware lifetime owner");
