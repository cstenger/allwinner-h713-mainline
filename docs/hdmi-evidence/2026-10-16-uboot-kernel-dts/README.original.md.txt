# U-Boot on the kernel's device tree — stage 1 (2026-10-16)

Goal: U-Boot and Linux share one hardware description. U-Boot (`OF_UPSTREAM`)
now builds the kernel's H713 DTS verbatim; stage 1 changes nothing U-Boot does.

## What changed

- **U-Boot** (worktree `build/uboot-src-kdts`, branch `h713-kernel-dts` on the
  flashed `320a17f`; uncommitted at flash time, hence `-dirty`):
  - `drivers/clk/sunxi/clk_h713.c`: H713 gates/resets keyed by the kernel's
    binding IDs, generated from the kernel's CCU driver
    (`tools/build/gen-uboot-h713-ccu.py`); replaces the reused D1 tables.
  - `phy-sun4i-usb`: `allwinner,sun50i-h713-usb-phy` → the D1 config it used.
  - `dts/upstream`: the kernel's dtsi, both board files and binding headers,
    copied by `tools/build/sync-uboot-dts.sh` (`--check` fails on drift).
  - `arch/arm/dts/sun50i-h713*-u-boot.dtsi`: U-Boot's only deviations —
    eMMC alias `mmc1`, the handoff windows unreserved (U-Boot fills them;
    `fs_read` refuses reserved memory), no `assigned-clock-rates` on the eMMC
    (no `set_rate`; would fail the probe), musb as peripheral, unused
    controllers unbound.
- **Kernel** patches 0185–0187 (found by the comparison): the OTG controller
  node (disabled in Linux), the watchdog's real A523 layout (Linux was writing
  the A31 registers; systemd's 16 s reboot watchdog never ran), and the
  console UART's pin group.

## Offline proof against the flashed `lamp-B`

Config: identical but `CLK_SUN20I_D1` → `CLK_SUN50I_H713`. Symbols: only the
clock tables, one PHY match entry, one clock match entry, the version string.
Bound devices: the same drivers on the same nodes, plus an inert GPIO-less
fixed regulator. Property differences all inert (traced in the session). One
register-level change: the OTG PHY clock gate (`0xa70` bit 31) is set when
fastboot runs, as Linux does. FIT: same images and load addresses; proper
955,457 B (1,867 sectors).

## Hardware

- `precheck.log`: live `41b1e1bd…` (lamp-B), rescue `c882461d…`, SPL
  `cb9da874…`, env `de2f2560…`; the 69 newly used sectors zero.
- `write.log`: `uboot-proper-kdts-1867.bin` `60ddf7c4…` at `0x49ac00`,
  direct-I/O readback equal; rescue, SPL, env unchanged.
- `warm-boot-serial-2.log`: warm boot to login. All 121 U-Boot lines equal
  step 3's verified warm boot except: `-dirty`; 49 vs 37 DM devices (more
  pin-group subnodes); `FIFO status 0x2; reset applied` (Linux's new panel
  teardown leaves the LVDS off); the kernel FIT's size/hashes. Every register
  write of the display sequence is identical; display.bin loaded into its
  window. Linux: `running`, no failed units.
- `warm-boot-serial.log`: an earlier attempt whose capture was garbage; the
  board booted normally (the host-side capture was at fault; the plain
  `stty`/`cat` capture and the same Python port setup both read cleanly after).

## Not yet covered

The cold HDMI path, and fastboot (no USB cable on the OTG port).

# Stage 2 — the panel's supply and reset from the shared tree

- **Kernel** 0183 (revised): PF6 is `vcc-panel`, a `regulator-fixed`
  (`regulator-boot-on`: U-Boot leaves it on; `off-on-delay-us` 250 ms =
  PanelOffTiming1), the display's `power-supply`; PH16 `panel-reset-gpios`.
  0184 (revised): afbd claims the supply after every deferrable resource and
  registers the ordered power-down as the claim's release; shutdown runs the
  same: lamp, LVDS at rest, 20 ms, reset, 75 ms, supply off, the supply's
  off-on-delay-us. Residual: a probe that fails before the claim leaves the
  supply unclaimed, and the regulator core turns it off ~30 s after boot.
- **U-Boot**: `h713_disp` takes the supply (`power-supply` of the display
  node) and the reset from the DT; no panel pin numbers remain in
  `h713_mips.c`. Power-on, teardown and the bench control test use them. The
  a1 `-u-boot.dtsi` drops `regulator-boot-on` (in U-Boot it means "enable at
  init", which would power the panel before the logo records).

Hardware: kernel FIT `0877293b…`, startup script `391835c5…`
(`stage2-kernel-install.log`); U-Boot proper `cf1941d6…`
(`stage2-write.log`; rescue/SPL/env unchanged).
`stage2-boot-serial.log`: U-Boot "stock power phase complete: supply on,
reset released", logo committed, Linux up; `vcc-panel` claimed once by the
display, PF6 owned by the regulator, nothing deferred.
`stage2-teardown-serial.log`: Linux "panel powered down: supply off, reset
line 0, PHY 18000000/00000030, route 40000000", restart, U-Boot powers the
panel from off. The now-working reboot watchdog armed (16 s) and was stopped
by the kernel at restart.

Still open: the cold HDMI path on this stack, the visual check after a long
power-off, fastboot (no OTG cable).

## Trial 22 — HPD already low before the reset (2026-10-17): BLACK

`trial22-host-hdmi-monitor/`: normal cold boot (cold path, capture + signal
on, cable to the host PC), then a warm reboot. The host's connector state
(`card1-HDMI-A-1`) was polled throughout (`host-hdmi.log`): connected at
14:49:31 when the signal owner asserted HPD, **disconnected at 14:50:20**,
when the production stop put 0x07091014 back to 7, before the shutdown's
receiver park, MIPS reset and panel power-down (serial, 68.9–75.7 s). The
reset followed; U-Boot took the warm branch (latch set) and the panel came up
**lit but black**. The host stayed disconnected for the whole black boot.

So HPD low, the receiver parked and the source idle before the reset do not
prevent it, and nothing re-drives the link in the black boot. What unplugging
the cable removed in trial 21b, and HPD low does not, is the cable itself:
the source's +5 V (pin 18, present whatever HPD says) and the DDC lines. HDMI
receivers commonly power their EDID/5 V-detect block from that pin, so the
source can read EDID with the sink off; state there would survive a SoC reset
and a short mains-off while the host stays on (an overnight off may also have
been a host asleep). 21b is one trial: repeat it from this black state.

## Trial 23 — repeat of 21b from trial 22's black state (2026-10-17): GOOD

`trial23-unplugged-from-black/`: the board sat ~30 min black after trial 22;
the cable was unplugged at the projector, then a warm reboot at 15:21:27.
U-Boot took the warm branch as before; the panel showed the **logo, then the
console**. The unplug clearing a black state is now 2/2 (21b, 23); nothing
else short of a long mains-off ever has. With trial 22 (HPD low, source idle,
still black), what the cable carries apart from HPD -- the source's +5 V and
DDC -- is what holds the bad state across the SoC reset.

## What the cold path writes in the 5 V blocks, and what stock does (2026-10-17, read-only)

- **The cold path never writes the HDMI 5 V/EDID/DDC block.** The EDID banks
  (0x07091c00/1d00/1e00), DDC control (0x1b00/1b04/1b08), HPD (0x1014) and the
  IO words (0x1020-0x1038) sit in the CPUS domain, where only the SCP can read
  or write them. On our boards the only writer is the Linux signal owner's SCP
  payload, which writes the saved values back and checks them at every stop
  (trial 22: "stop readback 1014=7 ..."). display.bin's MMIO windows are
  0xBA00xxxx (ARM 0x0500xxxx). The MIPS reports a 5 V change by messaging the
  ARISC (User1 port 1, 0x03003574) and doesn't drive HPD itself; no ARISC
  firmware runs here to answer. In trial 9b (black, no Linux HDMI), nothing
  touched that block.
- **Stock has no HDMI teardown on reboot in its kernel modules.** None of the
  45 vendor modules (cpu_comm_dev, mcu_comm_dev, tvutils, hidtvreg_dev, decd
  included) has a shutdown or reboot hook for HDMI/TV. The only teardown found
  is in the stock ARISC firmware (board-A scp.bin, words byte-reversed):
  `SysResetHotplug` (~0x128d8) pulses HPD on each port, through the HPD writer
  at 0x1284c: low, wait N ms, high. Trial 22 already covered the HPD-low half,
  and it didn't help. Its "reset system now" path (0x8cfc) writes RTC 0x07090100
  and 0x07040030, with no HDMI involved.
- **Nothing readable differs.** The black boot (trial 23 before) and the good
  boot (trial 23 after) have the same display registers (only counters
  differ) and the same R-domain snapshot (PPU, R_CCU, R_PIO L).

So the bad state sits outside every register we can read. The open question
is whether it's stored state that a boot with the cable's +5 V present picks
up, or a live electrical effect of the connected cable on a panel brought up
after a cold-path boot.

## Trial 24 — cable back in, warm reboot (2026-10-17): GOOD

`trial24-replugged-warm-reboot/`: from trial 23's good boot (cable out), the
cable was plugged back in while the operator watched the lens: **no change**
(the console stayed). A warm reboot at 15:37:16 with the cable connected (warm
branch, latch set) gave the **logo, then the console**.

So the unplug *cleared* the bad state. The cable being present at the next
boot doesn't recreate it, and connecting a source to a good board is harmless.
The state is set during a cold-path boot with the cable connected, survives
SoC resets, PL6 cuts and a 1-min mains-off, and is cleared when the cable's
+5 V goes away. That fits something powered or reset by the HDMI +5 V
(the receiver's 5 V-detect/PHY side; the stock DT has no 5 V-detect GPIO, so
it goes into the SoC). Candidate software teardown: have the MIPS switch away
from source 3 (the way stock leaves HDMI when the user changes input) before
the park and reboot, instead of resetting it while source 3 is active.

## Trial 25 — leave source 3 before the park (2026-10-17): BLACK

`trial25-source-away/` (tools/display/source-away-trial.sh): normal cold boot
(cold path, session up, cable connected). At 15:47:23,
`cpu-comm-probe THal_Vp_SetSource_1_000 1` returned CALL_OK in 11.9 ms, and the
firmware's trace confirmed the switch (`requested` 3->1, `dispatch_source`
1, last transition old=3 new=1). Then the production stop: audio restore
lines and the terminal MIPS park, verified. Warm reboot at 15:48:02, warm
branch: **lit but black**.

So switching the firmware away from HDMI (what stock does on an input change)
doesn't undo it. With trial 22 (HPD low first) also black, neither the HDMI
source selection nor HPD clears the state once it's set; only losing the
cable's +5 V does (21b, 23, 24).

## Trial 26 — TCON pattern generator in the black state (2026-10-17): BLACK

`trial26-tcon-pattern-black/`: on the black boot after trial 25, the TCON's
own pattern generator was switched on at 15:56:00 (0x0588001c=5,
0x0588000c bit 3, 128 px cells, red/blue; recipe from
docs/handoff-2026-09-04-video-scaling-and-display.md). The registers read
back as written. The operator saw **still black**; everything was then
restored to 0x00E40202/4/00080008/0/3FFFFFFF. The pattern bypasses the
framebuffer, AFBD, OSD, DE and vblender, so the fault is at or after the
TCON: the LVDS PHY/serialiser, the panel's receiver, or the panel itself.
**Needs its control**: the same pattern on a good boot must show the
checkerboard before this narrows anything.

### Trial 26 control — the same pattern on a good boot: CHECKERBOARD

`trial26-control-good/`: cable unplugged, warm reboot at 16:09:12 -> logo +
console; the identical pattern at 16:11:32 -> the **red/blue checkerboard**;
restored. So the test discriminates, and trial 26 stands: **in the black state
the fault is downstream of the TCON**, in the LVDS PHY/serialiser
(0x051c0000), the lane drive, or the panel's receiver/power-up. The framebuffer,
AFBD, OSD, DE, vblender and the TCON's timing are all exonerated. The 60
LVDS-PHY words and the TCON block read identically in the black and good boots
(only the 0x05880000 scan counter differs), so whatever differs is analog or
in the panel, not in a register we program. Diff target for the stock RE:
what stock (boot0, U-Boot, display.bin) does to the LVDS PHY, its PLL/reset/
gate, and the panel power/reset order before driving lanes, which a warm reset
plus the cable-held state would need.

## Stock RE diff: the reset itself differs (2026-10-17, read-only)

- **Bring-up is the same.** Stock's display bring-up is boot0 (no display
  registers), BL31/OP-TEE/SCP items (none), U-Boot replaying LogoRegData.bin
  (LVDS lane 0x05800000, TCON, display PLL 0x058c0000) plus the panel
  power (550 ms, supply, reset low 2 ms / high 5 ms, 20 ms) and the MIPS
  release. Our warm path replays the same table and the same power order
  (h713_mips.c h713_disp_stock_panel_power, h713_disp_fifo_reset). No ARM-side
  step is missing that the RE shows.
- **The reset is different.** Stock BL31 hands PSCI SYSTEM_RESET to the SCP
  ("Sunxi System Reset: SCP error %u"). The ARISC's "watchdog reset" path
  (board-A scp.bin 0xcd70) arms the **R-domain watchdog at 0x07020400**:
  +0x00 <- 0, +0x10 <- 0x16aa0101, +0x14 <- 0x16aa0000, a delay,
  +0x14 |= 0x16aa0001. Our TF-A (plat/allwinner/sun50i_h713) defines
  SUNXI_R_WDOG_BASE as the **main** watchdog 0x02051000 and writes config
  0x16aa0001, without bit 8. A reset raised from the always-on domain may
  reset what the main watchdog leaves alone, and that would fit a state that
  survives every reset we've tried.
- Also noted: the ARISC sets bit 4 of TVTOP 0x05700040/44/80 in one sequence
  (scp.bin ~0xe478, context not yet identified).

Bench vehicle: modules/r-wdog-reboot-bench (h713-r-wdog-reboot.ko, staged at
/root, sha256 3e6dfd7e...). armed=1 registers a restart handler at priority
200, above PSCI's 129, which replays the stock sequence after device shutdown,
so the panel power-down still runs first. If R_WDOG doesn't fire within 2 s,
it falls back to PSCI.

## Trial 27 — reset through R_WDOG, as stock does (2026-10-17): GOOD

`trial27-r-wdog-reboot/`: normal cold boot (cold path, capture + signal on,
cable connected; the host saw the link from 16:21:27). At 42 s,
`insmod /root/h713-r-wdog-reboot.ko armed=1`, then `systemctl reboot` at
16:21:55: the full production stop ran (signal stop restored 1014=7, audio
restored, terminal MIPS park, panel powered down). Serial then shows
"resetting through R_WDOG 0x07020400" and no fallback line, so the R-domain
watchdog performed the reset. The next boot took the warm branch (latch set,
so the RTC survived), and the panel showed the **logo, then the console**,
with the cable connected throughout.

First good warm reset from a cold-path session with the cable in since the
reset source became the variable. One trial: cold-path boots are good about
1 in 5 by chance, so repeat at least twice before changing TF-A. If it
holds, the proper fix is PSCI SYSTEM_RESET in our TF-A going through R_WDOG
0x07020400 with stock's sequence.

## Trial 28 — R_WDOG repeat (2026-10-17): BLACK

`trial28-r-wdog-repeat/`: the same as trial 27 (cold path, cable in, armed at
38 s, full production stop, panel down, "resetting through R_WDOG", warm
branch) -> **lit but black**. The reset source isn't the variable;
trial 27 was the ~1-in-5 chance. The R_WDOG stays a correct stock-parity
difference, but it isn't this fix.
