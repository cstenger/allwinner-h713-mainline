// SPDX-License-Identifier: GPL-2.0-only
/* DDC pin ownership (PL10-PL15) for the HDMI signal owner. The pins and
 * their states live in the device tree (h713-lab,ddc-pins, kernel patch
 * 0179): binding this driver applies "default" (s_twi0/1/2); release=1
 * applies "sleep" (io_disabled, the reset state, patch 0178), verifies it
 * and only then lets the module go, which is the only way out. The PL8-PL15
 * mux register is read to prove each transition, never written here: PL9 in
 * the same register is the IR receiver. */
#include <linux/io.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/pinctrl/consumer.h>
#include <linux/platform_device.h>

#define PL_MUX_REG 0x07022004 /* R_PIO bank L, pins 8-15, 4 bits each */
#define PL10_15(reg) ((reg) >> 8)
#define DDC_MUX 0x222222 /* s_twi0/1/2 */
#define IDLE_MUX 0xffffff /* io_disabled */

static bool run, released, held;
static unsigned int original_mux, released_mux;
module_param(run, bool, 0400);
module_param(released, bool, 0444);
module_param(original_mux, uint, 0444);
MODULE_PARM_DESC(original_mux, "PL10-PL15 mux fields (PL10 lowest) before the claim");
module_param(released_mux, uint, 0444);
MODULE_PARM_DESC(released_mux, "PL10-PL15 mux fields read back after release");
static DEFINE_MUTEX(ddc_lock); /* release is writable before and during init */
static struct pinctrl *pins;
static struct pinctrl_state *sleep;
static void __iomem *mux;

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
	ret = pinctrl_select_state(pins, sleep);
	if (ret) {
		pr_err("h713-ddc-pins: sleep-state restore failed: %d; pins and module retained\n", ret);
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
	pr_info("h713-ddc-pins: DDC pins returned to io_disabled (mux %06x, original %06x%s); module may be removed\n",
		released_mux, original_mux,
		original_mux == IDLE_MUX ? "" : ", differs from the original");
	module_put(THIS_MODULE);
out:
	mutex_unlock(&ddc_lock);
	return ret;
}
static const struct kernel_param_ops release_ops = { .set = release_pins };
module_param_cb(release, &release_ops, NULL, 0200);
MODULE_PARM_DESC(release, "Return PL10-PL15 to io_disabled and verify the mux; required before rmmod");

/* The driver core has already applied "default" when this runs. */
static int h713_ddc_pins_probe(struct platform_device *pdev)
{
	unsigned int claimed = PL10_15(readl(mux));
	int ret;

	pins = devm_pinctrl_get(&pdev->dev);
	if (IS_ERR(pins))
		return PTR_ERR(pins);
	sleep = pinctrl_lookup_state(pins, PINCTRL_STATE_SLEEP);
	if (IS_ERR(sleep))
		return PTR_ERR(sleep);
	if (claimed != DDC_MUX) {
		ret = pinctrl_select_state(pins, sleep);
		pr_err("h713-ddc-pins: claim reads mux %06x, want %06x; sleep restore %d\n",
		       claimed, DDC_MUX, ret);
		return -EIO;
	}
	__module_get(THIS_MODULE); /* dropped only by a verified release */
	mutex_lock(&ddc_lock);
	held = true;
	mutex_unlock(&ddc_lock);
	pr_info("h713-ddc-pins: PL10-PL15 claimed for three DDC ports (mux %06x, original %06x)\n",
		claimed, original_mux);
	return 0;
}

static const struct of_device_id h713_ddc_pins_match[] = {
	{ .compatible = "h713-lab,ddc-pins" },
	{ }
};

static struct platform_driver h713_ddc_pins_driver = {
	.probe = h713_ddc_pins_probe,
	.driver = {
		.name = "h713-ddc-pins",
		.of_match_table = h713_ddc_pins_match,
		.suppress_bind_attrs = true, /* no sysfs unbind around release */
	},
};

static int __init h713_ddc_pins_init(void)
{
	int ret;

	if (!run || !of_machine_is_compatible("allwinner,sun50i-h713"))
		return -EINVAL;
	/* r_pio owns the region; this mapping only reads it. */
	mux = ioremap(PL_MUX_REG, 4);
	if (!mux)
		return -ENOMEM;
	original_mux = PL10_15(readl(mux)); /* before binding applies "default" */
	ret = platform_driver_register(&h713_ddc_pins_driver);
	if (ret)
		goto unmap;
	if (!held) { /* no h713-lab,ddc-pins node (older DTB) or a failed claim */
		pr_err("h713-ddc-pins: no DDC pin node bound; nothing claimed\n");
		ret = -ENODEV;
		goto unregister;
	}
	return 0;
unregister:
	platform_driver_unregister(&h713_ddc_pins_driver);
unmap:
	iounmap(mux);
	return ret;
}

static void __exit h713_ddc_pins_exit(void)
{
	/* Reachable only after release dropped the pin: nothing can fail here,
	 * and unbinding only drops pin ownership, never the mux. */
	WARN_ON(!released);
	platform_driver_unregister(&h713_ddc_pins_driver);
	iounmap(mux);
	pr_info("h713-ddc-pins: ownership released\n");
}
module_init(h713_ddc_pins_init);
module_exit(h713_ddc_pins_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 DDC pin owner via device-tree pinctrl states, verified fallible release");
