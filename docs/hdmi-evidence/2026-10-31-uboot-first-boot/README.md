# Migrated U-Boot/environment: first cold boot — October 31, 2026

**PASS: expected new proper loaded the migrated environment and booted Linux
automatically.** The operator confirmed at least one minute powered off with
serial/USB disconnected, reconnected UART while still off, then powered on
after the sole passive 115200-baud reader confirmed OPEN. No serial data was
transmitted by the recorder. The operator reported Linux booted and requested
capture review and validation; all subsequent board checks were read-only.

The decisive captured line is:

```text
Loading Environment from MMC... Reading from MMC(1) at 0x93d80000... OK
```

That is intended LBA `0x49ec00`, not the old unintended location. The proper
banner is `g320a17f71d41-h713-b3b5f2d2`, matching the installed source generation.
There is one SPL banner, one proper banner, one environment-load message, one
shared HDMI handoff, one kernel start and one Linux login, in that order. The
autoboot countdown completed without a prompt hold. No bad-CRC/default-env
fallback, environment-read failure, panic or ext4 error appears in the capture.

[UART excerpt](uart-boot-excerpt.txt), [capture proof](UART-RESULT.json),
[combined verdict](RESULT.json).

## Read-only Linux confirmation

Fresh boot ID is `85768624-6a6e-4637-a50f-f45b2c156f31`, different from the
installation boot and stable throughout collection/checking. Model/eMMC CID,
user-device geometry and partition identities match the installed generation.
No old boot-bound installation guard was weakened or reused for writes.

Both installed write-region hashes remain exact. The migrated environment
CRC is valid, both environment copies are identical, and both GPT copies
validate and match the known layout. All eight protected ranges and the full
surrounding proper/environment regions are unchanged since post-install
verification. Boot FAT, installed SPL and rescue are preserved.

All four installed HDMI manifests pass, and all 56 accepted file/metadata pins
match. The existing read-only `check-startup.sh` passes: DT handoff magic/status/
PID are valid, capture/signal are ready, receiver clocks/clients/firmware/EDID
checks pass, DSP started at 0/0 and patched to 1/1, and capture PCM is RUNNING.
GP6 is HDOK, GP7 zero; the ready session belongs to this boot. All six services
have zero recovery restarts; signal is `none`, so video remains inactive.
Capture xruns and video rejects are zero. The filesystem superblock reports
clean with no recorded error count or current-boot ext4 error. This is a
mounted read-only health observation, not an offline filesystem check.

[Linux/storage evidence](LINUX-RESULT.json) and
[startup-check output](STARTUP-RESULT.json).

## Coverage and remaining qualification

This establishes **one physical cold boot, corrected-address environment load,
uninterrupted autoboot and digital startup**. No host source/tone, picture,
colour or acoustic acceptance was performed. Warm reboot, save-path/`saveenv`
persistence and hardware rollback remain unqualified. No reset/reboot,
service restart, manual GP6 acknowledgment, environment save or other board
write was performed by validation. The board is left powered on.

The full 54,282-byte UART transcript runs from SPL to the Linux root prompt,
with host UTC timestamps and no recorded OPEN failure/disconnect. **Correction:**
the initial PID query ran in a restricted namespace and was misinterpreted as
the recorder having stopped. The subsequent host-level ownership check found
the same original reader still alive. It was stopped cleanly, with CAPTURE STOP
and UART release verified, before a fresh warm-test reader was armed.
[Correction evidence](../2026-10-31-uboot-warm-validation/prior-recorder-correction.json).
The original archive preserves the pre-stop snapshot; current timestamped
log includes the deliberate stop. The retained boot proof is unchanged.
Always confirm host-level sole ownership and OPEN before a timed test.

Raw UART, timestamped capture, arming receipt and fresh private storage archive
are under `local/recovery/2026-10-31-uboot-first-boot/`; raw CID/environment/
firmware stay local-only. Public records carry hashes and selected boot lines.
Source/evidence and checksums are saved durably. No source commit or push.
