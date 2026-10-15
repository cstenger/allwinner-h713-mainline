// SPDX-License-Identifier: GPL-2.0-only
/* DDC pin ownership (PL10-PL15) for the HDMI signal owner, through the
 * pinctrl framework. Returning the pins is an explicit, fallible release=1
 * that keeps the module pinned on failure; exit only drops bookkeeping.
 * The PL8-PL15 mux register is read to prove each transition, never written
 * here: PL9 in the same register is the IR receiver. */
#include <linux/device.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/pinctrl/consumer.h>
#include <linux/pinctrl/machine.h>

#define PL_MUX_REG 0x07022004 /* R_PIO bank L, pins 8-15, 4 bits each */
#define PL10_15(reg) ((reg) >> 8)
#define DDC_MUX 0x222222 /* s_twi0/1/2 */
#define IDLE_MUX 0x000000 /* gpio_in */

static bool run, released, held;
static DEFINE_MUTEX(ddc_lock); /* release is writable before and during init */
static unsigned int original_mux, released_mux;
module_param(run, bool, 0400);
module_param(released, bool, 0444);
module_param(original_mux, uint, 0444);
MODULE_PARM_DESC(original_mux, "PL10-PL15 mux fields (PL10 lowest) before the claim");
module_param(released_mux, uint, 0444);
MODULE_PARM_DESC(released_mux, "PL10-PL15 mux fields read back after release");
static struct device *device;
static struct pinctrl *pins;
static struct pinctrl_state *idle;
static void __iomem *mux;
#define MAP(pin, fn) PIN_MAP_MUX_GROUP("h713-ddc-pins", "ddc", "7022000.pinctrl", pin, fn)
#define IDLE(pin) PIN_MAP_MUX_GROUP("h713-ddc-pins", "idle", "7022000.pinctrl", pin, "gpio_in")
static const struct pinctrl_map maps[] = {
	MAP("PL10", "s_twi0"), MAP("PL11", "s_twi0"),
	MAP("PL12", "s_twi1"), MAP("PL13", "s_twi1"),
	MAP("PL14", "s_twi2"), MAP("PL15", "s_twi2"),
	IDLE("PL10"), IDLE("PL11"), IDLE("PL12"), IDLE("PL13"),
	IDLE("PL14"), IDLE("PL15"),
};

static int release_pins(const char *value, const struct kernel_param *kp)
{
	bool next;
	int ret = kstrtobool(value, &next);

	if (ret || !next)
		return -EINVAL;
	mutex_lock(&ddc_lock);
	if (released || !held) {
		ret = released ? 0 : -EPERM;
		goto out;
	}
	ret = pinctrl_select_state(pins, idle);
	if (ret) {
		pr_err("h713-ddc-pins: input-state restore failed: %d; pins and module retained\n", ret);
		goto out;
	}
	released_mux = PL10_15(readl(mux));
	if (released_mux != IDLE_MUX) {
		pr_err("h713-ddc-pins: PL10-PL15 mux reads %06x after restore, want %06x; pins and module retained\n",
		       released_mux, IDLE_MUX);
		ret = -EIO;
		goto out;
	}
	released = true;
	pr_info("h713-ddc-pins: DDC pins returned to inputs (mux %06x, original %06x%s); module may be removed\n",
		released_mux, original_mux,
		original_mux == IDLE_MUX ? "" : ", differs: pinctrl has no disabled function");
	module_put(THIS_MODULE);
out:
	mutex_unlock(&ddc_lock);
	return ret;
}
static const struct kernel_param_ops release_ops = { .set = release_pins };
module_param_cb(release, &release_ops, NULL, 0200);
MODULE_PARM_DESC(release, "Return PL10-PL15 to inputs and verify the mux; required before rmmod");

static int __init h713_ddc_pins_init(void)
{
	struct pinctrl_state *ddc;
	unsigned int claimed;
	int ret;

	if (!run || !of_machine_is_compatible("allwinner,sun50i-h713"))
		return -EINVAL;
	/* pinctrl owns the region; this mapping only reads it. */
	mux = ioremap(PL_MUX_REG, 4);
	if (!mux)
		return -ENOMEM;
	original_mux = PL10_15(readl(mux));
	ret = pinctrl_register_mappings(maps, ARRAY_SIZE(maps));
	if (ret)
		goto unmap;
	device = root_device_register("h713-ddc-pins");
	if (IS_ERR(device)) {
		ret = PTR_ERR(device);
		goto unregister_maps;
	}
	pins = pinctrl_get(device);
	if (IS_ERR(pins)) {
		ret = PTR_ERR(pins);
		goto unregister_device;
	}
	idle = pinctrl_lookup_state(pins, "idle");
	if (IS_ERR(idle)) {
		ret = PTR_ERR(idle);
		goto put_pins;
	}
	ddc = pinctrl_lookup_state(pins, "ddc");
	if (IS_ERR(ddc)) {
		ret = PTR_ERR(ddc);
		goto put_pins;
	}
	ret = pinctrl_select_state(pins, ddc);
	claimed = PL10_15(readl(mux));
	if (!ret && claimed != DDC_MUX)
		ret = -EIO;
	if (ret) {
		pinctrl_select_state(pins, idle);
		pr_err("h713-ddc-pins: claim failed: %d (mux %06x)\n", ret, claimed);
		goto put_pins;
	}
	__module_get(THIS_MODULE); /* dropped only by a verified release */
	mutex_lock(&ddc_lock);
	held = true;
	mutex_unlock(&ddc_lock);
	pr_info("h713-ddc-pins: PL10-PL15 claimed for three DDC ports (mux %06x, original %06x)\n",
		claimed, original_mux);
	return 0;
put_pins:
	pinctrl_put(pins);
unregister_device:
	root_device_unregister(device);
unregister_maps:
	pinctrl_unregister_mappings(maps);
unmap:
	iounmap(mux);
	return ret;
}

static void __exit h713_ddc_pins_exit(void)
{
	/* Reachable only after release dropped the pin: nothing can fail here. */
	WARN_ON(!released);
	pinctrl_put(pins);
	root_device_unregister(device);
	pinctrl_unregister_mappings(maps);
	iounmap(mux);
	pr_info("h713-ddc-pins: ownership released\n");
}
module_init(h713_ddc_pins_init);
module_exit(h713_ddc_pins_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 DDC pinmux hold with verified, fallible release");
