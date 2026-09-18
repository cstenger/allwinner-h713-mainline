// SPDX-License-Identifier: GPL-2.0-only
/* Test-only DDC pin ownership through the pinctrl framework. */
#include <linux/device.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/pinctrl/consumer.h>
#include <linux/pinctrl/machine.h>

static bool run;
module_param(run, bool, 0400);
static struct device *device;
static struct pinctrl *pins;
static struct pinctrl_state *idle;
#define MAP(pin, fn) PIN_MAP_MUX_GROUP("h713-ddc-pins", "ddc", "7022000.pinctrl", pin, fn)
#define IDLE(pin) PIN_MAP_MUX_GROUP("h713-ddc-pins", "idle", "7022000.pinctrl", pin, "gpio_in")
static const struct pinctrl_map maps[] = {
	MAP("PL10", "s_twi0"), MAP("PL11", "s_twi0"),
	MAP("PL12", "s_twi1"), MAP("PL13", "s_twi1"),
	MAP("PL14", "s_twi2"), MAP("PL15", "s_twi2"),
	IDLE("PL10"), IDLE("PL11"), IDLE("PL12"), IDLE("PL13"),
	IDLE("PL14"), IDLE("PL15"),
};

static int __init h713_ddc_pins_init(void)
{
	struct pinctrl_state *ddc;
	int ret;

	if (!run || !of_machine_is_compatible("allwinner,sun50i-h713"))
		return -EINVAL;
	ret = pinctrl_register_mappings(maps, ARRAY_SIZE(maps));
	if (ret)
		return ret;
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
	if (ret) {
		pinctrl_select_state(pins, idle);
		goto put_pins;
	}
	pr_info("h713-ddc-pins: PL10-PL15 claimed and selected for three DDC ports\n");
	return 0;
put_pins:
	pinctrl_put(pins);
unregister_device:
	root_device_unregister(device);
unregister_maps:
	pinctrl_unregister_mappings(maps);
	return ret;
}

static void __exit h713_ddc_pins_exit(void)
{
	int ret = pinctrl_select_state(pins, idle);

	if (ret)
		pr_err("h713-ddc-pins: input-state restore failed: %d\n", ret);
	pinctrl_put(pins);
	root_device_unregister(device);
	pinctrl_unregister_mappings(maps);
	pr_info("h713-ddc-pins: DDC pins returned to inputs and ownership released\n");
}
module_init(h713_ddc_pins_init);
module_exit(h713_ddc_pins_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Removable H713 DDC pinmux hold through kernel pinctrl");
