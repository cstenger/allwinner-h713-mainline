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
/* init_failed: the payload never reported ready after SCP release. terminal:
 * an attempt to act on hardware began and did not finish; nothing more is
 * tried. recovery: which proven state an init failure was undone from. */
enum { RECOVERY_NONE, RECOVERY_LATE_READY, RECOVERY_SELF_RESTORED, RECOVERY_UNTOUCHED };
static bool init_failed, terminal;
static unsigned int recovery;
#ifdef H713_SIGNAL_FAULT_INJECTION
/* Bench builds only: 1 corrupts the EDID header after ARM verified it (the
 * payload takes data_failed), 2 makes the payload's first EDID verify load
 * the wrong word (mismatch, then its own full restore), 3 refuses just
 * before SCP release through the real pre-launch failure path, 4 stops the
 * ready poll at once so the payload becomes ready only after init failed. */
static unsigned int fault;
module_param(fault, uint, 0400);
#endif
static void __iomem *sram, *reset;
static u8 *backup;
static u32 original, vectors[VECTOR_COUNT];
static DEFINE_MUTEX(signal_lock);
module_param(armed, bool, 0400);
module_param(ready, bool, 0444);
module_param(failed, bool, 0444);
module_param(restored, bool, 0444);
module_param(recovery, uint, 0444);
MODULE_PARM_DESC(recovery, "Init failure undone from: 1 late ready, 2 payload self-restored, 3 receiver untouched");

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
	u32 stopped = readl(reset) & ~BIT(0);

	/* Only bit 0 (SCP run) is ours: never write back a stale snapshot. */
	if (stopped != (original & ~BIT(0)))
		pr_warn("h713-hdmi-signal: R_CPUCFG other bits changed since init (%08x -> %08x)\n",
			original, stopped);
	writel(stopped, reset);
	if (readl(reset) != stopped)
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

static u32 marker(unsigned int offset) { return readl(sram + MARKER_OFFSET + offset); }

/* ARM must not read receiver MMIO; the SCP's post-restore readback is the
 * proof, or (untouched) the readback area still holding the launch poison. */
static bool readback_matches(void)
{
	unsigned int i;

	for (i = 0; i < RESTORED_REGS; i++)
		if (readl(sram + EDID_CHECK_OFFSET + 4 * i) !=
		    readl(sram + EDID_META_OFFSET + 4 * i))
			return false;
	return true;
}

static bool readback_poisoned(void)
{
	unsigned int i;

	for (i = 0; i < RESTORED_REGS; i++)
		if (readl(sram + EDID_CHECK_OFFSET + 4 * i) != ~0U)
			return false;
	return true;
}

/* The payload, in its wait loop, restores the peripheral on request. */
static int cooperative_restore(void)
{
	int i;

	writel(1, sram + MARKER_OFFSET + 16);
	readl(sram + MARKER_OFFSET + 16);
	for (i = 0; i < 100; i++) {
		if (marker(28) == MARKER)
			break;
		usleep_range(1000, 1500);
	}
	report("stop");
	if (i == 100 || marker(24) || marker(12) || !readback_matches())
		return -EIO;
	return 0;
}

/* Which proven state a post-release init failure left, read only from the
 * payload's own SRAM words. Anything else is not undone. */
static unsigned int classify_init_failure(void)
{
	bool done = marker(28) == MARKER;

	if (marker(12) || marker(0) != MARKER)
		return RECOVERY_NONE; /* trap, or never ran its first store */
	if (marker(8) == MARKER && !marker(24) && !done)
		return RECOVERY_LATE_READY; /* in the wait loop after all */
	if (marker(24) == 1 && done && marker(8) != MARKER && readback_matches())
		return RECOVERY_SELF_RESTORED; /* EDID mismatch, then its own restore */
	if (marker(24) == 3 && done && marker(8) != MARKER && readback_poisoned())
		return RECOVERY_UNTOUCHED; /* header check failed before any receiver write */
	return RECOVERY_NONE;
}

static int stop_signal(const char *value, const struct kernel_param *kp)
{
	unsigned int from = RECOVERY_NONE;
	bool stop;
	int ret = kstrtobool(value, &stop);

	if (ret || !stop)
		return -EINVAL;
	mutex_lock(&signal_lock);
	if (restored) {ret = 0;goto out;}
	if (terminal || !sram) {ret = -EPERM;goto out;}
	if (failed) {
		if (!init_failed) {ret = -EPERM;goto out;}
		report("recover");
		from = classify_init_failure();
		if (from == RECOVERY_NONE) {ret = -EPERM;goto out;} /* nothing touched */
	} else if (!ready) {
		ret = -EPERM;goto out;
	}
	/* From here a failure is terminal; retain every hold. */
	failed = true;terminal = true;
	ret = -EIO;
	if ((from == RECOVERY_NONE || from == RECOVERY_LATE_READY) && cooperative_restore())
		goto out;
	ret = restore_sram(); /* stops the SCP first */
	if (ret)
		goto out;
	ready = false;restored = true;failed = false;terminal = false;recovery = from;
	release_resources();
	if (from == RECOVERY_NONE)
		pr_info("h713-hdmi-signal: peripheral readback, SRAM and vectors restored; SCP stopped; receiver client released\n");
	else
		pr_info("h713-hdmi-signal: init failure undone from proven state %u; SRAM and vectors restored; SCP stopped; receiver client released\n",
			from);
	module_put(THIS_MODULE);
out:
	mutex_unlock(&signal_lock);
	return ret;
}
static const struct kernel_param_ops stop_ops = { .set = stop_signal };
module_param_cb(stop, &stop_ops, NULL, 0200);

#ifdef EDID_EXT_OFFSET
static unsigned int readvertised;
module_param(readvertised, uint, 0444);
MODULE_PARM_DESC(readvertised, "Completed HPD re-advertise cycles");

/* One request through the stop word; the payload acks and clears it. */
static int scp_request(u32 request)
{
	int i;

	writel(0, sram + MARKER_OFFSET + EDID_ACK_OFFSET);
	writel(request, sram + MARKER_OFFSET + 16);
	readl(sram + MARKER_OFFSET + 16);
	for (i = 0; i < 100; i++) {
		if (!marker(16) && marker(EDID_ACK_OFFSET) == request)
			return 0;
		usleep_range(1000, 1500);
	}
	return -EIO;
}

#ifdef EDID_DDC_DIAGNOSTIC
static unsigned int ddc_cycles;
module_param(ddc_cycles, uint, 0444);
MODULE_PARM_DESC(ddc_cycles, "Diagnostic DDC-only reset cycles; no programmed HPD edge");

/* Bench-only isolation of the two actions in the proven fallback. The
 * caller must require signal none; no callback, RPC or ARM receiver read. */
static int cycle_ddc(const char *value, const struct kernel_param *kp)
{
	unsigned int hold_ms;
	u32 hpd, ddc;
	int ret = kstrtouint(value, 0, &hold_ms);

	if (ret || hold_ms != 2000)
		return -EINVAL;
	mutex_lock(&signal_lock);
	if (!ready || failed || restored || terminal || !sram || ddc_cycles || readvertised) {
		ret = -EPERM;
		goto out;
	}
	hpd = readl(sram + EDID_META_OFFSET) & ~7U;
	ddc = marker(44) & ~7U;
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_HPD_OFFSET);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	ret = scp_request(EDID_REQ_DDC_OFF);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_HPD_OFFSET) != hpd || marker(EDID_RELEASE_DDC_OFFSET) != ddc)
		goto failed_cycle;
	msleep(hold_ms);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_HPD_OFFSET);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	ret = scp_request(EDID_REQ_DDC_ON);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_HPD_OFFSET) != hpd || marker(EDID_RELEASE_DDC_OFFSET) != (ddc | 7U))
		goto failed_cycle;
	msleep(100);
	ddc_cycles++;
	pr_info("h713-hdmi-signal: diagnostic DDC-only cycle %u, HPD unchanged %08x, DDC %08x; SCP verified\n",
		ddc_cycles, hpd, marker(EDID_RELEASE_DDC_OFFSET));
	ret = 0;
	goto out;
failed_cycle:
	failed = true;
	terminal = true;
	ret = -EIO;
	pr_err("h713-hdmi-signal: diagnostic DDC-only cycle failed; holds retained\n");
out:
	mutex_unlock(&signal_lock);
	return ret;
}
static const struct kernel_param_ops ddc_cycle_ops = { .set = cycle_ddc };
module_param_cb(ddc_cycle, &ddc_cycle_ops, NULL, 0200);
#endif

#ifdef EDID_HPD_PULSE
static unsigned int hpd_pulses;
module_param(hpd_pulses, uint, 0444);
MODULE_PARM_DESC(hpd_pulses, "Completed HPD-only pulses (DDC never written)");

/* HDMI 1.4 8.5: a sink signals "re-read my EDID" with an HPD low pulse of at
 * least 100 ms. Force HPD low for the written milliseconds without touching
 * DDC, then release it, checking the SCP's HPD/DDC readbacks after each step.
 * Some sources (NVIDIA 615.78.08 after its own boot) ignore the first HPD
 * rise but connect on such a pulse. A failed step is terminal and keeps every
 * hold, like a failed re-advertise. */
static int pulse_hpd(const char *value, const struct kernel_param *kp)
{
	unsigned int low_ms;
	u32 hpd, ddc;
	int ret = kstrtouint(value, 0, &low_ms);

	if (ret || low_ms < 100 || low_ms > 2000)
		return -EINVAL;
	mutex_lock(&signal_lock);
	if (!ready || failed || restored || terminal || !sram) {
		ret = -EPERM;
		goto out;
	}
	hpd = readl(sram + EDID_META_OFFSET) & ~7U;
	ddc = marker(44);
	if ((ddc & 7U) != 7U) {
		ret = -EPERM;
		goto out;
	}
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_HPD_OFFSET);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	ret = scp_request(EDID_REQ_HPD_LOW);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_HPD_OFFSET) != (hpd | 7U) || marker(EDID_RELEASE_DDC_OFFSET) != ddc)
		goto failed_pulse;
	msleep(low_ms);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_HPD_OFFSET);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	ret = scp_request(EDID_REQ_RELEASE);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_HPD_OFFSET) != hpd || marker(EDID_RELEASE_DDC_OFFSET) != ddc)
		goto failed_pulse;
	hpd_pulses++;
	pr_info("h713-hdmi-signal: HPD pulsed low for %u ms, DDC unchanged %08x (%u)\n",
		low_ms, ddc, hpd_pulses);
	ret = 0;
	goto out;
failed_pulse:
	report("hpd pulse");
	failed = true;
	terminal = true;
	ret = -EIO;
	pr_err("h713-hdmi-signal: HPD pulse failed; holds retained, cold cycle required\n");
out:
	mutex_unlock(&signal_lock);
	return ret;
}
static const struct kernel_param_ops hpd_pulse_ops = { .set = pulse_hpd };
module_param_cb(hpd_pulse, &hpd_pulse_ops, NULL, 0200);
#endif

#ifdef EDID_HPD_DIAGNOSTIC
static unsigned int hpd_cycles;
module_param(hpd_cycles, uint, 0444);
MODULE_PARM_DESC(hpd_cycles, "Diagnostic HPD-only pulses; DDC never written");

/* Bench-only mirror of cycle_ddc: one HPD low pulse with DDC left enabled.
 * The caller must require signal none; no callback, RPC or ARM receiver read. */
static int cycle_hpd(const char *value, const struct kernel_param *kp)
{
	unsigned int hold_ms;
	u32 hpd, ddc;
	int ret = kstrtouint(value, 0, &hold_ms);

	if (ret || hold_ms != 2000)
		return -EINVAL;
	mutex_lock(&signal_lock);
	if (!ready || failed || restored || terminal || !sram || hpd_cycles || readvertised) {
		ret = -EPERM;
		goto out;
	}
	hpd = readl(sram + EDID_META_OFFSET) & ~7U;
	ddc = marker(44);
	if ((ddc & 7U) != 7U) {
		ret = -EPERM;
		goto out;
	}
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_HPD_OFFSET);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	ret = scp_request(EDID_REQ_HPD_LOW);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_HPD_OFFSET) != (hpd | 7U) || marker(EDID_RELEASE_DDC_OFFSET) != ddc)
		goto failed_cycle;
	msleep(hold_ms);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_HPD_OFFSET);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	ret = scp_request(EDID_REQ_RELEASE);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_HPD_OFFSET) != hpd || marker(EDID_RELEASE_DDC_OFFSET) != ddc)
		goto failed_cycle;
	hpd_cycles++;
	pr_info("h713-hdmi-signal: diagnostic HPD-only pulse %u after a %u ms hold, DDC unchanged %08x; SCP verified\n",
		hpd_cycles, hold_ms, ddc);
	ret = 0;
	goto out;
failed_cycle:
	failed = true;
	terminal = true;
	ret = -EIO;
	pr_err("h713-hdmi-signal: diagnostic HPD-only pulse failed; holds retained\n");
out:
	mutex_unlock(&signal_lock);
	return ret;
}
static const struct kernel_param_ops hpd_cycle_ops = { .set = cycle_hpd };
module_param_cb(hpd_cycle, &hpd_cycle_ops, NULL, 0200);
#endif

#ifdef EDID_INITIAL_HPD_DEFERRED
/* Initial setup already verified EDID and enabled DDC while holding HPD.
 * Match the proven retry's DDC settle interval before the first HPD rise.
 * No preliminary advertisement, pulse or readvertise count is hidden here. */
static int initial_advertise(void)
{
	int ret;

	if ((marker(36) & 7) != 7 || marker(44) == ~0U)
		return -EIO;
#ifdef EDID_INITIAL_DDC_HOLD_MS
	if (marker(44) & 7)
		return -EIO;
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	msleep(EDID_INITIAL_DDC_HOLD_MS);
	ret = scp_request(EDID_REQ_DDC_ON);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_DDC_OFFSET) != (marker(44) | 7U))
		return -EIO;
	pr_info("h713-hdmi-signal: initial DDC enabled after %u ms disabled hold; SCP readback verified\n",
		EDID_INITIAL_DDC_HOLD_MS);
#else
	if ((marker(44) & 7) != 7)
		return -EIO;
#endif
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_HPD_OFFSET);
	writel(~0U, sram + MARKER_OFFSET + EDID_RELEASE_DDC_OFFSET);
	msleep(100);
	ret = scp_request(EDID_REQ_RELEASE);
	if (ret || marker(12) || marker(24) ||
	    marker(EDID_RELEASE_HPD_OFFSET) != (readl(sram + EDID_META_OFFSET) & ~7U) ||
	    marker(EDID_RELEASE_DDC_OFFSET) != (marker(44) | 7U))
		return -EIO;
	pr_info("h713-hdmi-signal: first HPD release after 100 ms DDC settle; SCP readback verified\n");
	return 0;
}
#endif

/* Hold HPD low with DDC off for the written number of milliseconds, enable
 * DDC, then raise HPD once the EDID can be read: what a sink does to make a
 * source detect it again. */
static int readvertise_signal(const char *value, const struct kernel_param *kp)
{
	unsigned int hold_ms;
	int ret = kstrtouint(value, 0, &hold_ms);

	if (ret || hold_ms < 100 || hold_ms > 15000)
		return -EINVAL;
	mutex_lock(&signal_lock);
	if (!ready || failed || restored || terminal || !sram) {ret = -EPERM;goto out;}
	ret = scp_request(EDID_REQ_HOLD);
	if (!ret) {
		msleep(hold_ms);
		ret = scp_request(EDID_REQ_DDC_ON);
	}
	if (!ret) {
		msleep(100);
		ret = scp_request(EDID_REQ_RELEASE);
	}
	if (ret || marker(12) || marker(24)) {
		/* The payload left its wait loop or reported an error: terminal,
		 * like a failed stop, and every hold is retained. */
		report("readvertise");
		failed = true;terminal = true;ret = -EIO;
		pr_err("h713-hdmi-signal: re-advertise failed; holds retained, cold cycle required\n");
		goto out;
	}
	readvertised++;
	pr_info("h713-hdmi-signal: HPD re-advertised after a %u ms hold (%u)\n", hold_ms, readvertised);
out:
	mutex_unlock(&signal_lock);
	return ret;
}
static const struct kernel_param_ops readvertise_ops = { .set = readvertise_signal };
module_param_cb(readvertise, &readvertise_ops, NULL, 0200);
#endif

#ifdef EDID_SAMPLER_OFFSET
/* Read-only DDC/HPD sampler report: the SCP polls stock-accessed receiver
 * registers in its idle loop and keeps, per register, the value at owner ready
 * (first), the latest value and every bit that toggled since the last clear.
 * Reading copies SCP SRAM only; no receiver access from the ARM. */
static int sample_get(char *buf, const struct kernel_param *kp)
{
	int i, n;

	if (!sram || !ready)
		return sysfs_emit(buf, "unavailable\n");
	n = sysfs_emit(buf, "seq %u\n", readl(sram + EDID_SAMPLE_SEQ));
	for (i = 0; i < EDID_SAMPLE_COUNT; i++)
		n += sysfs_emit_at(buf, n, "%08x first %08x last %08x toggled %08x\n",
				   edid_sample_regs[i], readl(sram + EDID_SAMPLE_FIRST + 4 * i),
				   readl(sram + EDID_SAMPLE_PAIRS + 8 * i),
				   readl(sram + EDID_SAMPLE_PAIRS + 8 * i + 4));
	return n;
}
/* Writing 1 asks the sampler to restart its toggle masks; SRAM only. */
static int sample_clear(const char *value, const struct kernel_param *kp)
{
	bool yes;

	if (kstrtobool(value, &yes) || !yes)
		return -EINVAL;
	if (!sram || !ready || failed || restored)
		return -EPERM;
	writel(1, sram + EDID_SAMPLE_CLR);
	return 0;
}
static const struct kernel_param_ops sample_ops = { .get = sample_get, .set = sample_clear };
module_param_cb(ddc_sample, &sample_ops, NULL, 0600);
#endif

#ifdef EDID_SCAN_OFFSET
/* Read-only scan of the undocumented DDC block. The SCP idle loop reads the
 * 16 receiver offsets in its SRAM table; per entry it keeps the value on the
 * first pass after a window change (first), the latest value and every bit
 * that toggled since. Writing "<addr> [count]" points count (1..16) entries
 * at consecutive words from addr inside 0x07091b00-0x07091bfc and parks the
 * rest on the stock-read 0x07091b04; "off" parks all of them. Only SCP SRAM
 * is touched from the ARM: the receiver is read by the SCP alone. */
static u32 scan_start, scan_count;
#ifdef EDID_SCAN_BYTES
/* Byte variant: full SCP addresses read with l.lbz, limited to the byte-wide
 * MIPS HDCP/DDC wrapper; parked entries read the SCP's own SRAM marker. */
#define SCAN_LO 0x06840000
#define SCAN_HI 0x06840fff
#define SCAN_STEP 1
#define SCAN_ENTRY(a) (a)
#define SCAN_SHOW(v) (v)
#elif defined(EDID_SCAN_WORDS)
/* Word variant: full SCP addresses read with l.lwz, limited to the SCP-owned
 * receiver block below the EDID RAM; parked entries read SCP SRAM. */
#define SCAN_LO 0x07091000
#define SCAN_HI 0x07091bfc
#define SCAN_STEP 4
#define SCAN_ENTRY(a) (a)
#define SCAN_SHOW(v) (v)
#else
#undef EDID_SCAN_ACT
#undef EDID_SCAN_BUSY
#define SCAN_LO 0x07091b00
#define SCAN_HI 0x07091bfc
#define SCAN_STEP 4
#define SCAN_ENTRY(a) ((a) & 0xffff)
#define SCAN_SHOW(v) (0x07090000 | (v))
#endif
static int scan_get(char *buf, const struct kernel_param *kp)
{
	int i, n;

	if (!sram || !ready)
		return sysfs_emit(buf, "unavailable\n");
	n = sysfs_emit(buf, "window %08x count %u seq %u clear %u", scan_start, scan_count,
		       readl(sram + EDID_SCAN_SEQ), readl(sram + EDID_SCAN_CLR));
#ifdef EDID_SCAN_ACT
	/* act: seq+1 of the first pass with any toggle since the last clear; 0 = none. */
	n += sysfs_emit_at(buf, n, " act %u", readl(sram + EDID_SCAN_ACT));
#endif
#ifdef EDID_SCAN_BUSY
	/* last: seq+1 of the latest toggling pass; busy: toggling passes since clear. */
	n += sysfs_emit_at(buf, n, " last %u busy %u", readl(sram + EDID_SCAN_LASTACT),
			   readl(sram + EDID_SCAN_BUSY));
#endif
	n += sysfs_emit_at(buf, n, "\n");
	for (i = 0; i < EDID_SCAN_COUNT; i++)
		n += sysfs_emit_at(buf, n, "%08x first %08x last %08x toggled %08x\n",
				   SCAN_SHOW(readl(sram + EDID_SCAN_TABLE + 4 * i)),
				   readl(sram + EDID_SCAN_FIRST + 4 * i),
				   readl(sram + EDID_SCAN_LAST + 4 * i),
				   readl(sram + EDID_SCAN_MASK + 4 * i));
	return n;
}
static int scan_set(const char *value, const struct kernel_param *kp)
{
	u32 start = 0, count = 0;
	int i, ret = 0;

	if (sysfs_streq(value, "off")) {
		start = 0;
		count = 0;
	} else {
		i = sscanf(value, "%x %u", &start, &count);
		if (i == 1)
			count = EDID_SCAN_COUNT;
		if (i < 1 || start & (SCAN_STEP - 1) || count < 1 || count > EDID_SCAN_COUNT ||
		    start < SCAN_LO || start + SCAN_STEP * (count - 1) > SCAN_HI)
			return -EINVAL;
	}
	mutex_lock(&signal_lock);
	if (!sram || !ready || failed || restored) {
		ret = -EPERM;
		goto out;
	}
	for (i = 0; i < EDID_SCAN_COUNT; i++)
		writel(i < count ? SCAN_ENTRY(start + SCAN_STEP * i) : EDID_SCAN_IDLE,
		       sram + EDID_SCAN_TABLE + 4 * i);
	wmb();	/* the whole table lands before the SCP sees the clear */
	writel(1, sram + EDID_SCAN_CLR);
	scan_start = start;
	scan_count = count;
	pr_info("h713-hdmi-signal: DDC scan window %08x count %u\n", start, count);
out:
	mutex_unlock(&signal_lock);
	return ret;
}
static const struct kernel_param_ops scan_ops = { .get = scan_get, .set = scan_set };
static u32 scan_entry_at_init(int i)
{
#ifdef EDID_SCAN_ARM
	if (i < EDID_SCAN_ARM_COUNT)
		return EDID_SCAN_ARM + i;
#endif
	return EDID_SCAN_IDLE;
}
module_param_cb(ddc_scan, &scan_ops, NULL, 0600);
#endif

static int __init signal_init(void)
{
	u32 trap[] = {0x18000000, 0xa8604f00, 0xa8e00000, 0xd403380c,
		0x00000000, 0x15000000, 0x15000000, 0x15000000};
	u8 readback[sizeof(edid_trial_data)];
	unsigned int i, j, polls = 100;
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
#ifdef EDID_EXT_OFFSET
	for (i = 0; i < ARRAY_SIZE(edid_readvertise_code); i += 2)
		writeq((u64)edid_readvertise_code[i + 1] << 32 | edid_readvertise_code[i], sram + EDID_EXT_OFFSET + 4 * i);
#endif
#ifdef EDID_SAMPLER_OFFSET
	for (i = 0; i < ARRAY_SIZE(edid_sampler_code); i += 2)
		writeq((u64)edid_sampler_code[i + 1] << 32 | edid_sampler_code[i], sram + EDID_SAMPLER_OFFSET + 4 * i);
	/* seq 0 tells the sampler its first pass records the owner-ready values. */
	for (i = 0; i < 4 * EDID_SAMPLE_COUNT; i += 4)
		writel(0, sram + EDID_SAMPLE_FIRST + i);
	for (i = EDID_SAMPLE_SEQ; i < EDID_SAMPLE_PAIRS + 8 * EDID_SAMPLE_COUNT; i += 4)
		writel(0, sram + i);
#endif
#ifdef EDID_SCAN_OFFSET
	for (i = 0; i < ARRAY_SIZE(edid_scan_code); i += 2)
		writeq((u64)edid_scan_code[i + 1] << 32 | edid_scan_code[i], sram + EDID_SCAN_OFFSET + 4 * i);
	/* Parked (or, with EDID_SCAN_ARM, watching the DDC line byte from owner
	 * ready); clear 1 records first on pass 1. */
	for (i = 0; i < 4 * EDID_SCAN_COUNT; i += 4) {
		writel(scan_entry_at_init(i / 4), sram + EDID_SCAN_TABLE + i);
		writel(0, sram + EDID_SCAN_LAST + i);
		writel(0, sram + EDID_SCAN_MASK + i);
		writel(0, sram + EDID_SCAN_FIRST + i);
	}
	writel(0, sram + EDID_SCAN_SEQ);
	writel(1, sram + EDID_SCAN_CLR);
#ifdef EDID_SCAN_ACT
	writel(0, sram + EDID_SCAN_ACT);
#endif
#ifdef EDID_SCAN_BUSY
	writel(0, sram + EDID_SCAN_LASTACT);
	writel(0, sram + EDID_SCAN_BUSY);
#endif
#ifdef EDID_SCAN_ARM
	scan_start = EDID_SCAN_ARM;
	scan_count = EDID_SCAN_ARM_COUNT;
#endif
#endif
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
	/* Each vector is "j target; nop". Only the jump word is written; the
	 * delay-slot nop comes from the stock vector table, so require it. */
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
#ifdef EDID_EXT_OFFSET
	for (i = 0; i < ARRAY_SIZE(edid_readvertise_code); i += 2)
		if (readq(sram + EDID_EXT_OFFSET + 4 * i) !=
		    ((u64)edid_readvertise_code[i + 1] << 32 | edid_readvertise_code[i]))
			goto before_launch_failed;
#endif
#ifdef EDID_SAMPLER_OFFSET
	for (i = 0; i < ARRAY_SIZE(edid_sampler_code); i += 2)
		if (readq(sram + EDID_SAMPLER_OFFSET + 4 * i) !=
		    ((u64)edid_sampler_code[i + 1] << 32 | edid_sampler_code[i]))
			goto before_launch_failed;
	if (readl(sram + EDID_SAMPLE_SEQ))
		goto before_launch_failed;
#endif
#ifdef EDID_SCAN_OFFSET
	for (i = 0; i < ARRAY_SIZE(edid_scan_code); i += 2)
		if (readq(sram + EDID_SCAN_OFFSET + 4 * i) !=
		    ((u64)edid_scan_code[i + 1] << 32 | edid_scan_code[i]))
			goto before_launch_failed;
	for (i = 0; i < 4 * EDID_SCAN_COUNT; i += 4)
		if (readl(sram + EDID_SCAN_TABLE + i) != scan_entry_at_init(i / 4))
			goto before_launch_failed;
	if (readl(sram + EDID_SCAN_SEQ) || readl(sram + EDID_SCAN_CLR) != 1)
		goto before_launch_failed;
#endif
#ifdef H713_SIGNAL_FAULT_INJECTION
	if (fault == 1) {
		writeq(0, sram + EDID_PAYLOAD_OFFSET);
	} else if (fault == 2) {
		/* verify0's "lwz r8,0(r5)" is the word before the first "lwz r9,0(r6)" */
		for (i = 1; i < ARRAY_SIZE(edid_trial_code); i++)
			if (edid_trial_code[i] == 0x85260000)
				break;
		if (i < ARRAY_SIZE(edid_trial_code))
			writel(0x85050004, sram + SCP_PAGE_OFFSET + 4 * (i - 1));
		else
			fault = 0; /* pattern absent: inject nothing */
	}
	pr_warn("h713-hdmi-signal: BENCH BUILD, fault injection %u\n", fault);
	if (fault == 3)
		goto before_launch_failed;
	if (fault == 4)
		polls = 0;
#endif
	/* From release onward, failures retain the module and every resource
	 * unless stop=1 later proves the failure left a recoverable state. */
	__module_get(THIS_MODULE);
	writel(original | BIT(0), reset);readl(reset);
	for (i = 0; i < polls; i++) {
		if (readl(sram + MARKER_OFFSET + 12))
			break;
		if (readl(sram + MARKER_OFFSET) == MARKER &&
		    readl(sram + MARKER_OFFSET + 8) == MARKER &&
		    !readl(sram + MARKER_OFFSET + 24)) {
#ifdef EDID_INITIAL_HPD_DEFERRED
			ret = initial_advertise();
			if (ret) {
				mutex_lock(&signal_lock);
				terminal = true;
				mutex_unlock(&signal_lock);
				break;
			}
#endif
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
	failed = true;init_failed = true;
	mutex_unlock(&signal_lock);
	pr_err("h713-hdmi-signal: setup failed; holds retained until stop=1 proves a recoverable state\n");
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
#if defined(EDID_HPD_PULSE) && defined(EDID_SCAN_WORDS)
MODULE_VERSION("reg-scan-hpd-pulse-v1");
#elif defined(EDID_HPD_PULSE) && defined(EDID_SCAN_BUSY)
/* HPD pulse + the SCP DDC-line watch armed at owner ready (0x06840094..97):
 * the policy pulses on a failed-EDID-read signature. Same binary layout as the
 * ddc-activity-hpd-pulse-v2 diagnostic, now the event-driven candidate. */
MODULE_VERSION("hpd-event-v1");
#elif defined(EDID_HPD_PULSE) && defined(EDID_SCAN_ARM)
MODULE_VERSION("ddc-activity-hpd-pulse-v1");
#elif defined(EDID_HPD_PULSE) && defined(EDID_SCAN_BYTES)
MODULE_VERSION("byte-scan-hpd-pulse-v1");
#elif defined(EDID_HPD_PULSE) && defined(EDID_SCAN_OFFSET)
MODULE_VERSION("ddc-scan-hpd-pulse-v1");
#elif defined(EDID_HPD_PULSE)
MODULE_VERSION("hpd-pulse-v1");
#elif defined(EDID_SAMPLER_OFFSET) && defined(EDID_HPD_DIAGNOSTIC)
MODULE_VERSION("ddc-sampler-hpd-only-v1");
#elif defined(EDID_SAMPLER_OFFSET)
MODULE_VERSION("ddc-sampler-v1");
#elif defined(EDID_HPD_DIAGNOSTIC)
MODULE_VERSION("hpd-only-isolation-v1");
#elif defined(EDID_DDC_DIAGNOSTIC)
MODULE_VERSION("ddc-hpd-isolation-v1");
#elif defined(EDID_INITIAL_DDC_HOLD_MS)
MODULE_VERSION("first-advert-ddc-reset-v2");
#elif defined(EDID_INITIAL_HPD_DEFERRED)
MODULE_VERSION("first-advert-ddc-settle-v1");
#endif
