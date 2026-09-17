# Removable EDID clock/reset hold

This test module consumes the H713-specific R_CCU EDID clock and reset from
patch 0124. It enables the clock through the clock framework and releases the
reset through the reset framework. It does not access EDID/HPD/wrapper MMIO,
configure pinmux, change clock rates, or program an EDID.

On unload it restores an initially asserted reset and releases its clock
reference. The device tree consumer is test-only: append clock-hold.dtsi to
the private board DTS for a one-time FIT; it is not part of patch 0124 or the
normal boot image. No module is installed or configured to autoload.

Build against the matching private test kernel:

```sh
mkdir -p build/edid-clock
cp modules/edid-bringup/Makefile modules/edid-bringup/h713-edid-clock.c build/edid-clock/
make -C "$PWD/build/kernel-runtime" M="$PWD/build/edid-clock" ARCH=arm64 LLVM=1 modules
```

On the one-time test boot, after staging the module:

```sh
insmod /tmp/h713-edid-clock.ko
cat /sys/kernel/debug/clk/clk_summary
rmmod h713_edid_clock
```

Inspect the platform device's driver link and kernel log to confirm it
actually bound; a platform-driver module can load even if no device binds.
Before unloading, stop any SCP probe and hold SCP reset. Register values and
hardware test results belong in
[the validation record](../../docs/hdmi-edid-clock-validation.md).
