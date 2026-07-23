# Status

What works on the H713 mainline stack, and what's next. All hardware results are
on the **HY200 bench board (DDR3)** unless noted — the HY200 QZ713_V2 projector (LPDDR3)
is not risked for bring-up.

_Last updated: 2026-07-23._

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
| CPU frequency/thermal | ✅ PWM DVFS from 480 MHz/0.90 V through 1416 MHz/1.10 V; full-range transitions and peak load HW-verified; cpufreq cooling device backs 75/85 C passive trips |
| Reboot → fastboot / U-Boot | ✅ **done, both modes HW-validated (2026-07-23).** Two `nvmem-reboot-mode` modes over RTC GP7: `reboot fastboot` (magic `0xfa57b007`) → U-Boot `preboot` → fastboot, and `reboot bootloader` (magic `0xb007c0de`) → `preboot` sets `bootdelay -1` → U-Boot `=>` prompt — both confirmed console-free on the bench. `RTC_DRV_SUN6I` owns the region and exposes GP7 as an nvmem cell (`nvmem-cells` → `reboot-mode-magic@1c`); the old overlapping `syscon-reboot-mode` is gone. |
| Peripherals (drivers probe) | pinctrl, PWM, PPU (5 power domains), both MMC, EHCI/OHCI ×3, crypto, LRADC, IR, board-mgr, watchdog, **RTC** (`sun6i-rtc`, enabled — the canonical osc32k/iosc clock provider and the GP-register nvmem device, both HW-confirmed; `rtc0` reads back but the RTC is unset at first boot, and full set/read timekeeping was not exercised on the minimal bench rootfs — no `hwclock`). |

## Limitations / open items

- **32-bit SMP** — secondaries don't come up for a 32-bit kernel (BL31 brings
  cores up in AArch64; a 32-bit caller needs AArch32 secondaries). arm64 gets
  all four cores, so this is shelved.
- **One peripheral USB controller** — CDC ACM, UMS, and fastboot are deliberate
  successive modes, not a composite gadget. UART remains available throughout.
  Some Linux hosts retain a stale gadget identity across a warm reset; close
  the old device handle and power-cycle the board if re-enumeration is stale.
- **Main-PWM output validated; cooling fan is a power-enable, not PWM.** Patch
  0007's second-generation PWM map (previously proven only indirectly via the
  R_PWM `vdd-cpu` rail, patch 0028) was confirmed on real output during fan
  bring-up: on the bench, main `pwm@2000c00` channel 0 read back `enabled,
  39958/40000 ns` in `/sys/kernel/debug/pwm` with PH17 muxed to `pwm0`. But the
  fan itself is a **3-wire (VCC/GND/tach) on/off part**, not PWM-speed-controlled
  — DMM on the header showed the tach line at its 3.3 V pull-up (sense wired) and
  the +V pin floating (~1.1 V, decaying = unpowered). It stayed dead because the
  `fan_power_hog` for PB5 (shared backlight/fan enable) was malformed (linear
  `<37>` on a 3-cell controller → hog skipped → rail off). Patch 0030 fixes the
  hog to `<1 5>`; the earlier `pwm-fan`-on-PWM0 model was dropped (PH17 is the
  tach). **Bench-confirmed: the fan spins.** The fan and the LED backlight now
  both come up **at power-on from U-Boot** — `board_init` drives the shared PB5
  fan/backlight-enable under a bench-only `CONFIG_H713_POWERON_LIGHT_FAN`, so the
  panel is lit and cooled from reset (projector-as-boot-monitor), with the fan a
  hard interlock for the light. **Backlight brightness is still open:** the light
  is dim and PB4/PWM2 (the projector `panel_pwm_ch`) was proven *not* to control
  it — a correct running 25 kHz PWM on PB4 changed nothing — so brightness is set
  by an LED-driver mechanism yet to be RE'd, and is a U-Boot-level TODO. Panel
  backlight (channel 2 / PB4) also still needs its own re-verification.

The July 19 cleanup removed the CCU `MIPS_DIAG` mappings, enabled autofs in the
kernel, modeled the fixed 0.96 V `vdd-sys`/Mali supply from the stock DT, and
installed the clean U-Boot build through a bounded backup/write/readback path.
The rebuilt FIT boots with no diagnostic ioremap, autofs, or dummy-regulator
warning; Cedrus and Panfrost still bind and zero systemd units fail.

The July 21 thermal work added safe PLL_CPUX clock transitions, recovered the
R_PWM functional clock from the captured stock kernel, and wired the PL7 PWM
to VDD-CPU. DMM measurements validated 0.909 V for a 0.901 V request, 1.005 V
for a 0.999 V request, and 1.107 V idle for a 1.1005 V request. Every OPP from
480 to 1416 MHz transitions correctly. A two-minute four-core peak-frequency
load held 1416 MHz, raised the measured rail only to 1.127 V (below the 1.16 V
regulator ceiling), stayed below the 75 C passive trip at 68 C, and produced no
thermal, cpufreq, OPP, PWM, clock, or PLL errors. Both 75/85 C passive trips
are bound to the eight-state cpufreq cooling device.

The July 23 reboot→fastboot work finished the mechanism in code. `RTC_DRV_SUN6I`
is now enabled: the H713 RTC (H6-compatible block at `0x07090000`) gets a real
`sun6i-rtc` driver, which registers the previously-orphaned osc32k/iosc clocks,
provides timekeeping, and exposes the eight general-purpose registers as a
battery-backed nvmem device. The reboot handoff moved off the `syscon-reboot-mode`
window (which overlapped the RTC register region) onto **`nvmem-reboot-mode`** over
a fixed nvmem cell (`reboot-mode-magic@1c` → GP7, physical `0x0709011c`) defined
as a child of the rtc node; mainline's `add_legacy_fixed_of_cells` makes the cell
phandle-referenceable with no driver change. The magic (`0xfa57b007`), the
physical address, and the entire U-Boot side are unchanged, so no U-Boot rework
was needed. **Hardware-validated on the bench (2026-07-23):** the new kernel
boots to Debian, `sun6i-rtc` binds as `rtc0`, the RTC nvmem device
(`7090000.rtc/nvmem0`) and the `reboot-mode-magic@1c` cell both register, and the
`nvmem-reboot-mode` consumer binds to that cell; the reboot trigger then landed
the board in U-Boot fastboot with no console interaction (host saw the fastboot
device). One loose end, not blocking: `rtc0` read back as unset at first boot
(hctosys `unable to read` = an invalid, never-set time — expected), and full
set/read timekeeping was not exercised because the minimal rootfs ships no
`hwclock` (use `timedatectl` or add util-linux to check it later).

A follow-on refinement (2026-07-23) split the single handoff into **two modes**
so the two reboot verbs mean different things: `reboot fastboot` keeps magic
`0xfa57b007` → fastboot, while `reboot bootloader` now uses magic `0xb007c0de`
and, in `preboot`, runs `setenv bootdelay -1` to fall through to the U-Boot
prompt instead of fastboot. The DTS `reboot-mode` node carries both
(`mode-fastboot`/`mode-bootloader`); the U-Boot side is the runtime `preboot` env
(MMC @ `0x400000`):
`if itest.l *0x0709011c == 0xfa57b007; then mw.l 0x0709011c 0; run fastboot_mode; elif itest.l *0x0709011c == 0xb007c0de; then mw.l 0x0709011c 0; setenv bootdelay -1; fi; usb start`.
Both verbs were **hardware-validated on the bench (2026-07-23):** `reboot
fastboot` lands in fastboot and `reboot bootloader` drops to the U-Boot `=>`
prompt, each console-free.

## Board matrix

| Board | Silkscreen | DRAM | Bring-up status |
|-------|-----------|------|-----------------|
| Bench | HY200_QZ713DF_A1 | DDR3 (1 GiB) | primary target — everything above validated here |
| Projector | HY200_QZ713_V2 | LPDDR3 (1 GiB) | DRAM replay-verified only; **do not risk it first** |

See [bringup-notes.md](bringup-notes.md) for the driver-level findings behind
this, and [build.md](build.md) / [flash.md](flash.md) to reproduce it.
