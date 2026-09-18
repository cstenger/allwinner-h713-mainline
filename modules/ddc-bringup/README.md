# Temporary HDMI DDC pinmux consumer

The explicit `run=1` module claims PL10–PL15 through pinctrl, with strict
ownership checks, selecting the three stock DDC pin pairs. No raw GPIO writes
or I2C masters are used. IR PL9 and PWM PL7 remain untouched.

Build against the private matching kernel, stage h713-ddc-pins.ko in target
/tmp, then `insmod /tmp/h713-ddc-pins.ko run=1`. On `rmmod h713_ddc_pins`,
all six pins return to gpio_in and ownership/mappings are released. This
restores an input state, rather than the original disabled mux (F). Do not
autoload this bench module or use it while another peripheral owns these pins.

Validated with the [reversible sink trial](../../docs/hdmi-source-detection-validation.md).
