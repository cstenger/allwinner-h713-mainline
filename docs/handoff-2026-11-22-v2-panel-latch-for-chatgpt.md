# Handoff: V2 projector panel stays black after some warm boots

2026-11-22, from Claude to ChatGPT. Read this, then the "V2 boot
qualification" section of `docs/lpddr3-bringup-plan.md`, which has the full
evidence trail. Main is at the commit that adds this file. Nothing is
pushed.

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

## What is proven (operator confirmed the glass at every step)

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

Registers cannot tell black from good: the only differences are read-only
status words (DETN `0x050c0894/8ac/914/918/92c/930` = 0 and
`0x05140614` bit 0 = 0 when black). Trust the glass, not register diffs.

## What was done

- **Kernel 0221** (`1f15ffa6`): the V2 tree now describes `vcc-panel` on
  **PH19**, `panel-reset-gpios` on **PH16** and `backlight = <&lamp>`, as
  0183 does for the bench. That makes 0184's ordered power-down at shutdown
  run. Serial proves it runs: `panel powered down: supply off, reset line 0,
  PHY 18000000/00000030, route 40000000` just before `reboot: Restarting
  system`. It is correct and should stay, **but it is not sufficient.**
- **U-Boot 0020**: the V2 `-u-boot.dtsi` uses the kernel's `reg_panel`
  with `/delete-property/ regulator-boot-on`, as the bench's does. A V2
  build was checked. It is **not installed**, and the installed U-Boot
  behaves identically.
- Both RAUC slots hold bundle `2026.11.22.2314-1f15ffa6-0221`
  (`build/v2-panel-0221/h713-v2-panel-0221.raucb`; root `3e10f301…` with
  kernel 0220's cpu_comm fix, boot `058f681b…`). `BOOT_ORDER=A B`. The
  board was last left on boot `f3e4b1f9` (slot A), black. A power cycle
  or the PH19 cycle restores it.

## Where it latches: U-Boot's warm panel power-up

Serial on a black boot (`build/v2-panel-0221/serial-reboot-2/serial.txt`),
in order:

```
panel powered down: supply off, reset line 0 ...      (kernel 0184)
reboot: Restarting system
H713 panel: initial supply off, reset held; waiting 3000000 us   (U-Boot 0001)
H713 disp: restarted PLL during native V2 timing                  (U-Boot 0016)
H713 disp: FIFO status 0x00000002; reset applied
H713 panel: stock power pre-delay 550 ms
H713 panel: stock power phase complete: supply on, reset released
H713 panel: after display clocks: supply on, reset released
... logo committed, single MIPS launch, 720p latched, source 3, 720p latched
```

The operator saw no logo at all, so the panel fails at this power-up, after a
correct power-down and a 3 s off hold.

## The lead to pursue first

U-Boot **0016** (`patches/u-boot/0016-h713-restart-pll-during-native-v2-timing.patch`)
exists because the **native V2 timing block** "commits the logo framebuffer
but projects black". A single enable pulse on the display PLL
(`0x058c0014` bit 31, after the 20 µs setup delay, before the routing
records at offset `0x1684`) restored the logo **on one fresh FEL boot**.
That was one observation of what we now know is an intermittent failure. In
the same bring-up (`docs/lpddr3-bringup-plan.md` around the "A1 timing
block 6" table, evidence `build/v2-native-display/` and `.../minimal/`):
- the **A1 timing block 6** (648 bytes at `0x1654` of the A1
  `LogoRegData.bin`, staged at `0x60000000` with `h713_v2_a1_timing=yes`)
  gave a logo on the V2;
- the **full A1 PLL startup sequence**, with the rest of the V2 block in
  place, also gave a logo.

Since the panel is the bench's, the A1 timing and PLL startup are proven on
it across all the A1 testing. The hypothesis is that the native V2 PLL
startup, with one pulse, leaves the LVDS clock marginal at panel power-up
on warm boots, where clock and PHY state survive the reset. The live PH19
cycle works because it powers the panel up into an already stable 720p
signal.

Suggested order:
1. Diff the A1 block 6 and the V2 timing block record by record, especially
   the `0x058c0010/14` PLL records and delays. `adapt.py`, `a1-timing.bin`
   and `native-tested.c` are in `build/v2-native-display/`.
2. Over **FEL RAM boot** (no eMMC write, `tools/fel-uboot.sh`; see the plan
   doc), test the A1 PLL startup or A1 block 6 on the V2 across **repeated
   warm reboots with HDMI connected**. That is the failing case, black 2 of
   2 now. Count operator-confirmed glass results; one good boot proves
   nothing.
3. If that holds, make it the V2 default in U-Boot (replacing 0016's single
   pulse), build with `BOARD=lpddr3 tools/build/build.sh uboot`, and
   install with the existing guarded procedure
   (`local/recovery/2026-11-22-v2-hdmi-uboot/board-write-primary.sh`
   pattern: back up first, write the primary at LBA `0x49ac00`, read back).
   **Ask Chris before any eMMC U-Boot write.**
4. Alternatives if not: power the panel up only after the timing is latched
   (keep it off through the PLL restart and FIFO reset), or an ordered
   PH19 cycle at the end of U-Boot's sequence (costs seconds of boot time).

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
  with `local/recovery/2026-11-22-v2-boot-qualification/audit-slot-{a,b}-0221.py`.
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
- Write U-Boot to eMMC without Chris's go-ahead.

## Rest of the V2 open-items list (from Chris's list)

1. Boot testing: slot B passed a baseline, 5 warm reboots and a 4 h soak;
   slot A passed 3 cold and 5 warm, a replug, and a no-source boot. Those
   were digital checks without glass. This latch-up is the open finding.
   Still to do: a source-PC reboot with the board left on. It kills a
   Claude session running on that PC, so run board-side work detached.
2. Green stall: 1 in 18+ boots. `0x050c0c94` bit 30 and `0x05040814` toggle
   on healthy warm boots, so they are not markers.
3. Firmware log level: closed. The V2 runs the vendor's `mode 1 level 1`.
4. Speaker A/V delay: V2 still uses the A1's 0.115 s.
5. V2 release builds: still separate scripts, and the AV1 probe fails the
   production check.
6. Rollout: both slots now carry 0221. The hold-guard poweroff and the
   one-HDMI-start-per-power-cycle latch still need design work. Nothing is
   pushed.
