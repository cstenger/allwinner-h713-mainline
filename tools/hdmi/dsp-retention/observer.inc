/* SPDX-License-Identifier: GPL-2.0-only */
/* Built-in warm-retention bench. No power transition or reset assertion. */
#include <dt-bindings/clock/sun50i-h713-ccu.h>
#include <linux/clk-provider.h>
#include <linux/ioport.h>
#include <linux/kobject.h>
#include <linux/mutex.h>
#include <linux/of_clk.h>
#include <linux/sysfs.h>
#include "h713-dsp-lock.h"
#include "h713-dsp-completion.h"

static DEFINE_MUTEX(retention_mutex);
static struct kobject *retention_kobj;
static bool retention_failed, retention_timeout, retention_claimed;
static bool retention_inherited;
static unsigned int retention_step, retention_attempted, retention_last;
static u32 retention_ctl, retention_cfg, retention_raw[2] = { ~0U, ~0U };
/* 0 not requested, 1 completed, 2 timeout, 3 skipped after failure. */
static u32 retention_outcome[2];
static int retention_demod_before = -1;
static void __iomem *retention_ccu, *retention_top, *retention_port;
static void __iomem *retention_lock, *retention_at, *retention_mips, *retention_scp;
static struct clk *retention_clocks[17];
static struct reset_control *retention_demod;
static struct device_node *retention_ccu_node, *retention_tvtop;
static const unsigned int retention_clock_ids[] = {
	CLK_PLL_VIDEO0, CLK_PLL_ADC, CLK_BUS_TVCAP, CLK_BUS_CAP_300M,
	CLK_VINCAP_DMA, CLK_TVFE_1296M, CLK_BUS_HDMI_AUDIO, CLK_HDMI_AUDIO,
	CLK_AUDIO_CPU, CLK_AUDIO_UMAC, CLK_AUDIO_IHB, CLK_PLL_VIDEO2,
	CLK_DEINT, CLK_PANEL, CLK_SVP_DTL, CLK_AFBD, CLK_BUS_DISP,
};
static const u16 retention_offsets[] = {
	0x00, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28,
	0x30, 0x38, 0x3c, 0x40, 0x48, 0x4c, 0x50,
};
static const u32 retention_stock[] = {
	0x80000017, 0x80000000, 0x81000005, 0x80000002, 0x80000005,
	0x80000003, 0x80000003, 0x8000000b, 0x80000117, 0x80000002,
	0x80000002, 0x81000002, 0x80000002, 0x8000020b, 0x8000020b,
};
static u32 retention_words_before[15];
static struct h713_dsp_lock retention_stock_lock;

static int retention_health(void)
{
	u32 gate;

	if (!h713_tvfe_retain_applied || h713_tvfe_retain_violated)
		return -EPERM;
	gate = readl(h713_tvfe_trace_r_ccu + 0x1ac);
	if ((gate & 0x10001) != 0x10001)
		return -EIO;
	if ((readl(h713_tvfe_trace_ppu + 0xa4) & 0x30008) != 0x10000 ||
	    (readl(h713_tvfe_trace_ppu + 0x124) & 0x30008) != 0x10000)
		return -EIO;
	if (retention_mips && (readl(retention_mips) || (readl(retention_scp) & 1)))
		return -EBUSY;
	return 0;
}

static int retention_resources(void)
{
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;

	/* Any partial acquisition stays held until orderly poweroff. */
	if (!request_mem_region(0x06144000, 0x1c, "h713-dsp-retention") ||
	    !request_mem_region(0x05001530, 8, "h713-dsp-retention") ||
	    !request_mem_region(0x0614a000, 0x10, "h713-dsp-retention") ||
	    !request_mem_region(0x07000400, 4, "h713-dsp-retention"))
		return -EBUSY;
	retention_ccu = ioremap(0x02001d10, 0xcc);
	retention_top = ioremap(0x05700000, 0x90);
	retention_port = ioremap(0x06144000, 0x1c);
	retention_lock = ioremap(0x05001530, 8);
	retention_at = ioremap(0x0614a000, 0x10);
	retention_mips = ioremap(0x0306101c, 4);
	retention_scp = ioremap(0x07000400, 4);
	if (!retention_ccu || !retention_top || !retention_port || !retention_lock ||
	    !retention_at || !retention_mips || !retention_scp)
		return -ENOMEM;
	retention_stock_lock.peer = retention_lock;
	retention_stock_lock.own = retention_lock + 4;
	retention_ccu_node = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	retention_tvtop = of_find_compatible_node(NULL, NULL, "allwinner,sunxi-tvtop");
	if (!retention_ccu_node || !retention_tvtop)
		return -ENODEV;
	spec.np = retention_ccu_node;
	for (i = 0; i < ARRAY_SIZE(retention_clocks); i++) {
		spec.args[0] = retention_clock_ids[i];
		retention_clocks[i] = of_clk_get_from_provider(&spec);
		if (IS_ERR(retention_clocks[i]))
			return PTR_ERR(retention_clocks[i]);
	}
	retention_demod = of_reset_control_get_exclusive(retention_tvtop, "reset_bus_demod");
	return IS_ERR(retention_demod) ? PTR_ERR(retention_demod) : 0;
}

static int retention_routing(void)
{
	/* Only SPL-safe offsets until the exact routed value is verified. */
	if (readl(retention_top + 0x40) != 0x00011111 ||
	    readl(retention_top + 0x44) != 0x11111111 ||
	    readl(retention_top + 0x80) != 0x00001111)
		return -EPERM;
	return readl(retention_top) == 0xfff11111 &&
		readl(retention_top + 4) == 1 &&
		readl(retention_top + 0x84) == 0xfff000ef &&
		readl(retention_top + 0x88) == 0x11111111 ? 0 : -EPERM;
}

static int retention_interface_ready(void)
{
	int ret = retention_routing();

	if (ret)
		return ret;
	/* TVCAP and demod buses must be open before AudioTop/DSP/lock reads. */
	if ((readl(retention_ccu + 0x78) & 0x10001) != 0x10001 ||
	    (readl(retention_ccu + 0x54) & 0x10001) != 0x10001)
		return -EIO;
	return 0;
}

static int retention_read_version(unsigned int dev)
{
	u32 status, response;
	int ret;

	if (retention_timeout) {
		retention_outcome[dev] = 3;
		return 0;
	}
	ret = readl_poll_timeout(retention_port, status,
				 !(status & BIT(dev ? 7 : 4)), 10, 50000);
	if (!ret)
		ret = h713_dsp_stock_response(retention_port,
			retention_port + (dev ? 0x18 : 0x10), 0x80ff,
			BIT(dev ? 8 : 5), &status, &response);
	retention_last = status;
	if (ret) {
		retention_timeout = true;
		retention_outcome[dev] = 2;
		return 0; /* Release still runs; no command after timeout. */
	}
	retention_raw[dev] = response;
	retention_outcome[dev] = 1;
	return 0;
}

static int retention_operation(unsigned int n)
{
	u32 value;
	unsigned int i;
	int ret;

	if (n == 1)
		return retention_resources();
	ret = retention_health();
	if (ret)
		return ret;
	if (n == 2) {
		ret = retention_routing();
		if (ret)
			return ret;
		if ((readl(retention_ccu + 0x78) & 0x10001) != 0x10001)
			return -EPERM; /* Never release TVCAP reset in this bench. */
		for (i = 0; i < 15; i++)
			retention_words_before[i] = readl(retention_ccu + retention_offsets[i]);
		return 0;
	}
	if ((n >= 3 && n <= 8) || (n >= 26 && n <= 36)) {
		i = n <= 8 ? n - 3 : n - 20;
		ret = clk_prepare_enable(retention_clocks[i]);
		if (ret)
			return ret;
		if (i == 11)
			usleep_range(12000, 15000);
		retention_last = __clk_is_enabled(retention_clocks[i]);
		return retention_last ? 0 : -EIO;
	}
	if (n == 9) {
		ret = reset_control_status(retention_demod);
		retention_demod_before = ret;
		if (ret < 0)
			return ret;
		if (ret) {
			ret = reset_control_deassert(retention_demod);
			if (ret)
				return ret;
			usleep_range(10000, 15000);
		}
		return reset_control_status(retention_demod) == 0 ? 0 : -EIO;
	}
	if (n >= 10 && n <= 24) {
		i = n - 10;
		if (readl(retention_ccu + retention_offsets[i]) != retention_stock[i])
			writel(retention_stock[i], retention_ccu + retention_offsets[i]);
		retention_last = readl(retention_ccu + retention_offsets[i]);
		return retention_last == retention_stock[i] ? 0 : -EIO;
	}
	if (n == 25) {
		value = readl(retention_ccu + 0x54);
		if (!(value & BIT(16)))
			return -EIO;
		if (!(value & BIT(0)))
			writel(value | BIT(0), retention_ccu + 0x54);
		usleep_range(10000, 15000);
		return (readl(retention_ccu + 0x54) & 0x10001) == 0x10001 ? 0 : -EIO;
	}
	ret = retention_interface_ready();
	if (ret)
		return ret;
	switch (n) {
	case 37:
		retention_ctl = readl(retention_at);
		retention_cfg = readl(retention_at + 0xc);
		retention_inherited = (retention_ctl & 0x700) == 0x700 &&
			(retention_cfg & 0x01ffffff) == 0x011a5e00;
		/* Only known reset/baseline states, no arbitrary inherited config. */
		return retention_inherited || !(retention_cfg & 0x01ffffff) ? 0 : -EPERM;
	case 38:
		if (!retention_inherited)
			writel(retention_ctl | 0x700, retention_at);
		return readl(retention_at) == (retention_ctl | 0x700) ? 0 : -EIO;
	case 39:
	case 40:
		value = (retention_cfg & 0xfe000000) | 0x001a5e00;
		if (n == 40 || retention_inherited)
			value |= 0x01000000;
		if (!retention_inherited)
			writel(value, retention_at + 0xc);
		return readl(retention_at + 0xc) == value ? 0 : -EIO;
	case 41:
		retention_last = readl(retention_port);
		if (retention_last & (BIT(4) | BIT(7)))
			return -EBUSY;
		pr_notice("H713 RETENTION lock peer=%08x own=%08x\n",
			  readl(retention_lock), readl(retention_lock + 4));
		return 0;
	case 42:
		ret = h713_dsp_claim(&retention_stock_lock);
		if (!ret)
			retention_claimed = true;
		return ret;
	case 43:
	case 44:
		return retention_claimed ? retention_read_version(n - 43) : -EPERM;
	case 45:
		ret = h713_dsp_release(&retention_stock_lock);
		if (!ret)
			retention_claimed = false;
		return ret;
	case 46:
		return !retention_claimed && readl(retention_lock + 4) == 0xaa &&
			readl(retention_lock) != 0x55 ? 0 : -EIO;
	}
	return -EINVAL;
}

static ssize_t step_store(struct kobject *kobj, struct kobj_attribute *attr,
			 const char *buf, size_t count)
{
	unsigned int n;
	int ret;

	if (kstrtouint(buf, 0, &n))
		return -EINVAL;
	mutex_lock(&retention_mutex);
	if (retention_failed || n != retention_step + 1 || n > 46 ||
	    !h713_tvfe_retain_applied || h713_tvfe_retain_violated) {
		ret = -EPERM;
		goto out;
	}
	retention_attempted = n;
	pr_notice("H713 RETENTION step=%u BEGIN\n", n);
	ret = retention_operation(n);
	if (!ret)
		ret = retention_health();
	if (ret) {
		retention_failed = true;
		pr_err("H713 RETENTION step=%u FAILED ret=%d; poweroff only\n", n, ret);
	} else {
		retention_step = n;
		pr_notice("H713 RETENTION step=%u DONE value=%08x\n", n, retention_last);
	}
out:
	mutex_unlock(&retention_mutex);
	return ret ? ret : count;
}

static ssize_t state_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)
{
	ssize_t n;
	unsigned int i;
	mutex_lock(&retention_mutex);
	n = sysfs_emit(buf, "{\"schema\":\"h713-dsp-retention-v1\",\"step\":%u,\"attempted\":%u,"
		"\"hold\":%u,\"violated\":%u,\"failed\":%u,\"timeout\":%u,\"claimed\":%u,"
		"\"interface_inherited\":%u,\"ctl_before\":%u,\"cfg_before\":%u,"
		"\"outcome0\":%u,\"outcome1\":%u,\"raw0\":%u,\"raw1\":%u,\"last\":%u,"
		"\"demod_before\":%d,\"tv_before\":[",
		retention_step, retention_attempted, h713_tvfe_retain_applied,
		h713_tvfe_retain_violated, retention_failed, retention_timeout,
		retention_claimed, retention_inherited, retention_ctl, retention_cfg,
		retention_outcome[0], retention_outcome[1], retention_raw[0], retention_raw[1], retention_last,
		retention_demod_before);
	for (i = 0; i < 15; i++)
		n += sysfs_emit_at(buf, n, "%s%u", i ? "," : "", retention_words_before[i]);
	n += sysfs_emit_at(buf, n, "]}\n");
	mutex_unlock(&retention_mutex);
	return n;
}
static struct kobj_attribute retention_step_attr = __ATTR_WO(step);
static struct kobj_attribute retention_state_attr = __ATTR_RO(state);
static struct attribute *retention_attrs[] = {
	&retention_step_attr.attr, &retention_state_attr.attr, NULL,
};
static const struct attribute_group retention_group = { .attrs = retention_attrs };

static int __init retention_observer_init(void)
{
	struct device_node *chosen;
	bool handoff;
	int ret;

	if (!h713_tvfe_retain_applied || h713_tvfe_retain_violated)
		return 0;
	chosen = of_find_node_by_path("/chosen");
	handoff = chosen && of_find_property(chosen, "h713,hdmi-boot-v1", NULL);
	of_node_put(chosen);
	if (handoff)
		return -EPERM;
	retention_kobj = kobject_create_and_add("h713_dsp_retention", kernel_kobj);
	if (!retention_kobj)
		return -ENOMEM;
	ret = sysfs_create_group(retention_kobj, &retention_group);
	if (ret)
		kobject_put(retention_kobj);
	return ret;
}
late_initcall(retention_observer_init);
