# Porting the H713 IOMMU

The H713 has a working IOMMU that mainline does not drive. Nothing translates
DMA on this board today, which is why a decoder bug that every other Allwinner
SoC contains harmlessly (cedrus keeps writing after its buffers are freed —
`docs/vaapi-scope.md`) instead corrupts arbitrary kernel memory here. This
records what has been verified about the block, so the port starts from measured
facts rather than from the H6 driver's assumptions.

## Verified against board B's own eMMC, 2026-08-17

Everything below is read out of `local/h713-lab/captures/board-b/`, the
pre-modification capture of *this* unit, not from the retail OTA. The kernel DTB
lives at offset `0x00d1b400` in the capture (second copy at `0x0111f400`; the
boot package is stored twice) and is **byte-identical** to the retail image's
`sunxi.fex` — that file is simply the same 69380-byte blob zero-padded to 73728.
So the retail firmware and this board agree, and either can be used as reference.

```
mmu_aw: iommu@2010000 {
        compatible = "allwinner,sunxi-iommu";
        reg = <0x0 0x2010000 0x0 0x1000>;
        interrupts = <0 0x47 4>;        /* SPI 71 */
        interrupt-names = "iommu-irq";
        clocks = <&ccu 0x30>;           /* index 48 */
        clock-names = "iommu";
        #iommu-cells = <2>;
};
```

### The masters, as wired on this board

| device | node | `iommus` | notes |
| --- | --- | --- | --- |
| `ve` | `ve@1c0e000` | `<&mmu_aw 0 1>` | **our cedrus** |
| `ve1` | `ve1@1c0e000` | `<&mmu_aw 1 1>` | second VE view |
| `ge2d` | `ge2d@5240000` | `<&mmu_aw 2 0>` | |
| `dec` | `dec@5600000` | `<&mmu_aw 2 0>` | **our AFBD display** |
| `tvdisp` | `tvdisp@5000000` | `<&mmu_aw 3 1>` | |
| `tvcap` | `tvcap@6800000` | `<&mmu_aw 4 1>` | |
| `av1` | `av1@1c0d000` | `<&mmu_aw 5 1>` | AV1 decoder |
| `audbrg`, `demux`, `dtmb` | | `<&mmu_aw 6 1>` | |

Both engines in the combination that corrupts memory here — the video decoder
and the display — are translated in the vendor stack. That is very likely why
the vendor never had to notice cedrus's missing reset.

The second cell is not a master ID. Masters run 0–6 in the first cell; the
second is 0 or 1 and its meaning still needs establishing (bypass/permission or
a sub-port selector are the obvious candidates — check `sunxi_iommu_of_xlate`).

## The block is register-compatible with mainline's H6 driver

From the vendor `vmlinux` — extracted from `update.img` member `vmlinux.fex` at
offset 2877440, length 105860275, bzip2 → tar → a 220 MB ARM 32-bit 5.4.99
image **with full symbols**. Disassembling `sunxi_iommu_irq` shows it reading
`[base+0x108]`, `[base+0x180]` and `[base+0x184]`, which are mainline's
`IOMMU_INT_STA_REG`, `IOMMU_L1PG_INT_REG` and `IOMMU_L2PG_INT_REG` exactly.
Across the whole driver the offsets touched are:

| offset | mainline `sun50i-iommu.c` name | |
| --- | --- | --- |
| 0x010 | `IOMMU_RESET_REG` | ✓ |
| 0x020 | `IOMMU_ENABLE_REG` | ✓ |
| 0x030 | `IOMMU_BYPASS_REG` | ✓ |
| 0x040 | `IOMMU_AUTO_GATING_REG` | ✓ |
| 0x060 / 0x070 / 0x080 | TLB enable / prefetch / flush | ✓ |
| 0x098 / 0x0a8 | `TLB_IVLD_ENABLE` / `PC_IVLD_ENABLE` | ✓ |
| 0x108 | `IOMMU_INT_STA_REG` | ✓ |
| 0x180 / 0x184 | `L1PG_INT` / `L2PG_INT` | ✓ |
| 0x160–0x174, 0x1c0, 0x1dc, 0x1f0 | — | **not in the H6 map** |

So this is the same IP with extensions, not a different block. The port is
therefore an extension of `drivers/iommu/sun50i-iommu.c` rather than a new
driver. The 0x160–0x174 run is most likely the per-master `INT_ERR_DATA`
window widened for seven masters (H6 has fewer); 0x1c0/0x1dc/0x1f0 are
unidentified and should be treated as must-preserve until they are.

## What still has to be established before writing code

1. **The CCU gate.** Patch 0024 warns that probing an ungated block hangs this
   interconnect, so read the gate first — the CCU is always clocked, so reading
   it is free. The vendor clock index is `<&ccu 0x30>`; map that to our H713 CCU
   driver's gate and confirm the reset line too.
2. **Whether the block responds at all.** With the gate on, read a known
   register (e.g. `IOMMU_ENABLE_REG`) and confirm it is not all-zero, which is
   what `0x030f0000` gives today.
3. **The binding.** The vendor is `#iommu-cells = <2>`; mainline's `sun50i-iommu`
   is `<1>`. Either extend the driver's `of_xlate` to accept two cells for a new
   `allwinner,sun50i-h713-iommu` compatible, or normalise to one cell in our DT
   and document why. Decide this before writing the DTS, because it is the part
   that has to go upstream.
4. **Master count and `DM_AUT_CTRL` layout.** H6's driver assumes a master count
   in its domain/permission registers (`0x0b0 + (d/2)*4`); seven masters here may
   or may not fit that layout.

## Why this is worth doing

Beyond correctness: with the IOMMU on, a stray write from the VE becomes an
IOMMU fault naming the offending master, printed once, instead of six different
kernel structures corrupted across five reproductions and a session spent
bisecting. It converts this entire class of bug from archaeology into a log
line.
