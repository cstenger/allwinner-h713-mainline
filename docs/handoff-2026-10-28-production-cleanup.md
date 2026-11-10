# Resume production cleanup after shutdown — October 28, 2026

**Resumed October 30:** guard-only update and offline verification are prepared;
see [the new handoff](handoff-2026-10-30-guard-sync.md). No board contact or
installation occurred. The remainder below preserves the October 28 checkpoint.

Chris is taking a break and shutting down the host/board. Stop here; do not
start hardware work, tests, installations, reboots or clock changes on resume
without resolving the current state and applicable approval requirements.
No test player or known UART recorder remained running when checked.

## Work completed

Items 1, 2, 3 and 4 of the five-item board list are complete with their recorded
qualifications. Item 3 gives HDMI priority throughout the HDMI boot/session,
including signal loss; local playback requires a local-playback boot. Raw
decoder commands bypass this userspace policy. 640×480 remains unsupported.
Commit `d64aab0946dd09c32dda63485f1a4efee8bfeb3b` contains the installed policy,
tests and acceptance evidence and was pushed to `origin/h713-letterbox` on
Chris's fork. Earlier PipeWire and 40 ms calibration changes were also pushed.

The authorized item 3 install/restart verification passed: 59.63 fps, zero frame
rejects/capture xruns, and Chris confirmed motion, colours and continuous tone.
Only ring/video were restarted; capture/signal/speaker start identities and
the saved 40 ms delay were unchanged. The host test source stopped and the
HDMI endpoint volume was restored to raw 22937/35%, unmuted. See
[acceptance evidence](hdmi-evidence/2026-10-28-playback-ownership/README.md).

Item 5 began with the requested **read-only production audit**, now complete.
[Read this report first](production-audit/2026-10-28/README.md), then the
[machine-readable manifest](production-audit/2026-10-28/production-manifest.json).
The audit covers 155 installed paths and 19 boot display assets. Its files
are saved but **uncommitted and not pushed**; Chris has not asked to commit
them. Do not lose these untracked records during cleanup.

## Findings and next work

1. Both installed shutdown hold-guard copies are older than source and lack
   checks for `h713_hdmi_dsp_observe` and `h713_hdmi_dsp_access_audit`. Their old
   hashes still match their installed bundle manifest. Recommended first
   implementation task: prepare/test a narrow guard synchronization that also
   maintains the recorded installation manifest, then obtain installation
   approval. **No fix or board write has been authorized or performed yet.**
2. Installed U-Boot proper is the known October 20 diagnostic reset-controls
   image, SHA-256 `1b1f702fc7b52adf8246b124b8fbe209b7dadc651a37e53a600689810c45302e`,
   at LBA `0x49ac00`, **1877 sectors**, not the older 1798/1867-sector images.
   Its normal production build is different. Current SPL remains the older
   validated 64-sector image at LBA `0x10`, hash `cb9da874…`.
3. The documented U-Boot environment defect remains: configured LBA `0x49ec00`
   is all zero; valid active saved environment is at LBA `0x32ec00` inside
   `super`, SHA-256 `6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc`.
   Its bootcmd/preboot match the current generator. Source offset correction
   and environment migration need one explicit recovery/test plan. Never
   change the address arithmetic or save environment as an isolated repair.
4. Kernel FIT `0877293b…` and startup script `fcea3a95…` match retained/pinned
   bytes. Current startup generation reproduces exactly with retained ignored
   baseline inputs. A full clean-checkout assembly is not yet demonstrated;
   current kernel-input tree is absent, and 27 installed modules have no exact
   retained artifact match. That does not prove their source is incorrect.
5. All seven entries in `build/out/SHA256SUMS` are stale. Use the audit's actual
   hashes, not that ledger as a release identity. No ledger was repaired.
6. System and RTC calendars are wrong; no time synchronization is available.
   Use host time for evidence. Do not assume an RTC rate-driver defect: the
   existing rate fix was previously validated. Speaker experimental patches,
   retired consumer packaging, appearance/brightness closure and stale current
   documentation remain later cleanup.

## Durable recovery files

`local/recovery/2026-10-28-production-cleanup/` is a private host-disk checkpoint
outside the disposable `build/` cache. Its README, recovery archive, source
snapshot and checksum list identify what was preserved. Keep that directory
when pruning build artifacts; do not commit its proprietary/raw recovery data.
The archive includes the boot FAT snapshot and extracted display assets, the
matching installed proper/SPL/environment backup, exact prior item 3 backups,
regenerated startup bundle and the complete uncommitted audit/evidence records.

A last attempt to export the currently installed HDMI directories could not
connect to the board (SSH timeout); **no fresh complete installed-stack archive
was obtained**. The empty attempt file was removed. This does not lose the
installed update: player/services/calibration live on the board's persistent
filesystem, and their sources, exact hashes and verification are on host disk.
Existing rollback backups are verified and archived. No required work is held
only in `/run`, `/tmp`, an open terminal or a live test process.

## Resume procedure and boundaries

1. Read this handoff and the audit report; verify the checkpoint checksums.
   Check Git status and preserve the uncommitted audit files. HEAD is `d64aab0`.
2. Ask/establish whether the board is powered on before any new hardware work.
   Last successful audit boot ID was `c8f3308e-5c02-4be1-bc0e-3ee5991761e8`;
   a shutdown/restart will naturally change it. Read-only SSH checks are fine.
3. Continue the guard-sync preparation offline first, unless Chris changes
   priority. The existing [HDMI runbook](chatgpt-hdmi-remaining-work-2026-10-24.md)
   requires explicit approval for board writes/installs/panel changes and
   operator readiness for timed hardware sequences. No new authorization was
   supplied by the break/shutdown request.

Never access ARM MMIO `0x07091000`–`0x07091fff` or `0x06940000`. GP6 is the
startup/health latch; GP7 is reserved for the reboot-mode handoff. PB5 powers
both lamp and fan. This is the DDR3 bench board; the separate LPDDR3 board
remains unqualified. No additional cold/warm, physical 480p, local-playback-boot
or suspend qualification was performed by the audit.
