# Status

What works on the H713 mainline stack, and what's next. All hardware results are
on the **HY200 bench board (DDR3)** unless noted — the HY200 QZ713_V2 projector (LPDDR3)
is not risked for bring-up.

_Last updated: 2026-07-19._

## Summary

A fully open boot chain — U-Boot SPL → TF-A BL31 → U-Boot → Linux **6.18.38
LTS** — boots a **64-bit Debian 13** userland from eMMC to a **root login**, on
all four cores, with HS400 eMMC. It boots **standalone** (power-on → Debian, no
host), replacing the vendor Android stack end to end. All hardware-verified on
the HY200 bench board.

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
| DRAM init | ✅ DDR3 (HY200) hardware-proven; LPDDR3 (HY200 QZ713_V2) replay-verified, untested on HW |
| U-Boot proper | ✅ clean `g8a601c1` installed at LBA 16; correct HY200 model, persistent env (raw eMMC @4 MiB), `reset` via PSCI + `wdt` |
| BL31 / PSCI | ✅ `SYSTEM_RESET`, `CPU_ON` (all 4 cores), `CPU_SUSPEND` |
| arm64 Linux | ✅ **mainline 6.18.38 LTS** boots to Debian root login, **4-core SMP** (HW-verified) |
| 32-bit Linux | ✅ boots to userspace, **single-core** (see limitations) |
| eMMC | ✅ HS400, 26-partition Android GPT, read+write verified across reboots |
| Debian 13 rootfs | ✅ signed, key-only image boots from UDISK; growfs, serial autologin, persistent first-boot identity, modules, and sshd HW-verified |
| Standalone boot | ✅ power-on/reset → `boot_a` FIT → Debian, **no host attached** (HW-verified) |
| USB gadget | ✅ serial-default console; opt-in CDC ACM, UMS, and fastboot modes; ACM→fastboot transition and bounded raw bootloader target HW-verified |
| Peripherals (drivers probe) | pinctrl, PWM, PPU (5 power domains), both MMC, EHCI/OHCI ×3, crypto, LRADC, IR, RTC, board-mgr, watchdog |

## Limitations / open items

- **32-bit SMP** — secondaries don't come up for a 32-bit kernel (BL31 brings
  cores up in AArch64; a 32-bit caller needs AArch32 secondaries). arm64 gets
  all four cores, so this is shelved.
- **One peripheral USB controller** — CDC ACM, UMS, and fastboot are deliberate
  successive modes, not a composite gadget. UART remains available throughout.
  Some Linux hosts retain a stale gadget identity across a warm reset; close
  the old device handle and power-cycle the board if re-enumeration is stale.

The July 19 cleanup removed the CCU `MIPS_DIAG` mappings, enabled autofs in the
kernel, modeled the fixed 0.96 V `vdd-sys`/Mali supply from the stock DT, and
installed the clean U-Boot build through a bounded backup/write/readback path.
The rebuilt FIT boots with no diagnostic ioremap, autofs, or dummy-regulator
warning; Cedrus and Panfrost still bind and zero systemd units fail.

## Board matrix

| Board | Silkscreen | DRAM | Bring-up status |
|-------|-----------|------|-----------------|
| Bench | HY200_QZ713DF_A1 | DDR3 (1 GiB) | primary target — everything above validated here |
| Projector | HY200_QZ713_V2 | LPDDR3 (1 GiB) | DRAM replay-verified only; **do not risk it first** |

See [bringup-notes.md](bringup-notes.md) for the driver-level findings behind
this, and [build.md](build.md) / [flash.md](flash.md) to reproduce it.
