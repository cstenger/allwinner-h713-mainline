# Handoff: V2 projector panel stays black after some warm boots

Updated 2026-11-22 for Claude. Read this first, then the **V2 boot
qualification** section of `docs/lpddr3-bringup-plan.md` for the earlier
evidence and bring-up context. The latest production change on `main` is
`244194ba` (U-Boot 0022). `main` is pushed to the `cstenger` fork.

## Current state and next step

- The eMMC primary at LBA `0x49ac00` runs production **U-Boot 0022**, which
  includes 0020 and 0021. The 0021 and 0022 installs were individually authorized.
  Each guarded install backed up the previous primary and verified the payload and
  surrounding region after writing. The 0022 record, rollback and readback are in
  `local/recovery/2026-11-22-v2-uboot-0022.EZo6qV/`.
- Both RAUC slots retain `2026.11.22.2314-1f15ffa6-0221`, with
  `BOOT_ORDER=A B`. The board is running Linux on slot A, cold boot
  `249c4de1`, with the desktop visible. Serial and USB are unplugged.
- **0022 qualified on the glass: 10/10 normal warm reboots from Linux and
  1/1 true cold boot**, all with HDMI connected and lamp, logo and desktop
  confirmed by Chris (table below). It stays the production U-Boot.
  The LVDS-quiet and SPI builds stay parked as diagnostics. If black ever
  recurs, follow "If black recurs on installed 0022".
- The return from the RAM diagnostic prompt used the FEL-trial teardown
  without the GP7 FEL marker (`h713_disp teardown`, HDOK, `reset`, with GP7
  checked zero). The eMMC SPL then ran installed 0022 into slot A.
- Use `audit-slot-a-0022.py` from the 0022 recovery directory for this
  install. `audit-slot-a-0221.py` in the qualification directory still pins
  the 0021 primary (`2b945e2f…`) and fails against 0022.

## The bug in one paragraph

On the HY200_QZ713_V2 projector (LPDDR3, native `display.bin` `16c74a28…`),
some **warm** boots leave the LCD panel lit but black. HDMI capture, the
AFBD video plane, TCON timing, backlight and lamp are all correct, and every
digital check passes, but the glass shows nothing. Even the TCON test
pattern stays black. A **power cycle**, or an **ordered PH19 supply cycle
from Linux**, clears it. Cold boots have always been fine. The panel is
physically the same part the A1 bench board used. This is the A1's October
2026 "lit but black" latch-up (`docs/panel-investigation-history/README.md`,
`docs/uboot-panel-initial-state.md`) on a different board.

## Baseline before U-Boot 0021 (operator observations)

| Observation | Result |
| --- | --- |
| Capture ring content on a black boot (`read-coherent-frame.py --copies 1`) | correct desktop picture |
| `systemctl restart h713-hdmi-video`, HDMI replug | still black |
| Warm reboot with HDMI connected, from a black boot | still black |
| Cold power cycle (≥1 min off) | picture back |
| TCON test pattern (`0x0588000c/1c/38/3c/40` = `00E4020A/5/00800080/3F000000/FF`; normal `00E40202/4/00080008/0/3FFFFFFF`) | still black, so the fault is after the TCON |
| Live ordered PH19 cycle (script below) | **picture back, 4 of 4** |
| Cold no-source power-on, plug-in later | picture |
| Warm reboot taken while HDMI unplugged, **before** kernel 0221 | black 2 of 3 |
| Warm reboot taken while unplugged, **with** 0221 | picture 3 of 3 |
| Warm reboot with HDMI connected, **with** 0221 | **black 2 of 2** |
| Watched warm reboot with 0221 (serial captured) | **panel never lit, no logo** |

The captured black/working diffs yielded two read-only status clues. DETN
`0x050c0894/8ac/914/918/92c/930` and `0x05140614` bit 0 read zero on the
black boot. Their value as failure markers remains unverified across boots.
The optical result decides whether a boot passed.

## Changes and optical results

- **Kernel 0221** (`1f15ffa6`) describes the V2 panel supply on **PH19**,
  active-low **PH16** reset and the lamp. It enables the existing 0184
  shutdown sequence. UART confirms the panel is quieted and powered down
  before the restart. That ran even on black boots. Keep it.
- **U-Boot 0020** removes `regulator-boot-on` from the V2 U-Boot panel
  supply description. **0021** (`713d9731`) replaces 0016's single PLL pulse
  with the A1 PLL startup while retaining V2 timing/routing. A1 block 6
  and native V2 timing evidence are under `build/v2-native-display/`.
- **U-Boot 0022** (`244194ba`) keeps PH19 off and PH16 asserted while the
  LVDS setup and MIPS launch run. It waits for the asynchronous HDMI source
  3 transition, latches final 720p, then runs the existing 550 ms pre-power
  delay, enables PH19, waits 2 ms before releasing PH16, waits the existing
  5 ms and 20 ms, and enables the lamp. With earlier U-Boot, the panel was
  already awake when MIPS started and changed source. 0022 changes both
  the order and elapsed panel-off time.

All trials below had HDMI connected. A FEL boot ends at the U-Boot prompt.
The normal boots reach Linux and are the closest match to the original
failure. The operator confirmed each optical result.

| Build | Boot path | Observations |
| --- | --- | --- |
| Single-pulse control | Warm FEL | Logo 2/2 |
| A1 PLL candidate for 0021 | Warm FEL | Logo 3/3 |
| Installed 0021 | Normal warm from slot A | Logo and desktop 2/3. Trial 3 (`6ac287a1`) had lamp on, no logo and black glass. Live ordered PH19 cycle restored the desktop on that boot. |
| Delayed-power candidate for 0022 | Warm FEL | Logo 3/3 |
| Installed 0022 | Normal warm from slot A | Desktop 3/3 (`86c98c25`, `a85a4db2`, `5e44e0e1`). Logo confirmed on trials 1 and 3. |
| Installed 0022 | Normal warm from Linux, slot A | Lamp, logo and desktop 7/7 (`397aed2a`, `8221795a`, `c5fd5b2d`, `1ddd0e21`, `3eed8cea`, `ec6e74d0`, `06d93cce`). UART showed ordered shutdown and 0022 order each time. Startup check PASS, 59.7 fps. |
| Installed 0022 | True cold (serial and USB out, ≥1 min off) | Lamp, logo and desktop 1/1 (`249c4de1`). Prior shutdown PASS, AFBD clean. |
| Instrumented 0022 and 0021 | Warm FEL | Logo 1/1 and 3/3 respectively. Instrumented 0021 did not reproduce black. |
| 0022 with LVDS held quiet during panel power-up | Warm FEL | Lamp and logo 3/3. All five off-state checkpoints and restoration passed each time. |

Evidence is in `build/v2-panel-fel-pll-trial/`,
`build/v2-panel-late-power-trial/`, and the optical records under
`local/recovery/2026-11-22-v2-uboot-0021.mmgSJA/` and
`local/recovery/2026-11-22-v2-uboot-0022.EZo6qV/` (later runs in its
`qual-linux/` and `return-to-0022/`).
The older serial baseline is `build/v2-panel-0221/serial-reboot-2/serial.txt`.
The missing boot logo puts the failure before Linux. A three-second
U-Boot off hold and the A1 PLL alone both allowed failures. The live PH19
cycle shows that the panel path can recover without restarting the SoC.

## PH10–PH13 and SPI1

The panel ribbon reads **Z20HD720M-V03**, with 30 contacts. The photos are
in `local/device-photos/panel/`. No controller part number, pinout, or
readable panel status was verified. The MIPS is the H713 display firmware
processor. It writes host-side LVDS settings. That does not identify the
separate controller on the LCD assembly.

The stock V2 DT has `spi_cs/scl/sda` GPIO definitions on PH10/11/12,
and an alternate SPI1 pin group that includes PH13. SPI0 and SPI1 both
have disabled controller nodes. See
`build/v2-native-display/hdmi-slot-a/dt/stock-v2.dts`.
On Linux boot `6ac287a1`, after the supply cycle recovered the picture,
7,029 samples showed all four muxes disabled, GPIO data bits zero, and
SPI1 clocks off/reset asserted. Linux exposed no SPI masters or devices.
The same values held across 83,369 samples in instrumented 0022, and
82,388, 82,543 and 82,529 samples in the three instrumented 0021 trials.
These were selected startup intervals, all with a visible logo. GPIO
data bits with mux disabled do not establish electrical pin levels.
There was no stock-startup or failing-boot trace, no SPI1 enable test,
and no verified PH12/PH13 reply. Leave this branch of the investigation
parked unless there is a schematic, a stock trace, or other new evidence.
See `working-boot-ph10-13-spi1.log` in the 0021 recovery directory and
`build/v2-panel-002{1,2}-spi-trace/`.

## RAM-only LVDS-quiet experiment

The A1 staged test already showed that applying and restoring the PHY
and route words can leave the 720p timing readbacks intact with MIPS
parked. That earlier attempt to recover an existing black screen without
cycling the panel supply failed. See
`docs/review-2026-10-17-panel-black-chatgpt.md` under “isolated LVDS output
restart”. V2 logs show MIPS programs the PHY and route during startup.
The new trial applies the off state **after** the source switch and final
720p latch while MIPS is still running.

The FEL image saves and quiets `0x051c00d4/d8/dc/e0` (zero),
`0x051c0014` (`0x18000000`), `0x051c0028` (`0x00000030`), and
`0x05140054` (`0x40000000`). It checks the values immediately and after
the existing 550, 2, 5 and 20 ms waits. It restores the saved words after
the last wait, before backlight PWM and lamp enable. Every trial logged
`mismatch checkpoints=0x00, restored=yes`. The readbacks verify the
sampled register states. A differential measurement is needed to establish
whether the lanes were electrically quiet or high impedance. The trial also
leaves open whether a longer off interval or the absence of a timing
transition at panel wake is what helps on 0022.

Reproducibility artifacts under `build/v2-panel-0022-lvds-quiet/`:

- `trial.diff` is the diagnostic source change against the prepared 0022
  FEL source. `uboot/.config` sets `ENV_IS_NOWHERE`, `BOOTDELAY=-1` and
  `PREBOOT=h713_disp boot-v2` so it shows the logo and stops at a prompt.
- `uboot/u-boot.bin` SHA-256 is
  `caa2e04167bfeaec2666bcebc926a847c6a291a4258af4d57cc68481ea8f8643`.
  UART/FEL logs are in `warm-01.7yWdzh/`, `warm-02.0AwIvm/`, and
  `warm-03.NzZiok/`. Each FEL load verified the image by RAM readback.
- The FEL workflow used ordered U-Boot teardown, a warm reset into fresh
  FEL, `tools/board-guard.py --expect hy200-qz713-v2 --fel`, and
  `tools/fel-uboot.sh build/out/h713-v2-felrescue.bin <U-Boot binary>`.
  See the saved teardown and loader logs. Check the live state again before
  using those steps. The current RAM session is a console hold, not Linux.

## If black recurs on installed 0022

1. Record the optical result and boot ID. If Linux comes up, preserve the
   failing boot for the read-only comparison before recovery. Sample DETN
   and `0x05140614[0]` on black and again after the ordered PH19 cycle on
   that same boot. Ask Chris to confirm each optical state.
2. Vary the panel-off dwell while holding 0022 startup order fixed, or
   compare stock 0022 with the LVDS-quiet diagnostic while holding panel
   power and reset timings fixed. A FEL result alone cannot qualify the
   intermittent normal reboot path. Avoid rolling back 0022 just to
   reproduce black.
3. When the case is next open, measure actual panel-side VDD, PH16 reset
   and the LVDS clock across the warm restart. PH19 reports the supply
   command. It cannot establish how far the rail discharged, how fast it
   rose, or whether the LVDS lanes were quiet.

English and Chinese searches found no public datasheet for the exact panel
or verified fix on this board. A related H713 report attributes its black
screen to Android boot video and input selection. The V2 failure was visible
before Linux, at the U-Boot logo. Comparable LVDS designs separate panel VDD,
valid LVDS, and lamp enable. An upstream i915 fix on a different (DSI)
panel enforced minimum rail-off time after reproducing a black screen.
These are precedents for the comparisons above, with no panel-specific
delay values to import.
[杭州旭虹 LVDS guide](https://www.hzxuhong.com/solutions/202206011719.html) ·
[TI FlatLink sequencing](https://www.ti.com/lit/an/slla300/slla300.pdf#page=15) ·
[Linux i915 fix](https://lkml.indiana.edu/hypermail/linux/kernel/2104.2/02588.html) ·
[Chinese Allwinner R128 display guide](https://aw-r128.100ask.net/developer-guide/part1/chapter4/) ·
[HY300 Pro+ report](https://github.com/erikhric/magcubic-hy300-fix/blob/main/README.md#symptoms)

## How to run the tests

- Board: ssh `root@192.168.4.1` (the host joins the board's Wi-Fi AP),
  with the sandbox off, `-o UserKnownHostsFile=local/recovery/2026-11-22-v2-boot-qualification/known_hosts`
  and `StrictHostKeyChecking=yes`. The host shell is **zsh**: put ssh
  options in an array (`SSHO=(...)`, `"${SSHO[@]}"`), because a string
  variable won't word-split.
- Guarded reboot: assert the boot ID (and `signal none` for unplugged
  tests), `sync`, `systemctl reboot --no-block`. Never resend.
  `tools/hdmi/v2-qualification-run.py --poweroff` does the poweroff
  variant.
- Collection: `tools/hdmi/startup-qualification.py collect --previous-boot`
  (or `warm --from-boot ID`, which also does the guarded reboot) with
  `local/recovery/2026-11-22-v2-uboot-0022.EZo6qV/audit-slot-a-0022.py`.
  The `audit-slot-{a,b}-0221.py` files pin the 0021 primary.
  Make new audits with `tools/hdmi/make-v2-runtime-audit.py --slot X --bundle ...`.
- Serial: the CP2102 is `/dev/ttyUSB0` and is connected to the board UART.
  Run `python3 tools/serial/console.py --port /dev/ttyUSB0 --listen 120 > file &`,
  then `dmesg -n 8` on the board before rebooting (the console defaults to
  warnings only, which hides 0184's line). U-Boot lines have no timestamps.
- **Live recovery (the PH19 cycle):** `tools/display/v2-panel-supply-cycle.py`.
  Run `ssh … root@192.168.4.1 python3 - <BOOT_ID> [OFF_S] < tools/display/v2-panel-supply-cycle.py`.
  It works through `/dev/mem`: PIO base `0x02000000`, bank stride **0x30**,
  PH data at `+0x160`. It saves and quiets the LVDS/route words, holds
  reset (PH16), switches the supply (PH19) off for 5 s, powers back up and
  restores the words. It refuses on the wrong boot ID or if the pins aren't
  outputs driven high. Its `OFF_S` argument also lets you measure the
  minimum off time.
- **Every glass result needs the operator.** Ask, end the turn, and wait.
  Cold boots mean serial and USB unplugged with ≥1 min off; with serial
  connected you only get warm results.

## Do not

- Drive **PL5** low (it hard-hangs the board) or poke other `r_pio` pins.
- Read `0x07091000–0x07091fff`, `0x0694xxxx` or the `0x0500153x` lock
  window (hard locks).
- Treat register equality or "PASS digital" as a picture.
- Write U-Boot to eMMC or push without Chris's go-ahead. Approved pushes
  go only to `cstenger/*` forks. Production changes belong in `patches/`;
  generated trees and FEL diagnostics are local artifacts.

## Rest of the V2 open-items list (from Chris's list)

1. Boot testing: slot B passed a baseline, 5 warm reboots and a 4 h soak;
   slot A passed 3 cold and 5 warm, a replug, and a no-source boot. Those
   were digital checks without glass. The optical qualification above
   is complete. A source-PC reboot with the board left on passed once
   (2026-11-22): one drop, then a 720p lock 0.7 s after host nvidia-drm
   loaded, and the desktop came back with no cable touch. Evidence is in
   `local/recovery/2026-11-22-v2-host-reboot/`. That reboot kills a Claude
   session running on the PC, so run board-side work detached in `/run`.
2. Green stall: not reproduced in 60 unattended warm reboots plus the
   baseline boot (0 in 61, 2026-11-22), so the warm-boot rate is under
   about 5%. Across those boots `0x050c0c94` bit 30 and `0x05040814`
   toggled, so they are not markers. Nothing writes the four stall words.
   Both known stalls followed unusual starts (a late HPD-pulse stream on
   the A1, a FEL boot on the V2). A 30-boot FEL chain with the 0022 U-Boot
   loaded into RAM was also clean (0 in 30, 2026-11-23), so FEL alone is not
   the trigger. The same 30 with the exact 0019 U-Boot that the stalled
   boot ran were clean too, so it is 0 in 121 across the three chains.
   Untested: a first boot of a fresh slot and a late HPD-pulse stream.
   The stall stays closed as rare. See the plan's three green-stall chain
   paragraphs.
3. Firmware log level: closed. The V2 runs the vendor's `mode 1 level 1`.
4. Speaker A/V delay: V2 still uses the A1's 0.115 s.
5. V2 release builds: still separate scripts, and the AV1 probe fails the
   production check.
6. Rollout: both slots now carry 0221. The hold-guard poweroff and the
   one-HDMI-start-per-power-cycle latch still need design work. `main` is
   pushed to `cstenger/allwinner-h713-mainline`.
