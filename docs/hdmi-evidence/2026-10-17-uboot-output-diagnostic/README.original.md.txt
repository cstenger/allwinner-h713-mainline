# U-Boot-only panel output diagnostic, 2026-10-17

Goal: genuine cold HDMI session -> first warm reboot -> stop before automatic Linux boot -> execute the ordinary warm-path logo initialization once -> remain in U-Boot with initialized display for visual verdict, safe state inspection and targeted recovery. Keep HDMI attached at both ends. Avoid an intervening Linux warm boot/reboot that might clear the fault.

Initial working warm boot909a1cdf-4c81-45db-a63d-c1c51bf14b99, GP6 48444d49, capture/signal inactive. Starting passive UART capture; cold cycle required to reach trigger again.

Source-reviewed warm startup: if MIPS status0306101c==0, clear PB5, `h713_disp auto 0x34 logo`, set PB5. Then ordinary startup loads kernel and bootm. Diagnostic stops after logo and never issues bootm. PB5 also powers fan; always restore PB5 after bounded initialization, including failure.

One-shot boot stop: deployed startup source handles GP7=0xb007c0de by clearing GP7 and setting volatile bootdelay=-1. Verify actual behavior at reboot; do not save environment or modify GP6. Host capture can support an autoboot-key fallback if necessary. Before display init, never read gated display registers. Never ARM-read07091000..07091fff or06940000. Only inspect display registers after successful initialization/clock establishment. Record any extra pause introduced by interception.

No firmware, stock partitions or persistent environment changes planned. Capture reconnects after serial USB removal during physical cold cycle. Target wall clock wrong; use host timestamps/uptime. Current phase: setup, before cold cycle.

Cold session verified via serial: boot62fc17e9-f74a-4a18-9225-d36558cb66d2, uptime46.85s, correct handoff bytes, GP6 48444d49, GP7 initially0, capture/signal active. SSH timed out. Set GP7 b007c0de with readback check then systemctl reboot. U-Boot consumed stop word: GP7=0, GP6 preserved, volatile bootdelay=-1, MIPS status0. No fallback key needed. Executed warm-path lamp-off/logo/lamp-on once; logo initialization reported success and returned to prompt. Linux has NOT started on this warm boot. Source-reviewed non-force h713_disp dump and selected safe status/PIO reads captured only after initialization. No recovery writes yet. Awaiting operator visual verdict.

## U-Boot-only attempt 1: GOOD

Operator report received 2026-10-17T19:34:48.104351-07:00: logo visible while held at U-Boot prompt after display initialization; Linux has not started. No black U-Boot state captured on this attempt. Initialized snapshot is a GOOD reference, not a black dump. The trigger is intermittent and interception also changes pre-init timing; no conclusion that Linux is required or interception fixes the fault.

Attempt1 timing confound: panel power phase completed20.822s after reset vs8.640s in normal first-warm black reference; logo commit21.907s vs9.721s. Manual inspection/prompt delay added about12.18s before initialization. Next attempt controller is PREPARED BUT NOT RUNNING: intercept warm one-shot stop, verify GP6 nonzero/MIPS status0, sleep5 to approximate standard countdown, initialize logo once, PB5 restored on success/failure, stop before Linux. No persistent environment writes. Current board remains in GOOD U-Boot output state; physical cold cycle can start directly since Linux has not run/filesystems not mounted in this boot. UART capture remains active.

Attempt2: new cold bootff5a821b-c5e5-4a0b-873f-1c22a768f1e6, chosen HDMI handoff verified, GP6 preserved, GP7 initially0. Services activating/inactive at17.63s, both active at45.52s. First warm reboot timer targeted70s; stop word readback checked. Automated U-Boot prompt intercept, five-second delay, guarded warm-logo sequence once, PB5 restored. Init OK, no Linux boot. Same read-only snapshot saved as attempt2-initialized-snapshot.txt before visual verdict, no recovery writes. Timing:
2026-10-17T19:37:50.508796-07:00 reset_plus=0.000s reboot: Restarting system
2026-10-17T19:37:59.116151-07:00 reset_plus=8.607s H713 panel: stock power phase complete
2026-10-17T19:38:00.200616-07:00 reset_plus=9.692s H713 disp: boot logo published and committed
Awaiting operator visual result.

## U-Boot-only attempt 2: BLACK

Operator report received 2026-10-17T19:39:46.669898-07:00: lit but black, HDMI connected at both ends. Linux has never started on this warm boot. Init timing matches ordinary boot (power phase8.607s/reset, logo9.692s/reset). Good/black snapshots compare382 addresses: only05880000 free-running counter differs. This localizes manifestation to U-Boot/hardware output; preceding Linux shutdown may still produce inherited state. Preserve state and use individual operations rather than full rerun.

First targeted intervention: read-only h713_disp scanrate confirms counter moving (3014 high-half wraps/200ms); its derived line/frame/DCLK labels are obsolete given source comments documenting a free-running10-bit clock witness, so do NOT interpret reported20.49MHz as actual pixel clock. Then ONLY pulsed TCON0588000c bit0 via00e40203 ->00e40202, matching stock timing-latch pulse; before/after readbacks00e40202. No timing registers, PLLs, panel GPIOs, firmware, full bring-up or reboot changed. Awaiting visual result.

Operator report received 2026-10-17T19:41:53.676481-07:00: still lit but black after latch-only pulse. Preparing forced stock FIFO-reset pulse plus same TCON latch pulse, with no panel power/clock/timing changes.

FIFO recovery test: baseline05700088=11111111,0588000c=00e40202,05880fe0=0. Forced stock bit8 reset clear/set11111011 ->11111111 despite status0, rewrote saved TCON config then applied same bit0 latch pulse00e40203 ->00e40202. Final readbacks control11111111, TCON00e40202, status0. No panel GPIO, clock, firmware or timing-value changes. Awaiting visual verdict.

Operator report received 2026-10-17T19:43:41.275438-07:00: still lit but black after forced stock FIFO reset plus latch. Next targeted operation: PH16 reset only, low1s then high, panel supply and LVDS/clocks unchanged. GPIO voltage at the physical panel is not measured; software readback alone cannot prove external reset delivery.

PH16 reset-only operation completed; transcript saved in panel-reset-only-test.txt. Panel supply PF6 held on; no display configuration changes. Awaiting operator visual outcome (logo, flashes or no change).

Operator report received 2026-10-17T19:45:30.045983-07:00: PH16 reset-only still lit but black. Next test is ordered panel-only supply cycle with known LVDS output-at-rest values, clocks/timing/firmware retained. No physical rail-voltage measurement available, so PF6 off proves only command/readback.

Ordered panel supply test completed: LVDS tail/ctrl/mid and route placed at known rest values; PH16 held low, PF6 commanded low with data0,3s hold, PF6 high, reset release2ms later,25ms settle, saved route40000080/mid1f300030/ctrl18000005/tail restored. Kept clock tree, firmware and AFBD configuration unchanged; PB5/fan untouched. Final GPIO/output readbacks in panel-power-cycle-test.txt. PF6 data low is not proof of actual rail collapse. Awaiting visual verdict.

## Targeted recovery: GOOD after ordered panel/LVDS cycle, same U-Boot session

Operator report received 2026-10-17T19:46:45.775983-07:00: logo returned after ordered panel supply cycle. Linux never started in this warm boot; no SoC reboot, MIPS relaunch, firmware reload, clock retune or HDMI interruption during recovery.

In this same black session: TCON latch alone -> black; forced stock FIFO-reset plus latch -> black; PH16 low1s/high with supply on and LVDS active -> black; ordered LVDS-output rest, PH16 held, PF6 off3s/on, reset release, output restore -> logo. This establishes local recovery with the compound panel/LVDS sequence, not proof that PF6 alone or3s specifically is required. Could involve panel discharge/POR, reset while lanes quiet, LVDS analog/serializer restart or routing latch effects. GPIO low did not measure actual rail voltage. Interventions were sequential and time elapsed; independent reproduction and isolation are still needed.

IMPORTANT recovered-state confound: black/recovered382-register diff shows TCON changed from720p to1080p values (mode4->2, totals02f80550->04650898, active02d00500->04380780, porch/sync words also changed) plus AFBD mux0560030c00804258->0080c258. The ordered panel/output command did not write those registers. Do not attribute recovery to panel discharge alone or claim final hardware configuration remained identical. Read-only MIPS/ownership follow-up saved in recovered-ownership.txt.

Ownership follow-up:0200160c=0 and0306101c=0 on repeated reads, consistent with MIPS still held in reset. Timing1080p readbacks stable across1s.0560030c reverted from0080c258 in recovered dump to00804258, so that bit may be live status and not persistent configuration. No new recovery writes. Timing registers were NOT sampled after every earlier latch/FIFO/reset intervention, so current data cannot locate when720p readbacks changed or attribute that transition specifically to panel cycling. Possible shadow/banked/latch behavior requires investigation; no evidence of intentional MIPS release during tests.

Next fresh-black LVDS-output-only isolation authorized 2026-10-17T19:49:06.169770-07:00. Preparation in lvds-only/README.md; reuse active UART capture and automated5s prompt/logo interception. Current board remains in recovered GOOD U-Boot state. No new writes or recovery operations performed during preparation. Awaiting physical cold cycle, HDMI connected throughout.

Quiet-LVDS panel-reset-only test authorized 2026-10-17T23:11:27.025655-07:00. Preparing staged snapshots, PF6 high throughout, no power cycle, HDMI attached, remain U-Boot. Evidence in quiet-reset/.

Staged ordered supply cycle authorized 2026-10-17T23:14:12.802851-07:00. Add3s PF6 interval with per-stage snapshots on same black U-Boot state. Script/evidence in staged-supply-cycle/.

RAM-only pre-initialization power-sequence validation prepared 2026-10-17T23:24:04.988621-07:00. Controller/evidence plan in preinit-validation/. No hardware changes made during preparation. Awaiting fresh cold cycle with HDMI attached; current good U-Boot session preserved and serial capture remains active.
