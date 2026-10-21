// SPDX-License-Identifier: GPL-2.0-only
/* Cold logo-free staged access audit. Init performs software/DT checks only.
 * Each sysfs step performs ONE named operation.
 *
 * Steps 1-33 (prefix): no hardware writes, domain attachment/resume, clock
 * enables or reset changes. Steps 34-40 add read-only census samples.
 * Steps 41-82 (extension, boot-v4 DT only) power the TVFE/TVCAP domains,
 * enable clocks, release resets and write the stock TVFE CCU words, one
 * operation per step with hardware read-back. Nothing maps or reads
 * AudioTop, the DSP port or the lock window.
 *
 * Error retains the module pin and acquired resources until cold poweroff.
 * After the first state-changing step there is no software restore: the
 * only supported end is an orderly poweroff with the module loaded.
 */
#include <dt-bindings/clock/sun50i-h713-ccu.h>
#include <linux/clk-provider.h>
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/pm_domain.h>
#include <linux/pm_runtime.h>
#include <linux/reset.h>

static bool armed, failed, released, prefix_complete, pinned, initialized;
static bool extension_available, extension_complete;
static unsigned int completed, attempted, last_value;
module_param(armed, bool, 0400);
module_param(failed, bool, 0444);
module_param(released, bool, 0444);
module_param(prefix_complete, bool, 0444);
module_param(extension_available, bool, 0444);
module_param(extension_complete, bool, 0444);
module_param(completed, uint, 0444);
module_param(attempted, uint, 0444);
module_param(last_value, uint, 0444);
static DEFINE_MUTEX(audit_lock);
static struct device_node *ccu, *tvtop, *ppu;
static struct reset_control *display_reset, *demod, *tvcap_reset;
static struct clk *clocks[17];
static unsigned int clocks_acquired, regions_acquired;
static void __iomem *maps[4], *ppu_status[2];
static const struct {
	resource_size_t base, size;
} regions[] = {
	{0x06144000, 0x1c}, {0x05001530, 8},
	{0x0614a000, 0x10}, {0x07000400, 4},
}, windows[] = {
	{0x0306101c, 4}, {0x07000400, 4},
	{0x02001d10, 0x58}, {0x02001dd8, 4},
};
/* PPU status words for hw domains 1 (TVFE) and 2 (TVCAP): PMU + 0x24 + d*0x80. */
static const resource_size_t ppu_status_addr[] = { 0x070010a4, 0x07001124 };
#define PPU_STATE_MASK GENMASK(17, 16)
#define PPU_STATE_ON BIT(16)
static const unsigned int clock_ids[] = {
	CLK_PLL_VIDEO0, CLK_PLL_ADC,	CLK_BUS_TVCAP,	    CLK_BUS_CAP_300M,
	CLK_VINCAP_DMA, CLK_TVFE_1296M, CLK_BUS_HDMI_AUDIO, CLK_HDMI_AUDIO,
	CLK_AUDIO_CPU,	CLK_AUDIO_UMAC, CLK_AUDIO_IHB,	    CLK_PLL_VIDEO2,
	CLK_DEINT,	CLK_PANEL,	CLK_SVP_DTL,	    CLK_AFBD,
	CLK_BUS_DISP,
};
static_assert(ARRAY_SIZE(clock_ids) == ARRAY_SIZE(clocks));
/* Stock TVFE CCU words, from the old bench (offsets from 0x02001d10). */
static const u16 tv_offsets[] = {
	0x00, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28,
	0x30, 0x38, 0x3c, 0x40, 0x48, 0x4c, 0x50,
};
static const u32 tv_stock[] = {
	0x80000017, 0x80000000, 0x81000005, 0x80000002, 0x80000005, 0x80000003,
	0x80000003, 0x8000000b, 0x80000117, 0x80000002, 0x80000002, 0x81000002,
	0x80000002, 0x8000020b, 0x8000020b,
};
static_assert(ARRAY_SIZE(tv_offsets) == ARRAY_SIZE(tv_stock));
static unsigned int tv_words[ARRAY_SIZE(tv_offsets)];
static unsigned int tv_words_count = ARRAY_SIZE(tv_offsets);
module_param_array(tv_words, uint, &tv_words_count, 0444);
static unsigned int tvcap_reset_before = ~0U;
module_param(tvcap_reset_before, uint, 0444);
static int display_reset_before = -1;
static struct device *domains[2];
static unsigned int attached;
static const char *const domain_names[] = { "h713-dsp-access-tvfe",
					    "h713-dsp-access-tvcap" };

enum action {
	CLAIM,
	MAP,
	READ_MIPS,
	READ_SCP,
	READ_DEMOD_BUS,
	READ_DISP_BUS,
	GET_DISP_RESET,
	READ_DISP_RESET,
	GET_DEMOD_RESET,
	READ_DEMOD_RESET,
	GET_CLOCK,
	/* Census (read-only). */
	MAP_PPU,
	READ_PPU,
	GET_TVCAP_RESET,
	READ_TVCAP_RESET,
	CLOCK_CENSUS,
	READ_TV_WORDS,
	/* Extension (state-changing). */
	ATTACH_DOMAIN,
	RESUME_DOMAIN,
	RECHECK_STOPPED,
	DEASSERT_TVCAP_RESET,
	ENABLE_CLOCK,
	DEASSERT_DEMOD_RESET,
	WRITE_TV_WORD,
	SET_DEMOD_BUS_GATE,
	DEASSERT_DISP_RESET,
	FINAL_RECHECK,
};
struct audit_step {
	enum action action;
	unsigned int arg;
	const char *name;
};
#define CLOCK_STEP(i, name) { GET_CLOCK, i, "get-clock-" name }
#define ENABLE_STEP(i, name) { ENABLE_CLOCK, i, "enable-clock-" name }
#define TV_WORD_STEP(i, off) { WRITE_TV_WORD, i, "write-tv-word-" off }
static const struct audit_step steps[] = {
	{ CLAIM, 0, "claim-dsp-port" },
	{ CLAIM, 1, "claim-lock-window" },
	{ CLAIM, 2, "claim-audiotop" },
	{ CLAIM, 3, "claim-scp-reset" },
	{ MAP, 0, "map-mips-status" },
	{ MAP, 1, "map-scp-reset" },
	{ MAP, 2, "map-tv-ccu" },
	{ MAP, 3, "map-display-ccu" },
	{ READ_MIPS, 0, "read-mips-stopped" },
	{ READ_SCP, 0, "read-scp-stopped" },
	{ READ_DEMOD_BUS, 0, "read-demod-bus" },
	{ READ_DISP_BUS, 0, "read-display-bus" },
	{ GET_DISP_RESET, 0, "get-display-reset" },
	{ READ_DISP_RESET, 0, "read-display-reset" },
	{ GET_DEMOD_RESET, 0, "get-demod-reset" },
	{ READ_DEMOD_RESET, 0, "read-demod-reset" },
	CLOCK_STEP(0, "pll-video0"),
	CLOCK_STEP(1, "pll-adc"),
	CLOCK_STEP(2, "bus-tvcap"),
	CLOCK_STEP(3, "bus-cap-300m"),
	CLOCK_STEP(4, "vincap-dma"),
	CLOCK_STEP(5, "tvfe-1296m"),
	CLOCK_STEP(6, "bus-hdmi-audio"),
	CLOCK_STEP(7, "hdmi-audio"),
	CLOCK_STEP(8, "audio-cpu"),
	CLOCK_STEP(9, "audio-umac"),
	CLOCK_STEP(10, "audio-ihb"),
	CLOCK_STEP(11, "pll-video2"),
	CLOCK_STEP(12, "deint"),
	CLOCK_STEP(13, "panel"),
	CLOCK_STEP(14, "svp-dtl"),
	CLOCK_STEP(15, "afbd"),
	CLOCK_STEP(16, "bus-disp"),
	/* 34-40: census, read-only. Release is still allowed through 40. */
	{ MAP_PPU, 0, "map-ppu-status" },
	{ READ_PPU, 0, "read-ppu-tvfe-status" },
	{ READ_PPU, 1, "read-ppu-tvcap-status" },
	{ GET_TVCAP_RESET, 0, "get-tvcap-reset" },
	{ READ_TVCAP_RESET, 0, "read-tvcap-reset" },
	{ CLOCK_CENSUS, 0, "census-clock-enabled" },
	{ READ_TV_WORDS, 0, "read-tv-ccu-words" },
	/* 41-45: power domains, TVFE then TVCAP (0087 and 09-18 order). */
	{ ATTACH_DOMAIN, 0, "attach-tvfe" },
	{ RESUME_DOMAIN, 0, "resume-tvfe" },
	{ ATTACH_DOMAIN, 1, "attach-tvcap" },
	{ RESUME_DOMAIN, 1, "resume-tvcap" },
	{ RECHECK_STOPPED, 0, "recheck-stopped-after-power" },
	/* 46-53: TV resets and receiver clocks. */
	{ DEASSERT_TVCAP_RESET, 0, "deassert-tvcap-reset-if-asserted" },
	ENABLE_STEP(2, "bus-tvcap"),
	ENABLE_STEP(3, "bus-cap-300m"),
	ENABLE_STEP(4, "vincap-dma"),
	ENABLE_STEP(5, "tvfe-1296m"),
	{ DEASSERT_DEMOD_RESET, 0, "deassert-demod-reset" },
	ENABLE_STEP(0, "pll-video0"),
	ENABLE_STEP(1, "pll-adc"),
	/* 54-69: raw stock TVFE words, then the demod bus gate. */
	TV_WORD_STEP(0, "d10"),
	TV_WORD_STEP(1, "d20"),
	TV_WORD_STEP(2, "d24"),
	TV_WORD_STEP(3, "d28"),
	TV_WORD_STEP(4, "d2c"),
	TV_WORD_STEP(5, "d30"),
	TV_WORD_STEP(6, "d34"),
	TV_WORD_STEP(7, "d38"),
	TV_WORD_STEP(8, "d40"),
	TV_WORD_STEP(9, "d48"),
	TV_WORD_STEP(10, "d4c"),
	TV_WORD_STEP(11, "d50"),
	TV_WORD_STEP(12, "d58"),
	TV_WORD_STEP(13, "d5c"),
	TV_WORD_STEP(14, "d60"),
	{ SET_DEMOD_BUS_GATE, 0, "set-demod-bus-gate" },
	/* 70-74: audio clocks. */
	ENABLE_STEP(6, "bus-hdmi-audio"),
	ENABLE_STEP(7, "hdmi-audio"),
	ENABLE_STEP(8, "audio-cpu"),
	ENABLE_STEP(9, "audio-umac"),
	ENABLE_STEP(10, "audio-ihb"),
	/* 75-81: display tree, last (only the later lock stage needs it). */
	ENABLE_STEP(11, "pll-video2"),
	ENABLE_STEP(12, "deint"),
	ENABLE_STEP(13, "panel"),
	ENABLE_STEP(14, "svp-dtl"),
	ENABLE_STEP(15, "afbd"),
	ENABLE_STEP(16, "bus-disp"),
	{ DEASSERT_DISP_RESET, 0, "deassert-display-reset-if-asserted" },
	/* 82: final read-only recheck. */
	{ FINAL_RECHECK, 0, "final-recheck" },
};
#undef CLOCK_STEP
#undef ENABLE_STEP
#undef TV_WORD_STEP
#define PREFIX_STEPS 33
#define LAST_READ_ONLY_STEP 40
static_assert(ARRAY_SIZE(steps) == 82);
static_assert(ARRAY_SIZE(tv_offsets) == 15);

static int next_operation_get(char *buffer, const struct kernel_param *kp)
{
	const char *name = "extension-end";

	if (failed)
		name = "failed";
	else if (released)
		name = "released";
	else if (completed == PREFIX_STEPS && !extension_available)
		name = "prefix-end";
	else if (completed < ARRAY_SIZE(steps))
		name = steps[completed].name;
	return scnprintf(buffer, PAGE_SIZE, "%s\n", name);
}
static const struct kernel_param_ops next_ops = { .get = next_operation_get };
module_param_cb(next_operation, &next_ops, NULL, 0444);

static void op_done(unsigned int step)
{
	pr_notice("h713-dsp-access-audit: OP-DONE step=%u\n", step);
}

static int stopped(void)
{
	return readl(maps[0]) == 0 && !(readl(maps[1]) & BIT(0)) ? 0 : -EBUSY;
}

static int domain_event(struct notifier_block *nb, unsigned long event,
			void *data);
static struct notifier_block domain_notifiers[2] = {
	{ .notifier_call = domain_event },
	{ .notifier_call = domain_event },
};
static bool notified[2];
static int domain_event(struct notifier_block *nb, unsigned long event,
			void *data)
{
	pr_notice("h713-dsp-access-audit: domain %td genpd event %lu\n",
		  nb - domain_notifiers, event);
	return NOTIFY_OK;
}

static int execute_step(const struct audit_step *s, unsigned int step)
{
	struct of_phandle_args spec = { .np = ccu, .args_count = 1 };
	struct clk *clk;
	struct reset_control *reset;
	unsigned int i;
	u32 value;
	int ret;

	last_value = 0; /* Only steps with a hardware sample set it. */
	switch (s->action) {
	case CLAIM:
		if (!request_mem_region(regions[s->arg].base,
					regions[s->arg].size,
					"h713-dsp-access-audit"))
			return -EBUSY;
		regions_acquired++;
		return 0;
	case MAP:
		maps[s->arg] =
			ioremap(windows[s->arg].base, windows[s->arg].size);
		return maps[s->arg] ? 0 : -ENOMEM;
	case READ_MIPS:
		last_value = readl(maps[0]);
		return last_value == 0 ? 0 : -EBUSY;
	case READ_SCP:
		last_value = readl(maps[1]);
		return !(last_value & BIT(0)) ? 0 : -EBUSY;
	case READ_DEMOD_BUS:
		last_value = readl(maps[2] + 0x54);
		return !(last_value & (BIT(16) | BIT(0))) ? 0 : -EBUSY;
	case READ_DISP_BUS:
		last_value = readl(maps[3]);
		return 0;
	case GET_DISP_RESET:
	case GET_DEMOD_RESET:
		reset = of_reset_control_get_exclusive(
			tvtop, s->action == GET_DISP_RESET ? "reset_bus_disp" :
							     "reset_bus_demod");
		if (IS_ERR_OR_NULL(reset))
			return reset ? PTR_ERR(reset) : -ENODEV;
		if (s->action == GET_DISP_RESET)
			display_reset = reset;
		else
			demod = reset;
		return 0;
	case READ_DISP_RESET:
	case READ_DEMOD_RESET:
		ret = reset_control_status(
			s->action == READ_DISP_RESET ? display_reset : demod);
		if (ret < 0)
			return ret;
		last_value = ret;
		if (s->action == READ_DISP_RESET)
			display_reset_before = ret;
		return (s->action == READ_DISP_RESET ? ret == 0 || ret == 1 :
						       ret == 1) ?
			       0 :
			       -EBUSY;
	case GET_CLOCK:
		spec.args[0] = clock_ids[s->arg];
		clk = of_clk_get_from_provider(&spec);
		if (IS_ERR_OR_NULL(clk))
			return clk ? PTR_ERR(clk) : -ENODEV;
		clocks[clocks_acquired++] = clk;
		return 0;
	case MAP_PPU:
		/* The R_CCU owns this range; map without claiming, as the PPU driver does. */
		for (i = 0; i < ARRAY_SIZE(ppu_status); i++) {
			ppu_status[i] = ioremap(ppu_status_addr[i], 4);
			if (!ppu_status[i])
				return -ENOMEM;
		}
		return 0;
	case READ_PPU:
		last_value = readl(ppu_status[s->arg]);
		return 0;
	case GET_TVCAP_RESET:
		reset = of_reset_control_get_exclusive(tvtop, "reset_bus_tvcap");
		if (IS_ERR_OR_NULL(reset))
			return reset ? PTR_ERR(reset) : -ENODEV;
		tvcap_reset = reset;
		return 0;
	case READ_TVCAP_RESET:
		ret = reset_control_status(tvcap_reset);
		if (ret < 0)
			return ret;
		last_value = tvcap_reset_before = ret;
		return ret == 0 || ret == 1 ? 0 : -EIO;
	case CLOCK_CENSUS:
		for (i = 0; i < ARRAY_SIZE(clocks); i++)
			if (__clk_is_enabled(clocks[i]))
				last_value |= BIT(i);
		return 0;
	case READ_TV_WORDS:
		for (i = 0; i < ARRAY_SIZE(tv_offsets); i++)
			tv_words[i] = readl(maps[2] + tv_offsets[i]);
		return 0;
	case ATTACH_DOMAIN:
		domains[s->arg] = root_device_register(domain_names[s->arg]);
		if (IS_ERR(domains[s->arg])) {
			ret = PTR_ERR(domains[s->arg]);
			domains[s->arg] = NULL;
			return ret;
		}
		spec.np = ppu;
		spec.args[0] = s->arg + 1; /* Provider index 1 = TVFE, 2 = TVCAP. */
		ret = of_genpd_add_device(&spec, domains[s->arg]);
		if (ret)
			return ret; /* Device stays registered; retained until cold poweroff. */
		attached++;
		ret = dev_pm_genpd_add_notifier(domains[s->arg],
						&domain_notifiers[s->arg]);
		if (ret)
			return ret;
		notified[s->arg] = true;
		return 0;
	case RESUME_DOMAIN:
		pm_runtime_enable(domains[s->arg]);
		ret = pm_runtime_resume_and_get(domains[s->arg]);
		if (ret < 0)
			return ret;
		op_done(step);
		last_value = readl(ppu_status[s->arg]);
		return (last_value & PPU_STATE_MASK) == PPU_STATE_ON ? 0 : -EIO;
	case RECHECK_STOPPED:
		return stopped();
	case DEASSERT_TVCAP_RESET:
		if (tvcap_reset_before == 0) {
			last_value = 0; /* Already released at census: recorded no-op. */
			return 0;
		}
		ret = reset_control_deassert(tvcap_reset);
		if (ret)
			return ret;
		op_done(step);
		last_value = 1;
		return reset_control_status(tvcap_reset) == 0 ? 0 : -EIO;
	case ENABLE_CLOCK:
		if (__clk_is_enabled(clocks[s->arg])) {
			last_value = 1; /* Inherited on; no reference taken, as the old bench. */
			return 0;
		}
		ret = clk_prepare_enable(clocks[s->arg]);
		if (ret)
			return ret;
		if (s->arg == 11)
			usleep_range(12000, 15000); /* pll-video2 settle, as the old bench. */
		op_done(step);
		return __clk_is_enabled(clocks[s->arg]) ? 0 : -EIO;
	case DEASSERT_DEMOD_RESET:
		ret = reset_control_deassert(demod);
		if (ret)
			return ret;
		usleep_range(10000, 15000);
		op_done(step);
		return reset_control_status(demod) == 0 ? 0 : -EIO;
	case WRITE_TV_WORD:
		writel(tv_stock[s->arg], maps[2] + tv_offsets[s->arg]);
		op_done(step);
		last_value = readl(maps[2] + tv_offsets[s->arg]);
		return last_value == tv_stock[s->arg] ? 0 : -EIO;
	case SET_DEMOD_BUS_GATE:
		writel(readl(maps[2] + 0x54) | BIT(0), maps[2] + 0x54);
		usleep_range(10000, 15000);
		op_done(step);
		last_value = readl(maps[2] + 0x54);
		return (last_value & (BIT(16) | BIT(0))) == (BIT(16) | BIT(0)) ?
			       0 :
			       -EIO;
	case DEASSERT_DISP_RESET:
		if (display_reset_before != 1) {
			last_value = 0; /* Released at prefix sample: recorded no-op. */
			return 0;
		}
		ret = reset_control_deassert(display_reset);
		if (ret)
			return ret;
		usleep_range(12000, 15000);
		op_done(step);
		last_value = 1;
		return reset_control_status(display_reset) == 0 ? 0 : -EIO;
	case FINAL_RECHECK:
		ret = stopped();
		if (ret)
			return ret;
		value = readl(ppu_status[0]);
		last_value = readl(ppu_status[1]);
		return (value & PPU_STATE_MASK) == PPU_STATE_ON &&
			       (last_value & PPU_STATE_MASK) == PPU_STATE_ON ?
			       0 :
			       -EIO;
	}
	return -EINVAL;
}

static int advance(const char *value, const struct kernel_param *kp)
{
	unsigned int step;
	int ret = kstrtouint(value, 10, &step);

	if (ret)
		return ret;
	mutex_lock(&audit_lock);
	if (!initialized || failed || released || attempted != completed ||
	    completed >= ARRAY_SIZE(steps) || step != completed + 1 ||
	    (step > PREFIX_STEPS && !extension_available)) {
		ret = -EPERM;
		goto out;
	}
	attempted = step; /* Set before access. Never rewind after failure. */
	pr_notice("h713-dsp-access-audit: BEGIN step=%u operation=%s\n", step,
		  steps[step - 1].name);
	ret = execute_step(&steps[step - 1], step);
	if (ret) {
		failed = true;
		pr_err("h713-dsp-access-audit: FAIL step=%u error=%d value=%08x; cold poweroff required\n",
		       step, ret, last_value);
		goto out;
	}
	completed = step;
	prefix_complete = completed >= PREFIX_STEPS;
	extension_complete = completed == ARRAY_SIZE(steps);
	pr_notice(
		"h713-dsp-access-audit: DONE step=%u operation=%s value=%08x%s\n",
		step, steps[step - 1].name, last_value,
		completed == PREFIX_STEPS ?
			"; prefix end, NO domain/clock/reset writes or DSP access" :
		extension_complete ?
			"; extension end, NO AudioTop/DSP/lock access; poweroff only" :
			"");
out:
	mutex_unlock(&audit_lock);
	return ret;
}
static const struct kernel_param_ops advance_ops = { .set = advance };
module_param_cb(advance, &advance_ops, NULL, 0200);

static void release_resources(void)
{
	unsigned int i;

	/* Reached only while no domain is attached (release limited to census). */
	WARN_ON(attached);
	for (i = 0; i < ARRAY_SIZE(ppu_status); i++) {
		if (ppu_status[i]) {
			iounmap(ppu_status[i]);
			ppu_status[i] = NULL;
		}
	}
	while (clocks_acquired)
		clk_put(clocks[--clocks_acquired]);
	if (tvcap_reset) {
		reset_control_put(tvcap_reset);
		tvcap_reset = NULL;
	}
	if (demod) {
		reset_control_put(demod);
		demod = NULL;
	}
	if (display_reset) {
		reset_control_put(display_reset);
		display_reset = NULL;
	}
	for (i = 0; i < ARRAY_SIZE(maps); i++) {
		if (maps[i]) {
			iounmap(maps[i]);
			maps[i] = NULL;
		}
	}
	while (regions_acquired) {
		--regions_acquired;
		release_mem_region(regions[regions_acquired].base,
				   regions[regions_acquired].size);
	}
}

/* A healthy read-only run can release software handles/maps. No hardware
 * restore is involved: through step 40 nothing enabled clocks, changed
 * resets or domains. From step 41 the only end is an orderly poweroff.
 */
static int release_prefix(const char *value, const struct kernel_param *kp)
{
	bool next;
	int ret = kstrtobool(value, &next);

	if (ret)
		return ret;
	mutex_lock(&audit_lock);
	if (!initialized || !next || failed || released ||
	    attempted != completed || attempted > LAST_READ_ONLY_STEP) {
		ret = -EPERM;
		goto out;
	}
	pr_notice("h713-dsp-access-audit: BEGIN software resource release\n");
	release_resources();
	released = true;
	if (pinned) {
		pinned = false;
		module_put(THIS_MODULE);
	}
	pr_notice("h713-dsp-access-audit: DONE software resource release\n");
out:
	mutex_unlock(&audit_lock);
	return ret;
}
static const struct kernel_param_ops release_ops = { .set = release_prefix };
module_param_cb(release_prefix, &release_ops, NULL, 0200);

static int __init audit_init(void)
{
	struct device_node *node;
	u32 marker;
	bool valid;

	pr_notice(
		"h713-dsp-access-audit: INIT software validation only; no MMIO\n");
	if (!armed)
		return -EPERM;
	node = of_find_node_by_path("/chosen");
	valid = node &&
		!of_property_read_u32(node, "h713,dsp-observation-v1",
				      &marker) &&
		marker == 0x44535031 &&
		!of_find_property(node, "h713,hdmi-boot-v1", NULL);
	/* boot-v4 marker; extension steps also need hardware-backed TVCAP genpd. */
	extension_available = valid &&
		!of_property_read_u32(node, "h713,dsp-observation-v2",
				      &marker) &&
		marker == 0x44535032;
	of_node_put(node);
	if (!valid)
		return -EPERM;
	node = of_find_node_by_path("/soc/display@5600000");
	valid = node && !of_device_is_available(node);
	of_node_put(node);
	if (!valid)
		return -EPERM;
	node = of_find_node_by_path("/soc/cpu-comm@3003000");
	valid = node && !of_device_is_available(node);
	of_node_put(node);
	if (!valid)
		return -EPERM;
	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	tvtop = of_find_compatible_node(NULL, NULL, "allwinner,sunxi-tvtop");
	ppu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ppu");
	valid = ccu && tvtop && ppu && of_device_is_available(ccu) &&
		of_device_is_available(ppu);
	if (valid && of_property_read_bool(ppu, "allwinner,keep-tvcap-on"))
		extension_available = false;
	if (!valid || !try_module_get(THIS_MODULE)) {
		of_node_put(ccu);
		of_node_put(tvtop);
		of_node_put(ppu);
		ccu = tvtop = ppu = NULL;
		return -ENODEV;
	}
	pinned = true;
	initialized = true;
	pr_notice(
		"h713-dsp-access-audit: INIT DONE completed=0 extension=%d; waiting for one explicit step\n",
		extension_available);
	return 0;
}

static void __exit audit_exit(void)
{
	release_resources();
	of_node_put(ccu);
	of_node_put(tvtop);
	of_node_put(ppu);
}
module_init(audit_init);
module_exit(audit_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION(
	"Cold logo-free staged access audit; individually acknowledged steps, no AudioTop/DSP access");
