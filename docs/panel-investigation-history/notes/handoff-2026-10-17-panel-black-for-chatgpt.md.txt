# Handoff: projector panel lit but black after a warm reboot

Written 2026-10-17 for an outside reviewer (ChatGPT). Self-contained: you don't
need the repository to follow it. 28 bench trials over two days haven't found
the mechanism, so we want a fresh view: challenge the reasoning, propose
mechanisms we haven't considered, and suggest discriminating tests.

Evidence for every trial: `docs/hdmi-evidence/2026-10-16-uboot-kernel-dts/`
(README plus one directory per trial: serial logs, register dumps).

## 1. The system

- **Board:** HY200 QZ713DF_A1, a small LCD projector. SoC Allwinner H713
  (sun50iw12): 4x Cortex-A53, plus a MIPS "TV" coprocessor that runs vendor
  display firmware (`display.bin`), plus an OR1K ARISC/SCP core (unused on
  our stack: no ARISC firmware is loaded).
- **Display path:** framebuffer -> AFBD -> OSD/DE/vblender ->
  panel-window block 0x051c0000 -> TCON 0x05880000 -> LVDS lane 0x05800000,
  clocked by a display PLL at 0x058c0000 -> single-port LVDS -> a 1280x720
  LCD panel, lit by an LED lamp (lamp enable PB5, which also drives the fan).
  Panel supply = GPIO PF6 (now a regulator-fixed in the DT), panel reset =
  PH16.
- **Our software:** mainline-based Linux 6.18 with our own patches; our
  U-Boot 2026.07 (OF_UPSTREAM, using the kernel's DTS); mainline TF-A with an
  H713 port. Stock Android (vendor U-Boot 2018.05, vendor BL31 + ARISC firmware)
  is kept bootable as a reference but hasn't been run in these trials.
- **HDMI input:** the projector has an HDMI receiver. The host PC (NVIDIA,
  connector `card1-HDMI-A-1`) is normally connected to it, and we use it as an
  instrument: its connector status shows whether the projector asserts HPD.

### How the display comes up (U-Boot)

U-Boot always draws the boot logo and Linux adopts that state. The steps are a
replica of stock U-Boot, reverse-engineered: load the vendor artifacts,
replay the vendor `LogoRegData.bin` register table (prologue, timing, LVDS
FIFO reset if its status is nonzero, DE table), stock panel power (550 ms,
supply on, reset low 2 ms / high 5 ms, 20 ms), release the MIPS firmware
briefly, apply an LVDS PHY tail, quiesce the MIPS (core reset only), latch the
720p timing and publish the logo.

The boot script then branches on a once-per-power-cycle latch in RTC general
purpose register GP6 (0x07090118):

- **Cold branch** (latch 0, i.e. the first boot after power is applied): set
  the latch, bring up the display as above, then a *relaunch* of the MIPS
  firmware with a trace hook, `THal_Vp_SetSource(3)` (HDMI1) over the
  CPU_COMM RPC, re-latch 720p (the firmware reprograms the TCON to 1080p),
  and hand the HDMI session to Linux. Linux then runs the HDMI capture
  services: the receiver owner, audio, and a signal owner that asserts HPD
  via an SCP payload (HPD register 0x07091014 is reachable only from the SCP:
  an ARM read of 0x07091000 wedges the SoC).
- **Warm branch** (latch set, i.e. any later boot without a physical power
  cycle): logo only, no relaunch, no source 3, no HDMI services.

The cold branch is new (2026-10-15/16), and this bug appeared with it.

## 2. The problem

After a warm reboot (`systemctl reboot`, i.e. a SoC watchdog reset) from a
cold-branch boot, with the HDMI cable connected, the next boot (warm branch)
usually leaves the panel **lit but black**: the lamp is on, but there's no
logo and no console, on this boot and on every later warm boot. Serial shows
U-Boot's display sequence completing normally, and Linux runs fine.

- About 80% of cold-branch boots followed by a warm reset go black (good only
  about 4 in 19). Warm-branch boots followed by a warm reset: always good.
- Once black, it stays black across warm resets, PL6 core-rail cuts, and a
  1-minute mains-off. It cleared after an overnight power-off, and it clears
  when the **HDMI cable is unplugged** (then a warm reboot).

## 3. What's established

| # | Fact | Evidence |
|---|---|---|
| E1 | The trigger is the **cold branch** (MIPS relaunch + SetSource(3)), not Linux. | Cold boots forced onto the warm branch at the U-Boot prompt -> warm reboot -> good 3/3 (trials 20, 20b, 20c). Cold branch with **no** Linux HDMI at all -> black (9b). |
| E2 | A connected HDMI source is part of it. | Unplugging the cable at the projector, then a warm reboot, cleared a black state 2/2 (21b, 23); trial 24 shows it stays cleared. Nothing else short of a long mains-off ever cleared it (trial 3's PL6 recovery did not repeat in 8). |
| E3 | Unplugging **clears** the state; the cable at boot doesn't recreate it. | Trial 24: from a good boot, replug live -> no change; warm reboot with the cable in -> good. |
| E4 | It isn't HPD or an active link. | Trial 22: the signal owner put HPD back low and the host showed *disconnected* before the reset, and it stayed disconnected through the black boot -> still black. |
| E5 | It isn't the selected HDMI source. | Trial 25: `SetSource(1)` (VideoDecoder) before the park, with the firmware trace confirming 3->1 -> still black. |
| E6 | The fault is **downstream of the TCON**. | Trial 26: the TCON's internal pattern generator (bypasses framebuffer/AFBD/DE/vblender) shows **black** in the black state and a **checkerboard** on a good boot (the control). |
| E7 | No register we can read differs. | Black vs good boot: the display dump (TCON, LVDS lane, display PLL, panel-window 0x051c 60 words, AFBD, DE...) is identical except counters; the R-domain snapshot (PPU power domains, R_CCU, R_PIO L bank) is identical. |
| E8 | The panel power-down isn't the fix. | An ordered panel teardown before the reset (lamp off, LVDS at rest, reset low, 75 ms, supply off, 250 ms) is deployed and serial-verified; black still happens. Holding the panel supply off for 3 minutes in the black state, then a warm reboot -> still black (trial 2). |
| E9 | It isn't the reset source. | Our reset = main watchdog 0x02051000. Stock resets via the ARISC through the R-domain watchdog 0x07020400 (RE'd from the stock SCP firmware). Replaying stock's R_WDOG sequence: trial 27 good, repeat trial 28 **black**. |
| E10 | Stock's ARM-side bring-up = ours. | boot0 and the BL31/OP-TEE/SCP items touch no display registers. Stock U-Boot's only display code is the LogoRegData replay + panel power + MIPS release, which we replicate. None of the 45 stock kernel modules has an HDMI/TV reboot hook. Stock ARISC's only HDMI teardown is an HPD low/high pulse (`SysResetHotplug`). |

## 4. Everything tried (chronological)

| Trial | Condition | Result |
|---|---|---|
| day 1 | cold-branch session -> `systemctl reboot` | black, repeated; survived ~1-min power-offs; cleared overnight |
| step 3 | U-Boot lamp work, warm reboot from an HDMI session at ~58 s | good (U-Boot printed "FIFO status clear"; every black boot prints "FIFO status 0x2; reset applied", but so does a genuine cold power-on in trial 20, so not a marker) |
| 1 | ordered panel teardown deployed, cold branch -> reboot at 151 s | black; display regs identical good vs black |
| 2 | in black: PF6 held off 3 min, then reboot | black |
| — | in black: drove the floating PH15 (lcd_standby) and PH10-12 (SPI) high | no change (stock never drives them either) |
| 3 | in black: panel down, sync, PL6 low (collapses vdd-cpu/sys/pll/dram; board self-restarts) | good (didn't reproduce, see 8) |
| 4 | three PL6 cuts | inconclusive (rounds not attributed) |
| 5A-C | PL6 cuts from warm-branch sessions | good 3/3 |
| 6 | PL6 cut at 17.6 s on a cold-branch boot, before the HDMI services | good |
| 7 | PL6 cut from a running cold-branch session | black |
| 8 | PL6 cut from a black warm-branch session | black |
| 9 | cold branch, all Linux HDMI services disabled -> reboot | good |
| 10-19 | Linux-side bisection (capture only; receiver only; audio without DSP; TVFE hold; AudioTop bits...) | mixed; **later shown to be noise**: 13 didn't repeat (13b black), 19 (control) black |
| 9b | repeat of 9 (no Linux HDMI) | **black** -> Linux not necessary |
| 20, 20b, 20c | genuine cold power-on, forced onto the warm branch at the U-Boot prompt -> reboot | good 3/3 |
| 21a | normal cold branch -> reboot | black |
| 21b | in black: unplug HDMI at the projector -> reboot | **good** |
| 22 | cold branch, host monitored: HPD low before the reset | black; host stayed disconnected |
| 23 | in black: unplug -> reboot | good |
| 24 | from good: replug live (no change), reboot with the cable in | good |
| 25 | cold branch, `SetSource(1)` confirmed, then park + reboot | black |
| 26 | TCON pattern generator: in black / on good (control) | black / checkerboard |
| 27 | cold branch, reset through R_WDOG as stock does | good |
| 28 | repeat of 27 | black |

Cost model: every black result needs a recovery (unplug + warm reboot is
cheap now; before trial 21 it needed a long mains-off). Every test of the
trigger needs a physical cold cycle by the operator (about 1 min off). A single
good result is weak evidence because cold-branch boots come back good about
20% of the time by chance.

## 5. Current hypothesis (ours, not yet tested)

**Back-feed from the cable's +5 V.** HDMI pin 18 carries +5 V from the source,
present whatever HPD says. Once the cold branch has configured the
receiver side (the RX PHY termination / 5 V-detect path, or the DDC pin mux,
which our Linux stop returns to `io_disabled`), current from the cable may
leak into the panel or LVDS supply. Then:

- when the panel supply is "off" (reboot, PF6 held low), the rail doesn't
  collapse, so the panel's own controller / LVDS receiver never sees a
  clean power-on reset and comes up latched (E6: black even with the TCON
  pattern; E7: SoC registers fine);
- unplugging removes the source, so the next power-up is clean (E2, E3);
- a 1-min mains-off doesn't help while the PC keeps the cable live, and an
  overnight off may have coincided with the PC sleeping;
- a genuine cold power-on is fine because the leak path isn't configured
  until the cold branch runs.

Weak points: the leak path would have to survive a SoC reset (the PHY or
pin state would need to live in a domain the reset doesn't touch), and the
R-domain snapshot shows no PIO-L difference. We haven't identified what on
the board is wired to HDMI +5 V (the stock DT has no 5 V-detect GPIO, so it
goes into the SoC).

## 6. Suggestions (in the order we'd do them)

1. **Meter the panel supply.** In the black state, hold PF6 low from Linux and
   measure the panel supply rail (and the LVDS lane common mode, if
   reachable) with the cable in, then out. Any voltage with the cable in
   confirms the back-feed, and the fix becomes a hardware/sequence question.
2. **Separate "receiver configured" from "MIPS relaunched".** The cold branch
   does both. Variants: (a) cable unplugged during the cold-branch boot,
   plugged in once Linux is up, then reboot; (b) cold branch with the
   relaunch but without `SetSource(3)`. Either one says which half sets it.
3. **Read the MIPS firmware's HDMI RX bring-up for PHY/termination and
   5 V-detect writes** (`HdmiRx_5VDetectCallBack`, `port%d 5VDetect bOn`,
   `HdmiRx_Audio_PowerUpAPLL`/`PowerDownAPLL` in display.bin; MIPS address =
   ARM physical + 0xB5000000 for MMIO, image at 0x8b100000). Look for blocks
   it powers up that nothing powers down. Our park only resets the MIPS core;
   it doesn't return the RX PHY to its reset state.
4. **Stock reference run.** Boot stock Android cold with the cable in, use HDMI
   input, then warm reboot. If stock survives, its ARISC/MIPS shutdown does
   something we don't. If stock goes black too, it's a hardware quirk and we
   only need a sequence workaround.
5. **Panel-side re-init without a reboot.** In the black state, run a full
   panel power-cycle *with the cable unplugged during the off phase* versus
   *with it plugged*, then re-run the LVDS/TCON enable and the pattern
   generator. This tests the back-feed live and avoids a cold cycle per test.
6. **Statistics.** Any variant that "works" once needs at least two repeats
   (chance of a good result is about 0.2 per cold-branch trial; three goods in
   a row by chance is about 0.008).

## 7. Constraints and hazards

- Never ARM-read 0x07091000-0x07091fff (wedges the SoC; the SCP can) or
  0x06940000.
- The lamp enable PB5 also powers the fan; don't hold it low for long.
- Stock Android must stay bootable (its partitions are kept as a reference).
- Operator steps: a "cold boot" means serial + USB unplugged and power off at
  least 1 min. The host-side tools and serial capture are automated; lens
  observations need the operator.
- We prefer root-cause fixes over workarounds. A workaround would be to make
  every boot take the warm branch and give up HDMI-in on cold boots, which we
  don't want.

## 8. Questions for you

- Is the back-feed hypothesis plausible for a projector LCD panel on LVDS, and
  is there a better explanation for "only cable removal clears it"?
- What state could survive a SoC watchdog reset, a core-rail (PL6) cut and a
  short mains-off, yet be cleared by removing HDMI +5 V with the board
  running?
- Which single test would best split the remaining hypotheses?
