# Status

What works on the H713 mainline stack, and what's next. All hardware results are
on the **HY200 bench board (DDR3)** unless noted — the HY310 projector (LPDDR3)
is not risked for bring-up.

_Last updated: 2026-07-18._

## Summary

A fully open boot chain — U-Boot SPL → TF-A BL31 → U-Boot → Linux — boots a
**64-bit Debian 13** userland from eMMC to a **root login**, on all four cores,
with HS400 eMMC. This replaces the vendor Android stack end to end.

## Boot chain

```
BROM → U-Boot SPL (DRAM init) → TF-A BL31 (EL3, @0x40000000)
     → U-Boot proper (AArch64 EL2) → FIT (bootm):
         arch=arm64 → EL1 AArch64  — native, 4-core SMP     ✅
         arch=arm   → EL1 AArch32  — via el2_to_aarch32      ✅ (single-core)
```

## Works

| Area | State |
|------|-------|
| DRAM init | ✅ DDR3 (HY200) hardware-proven; LPDDR3 (HY310) replay-verified, untested on HW |
| U-Boot proper | ✅ interactive prompt, persistent env (raw eMMC @4 MiB), `reset` via PSCI + `wdt` |
| BL31 / PSCI | ✅ `SYSTEM_RESET`, `CPU_ON` (all 4 cores), `CPU_SUSPEND` |
| arm64 Linux | ✅ mainline 6.16.7 boots to userspace, **4-core SMP** |
| 32-bit Linux | ✅ boots to userspace, **single-core** (see limitations) |
| eMMC | ✅ HS400, 26-partition Android GPT, read+write verified across reboots |
| Debian 13 rootfs | ✅ boots from eMMC UDISK (p26) to root login over serial |
| USB gadget | ✅ CDC ACM console, UMS (`ums 0 mmc 1`), fastboot |
| Peripherals (drivers probe) | pinctrl, PWM, PPU (5 power domains), both MMC, EHCI/OHCI ×3, crypto, LRADC, IR, RTC, board-mgr, watchdog |

## Limitations / open items

- **Boot is not standalone yet.** The kernel FIT is loaded over the CDC console
  each boot rather than from eMMC. Making power-on → Debian autonomous means
  writing the kernel FIT to the `boot_a` partition and setting a U-Boot
  `bootcmd`. _(reorg step #6)_
- **Reproducible kernel build is incomplete.** `build/build.sh kernel` builds a
  bootable `Image` but not a DTB/FIT — the arm64 board DTS
  (`sun50i-h713-hy310`) was a scratch file that wasn't preserved and needs
  reconstruction. _(folded into the 6.18.38 bump — [kernel-bump.md](kernel-bump.md))_
- **Kernel is 6.16.7; bumping to 6.18.38 LTS** is planned. _(reorg step #5)_
- **32-bit SMP** — secondaries don't come up for a 32-bit kernel (BL31 brings
  cores up in AArch64; a 32-bit caller needs AArch32 secondaries). arm64 gets
  all four cores, so this is shelved.
- **rootfs** — 2 GiB image on a 4.6 GiB partition; `resize2fs` to fill it and
  swap the root password for an SSH key before any real use. The bootstrap is
  unsigned (no Debian keyring on the Arch host) — rebuild with a keyring for
  production. See [rootfs.md](rootfs.md).

## Board matrix

| Board | Silkscreen | DRAM | Bring-up status |
|-------|-----------|------|-----------------|
| Bench | HY200 | DDR3 (1 GiB) | primary target — everything above validated here |
| Projector | HY310 | LPDDR3 (1 GiB) | DRAM replay-verified only; **do not risk it first** |

See [bringup-notes.md](bringup-notes.md) for the driver-level findings behind
this, and [build.md](build.md) / [flash.md](flash.md) to reproduce it.
