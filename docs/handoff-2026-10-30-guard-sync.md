# Shutdown guard preparation handoff — October 30, 2026

**Latest endpoint, November 2: native U-Boot save-path validation PASS.**
Two native saves/two synced warm boots prove the corrected slot, probe reload
and cleanup. All nine protected regions, 59 file checks and startup health
pass. Board running Linux with HDMI locked at 1280×720; UART released.
The accepted environment now has SHA-256 `89862e4ba5304fcae54affe09d87ff7da026316c80c8b4a5a17d7a44eb3ce206`.
Older `6eb7b795…` environment pins are historical; do not reuse them as the
current generation. [Evidence and parser-stop qualification](hdmi-evidence/2026-11-02-uboot-savepath/README.md).

## Latest endpoint — installed and verified

**Latest board-focused check, November 1:** one operator power-on captured
passively; correct environment load, Linux/startup and all 56 file pins pass.
Boot `afe48e93-6604-44de-a220-acb9416e8363` remains on with HDMI none and zero
transitions/frames; host has no HDMI EDID. No recovery action. UART capture
completed and host recorder stopped cleanly. [Fresh evidence](hdmi-evidence/2026-11-01-board-boot/README.md).

**Latest host NVIDIA attempt, November 1:** one authorized attempt denied Device
allocation (`0x1b`), freed its own client and stopped before display queries.
The control-only design missed a required caller GPU FD; no retry or privilege
change ran. Later host boot changed; board remains powered off as reported.
[Analysis and consumed authorization](hdmi-evidence/2026-11-01-nvidia-cache-live/README.md).

**Latest operator state:** board powered off; the preserved HDMI failure and
live SCP session have ended. NVIDIA cached reader v2 is prepared/tested, with
no live GPU ioctl or board action. Do not reuse the old boot-bound SCP packet.
[Qualification and next snapshot](nvidia-cache-reader-2026-10-31.md).
Earlier retained-session paragraphs below are historical.

**Latest live SCP capture:** one authorized guarded sample and read-only
verification PASS. All 14 reads completed; 56 file pins, boot and HDMI bad state
are unchanged. Companion/owner lock/guard/scratch remain resident. Do not rerun,
unload, read locked owner parameters or run ordinary startup checks. No release,
HPD pulse, restart or reboot. [Retained endpoint](hdmi-evidence/2026-10-31-scp-capture-live/README.md).

**Latest SCP preparation:** sampler v2 is qualified offline and packaged against
the exact running kernel. No module was loaded and no live sample was attempted.
Same boot/SRAM, all 56 file pins and the HDMI bad state pass final read-only
checks. Capture remains a separate explicit action and retains the owner stop
lock on success or ambiguity. [Result and operating constraints](hdmi-evidence/2026-10-31-scp-capture-v2/README.md).

**Latest read-only preflight:** board now on in Linux boot
`2d8c3970-4164-4a38-8e86-375bb440c971`; identity, environment/storage/GPTs,
nine protected ranges, 56 pins and startup pass. No signal/video service
activation, so the controller's six-service gate holds live readiness.
No UART arming, service changes, save or reboot. [Fresh evidence](hdmi-evidence/2026-10-31-uboot-savepath-preflight-01/README.md).
The next power-off/preparation paragraph is historical.

**Current preparation, October 31:** save-path backups and the UART controller
are tested offline, including probe/cleanup PTY sessions and fault handling.
No recorder is armed and no hardware save or reboot occurred during this
preparation. The operator reports the board off; obtain a fresh normal Linux
boot and read-only preflight before the separately authorized warm sequence.
[Reviewable protocol/package](uboot-savepath-validation-2026-10-31.md).
The powered-on endpoints below are historical.

**Latest: one ordinary migrated warm reboot PASS, October 31.** Operator ready
and reboot authorization recorded; UART shows one restart, correct new proper,
environment load at `0x93d80000` OK and unattended Linux return. Boot
`b6849123-0398-4736-b06f-cfe25b19e593` is healthy: automatic startup/HDOK/GP7,
manifests/files, both writes/eight protected ranges and zero error/recovery
counts pass. Signal became 1280×720 lock; operator saw normal boot and the
host desktop. No extra reboot, prompt hold, RAM script, manual latch arming,
service recovery or saveenv. Fresh UART service stopped cleanly after capture;
board left on. [Warm result and coverage](hdmi-evidence/2026-10-31-uboot-warm-validation/README.md).
Audio, repeated lifecycle, save-path and hardware rollback remain pending.
No commit or push. Preparation/cold/installation entries below are history.

**Warm validation prepared, not run:** fresh passive UART service
`h713-uboot-warm-uart-20261031-01.service` is the sole reader; current-boot
read-only storage/files/startup/latch/diagnostic preflight passes. Await
operator ready for exactly one ordinary warm reboot and unattended Linux
return. [Plan and state](hdmi-evidence/2026-10-31-uboot-warm-validation/README.md).

**Latest production-cleanup endpoint, October 31: first migrated cold boot
passes.** Expected new U-Boot loaded environment from MMC(1) byte address
`0x93d80000` (`0x49ec00` LBA), reported OK, completed shared handoff and booted
Linux automatically. Boot `85768624-6a6e-4637-a50f-f45b2c156f31` passes read-only
storage/startup checks, all manifests and file pins, with HDOK/GP7 zero and no
capture/reject/restart errors. Both writes/eight protected ranges are intact.
[Current cold-boot verdict](hdmi-evidence/2026-10-31-uboot-first-boot/README.md).
No validation writes or reset/reboot; board left on. Warm boot/media/save-path
acceptance remains pending. UART log covers SPL through Linux prompt. The
earlier absent-PID interpretation was incorrect because the query used the
restricted process namespace. Host-level ownership found the original reader
alive; it was stopped cleanly before the fresh reader started. Confirm the
host user-service MainPID/sole ownership immediately before a timed test.
New work is uncommitted.
Earlier installation/preparation endpoints below are history.

**Latest production-cleanup endpoint: U-Boot/environment migration installed,
independently verified, no reboot.** Current boot
`3474b865-26f2-4b2d-bf37-1baddef732fe` remains running. Both write regions match
the pinned package and all eight protected regions are unchanged; four HDMI
manifests, file/metadata pins, services/start identities, counters, latches and
40-ms calibration pass. New proper has not run; first-boot qualification
requires a separately approved sequence. Persistent board rollback/journal:
`/var/lib/h713-uboot-migration/20261030-9efcb1e7488515a1/`; host backup under
`local/recovery/2026-10-30-uboot-migration-install/`.
[Current installed verdict](hdmi-evidence/2026-10-30-uboot-migration-install/README.md).
No service restart, clock/latch write, commit or push. Earlier checkpoints
below are retained as history.

**Latest production-cleanup continuation:** fresh read-only board/storage
preflight passes and the migration package is finalized with actual CID, GPT,
preimages and boot/runtime pins. No board staging, install, restart or reboot.
Same boot as the guard update. Twenty preflight/31 rehearsal cases pass;
19 fresh-guard/14 transaction mutations caught. Private archive:
`local/recovery/2026-10-30-uboot-migration-live/package.tar.gz`.
[Current verdict and qualifications](hdmi-evidence/2026-10-30-uboot-migration-live/README.md).
Installation still requires explicit authorization; new work is uncommitted.

**Latest continuation:** the requested U-Boot source fix, normal DDR3 candidate
and private migration package now pass offline rehearsal. No board contact or
installation. [New endpoint and deployment limits](uboot-environment-migration-2026-10-30.md).
Thirteen source/eleven panel/twenty-nine migration cases pass; nine source and
fourteen migration mutations are caught. New work remains uncommitted.
The package refuses block devices; fresh live identity/GPT/preimage collection
and finalization precede any deployment approval.

**Subsequent cleanup continuation:** `848339d` was pushed to Chris's fork.
The [offline U-Boot/environment migration plan](uboot-environment-migration-2026-10-30.md)
now pins recovery inputs and transaction/recovery ordering. Retained-input
verification, seven host tests and eight caught validation mutations pass.
No board contact or candidate build/installation in that continuation; source
fix and migration-package implementation/rehearsal are next. New work remains
uncommitted. The installation checkpoint below is preserved.

Chris explicitly approved installation, powered on the board and confirmed it
had booted. Preflight matched the reviewed generation. The guard-only update
is now installed: both copies are `96f37655…`, root:root 0755, and the backend
manifest is `4373e9ec…`, root:root 0644. All 18 backend entries and all four
installed bundle manifests pass. Exactly the three intended existing files
changed. No reboot, service restart, panel/clock/firmware operation occurred.
HDMI had no source (`none`); video stayed inactive. All service states/start
identities/restart counters and sampled error counters are unchanged, as are
the playback tools and saved 40 ms delay. No physical shutdown test was run.

Current boot ID: `7ca604ba-a805-4f0a-9bd4-2df936f50479`. Rollback backup:
`/var/lib/h713-hdmi-startup/guard-sync-537cfedf47f7420cb08aad5dbc323e21`.
Backup payloads/metadata and committed marker were saved on host at
`local/recovery/2026-10-30-guard-sync/installed-guard-backup.tar.gz`.
Read-only rollback preview passes; no rollback was performed. Board left on.
[Installation results and evidence](hdmi-evidence/2026-10-30-guard-sync/INSTALLATION-RESULT.json).

Audit, guard-sync tooling/tests and installation evidence are included in the
requested production audit/guard synchronization commit; no push. Continue
the remaining production cleanup next. U-Boot/environment migration,
stale build ledger, clocks and full assembly remain open. Preserve the original
audit as a dated baseline; its guard drift is now resolved by this new record.
The preparation history follows; repository-state statements there describe
the earlier checkpoint rather than the subsequent requested commit.

## Earlier offline preparation

Chris resumed from the [October 28 checkpoint](handoff-2026-10-28-production-cleanup.md)
and requested **offline guard synchronization preparation and tests before
installation**. The original recovery hashes were verified and audit files
preserved. **No board contact or action occurred; board power state is unknown.**

Read the [preparation report and proposed installation/rollback sequence](hdmi-evidence/2026-10-30-guard-sync/README.md).
The repository guard already has the correct additional module checks; its
bytes were not changed. New tools build and apply a narrowly pinned update
to both installed guard copies and only that backend checksum entry. No
module, service, boot/RTC/environment, lamp hook or calibration change is part
of this package. The broad signal-owner updater is not used.

Validation: 12 updater/builder tests plus three guard tests pass. All 22
deliberately faulty variants are caught, including a fault in the exact audited
generation rehearsal. The rehearsal verifies all 18 recorded backend files,
applies exactly three path changes in a host fixture, and restores original
bytes/modes. Tests substitute all log devices and lamp/poweroff actions.
No hardware shutdown behavior or live installation has been verified.

Package: `build/hdmi-guard-sync-2026-10-30/`; durable copy and source snapshot:
`local/recovery/2026-10-30-guard-sync/`. Package before-manifest hash is
`5c57391a…`; after-manifest is `4373e9ec…`. The full hashes are in the report
and package metadata. Do not use stale general build/out checksums.

The earlier next step was installation approval and a fresh generation check;
both are now complete as recorded above. Any physical shutdown test remains
a separate approved operator sequence.

At preparation time the audit, October 28 checkpoint/index edits and preparation
were uncommitted; HEAD was `d64aab0` (already pushed). They are now included in
the requested audit/guard-sync commit; no push. Historical
read-only audit and its checksums remain unchanged; the drift stays open until
live installation succeeds. The other production issues (diagnostic proper,
environment migration, stale output ledger, clocks and full release assembly)
remain as recorded on October 28.
