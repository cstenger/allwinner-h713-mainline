# Remove the autoboot countdown

Chris accepted the completion-aware IPC and parallel capture startup changes
for continued development, after the six matched cold observations and earlier
five warm checks. The earlier rejection evidence remains preserved. Chris then
explicitly chose removal of the countdown instead of reducing it to two seconds.

The saved RC environment was pinned to SHA-256
`89862e4ba5304fcae54affe09d87ff7da026316c80c8b4a5a17d7a44eb3ce206`.
It contained bootdelay=5. The installed candidate changes that one payload byte
to bootdelay=0 and recomputes the four-byte CRC; every other byte, ordering and
padding are retained. Candidate SHA-256:
`e6a56d4c6f2703c9360c29da4d1e1aec2d35bafd57bc6ca8232896e0296bc3ab`.
No bootloader binary rebuild/write is involved. The first cold boot measured a 4.996-second saving to the kernel-entry UART
message, consistent with removing the five-second wait.
[Cold-boot result](cold-01-result.json).

The inspected U-Boot common/autoboot.c and boot/Kconfig specify that zero has
no timed countdown but still checks buffered key input. -1 disables autoboot;
-2 would bypass the abort check and was not selected. Saved preboot remains
unchanged: the kernel bootloader reboot-mode marker b007c0de is consumed and
sets volatile bootdelay=-1, independently of the saved zero. The existing
fastboot marker and physical FEL recovery entry remain defined unchanged.

The installer validates the exact RC environment, CRC, parsed policy, board,
boot ID, eMMC CID/type/capacity/sector size, reserved partition bounds and lack
of mounts/holders. It verifies pinned SPL/proper before and after, as well as
unchanged neighboring 64-KiB regions, both GPTs and the two-MiB preserved rescue
proper at LBA 0x4a0c00. Only the environment's 64-KiB range is written, with
fsync and direct-I/O readback. A durable intent and exact before/after images
are saved first; a failed/short write restores the original while Linux is
alive. Sudden power loss is not an atomic or fully rehearsed recovery claim.

Five host tests cover exact-byte policy preservation, CRC/duplicate/wrong-image
refusal, apply/explicit rollback, short-write rollback and bad-readback rollback.
The exact package and full 73-file/current-kernel/package/raw-boot/bundle audit
passed before installation. Afterward the same audit passed with only the
expected raw environment SHA changed; both startup optimizations and the
unchanged-guard diagnostic module remain installed.

On-board committed backup:
`/var/lib/h713-hdmi-startup/autoboot-zero-1530d383e36c4edea75ef76b3e6d76a3`.
Its full archive and original image are also retained on the host. Explicit
rollback supports only the recognized zero-delay state and restores the exact
original five-second environment. Historical frozen release artifacts were not
rewritten; their original environment pin remains intact.

The recorded orderly reboot-to-bootloader validation passed. It used the
existing tested run-warm-shared.py request function with reboot-mode driver/DT
checks and systemctl --reboot-argument=bootloader, without raw RTC writes.
No MIPS owner will be restarted from the parked prompt. Cold boot is required
for the subsequent normal HDMI timing measurement.

Private package, backups, test logs and UART evidence:
`local/recovery/2026-11-05-autoboot-countdown/`.

## Bootloader-stop validation

Exactly one orderly restart reached the held U-Boot prompt without running the
HDMI startup script. `printenv` confirmed the unchanged bootcmd/preboot and
volatile bootdelay=-1 from the existing marker handler. A bounded 128-sector
MMC read from LBA 0x49ec00 into 0x50000000 returned CRC32 9a6d7d6f, matching the
full saved zero-delay image. No `saveenv` was issued at the prompt. The SSH
connection closed with 255 during the successful restart; it was not retried.
[Structured validation](bootloader-stop-result.json).

The held bootloader was then powered off with its supported poweroff command.
Separate passive UART and five-minute Linux observers are armed for cold-01.
Cold boot requires power and UART/USB removed for over one minute. Compare
first-SPL → countdown/startup-script/kernel milestones against the previous
matched captures, with the same desktop source. Linux service readiness should
remain near 16.24 s; predicted first-SPL-to-video saving is about five seconds.
Do not treat the installed update or stop-path success as a completed cold
latency measurement. The post-cold RC audit must use audit-after.py, whose only
new pin relative to the optimized trace arm is the raw environment SHA.

## First cold-boot measurement completed

Chris disconnected power and board-side UART/USB for over one minute, then
confirmed the HDMI desktop returned and kept the same desktop showing.
Boot `3636858d-5ab9-49a8-9445-5e3ae5bd4048` passed the fixed five-minute
observation and the full post-cold 73-file/kernel/package/storage/boot/bundle
runtime audit, with only the authorized environment pin changed.

| UART interval | Previous optimized cold boots (mean of 3) | Zero countdown |
| --- | ---: | ---: |
| Autoboot message → script execution | 5.023255 s | 0.008147 s |
| First SPL output → kernel-entry message | 14.725 s | 9.729 s |

Measured kernel-entry-message saving: **4.995805 seconds**. Script-to-kernel
work remained near 7.65 s; the improvement comes from the removed countdown.
[Per-capture timestamps](uart-timing-comparison.json). Host UART receive times
exclude power-on-to-first-SPL and do not measure first visible pixel latency.
This is one zero-delay cold boot compared to three preceding optimized boots.

Linux video service active at 16.147241 s, consistent with the previous
optimized 16.105–16.358 s range. Capture ready at 14.418867 s, prepare/user
startup overlap 3.272163 s; five IPC checks passed in 0.425–0.450 s, prepared
backend adoption and HDOK/zero GP7 passed. The loaded diagnostic module build-ID
matches the prior optimized baseline. Fixed window ended at 316.147241 s, final
sample 316.32 s; sampled 59.710 fps, zero rejected copies, audio xruns, bad guards,
invalid pairs and service restarts. Source remained locked 720p, both PCMs RUNNING.

Host Wi-Fi needed its saved profile reactivated. First live sample was 59.83 s;
the deadline stayed fixed and boot-wide kernel journal/cumulative counters cover
earlier rejection outcomes. No board network/service recovery was performed.
The preceding orderly reboot restored signal ownership, 22 DSP and 15 TVFE
words, parked/removed the receiver and stopped capture before the user manager.
The board remains running with zero countdown, both accepted startup changes,
and the unchanged-guard diagnostic trace. The passive recorder/observer are closed.
Historical rejection evidence remains intact.

## Next candidate: independent AIC8800 module startup

Read-only collection confirms that modules-load takes 2.859 s in this boot and
blocks sysinit/basic, HDMI prepare, hotspot and Bluetooth attach. The rootfs
builder places aic8800_bsp, aic8800_fdrv and aic8800_btlpm together in the global
modules-load list. Both hotspot and BT attach currently depend on that global
service rather than a dedicated AIC readiness unit.

Prepare a separate module owner that preserves BSP → Wi-Fi/BT dependency order,
explicitly orders hotspot/BT after it, and allows HDMI to proceed independently.
First verify SDIO/udev autoload interactions and shared combo-chip power
ownership; removing lines alone may neither remove the wait nor preserve
readiness. Keep required HDMI/scanout module loading and all current recovery/
shutdown rules. This is a candidate for overlap, not a measured additional
2.859-second saving. No Wi-Fi startup modification is installed.
Private read-only dependency receipt: next-wifi-dependencies.log.
