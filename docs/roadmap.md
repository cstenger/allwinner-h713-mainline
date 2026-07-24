# Roadmap

Where the project goes after the foundation (open boot chain + Debian 6.18.38 +
standalone boot, all hardware-verified on the bench). Ordered by dependency, not
just priority. See [status.md](status.md) for what already works.

## Guiding constraints

- **Bench (`HY200_QZ713DF_A1`, DDR3) is the safe dev board.** The projector
  (`HY200_QZ713_V2`, LPDDR3) lives inside a projector and is untested — bring it
  up carefully, FEL-first, brick-avoidance paramount.
- **The kernel is a patch series, and that's its home by design.**
  `patches/kernel/` applied to a pinned mainline tarball is deliberate (the tree
  is too big to fork, and this keeps our delta reviewable + rebasable). Driver
  work = edit the series + `build/build.sh kernel`. No "kernel fork" is needed;
  what *is* worth adding is a hackable persistent tree for iteration (Phase 1).
- **UART is the recovery anchor.** It is now the reliable U-Boot default, while
  ACM is an explicit faster mode. Networking/SSH still removes the throughput
  bottleneck for Linux-side iteration.

## Phase 1 — Build & OS polish (bench, near-term)

- **Rootfs workflow — complete and hardware-verified.** The rootless
  `tools/rootfs/build.sh` verifies signed Debian metadata, requires an SSH key,
  disables password SSH, installs all 24 Linux 6.18.38 modules, builds
  raw+sparse ext4 images, and validates growfs plus filesystem integrity. On
  the bench it boots repeatedly with a 4.5 GiB root filesystem, serial
  autologin, stable per-device identity, Cedrus/Panfrost modules, and active
  public-key-only sshd. A remote SSH login remains gated on networking.
- **Boot cleanup — complete and hardware-verified:** removed the CCU
  `MIPS_DIAG` residue, enabled autofs, modeled the Mali supply, installed clean
  U-Boot `g8a601c1`, and verified UART, ACM, fastboot, and normal Debian boot.
- **Dev workflow**: a persistent, hackable kernel worktree (separate from the
  ephemeral `build/linux-*`) + a fast "rebuild module → load on target" path.
- **Reboot → fastboot / U-Boot — done, both modes HW-validated (2026-07-23).**
  `RTC_DRV_SUN6I` is enabled (real RTC driver, the
  previously-orphaned osc32k/iosc clocks, GP registers as nvmem), and reboot-mode
  moved off the overlapping `syscon-reboot-mode` onto **`nvmem-reboot-mode`** over
  a fixed nvmem cell (`reboot-mode-magic@1c`) under the rtc node — no `sun6i-rtc`
  patch needed (`add_legacy_fixed_of_cells` makes the DT cell
  phandle-referenceable). The nvmem→GP7→`preboot`→fastboot chain was proven
  console-free on the bench. A follow-on split gives the two reboot verbs
  distinct meanings: `reboot fastboot` (`0xfa57b007`) → fastboot;
  `reboot bootloader` (`0xb007c0de`) → `preboot` runs `setenv bootdelay -1` →
  U-Boot prompt. DTS carries both modes; the U-Boot side is the runtime `preboot`
  env. Both verbs were confirmed console-free on the bench. Minor loose end: RTC
  timekeeping (set/read) unexercised on the minimal rootfs (no `hwclock`).
- **WiFi SDIO stability — fixed for load; bench-validated (no regression).**
  The AIC8800 `mmc1` link wedged under sustained load: `FIFO_RUN_ERROR` on CMD53
  that the phase-rotation retry can't recover (phase fixes CRC, not underruns) →
  CMD53 timeout → `aic8800_fdrv` `cmdqueue drain timeout` leaks an atomic context
  → `scheduling while atomic`. Patch 0006 now **classifies the CMD53 error**: FIFO
  underruns (`FIFO_RUN_ERROR`/`HARD_WARE_LOCKED`) get FIFO/DMA-reset recovery with
  a short AHB back-off and *no* phase rotation (which would only knock a good link
  off its stock sampling phase); CRC/timing errors keep the phase-rotation path.
  Independent retry budgets (7 phase / 15 FIFO) keep a burst of load-induced
  underruns from exhausting the CRC budget and surfacing as a hard `-ETIMEDOUT`.
  **Bench (2026-07-22):** 384 MB of sustained WiFi transfer completed with zero
  SDIO errors and no wedge (previously ~12 MB wedged it); the old failure is gone.
  The FIFO recovery path itself was **not provoked** — the SDIO data path never
  underran this session (the marginal weak-RF placement that produced the original
  `FIFO_RUN_ERROR` didn't reproduce), so it stands as defense-in-depth; to observe
  it firing, retest from the −71…−80 dBm spot. DVFS was ruled out (wedged even
  pinned at 1416 MHz).
- **AIC8800 firmware-command crash — detected + logged; no auto-recovery
  (by design).** Under *pathological* CPU/bus starvation (perf-pinned +
  memcpy/eMMC contention), the vendor driver's firmware command→confirm handshake
  times out (`cmd timed-out` → `wlan error reset flow`, `rwnx_cmds.c`), marking the
  cmd queue `CRASHED` and firing a `DHDISDOWN=1` uevent → WiFi/BT stay down (kernel
  survives; no atomic wedge). Distinct from the sunxi-mmc FIFO bug (no CMD53 error
  occurs). **Auto-recovery was attempted and abandoned as unsafe:** an
  unbind+reload of the SDIO stack races the mmc/driver core into a NULL-deref Oops
  (`__device_attach_driver` via `mmc_rescan`), and a graceful reboot fallback hung
  on BT teardown — bench-observed, board needed a power-cycle. The chip only comes
  back cleanly on a full boot. So the rootfs ships a **log-only notifier**
  (`h713-wifi-crashlog`, udev on `DHDISDOWN=1` → journal + console line); the
  operator reboots. Only reproduces under unrealistic load. Minor follow-up: a
  `TimeoutStopSec` on `h713-bt-attach.service` so a post-crash graceful reboot
  doesn't wait ~3 min on BT teardown.

## Phase 2 — Bench subsystem bring-up

On the bench board. Most items are SoC-general and mutually independent; the
**display path** is the exception and the linchpin — the whole *visible* stack
(GPU-on-screen, a compositor, even confirming the backlight brightness fix) hangs
off it. Because the bench board is itself a projector variant with the panel
attached, the display path can be brought up here, not only on the projector
(Phase 3/4). Ordered by dependency, not just priority.

1. **Networking (WiFi + BT) — highest value; unlocks SSH, ends the UART pain.**
   Verify *what's populated and on which bus* (the well0nez reference points at an
   **AIC8800** combo, SDIO or USB), then driver + firmware + DT node. Everything
   downstream gets easier once this lands.
2. **Thermal / cpufreq / DVFS — done; safety + real performance.**
   - **Bench cooling fan (0030) — DONE.** The fan is a 3-wire (VCC/GND/tach)
     on/off part, not PWM-speed-controlled (DMM: tach at its 3.3 V pull-up, +V
     floating/unpowered). It stayed dead because the PB5 backlight/fan
     power-enable hog was malformed (`<37>` on a 3-cell sunxi controller →
     skipped). 0030 fixes the hog to `<1 5>`; the earlier `pwm-fan`-on-PWM0 model
     was dropped once PH17 proved to be the tach line, not a control output
     (main-PWM output itself *was* validated in the process). **Bench-confirmed:
     the fan spins.** Both the fan and the LED backlight now come up **at
     power-on from U-Boot** (`board_init` drives the shared PB5 enable under
     `CONFIG_H713_POWERON_LIGHT_FAN`, bench-only), so the panel is lit and cooled
     from reset like a monitor showing the boot process; PB5 being the shared
     enable makes the fan a hard interlock for the light.
   - **Backlight brightness** is a display-path task, not a thermal one — tracked
     under item 3.
3. **Display path (LVDS panel → backlight → MIPS pipeline) — the linchpin;
   bench-doable.** The only display *output* is the projector's LVDS/LCD panel
   (HDMI is input-only — see Open questions), so this gates every *visible* thing:
   GPU-on-screen, a compositor, and confirming the backlight dimmer. Two coupled
   pieces:
   - **Backlight brightness.** PB4/PWM2 is the stock dimmer (vendor DTB
     `panel_pwm_ch = 2`, 25 kHz, `panel_backlight = 75` on 0..100; stock fastlogo
     `pwm_request(2, "fastlogo")`; the vendor Linux port dims on ch2). Patch 0032
     wires a mainline `pwm-backlight` on PWM2/PB4 and is **HW-correct** — debugfs
     shows channel 2 duty scaling 0/20000/40000 ns with PB4 muxed to `pwm2` — but
     the panel ignores it: brightness is gated on the panel **serial init**
     (LED-driver PWM-dim enable / LVDS program over PH10/11/12) that stock
     fastlogo runs before Linux. A cheap gpio-hog probe of the panel control
     lines (PH19/16/15/8/9, PB5 untouched) was **tried and is negative**,
     confirming it's the serial program, not the power/enable GPIOs. Cheapest way
     in: **capture the SPI off the wire** during a *stock* boot (logic-analyzer on
     PH10=cs/PH11=scl/PH12=sda up to "Display fastlogo finish!") and replay it in
     mainline, rather than disassembling `display.bin`. Watch the enable-ordering
     trap: mainline asserts PB5 before any init, and PB5 can't be freely toggled
     (fan interlock). 0032 stays as the correct front-end.
   - **LVDS panel bring-up + MIPS display coprocessor pipeline** (`mipsloader` +
     `nsi` + `cpu-comm` + `tvtop` + `decd`) — the projector's scanout path (RE'd
     by well0nez; the hardest, least-understood piece). Same hardware as Phase 4,
     but startable here on the bench.
4. **GPU (Mali-G31 / Panfrost).** Driver is mainline and binds now; Panfrost can
   render offscreen/headless (EGL/GBM, PRIME buffer sharing) for validation, but
   anything *visible* is gated on the display path (item 3), so it is downstream
   of that work, not a standalone bench item.
5. **Video decode (Cedrus / VE3)** — genuinely headless-testable (patch 0022 in
   series); independent of the display path.
6. **Audio** (I2S / codec / HDMI-in audio captured off the HDMI-RX) — depends on
   what's populated.
7. **IR receiver (sunxi-cir)** — patch 0021; needs the receiver populated.
8. **Crypto (sun8i-ce) + RNG — CLOSED: investigated to a definitive dead end;
   disabled.** Mainline `sun8i-ce` cannot drive the H713 CE, bench-proven step by
   step: the A53s already have ARMv8 AES/SHA (software crypto ~2 GB/s, faster than
   this CE, so no performance case); enabling the CE registers every algorithm
   then fails each self-test; wiring the stock's second interrupt (SPI 74) fixes
   task completion, but the CE then rejects mainline's task descriptors (`address
   invalid` for ciphers, `algorithm not supported` for standard AES/SHA) — a
   different descriptor **format** (the vendor two-bank block), not an
   IRQ/clock/addressing gap. No CE TRNG. Reopening means descriptor-level RE of
   the vendor `allwinner,sunxi-ce` driver (source unavailable) for no gain — left
   disabled; software crypto is fast and correct.

## Phase 3 — Projector board bring-up (`HY200_QZ713_V2`, LPDDR3)

- Build U-Boot with `hy200_qz713_v2_defconfig` — the **LPDDR3 params are
  replay-verified only, never run on hardware**.
- **FEL-boot first**, verify DRAM + console, *before* writing anything to its
  eMMC. Confirm the recovery vector exists on this board.
- Audit the existing projector DTS against the physical board, enable its
  vendor-only drivers in a separate config, and port `cpu-comm` away from its
  inherited 32-bit virtual-pointer ABI before enabling it on arm64. Then
  validate boot to Debian (rootfs auto-grows).

## Phase 4 — Projector-specific subsystems (needs Phase 3)

- **Display path (LCD panel + backlight + MIPS pipeline)** — the *same* hardware
  as the bench board, so bring-up starts in Phase 2 (item 3), not here. Phase 4's
  only display job is re-validating that path on the LPDDR3 projector board once
  Phase 3 boots.
- **Keystone motor** (GPIO stepper, patch 0009).
- **Fans + NTC** (board-mgr, patch 0008).

## Phase 5 — Upstreaming (long-term)

Clean the H713 driver series (CCU, pinctrl, PPU, LRADC, USB-PHY, MMC, …) + DT
bindings for mainline submission; upstream the board DTS once stable. The forks
were curated with this in mind (see [../PROVENANCE.md](../PROVENANCE.md)).

## Open questions — verify before committing effort

- **Board population**: what's actually fitted on each board — WiFi/BT chip +
  bus, HDMI, audio codec, IR receiver, fans, panel connector?
- **Projector safety**: can `HY200_QZ713_V2` be FEL-recovered (button / BROM
  fallback) if a flash goes wrong?
- **Display output on the bench — RESOLVED.** The only display *output* is the
  projector's LVDS/LCD panel; the HDMI connector is an HDMI-RX **input** (DW-HDMI-RX,
  no HDMI-TX on this SoC, no output/encoder node in the stock DTB), so it cannot
  be a monitor output. Consequence: all *visible* GPU/display bring-up is gated on
  the LVDS panel + MIPS display path (Phase 3/4) — there is no HDMI-monitor
  shortcut. Panfrost/Cedrus stay headless-testable meanwhile.
- **Status-LED source — RESOLVED (hardware rail indicator; bench-probed
  2026-07-23).** The power LED goes red → blue at main power-on and it is **not**
  software-driven. Probed live at the U-Boot prompt (via `reboot bootloader`):
  blue is already lit pre-Linux, so it is no Linux consumer. U-Boot configures
  only PL6 (the vdd-cpu/sys enable from `standby_param`) and leaves PL0/PL1
  **disabled** (`R_PIO CFG0 @0x07022000 = 0xf1ffffff`). Muxing PL1 (blue) then
  PL0 (red) as outputs and driving each high *and* low (`mw.l 0x07022010` /
  `0x07022000`) moved neither LED. So the status LED is a bi-colour power
  indicator wired to the rails (red = standby rail, blue = main rails up); it
  flips at the same instant PB5 enables the lamp/fan — hence the apparent PB5
  correlation, but there is no shared line and no GPIO involved. The vendor
  `led0/led1 = PL0/PL1` + `standby_param` mapping is not honoured at runtime on
  this revision (ARISC-only during real standby entry, or a different board rev).
