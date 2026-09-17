# Removable HDMI receiver power hold

`h713-hdmi-power.c` powers TVFE/TVCAP through the existing H713 PPU driver,
and holds the four clock references used by experiment 0087. It requires an
H713 device tree with the PPU and CCU providers enabled. No receiver DT node,
overlay, kernel replacement, or reboot is needed.

The module performs no receiver MMIO, reset operation, IRQ allocation, GPIO
operation, or clock-rate change. Unloading disables its clocks, releases its
runtime-PM references, detaches its two devices, and unregisters them. Other
consumers' references are retained by the normal clock and PM frameworks.

This is an investigation tool, not a V4L2 receiver driver. Do not add it to
production autoload configuration. Only use the kernel build matching the
running Image: this kernel has no module symbol version checks.

## Build and stage

For the first test, a private reflink copy of the matching kernel tree was
created as `build/kernel-runtime`. Copying creates independent files; do not
use symlinks or hardlinks to another agent's writable build tree.

From the HDMI worktree root:

```sh
mkdir -p build/hdmi-power
cp modules/hdmi-bringup/Makefile modules/hdmi-bringup/h713-hdmi-power.c build/hdmi-power/
make -C "$PWD/build/kernel-runtime" M="$PWD/build/hdmi-power" ARCH=arm64 LLVM=1 modules
modinfo build/hdmi-power/h713-hdmi-power.ko
scp -F /dev/null build/hdmi-power/h713-hdmi-power.ko root@192.168.4.1:/tmp/h713-hdmi-power.ko
```

Verify the kernel build version, vermagic and transferred checksum before
loading. On the target:

```sh
insmod /tmp/h713-hdmi-power.ko
cat /sys/kernel/debug/pm_genpd/pm_genpd_summary
```

TVFE and TVCAP should be `on`, with `h713-hdmi-tvfe` and `h713-hdmi-tvcap`
active. This establishes power ownership before any receiver access.

To release the hold:

```sh
rmmod h713_hdmi_power
cat /sys/kernel/debug/pm_genpd/pm_genpd_summary
```

Do not perform receiver reads after removing the power hold. The historically
hard-locking `0x07091014` access is not made safe by this module.

## Hardware validation, 2026-09-17

Running kernel and build tree both identify:

`6.18.38`, `#1 SMP Wed Sep 16 00:16:22 PDT 2026`

Module vermagic: `6.18.38 SMP mod_unload aarch64`.

Transferred module SHA256:

`1e343beab6a12f657095b523ac4074cff2bb9d2f5cd591c220ef26bd927fa9fb`

- Built cleanly with Clang/LLD 22.1.8 against the matching private build copy.
- Initial load succeeded; both domains changed from `off-0` to `on`.
- All four clock prepare/enable counts changed from 0/0 to 1/1.
  `bus-cap-300m` still displayed hardware-enabled `N`; reference counts alone
  are not proof of every hardware gate. No clock rate was changed.
- Unload succeeded; both domains returned to `off-0`, and both temporary
  root devices disappeared. Reload succeeded and restored active holds.
- The eight known THDMIRX reads at `0x050c0000`–`0x050c001c` completed and
  matched experiment 0087, including `0x70f80029`, `0xfe000115`, and
  `0x03ff00ff`. No receiver writes were made.
- SSH remained available; LVDS remained `connected`, and the H713 codec
  card remained listed. Video/audio playback quality was not tested.
- The workstation's connected HDMI output remained `disconnected`, with
  a zero-byte EDID. Power bring-up alone does not solve HPD/DDC.

Final target state: module loaded from `/tmp`, TVFE/TVCAP held on. Nothing
was installed in the module tree or configured to load after a reboot.
Serial was released after each command batch. Claude's checkout and its build
files were not modified.
