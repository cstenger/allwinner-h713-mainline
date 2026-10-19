# HDMI unplug/replug from an existing black warm boot

Serial captured on /dev/ttyUSB0, 115200, passive read; raw and host-timestamped logs.
Starting boot ID: 16d3edc4-f70c-4889-9389-6c6bebb12e4e.
Linux HDMI capture/signal services inactive; no HDMI handoff property observed.
Saved initial five pattern registers in before.txt. Applied trial-26 checkerboard and verified readback in pattern-on.txt.
Target wall clock is incorrect (reports April 13); use host timestamps and boot uptime for chronology.
Initial setup: no reboot performed at that point; awaiting operator observations.
Restore values: 0588000c=00E40202, 0588001c=00000004, 05880038=00080008, 0588003c=00000000, 05880040=3fffffff.

Operator report received 2026-10-17T16:44:21.283514-07:00: panel lit but black before HDMI removal; unplugged at projector and observed for 15 seconds with no change, flash or checkerboard. HDMI remains unplugged. This timestamp records receipt, not the exact unplug time.

Operator report received 2026-10-17T16:49:37.257557-07:00: reconnected HDMI and watched for 15 seconds; still lit but black, with no flash or checkerboard. HDMI remains connected. User authorized warm reboot. Timestamp is report receipt.

Warm reboot executed with HDMI reconnected. Normal five TCON register values restored before reboot; direct /dev/ttyS0 marker verified UART capture. Serial confirms ordered panel shutdown, warm branch, FIFO status 2 reset to 0, 720p timing latched, logo committed and Linux login. SSH returned on new boot f36206f8-73f6-44b4-931e-7e105976f7a9. System state reports degraded; failed-service details saved separately. Awaiting operator visual result. Serial capture remains active.

## Result: GOOD after unplug, replug, then warm reboot with HDMI attached

Operator report received 2026-10-17T16:51:33.292863-07:00: saw the logo and console after the warm reboot.

Sequence: known black warm boot with checkerboard enabled -> HDMI unplugged for at least 15 seconds (no visual change) -> HDMI reconnected for at least 15 seconds (no visual change) -> normal TCON settings restored -> warm reboot with HDMI attached -> visible logo and Linux console. The unplug interval also included time spent reporting and checking state; it was not a precisely controlled 15-second pulse.

This is the first successful unplug/replug-before-reboot control in this investigation. It supports a persistent change following cable interruption that a subsequent warm bring-up can recover from. Recovery did not require HDMI to remain absent during reboot in this trial. One trial does not prove causation or identify pin 18: unplugging also disconnects other HDMI conductors, and the pattern enable/restore plus additional elapsed time are co-interventions. A matched black-state reboot with pattern enable/restore but no cable interruption would strengthen the result.

The only failed service reported after reboot was systemd-growfs-root.service (Grow Root File System); HDMI capture and signal services remained inactive as expected on the warm branch. No service remediation was performed.

Subsequent matched-control result: see `../2026-10-17-matched-no-disconnect/README.md`. The same pattern/restore/warm-reboot sequence recovered a confirmed black panel with HDMI connected throughout. Therefore this earlier trial does not establish that cable removal caused recovery; pattern writes, elapsed time and repeat initialization are unresolved confounders.

Subsequent reboot-only control also recovered a confirmed black state at matched reboot age238.07s, without diagnostic TCON accesses or HDMI interruption. See `../2026-10-17-reboot-only-control/README.md`. Waiting, repeated shutdown/initialization or their combination remain unresolved; neither cable removal nor diagnostic pattern writes are established recovery causes.
