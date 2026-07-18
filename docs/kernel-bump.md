# Kernel bump: 6.16.7 → 6.18.38 LTS

The kernel is carried as a patch series (`patches/kernel/`) on a pinned
mainline tarball, so a version bump is a **rebase**, not a merge. This is the
planned move off the current hardware-verified `6.16.7` onto the newer
**6.18.38 longterm** kernel.

## Why 6.18.38 (longterm), not 7.1.3 (stable)

- **Support window** — 6.18 is a longterm branch (multi-year fixes); 7.1.3 is a
  regular stable that is superseded within weeks.
- **Smaller rebase** — 6.16 → 6.18 touches far less of the conflict-prone glue
  (CCU, pinctrl, Panfrost/Mali DRM, cedrus, IOMMU) than 6.16 → 7.1.
- It is the first LTS that is *newer* than our 6.16.7 (earlier LTS ~6.12 was
  numerically older — a downgrade).

## Procedure

1. Bump the pin: `KERNEL_VERSION=6.18.38` in `config/versions.env` (keep
   `KERNEL_TARGET` pointing at the next candidate).
2. `build/build.sh kernel` fetches the new tarball and tries the series. Expect
   fuzz/rejects — resolve per subsystem, in `series` order. The arch-neutral
   0001–0022 are the most likely to need touch-ups in CCU/pinctrl/cedrus.
3. Re-derive the two arm64 additions against the new tree:
   - refresh `board/hy310_arm64_defconfig` (new/renamed symbols),
   - re-confirm the `SUN20I_D1_R_CCU` `|| ARM64` Kconfig enable still applies.
4. **Land the board DTS** (the piece missing today): reconstruct
   `sun50i-h713-hy310` for arm64 from the 32-bit board DTS in
   `allwinner-h713-linux/dts/` plus `arm,armv8-timer` and the
   `secure-bl31@40000000 reg=<0x40000000 0x100000> no-map` reservation. Add it
   as a board patch so `build/build.sh kernel` can emit a DTB + bootable FIT.
5. Build `Image` + DTB, wrap as a FIT (`arch=arm64`, load/entry
   `KERNEL_LOAD=0x48000000`), boot on the **HY200 bench board** (never the
   projector first). Confirm 4-core SMP + HS400 eMMC as on 6.16.7.

## Watch items

- The 22 patches were authored against 6.16.7; treat every hunk that fuzzes as a
  review point, not an auto-accept.
- Keep BL31 / U-Boot pins unchanged across the kernel bump — isolate variables.
- Re-run the full boot-to-root-login check (see docs/status.md) before pinning
  6.18.38 as the new `KERNEL_VERSION`.
