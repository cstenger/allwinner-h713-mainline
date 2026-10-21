// SPDX-License-Identifier: GPL-2.0-only
/* Bench access setup with MIPS/SCP stopped. No firmware, DMA or IRQ setup.
 * Loading does NOT issue DSP commands. A separate one-shot sysfs request may
 * read the two version words after setup. Failure retains holds until cold
 * poweroff; no module reload/retry can clear the latch.
 */
#include <dt-bindings/clock/sun50i-h713-ccu.h>
#include <linux/clk-provider.h>
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_clk.h>
#include <linux/pm_domain.h>
#include <linux/pm_runtime.h>
#include <linux/reset.h>
#include "../hdmi-dsp-probe/h713-dsp-completion.h"
#include "../hdmi-dsp-probe/h713-dsp-lock.h"

static bool armed, ready, failed, attempted, released;
static unsigned int version0, version1;
static unsigned int status_before, peer_before, own_before;
module_param(armed, bool, 0400);
module_param(ready, bool, 0444);
module_param(failed, bool, 0444);
module_param(attempted, bool, 0444);
module_param(released, bool, 0444);
module_param(version0, uint, 0444);
module_param(version1, uint, 0444);
module_param(status_before, uint, 0444);
module_param(peer_before, uint, 0444);
module_param(own_before, uint, 0444);
static DEFINE_MUTEX(bench_lock);
static bool pinned;
static void __iomem *mips, *scp, *ccu_tv, *ccu_disp, *top, *port, *lock_window;
static struct reset_control *demod, *display_reset;
static bool reset_released, display_released, tv_saved, top_saved;
static u32 display_bus_before;
static int display_reset_before;
static u32 bus_before, top_ctl_before, top_cfg_before;
static const u16 offsets[] = {
    0x00, 0x10, 0x14, 0x18, 0x1c, 0x20, 0x24, 0x28, 0x30, 0x38, 0x3c, 0x40, 0x48, 0x4c, 0x50,
};
static const u32 stock[] = {
    0x80000017, 0x80000000, 0x81000005, 0x80000002, 0x80000005, 0x80000003, 0x80000003, 0x8000000b,
    0x80000117, 0x80000002, 0x80000002, 0x81000002, 0x80000002, 0x8000020b, 0x8000020b,
};
static_assert(ARRAY_SIZE(offsets) == ARRAY_SIZE(stock));
static u32 tv_before[ARRAY_SIZE(offsets)];
static const unsigned int clock_ids[] = {
    CLK_PLL_VIDEO0, CLK_PLL_ADC,	CLK_BUS_TVCAP,	CLK_BUS_CAP_300M, CLK_VINCAP_DMA,
    CLK_TVFE_1296M, CLK_BUS_HDMI_AUDIO, CLK_HDMI_AUDIO, CLK_AUDIO_CPU,	  CLK_AUDIO_UMAC,
    CLK_AUDIO_IHB,  CLK_PLL_VIDEO2,	CLK_DEINT,	CLK_PANEL,	  CLK_SVP_DTL,
    CLK_AFBD,	    CLK_BUS_DISP,
};
static_assert(ARRAY_SIZE(clock_ids) == 17);
static struct clk *clocks[ARRAY_SIZE(clock_ids)];
static bool clock_enabled[ARRAY_SIZE(clock_ids)];
static unsigned int clocks_acquired;
static struct device *domains[2];
static unsigned int attached, resumed;
static const char *const domain_names[] = {"h713-dsp-observe-tvfe", "h713-dsp-observe-tvcap"};
static const struct {
	unsigned long base, size;
} regions[] = {
    {0x06144000, 0x1c},
    {0x05001530, 8},
    {0x0614a000, 0x10},
    {0x07000400, 4},
};
static unsigned int claimed_regions;

static int stopped(void)
{
	return readl(mips) == 0 && !(readl(scp) & BIT(0)) ? 0 : -EBUSY;
}

static int enable_clock(unsigned int index)
{
	int ret;
	if (__clk_is_enabled(clocks[index]))
		return 0;
	ret = clk_prepare_enable(clocks[index]);
	if (!ret)
		clock_enabled[index] = true;
	return ret;
}

static int read_version(unsigned int device, u32 *response)
{
	u32 status;
	int ret = readl_poll_timeout(port, status, !(status & BIT(device ? 7 : 4)), 10, 50000);
	if (!ret)
		ret = h713_dsp_stock_response(port, port + (device ? 0x18 : 0x10), 0x80ff,
					      BIT(device ? 8 : 5), &status, response);
	pr_info("h713-dsp-observe: device=%u result=%d status=%08x\n", device, ret, status);
	return ret;
}

static int probe_versions(const char *value, const struct kernel_param *kp)
{
	struct h713_dsp_lock lock;
	bool next, owned = false;
	int ret = kstrtobool(value, &next);
	if (ret)
		return ret;
	mutex_lock(&bench_lock);
	if (!next || !ready || failed || attempted || released) {
		ret = -EPERM;
		goto out;
	}
	lock.peer = lock_window;
	lock.own = lock_window + 4;
	attempted = true; /* Includes refusals: this module never retries. */
	ret = stopped();
	if (ret)
		goto fail;
	ret = h713_dsp_claim(&lock);
	if (ret)
		goto fail;
	owned = true;
	ret = read_version(0, &version0);
	if (!ret)
		ret = read_version(1, &version1);
	if (owned && h713_dsp_release(&lock))
		ret = -EIO;
	if (ret)
		goto fail;
	pr_info("h713-dsp-observe: versions raw=%08x/%08x after controlled setup; not reset-entry "
		"proof\n",
		version0, version1);
	goto out;
fail:
	failed = true;
	pr_err("h713-dsp-observe: observation failed %d; holds retained, cold poweroff required\n",
	       ret);
out:
	mutex_unlock(&bench_lock);
	return ret;
}
static const struct kernel_param_ops probe_ops = {.set = probe_versions};
module_param_cb(probe_versions, &probe_ops, NULL, 0200);

/* Explicit successful cleanup only. Failed setup/transaction retains holds. */
static int restore(const char *value, const struct kernel_param *kp)
{
	bool next;
	unsigned int i;
	int ret = kstrtobool(value, &next);
	if (ret)
		return ret;
	mutex_lock(&bench_lock);
	if (!next || !ready || failed || released) {
		ret = -EPERM;
		goto out;
	}
	ret = stopped();
	if (ret)
		goto fail;
	if (top_saved) {
		writel(top_cfg_before, top + 0xc);
		writel(top_ctl_before, top);
		if (readl(top + 0xc) != top_cfg_before || readl(top) != top_ctl_before) {
			ret = -EIO;
			goto fail;
		}
	}
	if (tv_saved) {
		writel(bus_before | BIT(16), ccu_tv + 0x54);
		for (i = ARRAY_SIZE(offsets); i > 0; i--) {
			writel(tv_before[i - 1], ccu_tv + offsets[i - 1]);
			if (readl(ccu_tv + offsets[i - 1]) != tv_before[i - 1]) {
				ret = -EIO;
				goto fail;
			}
		}
	}
	if (reset_released) {
		ret = reset_control_assert(demod);
		if (ret || reset_control_status(demod) != 1) {
			ret = -EIO;
			goto fail;
		}
	}
	if (display_released) {
		ret = reset_control_assert(display_reset);
		if (ret || reset_control_status(display_reset) != 1) {
			ret = -EIO;
			goto fail;
		}
	}
	writel(bus_before, ccu_tv + 0x54);
	if (readl(ccu_tv + 0x54) != bus_before) {
		ret = -EIO;
		goto fail;
	}
	for (i = clocks_acquired; i > 0; i--)
		if (clock_enabled[i - 1]) {
			clk_disable_unprepare(clocks[i - 1]);
			clock_enabled[i - 1] = false;
		}
	if (readl(ccu_disp) != display_bus_before) {
		ret = -EIO;
		goto fail;
	}
	while (resumed) {
		ret = pm_runtime_put_sync_suspend(domains[resumed - 1]);
		if (ret < 0)
			goto fail;
		pm_runtime_disable(domains[--resumed]);
	}
	while (attached) {
		ret = pm_genpd_remove_device(domains[attached - 1]);
		if (ret)
			goto fail;
		root_device_unregister(domains[--attached]);
	}
	ready = false;
	released = true;
	if (pinned) {
		pinned = false;
		module_put(THIS_MODULE);
	}
	pr_info("h713-dsp-observe: controls restored and domain holds released\n");
	ret = 0;
	goto out;
fail:
	failed = true;
	pr_err("h713-dsp-observe: restore failed %d; cold poweroff required\n", ret);
out:
	mutex_unlock(&bench_lock);
	return ret;
}
static const struct kernel_param_ops restore_ops = {.set = restore};
module_param_cb(restore, &restore_ops, NULL, 0200);

static void release_mappings(void)
{
	unsigned int i;
	if (demod)
		reset_control_put(demod);
	if (display_reset)
		reset_control_put(display_reset);
	for (i = 0; i < clocks_acquired; i++)
		clk_put(clocks[i]);
	iounmap(lock_window);
	iounmap(port);
	iounmap(top);
	iounmap(ccu_tv);
	iounmap(ccu_disp);
	iounmap(scp);
	iounmap(mips);
	while (claimed_regions) {
		--claimed_regions;
		release_mem_region(regions[claimed_regions].base, regions[claimed_regions].size);
	}
}

static int __init observe_init(void)
{
	struct device_node *chosen, *ccu, *ppu, *tvtop;
	struct device_node *display_node, *comm_node;
	struct of_phandle_args spec = {.args_count = 1};
	u32 marker;
	unsigned int i;
	int ret = -EPERM;
	if (!armed)
		return -EPERM;
	chosen = of_find_node_by_path("/chosen");
	if (!chosen)
		return -ENODEV;
	if (of_property_read_u32(chosen, "h713,dsp-observation-v1", &marker) ||
	    marker != 0x44535031 || of_find_property(chosen, "h713,hdmi-boot-v1", NULL)) {
		of_node_put(chosen);
		return -EPERM;
	}
	of_node_put(chosen);
	display_node = of_find_node_by_path("/soc/display@5600000");
	comm_node = of_find_node_by_path("/soc/cpu-comm@3003000");
	ret = (!display_node || !comm_node || of_device_is_available(display_node) ||
	       of_device_is_available(comm_node))
		  ? -EPERM
		  : 0;
	of_node_put(display_node);
	of_node_put(comm_node);
	if (ret)
		return ret;
	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	ppu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ppu");
	tvtop = of_find_compatible_node(NULL, NULL, "allwinner,sunxi-tvtop");
	if (!ccu || !ppu || !tvtop || !of_device_is_available(ccu) ||
	    !of_device_is_available(ppu)) {
		ret = -ENODEV;
		goto nodes;
	}
	for (i = 0; i < ARRAY_SIZE(regions); i++) {
		if (!request_mem_region(regions[i].base, regions[i].size, "h713-dsp-observe")) {
			ret = -EBUSY;
			goto clean;
		}
		claimed_regions++;
	}
	mips = ioremap(0x0306101c, 4);
	scp = ioremap(0x07000400, 4);
	ccu_tv = ioremap(0x02001d10, 0x58);
	ccu_disp = ioremap(0x02001dd8, 4);
	if (!mips || !scp || !ccu_tv || !ccu_disp) {
		ret = -ENOMEM;
		goto clean;
	}
	ret = stopped();
	if (ret)
		goto clean;
	bus_before = readl(ccu_tv + 0x54);
	if (bus_before & (BIT(16) | BIT(0))) {
		ret = -EBUSY;
		goto clean;
	}
	display_bus_before = readl(ccu_disp);
	display_reset = of_reset_control_get_exclusive(tvtop, "reset_bus_disp");
	if (IS_ERR(display_reset)) {
		ret = PTR_ERR(display_reset);
		display_reset = NULL;
		goto clean;
	}
	display_reset_before = reset_control_status(display_reset);
	if (display_reset_before != 0 && display_reset_before != 1) {
		ret = display_reset_before < 0 ? display_reset_before : -EIO;
		goto clean;
	}
	demod = of_reset_control_get_exclusive(tvtop, "reset_bus_demod");
	if (IS_ERR(demod)) {
		ret = PTR_ERR(demod);
		demod = NULL;
		goto clean;
	}
	if (reset_control_status(demod) != 1) {
		ret = -EBUSY;
		goto clean;
	}
	spec.np = ccu;
	for (i = 0; i < ARRAY_SIZE(clock_ids); i++) {
		spec.args[0] = clock_ids[i];
		clocks[i] = of_clk_get_from_provider(&spec);
		if (IS_ERR(clocks[i])) {
			ret = PTR_ERR(clocks[i]);
			goto clean;
		}
		clocks_acquired++;
	}
	/* From here failures keep the module and partial holds until cold poweroff. */
	if (!try_module_get(THIS_MODULE)) {
		ret = -ENODEV;
		goto clean;
	}
	pinned = true;
	spec.np = ppu;
	for (i = 0; i < ARRAY_SIZE(domains); i++) {
		domains[i] = root_device_register(domain_names[i]);
		if (IS_ERR(domains[i])) {
			ret = PTR_ERR(domains[i]);
			goto fail;
		}
		spec.args[0] = i + 1;
		ret = of_genpd_add_device(&spec, domains[i]);
		if (ret) {
			root_device_unregister(domains[i]);
			goto fail;
		}
		attached++;
		pm_runtime_enable(domains[i]);
		ret = pm_runtime_resume_and_get(domains[i]);
		if (ret < 0) {
			pm_runtime_disable(domains[i]);
			goto fail;
		}
		resumed++;
	}
	/* The lock at 05001530 is in the display register window. Reproduce
	 * h713_display_clocks_on's complete tree before accessing that window.
	 * No mixer, panel, framebuffer or routing register is touched.
	 */
	ret = enable_clock(11);
	if (ret)
		goto fail;
	usleep_range(12000, 15000);
	for (i = 12; i < clocks_acquired; i++) {
		ret = enable_clock(i);
		if (ret)
			goto fail;
	}
	if (display_reset_before == 1) {
		ret = reset_control_deassert(display_reset);
		if (ret)
			goto fail;
		display_released = true;
	}
	usleep_range(12000, 15000);
	/* Match receiver acquisition; preserve inherited gates. */
	for (i = 2; i < 6; i++) {
		ret = enable_clock(i);
		if (ret)
			goto fail;
	}
	/* Stock demod reset release before functional-clock words, bus last. */
	ret = reset_control_deassert(demod);
	if (ret)
		goto fail;
	reset_released = true;
	usleep_range(10000, 15000);
	for (i = 0; i < 2; i++) {
		ret = enable_clock(i);
		if (ret)
			goto fail;
	}
	for (i = 0; i < ARRAY_SIZE(offsets); i++)
		tv_before[i] = readl(ccu_tv + offsets[i]);
	tv_saved = true;
	for (i = 0; i < ARRAY_SIZE(offsets); i++) {
		writel(stock[i], ccu_tv + offsets[i]);
		if (readl(ccu_tv + offsets[i]) != stock[i]) {
			ret = -EIO;
			goto fail;
		}
	}
	writel(readl(ccu_tv + 0x54) | BIT(0), ccu_tv + 0x54);
	if ((readl(ccu_tv + 0x54) & (BIT(16) | BIT(0))) != (BIT(16) | BIT(0))) {
		ret = -EIO;
		goto fail;
	}
	usleep_range(10000, 15000);
	for (i = 6; i < 11; i++) {
		ret = enable_clock(i);
		if (ret)
			goto fail;
	}
	top = ioremap(0x0614a000, 0x10);
	port = ioremap(0x06144000, 0x1c);
	lock_window = ioremap(0x05001530, 8);
	if (!top || !port || !lock_window) {
		ret = -ENOMEM;
		goto fail;
	}
	top_ctl_before = readl(top);
	top_cfg_before = readl(top + 0xc);
	top_saved = true;
	pr_info("h713-dsp-observe: AudioTop before setup ctl=%08x cfg=%08x\n", top_ctl_before,
		top_cfg_before);
	/* First cold control only: do not overwrite an inherited DSP setup. */
	if ((top_ctl_before & 0x700) || (top_cfg_before & 0x00ffffff)) {
		ret = -EBUSY;
		goto fail;
	}
	writel(top_ctl_before | 0x700, top);
	writel((top_cfg_before & 0xff000000) | 0x001a5e00, top + 0xc);
	writel((top_cfg_before & 0xff000000) | 0x011a5e00, top + 0xc);
	if (readl(top) != (top_ctl_before | 0x700) ||
	    readl(top + 0xc) != ((top_cfg_before & 0xff000000) | 0x011a5e00)) {
		ret = -EIO;
		goto fail;
	}
	ret = stopped();
	if (ret)
		goto fail;
	/* Plain status/ownership samples, after all access setup; no request. */
	status_before = readl(port);
	peer_before = readl(lock_window);
	own_before = readl(lock_window + 4);
	pr_info("h713-dsp-observe: pre-request status=%08x peer=%08x own=%08x\n", status_before,
		peer_before, own_before);
	if ((status_before & (BIT(4) | BIT(7))) || peer_before == 0x55 || own_before == 0x55) {
		ret = -EBUSY;
		goto fail;
	}
	ready = true;
	pr_info("h713-dsp-observe: access setup ready; AudioTop=%08x/%08x before setup; NO DSP "
		"command issued\n",
		top_ctl_before, top_cfg_before);
	goto nodes;
fail:
	failed = true;
	pr_err("h713-dsp-observe: setup failed %d; holds retained, cold poweroff required\n", ret);
	ret = 0;
	goto nodes;
clean:
	release_mappings();
nodes:
	of_node_put(tvtop);
	of_node_put(ppu);
	of_node_put(ccu);
	return ret;
}
static void __exit observe_exit(void)
{
	release_mappings();
}
module_init(observe_init);
module_exit(observe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION(
    "Logo-free DSP access-setup bench; one-shot version observation, no firmware or patch loading");
