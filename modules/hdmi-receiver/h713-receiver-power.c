// SPDX-License-Identifier: GPL-2.0-only
/* Firmware-lifetime TVFE/TVCAP power and receiver-clock owner.
 * No receiver MMIO, IRQs, GPIOs, or clock-rate changes.
 */
#include <linux/clk.h>
#include <linux/device.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/pm_domain.h>
#include <linux/pm_runtime.h>
#include <linux/io.h>
#include <linux/mutex.h>
#include "h713-receiver.h"
#include "h713-receiver-policy.h"
#include <dt-bindings/clock/sun50i-h713-ccu.h>

static struct device *domain_devs[2];
static struct clk_bulk_data clocks[] = {
	{ .id = "bus-tvcap" },
	{ .id = "bus-cap-300m" },
	{ .id = "vincap-dma" },
	{ .id = "tvfe-1296m" },
};
static const unsigned int clock_ids[] = {
	CLK_BUS_TVCAP,
	CLK_BUS_CAP_300M,
	CLK_VINCAP_DMA,
	CLK_TVFE_1296M,
};
static const char *const domain_names[] = {
	"h713-hdmi-tvfe",
	"h713-hdmi-tvcap",
};
static unsigned int attached, resumed, acquired;
static DEFINE_MUTEX(owner_lock);
static void __iomem *mips_status;
static bool firmware_pin, accepting_clients, armed, live_source3;
static unsigned int clients;
static int init_error;
module_param(armed, bool, 0400);
module_param(live_source3, bool, 0400);
module_param(clients, uint, 0444);
module_param(init_error, int, 0444);
module_param_named(edid_ready, h713_receiver_edid_ready, bool, 0444);
module_param(firmware_pin, bool, 0444);

static unsigned int enabled_clocks;
static unsigned int clock_count;
static bool resources_ready;
static unsigned int domain_count = ARRAY_SIZE(domain_devs);
static unsigned int notified;
static int trace_domain(struct notifier_block *nb, unsigned long event,
			void *data);
static struct notifier_block domain_notifiers[2] = {
	{ .notifier_call = trace_domain },
	{ .notifier_call = trace_domain },
};

static int trace_domain(struct notifier_block *nb, unsigned long event,
			void *data)
{
	pr_info("h713-hdmi-receiver: domain %td power event %lu\n",
		nb - domain_notifiers + 1, event);
	return NOTIFY_OK;
}

/* Monotonic staged startup: never gate a live firmware clock via sysfs. */
static int set_clock_count_unlocked(const char *value,
				    const struct kernel_param *kp)
{
	unsigned int count;
	int ret = kstrtouint(value, 0, &count);

	if (ret)
		return ret;
	if (init_error)
		return -EIO;
	if (count > ARRAY_SIZE(clocks))
		return -EINVAL;
	if (resources_ready) {
		if (domain_count < ARRAY_SIZE(domain_devs) && count)
			return -EINVAL;
		if (!h713_receiver_clock_step_allowed(enabled_clocks, count))
			return -EINVAL;
		while (enabled_clocks < count) {
			ret = clk_prepare_enable(clocks[enabled_clocks].clk);
			if (ret) {
				clock_count = enabled_clocks;
				init_error = ret;
				return ret;
			}
			pr_info("h713-hdmi-receiver: enabled clock %u (%s)\n",
				enabled_clocks, clocks[enabled_clocks].id);
			enabled_clocks++;
		}
	}
	if (resources_ready && count == ARRAY_SIZE(clocks) &&
	    !h713_receiver_edid_ready) {
		ret = h713_receiver_edid_register();
		if (ret) {
			init_error = ret;
			return ret;
		}
	}
	*(unsigned int *)kp->arg = count;
	return 0;
}

static int set_clock_count(const char *value, const struct kernel_param *kp)
{
	int ret;
	mutex_lock(&owner_lock);
	ret = set_clock_count_unlocked(value, kp);
	mutex_unlock(&owner_lock);
	return ret;
}
static const struct kernel_param_ops clock_count_ops = {
	.set = set_clock_count,
	.get = param_get_uint,
};
module_param_cb(clock_count, &clock_count_ops, &clock_count, 0600);
MODULE_PARM_DESC(clock_count,
		 "Receiver clocks to enable (0..4); runtime increases only");

static int release_resources(void)
{
	int ret;

	resources_ready = false;
	h713_receiver_edid_unregister();
	while (enabled_clocks)
		clk_disable_unprepare(clocks[--enabled_clocks].clk);
	while (acquired)
		clk_put(clocks[--acquired].clk);
	while (notified)
		dev_pm_genpd_remove_notifier(domain_devs[--notified]);
	while (resumed) {
		struct device *dev = domain_devs[--resumed];

		ret = pm_runtime_put_sync_suspend(dev);
		if (ret < 0)
			pr_warn("h713-hdmi-receiver: suspend failed: %d\n",
				ret);
		pm_runtime_disable(dev);
	}
	while (attached) {
		struct device *dev = domain_devs[attached - 1];

		ret = pm_genpd_remove_device(dev);
		if (ret) {
			/* Keep the device allocated if domain removal is refused. */
			pr_err("h713-hdmi-receiver: domain detach failed: %d\n",
			       ret);
			return ret;
		}
		root_device_unregister(dev);
		attached--;
	}
	return 0;
}

static int initialize_resources(void)
{
	struct device_node *ppu, *ccu;
	struct of_phandle_args spec = { .args_count = 1 };
	unsigned int i;
	int ret;

	if (domain_count > ARRAY_SIZE(domain_devs))
		return -EINVAL;
	if (domain_count < ARRAY_SIZE(domain_devs) && clock_count)
		return -EINVAL;

	ppu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ppu");
	ccu = of_find_compatible_node(NULL, NULL, "allwinner,sun50i-h713-ccu");
	if (!ppu || !ccu || !of_device_is_available(ppu) ||
	    !of_device_is_available(ccu)) {
		ret = -ENODEV;
		goto out_nodes;
	}

	spec.np = ccu;
	for (i = 0; i < ARRAY_SIZE(clocks); i++) {
		spec.args[0] = clock_ids[i];
		clocks[i].clk = of_clk_get_from_provider(&spec);
		if (IS_ERR(clocks[i].clk)) {
			ret = PTR_ERR(clocks[i].clk);
			goto fail;
		}
		acquired++;
	}

	/* Provider indices 1=TVFE and 2=TVCAP, as in experiment 0087. */
	spec.np = ppu;
	for (i = 0; i < domain_count; i++) {
		domain_devs[i] = root_device_register(domain_names[i]);
		if (IS_ERR(domain_devs[i])) {
			ret = PTR_ERR(domain_devs[i]);
			goto fail;
		}
		spec.args[0] = i + 1;
		ret = of_genpd_add_device(&spec, domain_devs[i]);
		if (ret) {
			root_device_unregister(domain_devs[i]);
			goto fail;
		}
		attached++;
		ret = dev_pm_genpd_add_notifier(domain_devs[i],
						&domain_notifiers[i]);
		if (ret)
			goto fail;
		notified++;
		pm_runtime_enable(domain_devs[i]);
		ret = pm_runtime_resume_and_get(domain_devs[i]);
		if (ret < 0) {
			pm_runtime_disable(domain_devs[i]);
			goto fail;
		}
		resumed++;
		pr_info("h713-hdmi-receiver: domain %u resumed\n", i + 1);
	}

	resources_ready = true;
	while (enabled_clocks < clock_count) {
		ret = clk_prepare_enable(clocks[enabled_clocks].clk);
		if (ret)
			goto fail;
		enabled_clocks++;
	}
	pr_info("h713-hdmi-receiver: %u domains and %u receiver clocks held on; no receiver MMIO\n",
		resumed, enabled_clocks);
	ret = 0;
	goto out_nodes;
fail:
	/* Firmware is live: retain partial holds and the module pin on failure. */
out_nodes:
	of_node_put(ccu);
	of_node_put(ppu);
	return ret;
}

int h713_receiver_acquire(void)
{
	int ret = -EAGAIN;
	mutex_lock(&owner_lock);
	if (accepting_clients && !init_error && resources_ready &&
	    enabled_clocks == ARRAY_SIZE(clocks) &&
	    READ_ONCE(h713_receiver_edid_ready) && readl(mips_status) == 1) {
		clients++;
		ret = 0;
	}
	mutex_unlock(&owner_lock);
	return ret;
}
EXPORT_SYMBOL_GPL(h713_receiver_acquire);
void h713_receiver_release(void)
{
	mutex_lock(&owner_lock);
	if (WARN_ON(!clients)) {
		mutex_unlock(&owner_lock);
		return;
	}
	clients--;
	mutex_unlock(&owner_lock);
}
EXPORT_SYMBOL_GPL(h713_receiver_release);

static int release_parked(const char *value, const struct kernel_param *kp)
{
	bool next;
	int ret = kstrtobool(value, &next);
	if (ret)
		return ret;
	if (!next || !mips_status)
		return -EINVAL;
	mutex_lock(&owner_lock);
	if (!firmware_pin ||
	    !h713_receiver_release_allowed(readl(mips_status), clients)) {
		ret = -EBUSY;
		goto out;
	}
	accepting_clients = false;
	ret = release_resources();
	if (ret) {
		init_error = ret;
		goto out;
	}
	firmware_pin = false;
	module_put(THIS_MODULE);
	ret = 0;
out:
	mutex_unlock(&owner_lock);
	return ret;
}
static const struct kernel_param_ops release_ops = { .set = release_parked };
module_param_cb(release_when_parked, &release_ops, NULL, 0200);
MODULE_PARM_DESC(
	release_when_parked,
	"Release firmware lifetime pin only with hardware MIPS status zero and no audio clients; never stops MIPS");

static int __init h713_receiver_init(void)
{
	if (!armed || !live_source3 || clock_count)
		return -EPERM;
	/* Same read-only reset status used by cpu_comm_mips_running/mips-shell. */
	mips_status = ioremap(0x0306101c, 4);
	if (!mips_status)
		return -ENOMEM;
	if (readl(mips_status) != 1) {
		iounmap(mips_status);
		mips_status = NULL;
		return -EPERM;
	}
	__module_get(THIS_MODULE);
	firmware_pin = true;
	init_error = initialize_resources();
	if (!init_error)
		accepting_clients = true;
	else
		pr_err("h713-hdmi-receiver: setup error=%d; partial holds retained until parked/cold boot\n",
		       init_error);
	return 0;
}
static void __exit h713_receiver_exit(void)
{
	/* Reached only after the parked-only interface dropped the firmware pin. */
	release_resources();
	if (mips_status)
		iounmap(mips_status);
}
module_init(h713_receiver_init);
module_exit(h713_receiver_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 firmware-lifetime receiver power and EDID owner");
