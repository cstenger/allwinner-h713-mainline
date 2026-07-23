# H713 kernel patches

The H713 has no mainline kernel support yet, so the kernel is carried as a
**patch series applied to a pinned mainline tarball** (see
`config/versions.env` → `KERNEL_VERSION`), rather than a fork. `build/build.sh
kernel` fetches `linux-$KERNEL_VERSION`, applies these in `series` order with
`patch -p1`, then builds with `board/hy200_qz713df_a1_defconfig`.

## Provenance

Patches **0001–0022** are the H713 driver series by **well0nez**
(`github`/ `local/allwinner-h713-linux`), **GPL-2.0**, carried here **with
attribution**. They are architecture-neutral (only `drivers/` and
`include/dt-bindings/`, no `arch/`), which is why the same series that backed
the 32-bit port also builds on arm64. Six were adapted from their original
6.16 form to apply/build against the pinned kernel — see the table in
[../../docs/kernel-bump.md](../../docs/kernel-bump.md); the rest are unchanged.

| # | Area |
|---|------|
| 0001 | clk: sunxi-ng H713 CCU driver |
| 0002–0004, 0018 | pinctrl: H713 PIO / R-PIO / irq-mux / PB bank |
| 0005 | phy: sun4i-usb H713 PMU bit0 quirk |
| 0006 | mmc: sunxi H713 (v5p3x) |
| 0007 | pwm: sun8i 8-channel |
| 0008–0009 | misc: HY310 board-mgr / keystone-motor |
| 0010–0014 | misc/soc: mipsloader, nsi, tvtop, decd, cpu-comm IPC |
| 0015–0016 | H713 driver Kconfig + clock/reset dt-binding IDs |
| 0017 | iommu: sun50i decouple ARM_DMA_USE_IOMMU |
| 0019 | iio-adc: H713 LRADC |
| 0020 | pmdomain: H713 PPU |
| 0021 | media: sunxi-cir H713 vendor init |
| 0022 | staging: cedrus H713 VE3 clock/reset |

## Our arm64 additions

- **`board/hy200_qz713df_a1_defconfig`** — the bench arm64 defconfig (base
  arm64 defconfig slimmed, plus the SoC-general H713 drivers + PPU/LRADC/R-CCU).
  Projector-only vendor drivers (`board-mgr`, keystone motor, `tvtop`, `decd`,
  and `cpu-comm`) are deliberately disabled here; they need a separate,
  hardware-tested projector configuration. In particular, `cpu-comm` retains
  the vendor 32-bit shared-pointer ABI and is not safe to enable in an arm64
  kernel until that address model is ported. Copied into
  `arch/arm64/configs/` by the build. *(ours)*
- **0023 — R-CCU on arm64** — upstream gates `SUN20I_D1_R_CCU` to
  `MACH_SUN8I || RISCV || COMPILE_TEST`; the H713 reuses the D1 R-CCU, so this
  adds `|| ARM64` to that `depends` (without it R-PIO / PPU power domains never
  probe). A proper patch, anchored to the `SUN20I_D1_R_CCU` block so it does not
  also touch `SUN20I_D1_CCU`. *(ours)*

- **0024 — arm64 SoC + board devicetrees.** The reconstructed vendor tree is
  split into shared `sun50i-h713.dtsi`, a clean
  `sun50i-h713-hy200-qz713df-a1.dts` bench overlay that disables projector-only
  hardware, and `sun50i-h713-hy200-qz713-v2.dts` for the projector. Both DTBs
  have Makefile entries. Arm64 changes include `arm,armv8-timer` and a
  `secure-bl31@40000000` reservation so Linux leaves TF-A BL31 alone. The
  projector definition is structural only and remains untested on hardware.
  *(ours, reconstructed from well0nez's GPL-2.0 DTS with attribution)*

- **0025 — safe CPU clock transitions.** Registers the CPUX mux and PLL
  notifiers used by cpufreq. CPUX temporarily switches to the 24 MHz oscillator
  while PLL_CPUX is reprogrammed, and the notifier enables the H713 PLL lock
  detector with `LOCK_ENABLE` (BIT 29). *(ours, hardware verified)*

- **0026 — CPU cpufreq foundation.** Adds the shared initial OPP table from 480
  to 1008 MHz and binds it to all four Cortex-A53s, providing the cooling device
  required by the 75/85 C passive trips. Patch 0028 upgrades this table to full
  voltage scaling. *(ours, hardware verified)*

- **0027 — H713 R-PWM clocks.** Exports the recovered R-PWM functional mux/gate
  at R-CCU offset `0x130`, plus its bus gate and reset at `0x13c`. Both clocks
  are required for the PL7 VDD-CPU PWM output. *(ours, hardware verified)*

- **0028 — voltage-scaling CPU DVFS.** Models VDD-CPU as the stock R-PWM
  channel 1 / PL7 regulator and extends the default-bin OPP table from 480 MHz
  at 0.90 V through 1416 MHz at 1.10 V. DMM measurements validate the complete
  PWM transfer direction and representative low/mid/high voltage points; all
  transitions, the thermal bindings, and a two-minute four-core peak load are
  hardware verified. *(ours, hardware verified)*

- **0030 — fix fan-power gpio-hog cell count.** The bench cooling fan is a
  3-wire (VCC/GND/tach) on/off fan, not a PWM-speed part, and it never spun
  because its +V rail was never enabled: the `fan_power_hog` for PB5 (the shared
  backlight/fan power enable) used `gpios = <37 ...>` — a linear GPIO number on a
  `#gpio-cells = <3>` sunxi controller, which gpiolib can't parse, so the hog was
  silently skipped (`/sys/kernel/debug/gpio` showed zero claimed lines on
  gpiochip0). Corrects it to the 3-cell `<1 5 GPIO_ACTIVE_HIGH>` (bank B, pin 5),
  which also restores the projector's shared backlight-enable rail. Supersedes an
  earlier `pwm-fan`-on-PWM0 attempt: PWM0/PH17 was verified emitting on real
  silicon (debugfs register read-back + pinmux), which *did* validate the
  corrected main-PWM map (0007), but PH17 is the fan's tachometer, not a control
  line, so PWM drive does nothing to a 3-wire motor. `pwm-fan`, its `&pwm` mux,
  and `CONFIG_HWMON`/`CONFIG_SENSORS_PWM_FAN` are dropped. **Bench-confirmed: the
  fan spins**, and it (plus the LED backlight) now comes up at power-on from
  U-Boot — `board_init` drives the shared PB5 enable, so the panel is lit and
  cooled from reset with the fan a hard interlock. Backlight *brightness* is
  still open: PB4/PWM2 was proven not to control this LED (a running 25 kHz PWM
  changed nothing), so it needs a U-Boot-level RE — see the roadmap.
  *(ours, hardware-confirmed)*

With these patches in place `build/build.sh kernel` emits both DTBs and a bench-only
bootable FIT (`build/out/h713-kernel.fit`: gzip Image + bench DTB, load/entry
`0x48000000`).
