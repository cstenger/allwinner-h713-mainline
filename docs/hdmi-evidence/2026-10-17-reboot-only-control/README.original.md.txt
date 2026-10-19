# Reboot-only control, 2026-10-17

Goal: reproduce black with genuine cold HDMI startup -> warm boot. From confirmed black, leave HDMI connected at both ends and make no TCON writes; wait a comparable interval, then warm reboot. If still black, run the previously successful pattern/restore/reboot sequence on that same retained black state.

Prior matched-control reference: black boot 2cdaca84-d147-40bc-a8a0-d6cad4c9f96b, pattern start uptime 112.99s, restore 227.00s, reboot marker 238.07s; recovered with HDMI connected throughout. For this control aim to match total black-boot age at reboot (~238s) when operator confirmation allows; record actual age and any departure. No TCON pattern or restoration writes during the reboot-only phase.

Starting working warm boot 456fd8fc-a329-4580-a275-e1c1c10c168d, GP6 48444d49, no HDMI handoff, capture/signal inactive.

Passive raw/host-timestamped UART capture reconnects after USB removal. Keep HDMI connected throughout. Physical cold cycle removes mains and serial/USB for at least one minute; do not clear the launch guard in software. Target clock is incorrect, so use host timestamps and boot uptime. Preserve any recurring filesystem errors, no filesystem remediation in this test.

Current phase: setup before physical cold cycle.

Reproduction attempt 1: operator reports logo/console with HDMI connected through cold cycle. U-Boot source 3 and handoff verified. Linux handoff/GP6 verified at uptime18.68s, services then activating/inactive; waited for both to become active, as recorded in cold1-verification.txt. Trigger warm reboot initiated 2026-10-17T17:23:06.999041-07:00. No TCON writes.

Trigger warm reboot serial confirms terminal MIPS park, ordered panel shutdown, restart, warm branch, FIFO reset 2 -> 0 and boot logo commit. Awaiting operator confirmation of black before timed reboot-only control. HDMI untouched and no TCON writes by diagnostic.

Operator report received 2026-10-17T17:25:57.324950-07:00: panel lit but black, HDMI connected at both ends. Authorized timed reboot-only control with no TCON writes or HDMI disconnection. Target reboot marker uptime 238.07s to match previous pattern control.

Reboot-only control executed on black boot d465cd33-fc10-4956-8d54-d254b56f0cd4. Baseline uptime147.50s, both HDMI services inactive; timer start164.89s, reboot marker238.07s, matching prior pattern control reboot age238.07s. No TCON register accesses by this control and no HDMI disconnection. Serial: restart, warm branch, FIFO status clear/reset skipped (contrast preceding pattern control: status2/reset applied), logo committed. Awaiting operator visual outcome; capture still running.

## Result: GOOD with no diagnostic TCON accesses or HDMI disconnection

Operator report received 2026-10-17T18:32:07.540736-07:00: logo and console returned; HDMI stayed connected at both ends throughout.

A confirmed black warm boot recovered after waiting until uptime238.07s and requesting another warm reboot. No diagnostic TCON reads/writes were performed in the reboot-only phase. Normal production shutdown and U-Boot display initialization still occur on reboot and do write display registers. Therefore neither HDMI disconnection nor diagnostic checkerboard/restore writes are necessary for recovery in these controls. They are not established causes of earlier recoveries. This trial cannot separate elapsed time, another shutdown/initialization attempt, intermittent initialization, or cumulative reset effects.

Serial difference worth tracking: recovery reboot reported FIFO status clear/reset skipped; preceding matched pattern recovery reported FIFO status2/reset applied, both yielding good display. It is not a reliable good/bad classifier from these trials. Next: reproduce black and perform a prompt warm reboot with HDMI untouched and no diagnostic TCON access. If still black, wait until a recorded comparable boot age and reboot again; repeat independent trigger trials with randomized short/long waits to distinguish timing from reset count. A complementary long dwell before the FIRST post-HDMI warm reboot holds reset count fixed.
