# Fresh-black LVDS-output-only isolation

Follow-up to same-session logo recovery after compound LVDS-output rest + panel supply cycle. User authorizes reproducing black then LVDS output disable/restore ONLY, HDMI attached, no Linux on affected warm boot, timing captures before/after each operation. Do not repeat prior latch/FIFO/panel-reset experiments before this test.

Current board initially at U-Boot prompt with visible recovered logo. Main serial.log and serial-timestamped.log in parent directory remain active across the next physical cold cycle. Linux is not running and filesystems are not mounted, so physical power removal can begin directly.

Reproduction: keep HDMI connected at both ends, mains/serial/other USB off >=60s, reconnect serial then mains; let cold HDMI branch boot Linux. Verify handoff and active services. Prepare one-shot GP7 b007c0de stop request with readback and first warm reboot near cold uptime70s. Arm existing auto-logo controller ONLY after new cold session is verified, not during cold startup. Controller uses5s delay approximating normal countdown, runs warm logo once, restores PB5, and stops before Linux. Record reset-to-power/logo timings and operator black confirmation. Capture known-safe full initial dump before modifications.

Snapshot at each boundary: TCON0588000c and0588001c..40 (mode, totals, active, porch/sync, generator words), output051c0014/28, route05140054, tail051c00d4..e0, MIPS0200160c and0306101c, PF/PH mux/data020000f0/02000100/02000158/02000160, FIFO05880fe0. Only read these after successful display initialization. No forbidden CPUS/INCAP reads and no gated-access overrides.

Before the first write, save ACTUAL live output values and validate against the source-reviewed ranges. Do not assume the previous recovered1080p readbacks apply to the fresh black state. Save actual output values for restoration. Do not make TCON timing/latch/FIFO writes; snapshots only.

Planned disable stages, snapshot after each and compare with previous:
1. Set output tail051c00d4/d8/dc/e0 to zero as one known group.
2. Set051c0014 to18000000 (known rest).
3. Set051c0028 to00000030 (known rest).
4. Set05140054 to40000000 (known rest).
Brief1s rest with no panel GPIO writes.

Restore stages, snapshot after each:
5. Restore saved route05140054.
6. Restore saved mid051c0028.
7. Restore saved control051c0014.
8. Restore saved tail four-word group.

Panel PF6 and reset PH16 MUST remain high throughout; PB5/fan stays high. Clock tree, MIPS state, timing/latch/FIFO and frame content not intentionally changed. If unplanned timing changes occur, record exact first boundary instead of assuming an analog-only mechanism. Compare full post-test snapshot and obtain visual result; do not perform another intervention before operator observes the output-only result.

No persistent environment or firmware writes planned. Main capture continues; auto-intercept controller is PREPARED, NOT RUNNING while awaiting the physical cold cycle.

Cold session verified 2026-10-17T19:50:45.221820-07:00: bootb1b3801b-8e8b-4470-a504-2c9e797179bb, uptime39.86s, correct HDMI chosen handoff, GP6 latch preserved, GP7=0, capture/signal active. First warm reboot targeted70s, automated5s U-Boot logo interception before Linux.

Warm interception succeeded; init OK, lamp/fan restored and Linux NOT started. No preparatory latch/FIFO/reset/power-cycle writes. Initial full plus timing/output/ownership/GPIO snapshot saved. Timing:
reset_plus=0.000s reboot: Restarting system
reset_plus=8.588s H713 panel: stock power phase complete
reset_plus=9.673s H713 disp: boot logo published and committed
Awaiting visual black confirmation before LVDS-only intervention.

## Reproduction attempt1: GOOD, no LVDS-only writes performed

Operator report received 2026-10-17T19:52:09.267208-07:00: logo visible at U-Boot-only hold. Archived initial snapshot, cold verification and timing in attempt1-good/. Linux has not run on this warm boot. Do not interpret this as recovery: no output-disable/restore intervention was performed. Trigger remains intermittent. Continue physical cold cycles with unchanged HDMI and auto-interception timing to capture black. Serial capture remains active.

Reproduction attempt2: cold068b380e-0028-45f6-af84-e5760be8a654 verified at uptime36.86s, both services active, handoff valid. Timer targeted70s; automated5s interception/logo init succeeded. No Linux boot, no preliminary diagnostic writes. Full/timing/output/ownership/GPIO snapshot in attempt2/. reset_plus=0.000s reboot: Restarting system; reset_plus=8.721s H713 panel: stock power phase complete; reset_plus=9.822s H713 disp: boot logo published and committed Awaiting visual verdict.

## Reproduction attempt2: GOOD, no LVDS-only intervention

Operator report received 2026-10-17T20:27:26.013127-07:00: logo showing while held in U-Boot after initialization. No LVDS-only writes made. attempt2/ is a second fresh-good baseline, not a recovery result. Linux has not run on this warm boot. Continue same reproduction protocol; do not change test just because two independent attempts stayed good. Capture remains active.

Reproduction attempt3: cold18a49f4b-a2b9-4589-9329-6793fb1e8875 verified at28.80s, both services active, handoff valid. Same70s target and5s auto-interception/logo sequence succeeded; Linux not started. Initial snapshot in attempt3/. No diagnostic recovery writes. Awaiting visual verdict.

## Reproduction attempt3: GOOD, no LVDS-only intervention

Operator report received 2026-10-17T22:57:44.918538-07:00: logo currently visible in U-Boot. No output-only writes performed. Three consecutive fresh reproduction attempts for LVDS isolation stayed good. Do not treat them as successful recovery tests or assume old baseline failure probability is stationary. Before another cold cycle, add actual HDMI receiver/source-condition observations; active service/handoff is not equivalent to verified live input lock. Current good U-Boot state preserved, capture active.

Next reproduction observation plan: while cold Linux HDMI services/firmware are active, record PC connector /sys/class/drm/card1-HDMI-A-1/{status,enabled,modes} using existing host access, and firmware port status via existing read-only query `timeout 5s /root/cpu-comm-probe THal_Vp_HDMI_GetPortStatus_1_000` (run-detection-trial.py uses this query). Do not run the detection-trial orchestration itself: it changes source/setup. Do not load new capture helpers or force an output mode just to obtain status. This adds input-condition evidence before deciding whether to change reproduction timing. Existing receiver resource-owner status alone does not report actual RX lock. No additional hardware writes performed at this preparation step. Preserve normal70s trigger target if observations fit; report any overrun.

Reproduction attempt4: cold5220e171-2246-451d-bc61-5da92f34fedc verified29.82s, both services active. PC connector connected/enabled sampled40.54s; firmware GetPortStatus returned2, raw meaning not assumed to prove all lock bits. First warm trigger target70s, same5s automated U-Boot init successful, no Linux started. Initial snapshot saved in attempt4/. No diagnostic recovery writes. Awaiting visual result.

Attempt4 operator confirmed lit-but-black 2026-10-17T23:05:59.604390-07:00. Proceeding with output-only staged disable/restore; PF6/PH16 untouched, timing snapshots before/after each individual control group, no preliminary latch/FIFO/reset tests.

Attempt4 LVDS-only staged test COMPLETED. Source/initial state verified. Eight steps: tailoff, ctrloff, midoff, routeoff,1s rest, routerestore, midrestore, ctrlrestore, tailrestore. Each step captured timing/output/MIPS/panel GPIOs immediately before and after. No timing readback changes at any step; all remained720p. PF6 and PH16 high at all sampled boundaries, MIPS held reset, final output controls exactly restored. No panel GPIO writes, TCON writes, FIFO reset, clock retune, firmware reload, Linux boot, SoC reset or HDMI disconnection. stage-summary.txt and per-boundary snapshots in attempt4/. Awaiting operator visual outcome.

## Attempt4 LVDS-only result: BLACK

Operator report received 2026-10-17T23:07:51.397336-07:00: still lit but black after all eight LVDS-only steps. Output rest/restore alone insufficient on this fresh black state. Panel supply/reset untouched; timing readbacks720p throughout. No1080p transition. Preserving black in U-Boot; capture remains running.

Next discriminating operation: assert/release panel reset while LVDS output is at rest, keeping PF6 supply ON throughout. This separates reset sequencing with quiet lanes from actual supply cycling. Reset with active LVDS failed in previous black session; output rest/restore alone failed here. If quiet-lane reset fails, ordered rail cycle on this same state with timing captures at GPIO and output boundaries isolates the successful prior compound operation more closely. No additional intervention performed after this visual verdict.
