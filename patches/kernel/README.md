# H713 kernel patches

The H713 has no mainline kernel support yet, so the kernel is carried as a
**patch series applied to a pinned mainline tarball** (see
`config/versions.env` → `KERNEL_VERSION`), rather than a fork. `build/build.sh
kernel` fetches `linux-$KERNEL_VERSION`, applies these in `series` order with
`patch -p1`, then builds with `board/hy200_qz713df_a1_defconfig`.

## Provenance

Patches **0001–0022** are the H713 driver series by **well0nez**
(`github`/ `~/Projects/allwinner-h713-linux`), **GPL-2.0**, carried here **with
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

- **`board/hy200_qz713df_a1_defconfig`** — the arm64 defconfig (base arm64 defconfig
  slimmed, plus the H713 drivers above + PPU/LRADC/R-CCU). Copied into
  `arch/arm64/configs/` by the build. *(ours)*
- **0023 — R-CCU on arm64** — upstream gates `SUN20I_D1_R_CCU` to
  `MACH_SUN8I || RISCV || COMPILE_TEST`; the H713 reuses the D1 R-CCU, so this
  adds `|| ARM64` to that `depends` (without it R-PIO / PPU power domains never
  probe). A proper patch, anchored to the `SUN20I_D1_R_CCU` block so it does not
  also touch `SUN20I_D1_CCU`. *(ours)*

- **0024 — arm64 board DTS** (`arch/arm64/boot/dts/allwinner/sun50i-h713-hy200-qz713df-a1.dts`
  + its Makefile entry). Reconstructed from well0nez's 32-bit board DTS
  (GPL-2.0, with attribution) with three arm64 changes: `arm,armv7-timer` →
  `arm,armv8-timer`, a `secure-bl31@40000000 reg=<0x40000000 0x100000> no-map`
  reservation so the kernel leaves TF-A BL31 alone, and eMMC-root bootargs.
  `#address-cells = <1>` is kept (all addresses fit in 32 bits). *(ours)*

With 0024 in place `build/build.sh kernel` emits the DTB and a bootable FIT
(`build/out/h713-kernel.fit`: gzip Image + DTB, load/entry `0x48000000`).
