# H713 kernel patches

The H713 has no mainline kernel support yet, so the kernel is carried as a
**patch series applied to a pinned mainline tarball** (see
`config/versions.env` → `KERNEL_VERSION`), rather than a fork. `build/build.sh
kernel` fetches `linux-$KERNEL_VERSION`, applies these in `series` order with
`patch -p1`, then builds with `board/hy310_arm64_defconfig`.

## Provenance

Patches **0001–0022** are the H713 driver series by **well0nez**
(`github`/ `~/Projects/allwinner-h713-linux`), **GPL-2.0**, carried here
verbatim **with attribution**. They are architecture-neutral (only `drivers/`
and `include/dt-bindings/`, no `arch/`), which is why the same series that
backed the 32-bit port also applies cleanly to the arm64 build:

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

- **`board/hy310_arm64_defconfig`** — the arm64 defconfig (base arm64 defconfig
  slimmed, plus the H713 drivers above + PPU/LRADC/R-CCU). Copied into
  `arch/arm64/configs/` by the build. *(ours)*
- **R-CCU on arm64** — upstream gates `SUN20I_D1_R_CCU` to
  `MACH_SUN8I || RISCV || COMPILE_TEST`; the H713 reuses the D1 R-CCU, so the
  build adds `|| ARM64` to that `depends` (without it R-PIO / PPU power domains
  never probe). Applied as a scripted one-liner by `build/build.sh` today; to
  be promoted to a proper numbered patch at upstream-submission time. *(ours)*

## Not yet folded in — the board DTS (closes with the 6.18.38 bump)

The arm64 board **device tree** (`sun50i-h713-hy310` with `arm,armv8-timer`
instead of armv7, a `secure-bl31@40000000 reg=<0x40000000 0x100000> no-map`
reserved-memory node, and baked bootargs) is **not yet in this series** — the
last working copy was a standalone scratch DTS that was not preserved. It must
be reconstructed from the 32-bit board DTS in `allwinner-h713-linux/dts/` plus
those arm64 tweaks. Until then `build/build.sh kernel` builds a bootable
**Image** (drivers + defconfig) but stops short of a DTB / bootable FIT.

This is the natural first task of the **6.18.38 LTS rebase**
(`KERNEL_TARGET`): re-verify 0001–0022 against the new tree, re-derive the
arm64 defconfig + R-CCU patch, and land the board DTS — see
[../../docs/kernel-bump.md](../../docs/kernel-bump.md).
