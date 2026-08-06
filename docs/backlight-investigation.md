# H713 projector backlight: the case so far

**Status: OPEN.** Written 2026-08-05 for external review. This consolidates a
thread that runs across `docs/mips-display-recovery.md` (300 KB, chronological)
and `docs/claude-display-handoff.md`. Read this instead of reconstructing it
from those.

The question is narrow: **can the brightness of this projector's light engine be
controlled from the SoC, and if so how?** Everything else about the display —
panel init, timing, framebuffer, the MIPS coprocessor — works and is out of
scope here.

---

## 1. The hardware, as far as it is known

- Board `HY200_QZ713DF_A1 20250304`, Allwinner **H713** (`QA206DA`), sun50iw12.
- Panel: 1280x720 LVDS, driven via a MIPS coprocessor running vendor
  `display.bin`. **This all works** — the panel renders correct images.
- The light engine is a separate module. **Its cable has only two conductors,
  power and ground** (operator observation). It is believed to run at ~48 V.
- **53 photographs of the mainboard show no LED driver and no boost converter.**
  Every inductor is a 2R2 (2.2 µH) buck for the SoC rails, clustered near the DC
  jack. There is no high-voltage electrolytic, no power FET pair, no current
  shunt. Photos in `local/board_images/`.
- The board has a 2-pin connector silkscreened `LED`, next to a 3-pin `IR`. It
  has thin signal-width traces and no adjacent power stage, so it is very
  unlikely to be the light engine feed; it matches the DT's indicator LEDs
  (`led0` on PL0 red, `led1` on PL1 blue).
- `PB5` is `panel_bl_en` and is **shared with fan power**. Never drive it low —
  on a projector with an LED light engine that is a thermal risk.

**Implication, and the current leading hypothesis:** if the light is 2-wire and
no driver exists on the mainboard, the 48 V is generated off-board, and no SoC
PWM can affect it unless a control wire physically reaches that off-board
driver. Nobody has yet traced where the light's cable terminates.

---

## 2. What is proven, and how

| fact | evidence |
| --- | --- |
| PWM channel 2 on PB4 is configured correctly and **actually running** | `CNT` register advances +176 per 7 µs and wraps at exactly **960**, giving 24 MHz and 25.0 kHz; duty steps 960/720/480/240/0 against a fixed entire of 960; `GATE=0x4`, `EN=0x4` |
| the PWM register map is mainline `pwm-sun20i-d1` | the counter wrap at 960 confirms `PERIOD[31:16]` is *entire − 1*, not an active count |
| PB4's `pwm2` function is **mux 3** | shipping DTB `muxsel = <0x03>`, upstream mainline H616 table, and patch 0018 all agree |
| driving that correct, running PWM changes brightness **not at all** | bench run 2026-08-05, full-white field, panel initialised and rendering |
| the MIPS firmware cannot drive a PWM | exhaustive effective-address scan of all 240,266 instructions in `display.bin`: **zero** accesses to `0x02000000`–`0x02002000` (PIO/PWM/CCU). Run twice, second time preserving callee-saved registers across `jal` |
| `Thal_Vp_SetBacklightLevel` is a non-blocking post that reports success unconditionally | worker `0x8b148ca4` has no conditional branch and ends `addiu $v0,$zero,1`; it queues `{opcode 2, level}` to the `app_bottom` thread via `IThread` vtable slot 3 with timeout 0 |
| the vendor kernel has **no backlight support at all** | vendor `vmlinux` (ARM 32-bit 5.4.99, full DWARF): zero backlight-class symbols, zero references to any `panel_*` property, no `Thal_Vp`/`SetBacklight` strings |
| stock sets the backlight once, in U-Boot fastlogo | stock U-Boot contains `pwm_request`, `sunxi_pwm_pin_set_state`, `Display fastlogo finish!`, and reads the `panel_pwm_*` / `[PWMSetting]` keys |
| the shipping DTB's backlight config is ch2 / 25 kHz / active-high / 75 | `sunxi.fex` from the retail OTA: `panel_pwm_ch=2`, `panel_pwm_freq=0x61a8`, `panel_pwm_pol=0`, `panel_backlight=0x4b` |
| **`pwm5` cannot be muxed on this product** | `sunxi.fex` has a `pwm5@2000c15` controller node but **no pwm5 pin group**; pin groups exist only for pwm0–pwm4. Stock calls `sunxi_pwm_pin_set_state`, which needs one |

**Net:** the only backlight configuration stock can successfully apply is
channel 2 / PB4 / 25 kHz / active high — which is exactly what we now run, with
the PWM verified live, and it does nothing.

---

## 3. What is inferred, not proven

A reviewer should attack these first.

1. **That `panel_config.ini` is not a runtime input.** It says
   `pwm_channel = 5`, contradicting the shipping DTB's channel 2. The argument
   for discounting it: our own bring-up loads `display.bin`, `display_cfg.xml`
   and the `.TSE` files from `mmc 1:2` and never loads it; and channel 5 has no
   pin group so it could not work anyway. But stock U-Boot *does* contain INI
   parsing for exactly those keys, gated at `0x4a0239e0` on
   `ini_get("pwm_freq")`. **The instruction that loads `pwm_channel` into the
   backlight-create call was never located.** If someone can trace that data
   flow, it either confirms or overturns this.
2. **That the light has no dimming path at all.** Based on the 2-wire cable plus
   the absence of a driver on the mainboard. Nobody has traced the cable to its
   other end or identified an off-board driver.
3. **That the `LED` 2-pin connector is the indicator, not the light.** Based on
   trace width and absence of a power stage, not on continuity testing.
4. **That the waveform physically reaches the PB4 pad.** The counter proves the
   channel generates internally. Nothing has measured the pin. The PIO data
   register cannot answer this — it reports the output latch, not the pad
   (proof: PC's data register reads `0x00000000` while the eMMC bank on PC is
   actively in use).

---

## 4. Conclusions that were reached and then reversed

Recorded so a reviewer does not re-tread them, and because the pattern is
informative.

- **"The PWM register map was wrong in four places."** False. The original map
  (mainline `pwm-sun20i-d1`) was correct; it was changed to match
  `pwm-sun8i.c`/patch 0007 and that broke it — a block dump then showed
  `0x02000c40 = 0`, `0x02000c80 = 0` and a static counter. Reverted. The
  evidence cited for patch 0007, a live capture of `PERIOD2 = 0x03BF03C0`, is
  **degenerate**: 959 vs 960 reads as 25 kHz at ~100% duty under *either* field
  order, so it cannot discriminate between the layouts.
- **"Stock uses PWM channel 5."** Overstated, then withdrawn. It rested on the
  `pwm_freq` gate plus the parallel key sets, without a traced data flow. The
  shipping DTB is stronger evidence and says channel 2. This question flipped
  twice in one session, both times because the reasoning started from board-A
  and board-B *development* trees; **the shipping DTB governs the retail unit
  and should be consulted first.**
- **"PWM2/PB4 verifiably does not dim this panel" (commit `ec1d759`).** The
  observation was real but the conclusion was not earned — at the time PB4 was
  muxed to 2 instead of 3, so the waveform never reached the pad. The result
  only became meaningful after the mux fix.
- **"`0x8b253570` is never written, so the backlight service is NULL."** Static
  scan found only loads; a runtime read showed a live pointer. A static write
  map is a lower bound, never an inventory.

**The recurring methodological failure:** a read-back checked against the same
source that produced the value cannot detect an error in that source. `PB4
mux=2` was printed, read and approved three separate times before anyone
compared it against the vendor's own pin table.

---

## 5. What would actually settle it

In rough order of cost.

1. **Trace the light's two wires to their other end.** If they reach a separate
   driver PCB, that board's control input is the real dimming path and its part
   number tells us what it expects. If they reach the PSU directly, brightness
   is not electronically controllable and this thread is over. *No bench time,
   no risk.*
2. **DMM on PB4, DC mode, during `bl-sweep`.** At 25 kHz a meter averages, so
   100/50/0 % should read ~3.3 / ~1.65 / ~0 V if the waveform reaches the pad.
   Settles inference #4 outright. *Minutes.*
3. **Trace `pwm_channel` into the backlight-create call in stock U-Boot**
   (`u-boot.fex`, Thumb, base `0x4a000000`, create call at `0x4a0255a0`,
   selector at `0x4a0239e0`). Settles inference #1. *Static, no hardware.*
4. **Boot stock and read its U-Boot console** for `Display fastlogo finish!`
   versus `Pwm enable fail:%d`. Procedure drafted as `docs/flash.md` "Method 5"
   — **but its premise proved false**: stock's boot package is at none of the
   sectors `boot0` references (`0x6000`, `0x8020`, `0x10000` all checked and
   none contain `sunxi-package`). Would require writing an inferred sector over
   unidentified data with **no eMMC backup in existence**. Not recommended
   without a backup and a better reason.

---

## 6. Artifacts and where they are

| what | where |
| --- | --- |
| bench command | `h713_disp panel-test 0x33 bl-sweep` — 6 steps, 100/75/50/25/0/100, white field, prints `CNT` twice per step and warns if static |
| our implementation | `external/u-boot/arch/arm/mach-sunxi/h713_mips.c`, `h713_disp_backlight_set()` |
| board photographs | `local/board_images/` (53) |
| retail OTA firmware | `~/Documents/projector_firmware/H713 Magcubic projector.20250922.093247/update.img` |
| extracted stock boot parts | `local/stock-boot/` (`boot0_sdcard.fex`, `u-boot.fex`, `boot_package.fex`, `sunxi.fex`, `env.fex`) |
| stock U-Boot (identical copy) | `local/mips-display/board-b-stock/u-boot-stock.bin` — sha256 matches `u-boot.fex` |
| MIPS firmware | `local/mips-display/board-b-mips/display.bin` (MIPS32LE, VA `0x8b100000` = file offset 0 = ARM `0x4b100000`) |
| chronological detail | `docs/mips-display-recovery.md`, top sections |

**Warnings for anyone continuing.** There is **no eMMC backup on this machine**
(`docs/flash.md` claimed one; it does not exist). `mmc dev 1;` must be on the
same line as any `mmc read`/`write`, because a failed read leaves plausible
looking stale DRAM and this has corrupted three results including a "backup".
`backup_8020.bin` currently on `mmc 1:2` is 1.2 MB of uninitialised DRAM — not a
backup. And never drive PB5 low.
