// SPDX-License-Identifier: GPL-2.0-only
/* Cold logo-free prefix audit. Init performs software/DT checks only.
 * Each sysfs step performs ONE named operation. No hardware writes, domain
 * attachment/resume, clock enables, reset changes or AudioTop/DSP/lock reads.
 * Error retains the module pin and acquired resources until cold poweroff.
 */
#include <dt-bindings/clock/sun50i-h713-ccu.h>
#include <linux/clk.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/reset.h>

static bool armed, failed, released, prefix_complete, pinned, initialized;
static unsigned int completed, attempted, last_value;
module_param(armed, bool, 0400);
module_param(failed, bool, 0444);
module_param(released, bool, 0444);
module_param(prefix_complete, bool, 0444);
module_param(completed, uint, 0444);
module_param(attempted, uint, 0444);
module_param(last_value, uint, 0444);
static DEFINE_MUTEX(audit_lock);
static struct device_node *ccu, *tvtop;
static struct reset_control *display_reset, *demod;
static struct clk *clocks[17];
static unsigned int clocks_acquired, regions_acquired;
static void __iomem *maps[4];
static const struct {
	resource_size_t base, size;
} regions[] = {
	{0x06144000, 0x1c}, {0x05001530, 8},
	{0x0614a000, 0x10}, {0x07000400, 4},
}, windows[] = {
	{0x0306101c, 4}, {0x07000400, 4},
	{0x02001d10, 0x58}, {0x02001dd8, 4},
};
static const unsigned int clock_ids[] = {
	CLK_PLL_VIDEO0, CLK_PLL_ADC,	CLK_BUS_TVCAP,	    CLK_BUS_CAP_300M,
	CLK_VINCAP_DMA, CLK_TVFE_1296M, CLK_BUS_HDMI_AUDIO, CLK_HDMI_AUDIO,
	CLK_AUDIO_CPU,	CLK_AUDIO_UMAC, CLK_AUDIO_IHB,	    CLK_PLL_VIDEO2,
	CLK_DEINT,	CLK_PANEL,	CLK_SVP_DTL,	    CLK_AFBD,
	CLK_BUS_DISP,
};
static_assert(ARRAY_SIZE(clock_ids) == ARRAY_SIZE(clocks));

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
	GET_CLOCK
};
struct audit_step {
	enum action action;
	unsigned int arg;
	const char *name;
};
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
#define CLOCK_STEP(i, name) { GET_CLOCK, i, "get-clock-" name }
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
#undef CLOCK_STEP
};
static_assert(ARRAY_SIZE(steps) == 33);

static int next_operation_get(char *buffer, const struct kernel_param *kp)
{
	const char *name = "prefix-end";

	if (failed)
		name = "failed";
	else if (released)
		name = "released";
	else if (completed < ARRAY_SIZE(steps))
		name = steps[completed].name;
	return scnprintf(buffer, PAGE_SIZE, "%s\n", name);
}
static const struct kernel_param_ops next_ops = { .get = next_operation_get };
module_param_cb(next_operation, &next_ops, NULL, 0444);

static int execute_step(const struct audit_step *s)
{
	struct of_phandle_args spec = { .np = ccu, .args_count = 1 };
	struct clk *clk;
	struct reset_control *reset;
	int ret;

	last_value = 0; /* Only READ steps produce a hardware sample. */
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
	    completed >= ARRAY_SIZE(steps) || step != completed + 1) {
		ret = -EPERM;
		goto out;
	}
	attempted = step; /* Set before access. Never rewind after failure. */
	pr_notice("h713-dsp-access-audit: BEGIN step=%u operation=%s\n", step,
		  steps[step - 1].name);
	ret = execute_step(&steps[step - 1]);
	if (ret) {
		failed = true;
		pr_err("h713-dsp-access-audit: FAIL step=%u error=%d value=%08x; cold poweroff required\n",
		       step, ret, last_value);
		goto out;
	}
	completed = step;
	prefix_complete = completed == ARRAY_SIZE(steps);
	pr_notice(
		"h713-dsp-access-audit: DONE step=%u operation=%s value=%08x%s\n",
		step, steps[step - 1].name, last_value,
		prefix_complete ?
			"; prefix end, NO domain/clock/reset writes or DSP access" :
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

	while (clocks_acquired)
		clk_put(clocks[--clocks_acquired]);
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

/* A healthy prefix can release software handles/maps. No hardware restore
 * is involved: this module never enabled clocks, changed resets or domains.
 */
static int release_prefix(const char *value, const struct kernel_param *kp)
{
	bool next;
	int ret = kstrtobool(value, &next);

	if (ret)
		return ret;
	mutex_lock(&audit_lock);
	if (!initialized || !next || failed || released ||
	    attempted != completed) {
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
	node = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ppu");
	valid = ccu && tvtop && node && of_device_is_available(ccu) &&
		of_device_is_available(node);
	of_node_put(node);
	if (!valid || !try_module_get(THIS_MODULE)) {
		of_node_put(ccu);
		of_node_put(tvtop);
		ccu = tvtop = NULL;
		return -ENODEV;
	}
	pinned = true;
	initialized = true;
	pr_notice(
		"h713-dsp-access-audit: INIT DONE completed=0; waiting for one explicit step\n");
	return 0;
}

static void __exit audit_exit(void)
{
	release_resources();
	of_node_put(ccu);
	of_node_put(tvtop);
}
module_init(audit_init);
module_exit(audit_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION(
	"Cold logo-free read-only prefix audit; individually acknowledged access steps");
