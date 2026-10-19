# PC-end HDMI disconnect trial, 2026-10-17

Goal: reproduce black after a genuine cold HDMI branch followed by warm reboot; then disconnect/reconnect HDMI at the PC end only, leaving the projector socket untouched, and warm reboot with HDMI connected.

Starting state: visually good after preceding unplug/replug trial, boot f36206f8-73f6-44b4-931e-7e105976f7a9, RTC GP6 48444d49, no HDMI handoff, capture/signal inactive.

Passive UART recorder handles USB adapter removal and reconnect without writing UART commands. Target wall clock is wrong; use host timestamps and boot IDs/uptimes. Physical cold step must remove mains and serial/USB backpower for at least one minute. HDMI remains connected at both ends during reproduction.

Current phase: capture setup; physical cold cycle not yet performed. No PC-end disconnect yet.

UART marker verified. Issued systemctl poweroff; serial confirmed filesystems unmounted, panel shutdown and final `reboot: Power down`. Shutdown also reported `EXT4-fs error ... Orphan file not empty on read-only fs` before remounting root read-only; retained in serial log for follow-up, no filesystem repair attempted. Awaiting operator physical cold cycle with HDMI untouched.

Cold cycle completed by operator, logo and console visible. Serial confirms source 3 transition-complete=1 and cold startup handoff verified. Serial-shell verification: boot a4f15c64-9cd1-4c62-84d7-ba8d7eb3f42c, handoff bytes 48 44 4d 49 00 00 00 00 8b 8f 27 5c, GP6 48444d49, both capture and signal active. SSH timed out; serial shell used. Initiating warm reboot with HDMI untouched at 2026-10-17T16:58:24.168347-07:00.

Warm trigger reboot: serial confirms signal/audio shutdown, terminal MIPS park, ordered panel power-down, restart, warm branch selected, FIFO reset 2 -> 0, and boot logo committed. Awaiting operator visual verdict before any HDMI disconnection. Recorder remains active.

Operator report received 2026-10-17T17:00:09.244958-07:00: HDMI remains connected at both ends; Linux console visible after trigger reboot. Reproduction attempt 1: GOOD, black not reproduced. No PC-end disconnect performed. Preparing attempt 2 using another physical cold cycle; no launch guard cleared in software.

Attempt 2 cold startup: operator reports logo and console with HDMI connected. U-Boot source-3 transition and cold startup handoff verified. Linux serial verification: boot 3a511e0e-a5b8-4370-aee0-8a4bc56b8284, uptime 34.49s, correct HDMI handoff bytes, GP6 48444d49, both capture and signal active. Warm reboot requested at 2026-10-17T17:01:56.323423-07:00.

Attempt 2 warm reboot completed to serial login: terminal MIPS park verified, ordered panel shutdown, warm branch selected, FIFO reset 2 -> 0 and boot logo committed. HDMI untouched; awaiting visual verdict. No TCON pattern applied and no PC-end disconnect yet.

Operator report received 2026-10-17T17:04:33.385223-07:00: attempt 2 warm boot is lit but black, HDMI still connected at both ends. Black successfully reproduced. Beginning PC-end disconnect test.

Black baseline verified on warm boot 15e509ab-d816-465f-b46e-3dd296cee503, no HDMI chosen property, capture/signal inactive, normal TCON registers saved. Applied identical trial-26 checkerboard and verified all five register readbacks; see pattern-on-serial.txt. Awaiting operator PC-end unplug, with projector-end HDMI socket untouched.

Operator report received 2026-10-17T17:05:46.628621-07:00: HDMI unplugged at PC end only; projector end untouched. Watched 15 seconds, panel remained lit but black with no flashes or checkerboard. HDMI remains unplugged at PC. Timestamp records report receipt, not exact disconnect time.

Operator report received 2026-10-17T17:06:36.863002-07:00: reconnected HDMI at PC end, watched 15 seconds, remained lit but black with no flashes or checkerboard. Projector end untouched throughout. HDMI connected at both ends. User requested warm reboot.

PC-end recovery reboot executed with HDMI connected and projector-end connector untouched. All five normal TCON readbacks verified before reboot. Serial confirms ordered panel shutdown, restart, warm branch, FIFO reset 2 -> 0, logo committed and Linux login. Awaiting operator visual outcome; serial recorder remains active.

## Result: GOOD after PC-end disconnect/reconnect and warm reboot

Operator report received 2026-10-17T17:08:16.971655-07:00: logo and console returned. HDMI connected at both ends for reboot; projector-end connector never touched during recovery.

Attempt 1 did not reproduce black. Attempt 2 verified cold HDMI handoff and active services, then warm reboot reproduced black. From that black warm boot, enabled trial-26 checkerboard; PC-end disconnect and reconnect each produced no visible change over operator observation of at least 15 seconds. Normal TCON restored; warm reboot with HDMI attached restored visible logo and console. Disconnect duration included reporting/checking intervals, not a precisely controlled 15-second pulse.

Interpretation: recovery does not require manipulating the projector socket or leaving its HDMI receptacle empty during reboot. Source-side connection interruption is sufficient in this one trial, consistent with projector-end recovery in the preceding trial. It does not distinguish source +5 V removal, DDC/CEC/TMDS removal, PC ground/shield disconnection, or hotplug-induced changes at the PC. A durable state change followed by display reinitialization is supported; immediate recovery was not observed. A matched no-disconnect black-state pattern/restore/reboot control and selective electrical isolation remain useful. No hardware root cause established.

Subsequent matched-control result: see `../2026-10-17-matched-no-disconnect/README.md`. The same pattern/restore/warm-reboot sequence recovered a confirmed black panel with HDMI connected throughout. Therefore this earlier trial does not establish that cable removal caused recovery; pattern writes, elapsed time and repeat initialization are unresolved confounders.

Subsequent reboot-only control also recovered a confirmed black state at matched reboot age238.07s, without diagnostic TCON accesses or HDMI interruption. See `../2026-10-17-reboot-only-control/README.md`. Waiting, repeated shutdown/initialization or their combination remain unresolved; neither cable removal nor diagnostic pattern writes are established recovery causes.
