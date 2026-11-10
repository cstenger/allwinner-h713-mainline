# Abnormal-reset recovery trial 1

Authorized by operator, 2026-10-18. HDMI stays connected, passive serial capture
running. Starting from the clean cold audio listening session with capture,
signal and speaker services active and both PCMs RUNNING.

Method: verify expected boot ID, sync filesystem writes, record UART uptime
marker, then write `b` to `/proc/sysrq-trigger`. Kernel source review confirms
this calls `emergency_restart()` without `kernel_restart_prepare()` or
`device_shutdown()`. No systemctl reboot/poweroff, service stop, display teardown,
RTC latch clearing or diagnostic TCON writes. Filesystem sync does not run the
HDMI/panel teardown. Firmware/kernel/bootloader unchanged.

This tests an immediate kernel emergency reset with hardware still active.
It does not inject a kernel hang or demonstrate autonomous hardware watchdog
expiry. Evidence: [historical trigger source](../historical-scripts/abnormal-reset-trigger.py.txt),
trigger-output.log, serial.log and after-boot
health checks. The console marker was not captured on UART; exact kernel SysRq timestamp
465.752331s and saved pre-sync uptime465.71s establish timing.
normal HDMI/panel shutdown messages should be absent from that interval.

After reboot expect the warm branch: GP6 latch set; no second cold HDMI
handoff; normal logo init applies new verified-off hold; Linux adopts720p;
HDMI services intentionally inactive. Visual panel result must be confirmed
by operator separately from serial commit/readback.

Status: reset occurred at465.752331s; new boot38cf2574… reached Linux, new
initial-off hold and logo commit captured, Linux adopted720p. No normal panel
teardown log between trigger and SPL. Warm guard retained; HDMI services
inactive by design. Existing growfs-root failure remains (predates trial).
Operator confirms logo and console returned, HDMI connected at both ends.
**PASS for this single emergency-reset recovery trial.** Leave power and HDMI alone
until observed; no automatic recovery or retry reboot is part of this trial.
