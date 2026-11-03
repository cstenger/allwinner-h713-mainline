# U-Boot production migration: offline recovery plan

**November 2: native save/reload/cleanup validated.** Both native saves pass
at LBA `0x49ec00`; the marker reloads on the second warm entry and is absent
after cleanup. Storage outside the slot, nine protected regions, all 59 file
checks and startup health pass. Hardware rollback and power-loss behavior
remain untested. [Final results and accepted generation](hdmi-evidence/2026-11-02-uboot-savepath/README.md).

## Current preparation — save-path UART controller tested offline, October 31

**Fresh preflight update:** board now on in boot `2d8c3970-4164-4a38-8e86-375bb440c971`.
Identity/storage/GPTs, nine protected regions, all 56 file pins and startup
pass. Live readiness remains held: signal `none`, video inactive; the unchanged
controller service gate refuses this capture. No UART arming, save, service
change or reboot. [Read-only evidence](hdmi-evidence/2026-10-31-uboot-savepath-preflight-01/README.md).
The following power-off description is the earlier preparation checkpoint.

Fresh backups and source/semantic storage rehearsals are preserved. The
two-phase UART controller now passes offline protocol, pseudo-terminal and
fault tests; it is not armed and no hardware save has been attempted. The
operator reports the board off. A new normal Linux boot and fresh read-only
preflight are required before any separately authorized warm save-path run.
[Protocol, controller package and test evidence](uboot-savepath-validation-2026-10-31.md).
Hardware save/reload/cleanup and recovery remain unqualified. Prior boot
validation endpoints below describe their historical powered-on state.

## Latest endpoint — cold and one ordinary warm boot validated, October 31

The operator-authorized one ordinary warm reboot is complete. UART proves
one warm restart, expected proper, migrated environment load at `0x93d80000`
with OK, shared handoff and automatic Linux return. New boot
`b6849123-0398-4736-b06f-cfe25b19e593` passes startup and storage/file/manifest/
latch/health checks with zero errors/recovery restarts. Both write regions
and eight protected ranges remain intact. Initial signal `none` became
1280×720 lock after return; the operator confirmed normal boot and the host
desktop. No prompt hold, RAM script, manual latch arming/recovery or extra
reboot. Passive capture was stopped cleanly after verification; board left on.
[Warm verdict and exact coverage](hdmi-evidence/2026-10-31-uboot-warm-validation/README.md).
Repeated lifecycle, audio, save-path and hardware rollback remain unqualified.
Work is uncommitted. Earlier preparation/cold checkpoints follow as history.

## Earlier endpoint — first cold boot validated, October 31

**Warm-test preparation now complete:** a fresh sole passive UART reader is
armed under host user-service supervision and read-only preflight passes on
the same cold-boot session. No warm reboot has been issued; await operator
ready for one ordinary unattended reboot. [Exact plan and arming receipt](hdmi-evidence/2026-10-31-uboot-warm-validation/README.md).

UART confirms the expected new proper banner and
`Loading Environment from MMC... Reading from MMC(1) at 0x93d80000... OK`.
One physical cold boot reached Linux automatically, with no U-Boot prompt hold
or default-environment fallback. New boot
`85768624-6a6e-4637-a50f-f45b2c156f31` passes read-only storage, all four HDMI
manifests, 56 file/metadata pins and the automatic startup checker. Both write
regions and eight protected ranges remain intact; environment CRC is valid,
session is ready, latches HDOK/GP7 zero, and error/restart counts are zero.

[Cold-boot proof, Linux checks and coverage limits](hdmi-evidence/2026-10-31-uboot-first-boot/README.md).
No validation write, reset/reboot or service recovery was issued. Board left
on. Warm boot, picture/audio, save-path and hardware rollback qualification
remain pending. The earlier claim that the first reader stopped was a process-
namespace visibility error: a host-level check found it alive, then stopped
it cleanly before arming the fresh warm reader. The original boot proof is
unchanged. Confirm host-visible sole ownership/OPEN immediately before any
timed boot test. Work remains uncommitted.

## Earlier endpoint — installed and verified; no reboot

The authorized migration is installed on boot
`3474b865-26f2-4b2d-bf37-1baddef732fe`. A fresh collection matched the reviewed
board/CID, both preimages and all protected bytes; the finalizer refreshed
only boot-bound observations. One detached invocation copied the environment
to LBA `0x49ec00` first, then wrote the pinned proper at `0x49ac00`.
Journal is `installed`, exit zero. Independent direct reads verify both write
regions and all eight protected ranges, plus complete surrounding regions.
All four HDMI manifests, 56 file/metadata pins, service/start identities,
counters/signal, latches and 40-ms calibration remain unchanged.

**No reboot, service restart or clock/latch write.** Board remains running;
the new proper has not executed and boot/media/save-path acceptance remains
pending a separately approved operator sequence.
[Installation verdict, hashes and recovery](hdmi-evidence/2026-10-30-uboot-migration-install/README.md).
Exact board rollback and journal:
`/var/lib/h713-uboot-migration/20261030-9efcb1e7488515a1/`; verified host copy:
`local/recovery/2026-10-30-uboot-migration-install/installed-board-backup.tar.gz`.
Work is uncommitted. The earlier checkpoints below are history.

## Earlier installation authorization — awaiting board startup

Chris requested installation and verification of both write regions and all
protected storage, explicitly without reboot; the board is off. Offline
package/archive/recovery checks pass. No board contact or installation in this
step. Await normal power-on and boot confirmation, then refresh the boot-bound
preflight/package and install under the existing authorization without reboot.
[Installation checkpoint](hdmi-evidence/2026-10-30-uboot-migration-install/README.md).

## Earlier endpoint — fresh read-only preflight and finalized package

The requested read-only board identity/storage checks pass. Both GPT copies,
CID/user-device geometry, reserved partition ownership/use, full proper/rescue
regions, SPL, both environment regions/margins, boot FAT, installed files,
service/runtime identity and filesystem checks were collected without writes.
An stdin-only preview verified 56 files, eight protected ranges and direct
reads of both write preimages. Same boot `7ca604ba-a805-4f0a-9bd4-2df936f50479`;
no files staged on the board, installation, restart or reboot.

The durable live-pinned package is now
`local/recovery/2026-10-30-uboot-migration-live/package/` (and `package.tar.gz`).
It replaces synthetic markers with fresh GPT/boot backups and has an explicit,
guarded live mode; no live write mode was executed. Twenty preflight tests and
31 rehearsal cases pass; 19 preflight/live-mode and 14 transaction mutations
are caught. [Fresh evidence, exact identity and deployment qualifications](hdmi-evidence/2026-10-30-uboot-migration-live/README.md).

The package is pinned to this boot and exact service/runtime generation and
requires rechecking at use. Any installation remains separately authorized;
do not reboot, save environment or deploy proper alone as a follow-up to this
read-only request. Raw captures/CID/firmware stay private. Work is uncommitted.

## Earlier implementation endpoint — October 30

The requested source fix and offline package/rehearsal are complete; no board
contact or installation. Patch `0003-env-mmc-preserve-configured-offset-width.patch`
is in the normal series; unrelated untracked `0002` remains excluded. The final
normal DDR3 candidate embeds the accepted BL31 and DTB exactly and logs the
selected environment byte offset in the existing load message.

Thirteen compiled source cases, eleven panel cases and twenty-nine sparse-disk
rehearsal cases pass. Nine source mutations and fourteen migration mutations
are caught. Every source case fails under a relevant mutation. See
[results, identities and limits](hdmi-evidence/2026-10-30-uboot-migration/README.md).

Private final package: `build/uboot-migration-2026-10-30/package/`;
durable archive: `local/recovery/2026-10-30-uboot-migration/package.tar.gz`.
Candidate proper FIT is 955665 bytes (1867 sectors); the transaction/rollback
covers the full current 1877-sector extent. Intended environment is staged
before proper; rollback restores proper before the intended-slot preimage.

The package is restricted to regular host disk images. Its device markers are
synthetic fixtures, not live CID/GPT evidence. It cannot install to a block
device. Live collection/finalization of board identity, GPT ownership, current
preimages/full surrounding regions and recovery checks remains before
deployment review. The retained full-region tail/rescue inputs are historical,
not fresh live readbacks. Source/package work is uncommitted.
The original plan below is retained as preparation history.

## Original planning checkpoint

Prepared October 30 against `848339d`. **Offline planning and retained-input
verification only.** No board contact, source-series change, candidate firmware,
installer, environment save, reset or new hardware qualification is included.
The shutdown guard update is installed and was pushed in `848339d`; its
physical shutdown test remains open.

## Why proper and environment must move together

The pinned U-Boot source's `env/mmc.c:mmc_offset()` passes an `s64` fallback
through `ofnode_conf_read_int()`. That helper takes/returns `int`; a missing
`/config` node therefore narrows the absolute offset `0x93d80000` to
`-1814560768`. `mmc_get_env_addr()` adds capacity `7818182656`, then stores
`0x165d80000` in `u32`, leaving `0x65d80000`: LBA `0x32ec00`.
The [baseline](hdmi-evidence/2026-10-20-reset-baseline/README.md#confirmed-environment-address-defect)
and [October 28 inventory](production-audit/2026-10-28/board-inventory.json)
agree. This misplaced environment has a valid CRC and the accepted startup
guards. The intended slot at LBA `0x49ec00` was zero-filled.

The proposed source correction must preserve the full-width configured fallback
when the DT property is absent; do not change the global helper's API or merely
cast its already-narrowed result. Explicit DT overrides, negative relative-end
offsets, redundant copies, invalid-offset sentinels and partition/GUID precedence
need separate regression cases. Confirm the exact built DDR3 configuration,
DT `/config` contents and `mmc_get_env_dev()` boot-device selection. Do not
infer the environment device from `CONFIG_ENV_MMC_DEVICE_INDEX=0` alone:
the sunxi board overrides that choice at runtime.

Keep the existing SPL, BL31, display DT behavior and three-second initial
panel-off sequence. Build normal production proper from the pinned base plus
the selected patches, excluding reset-trace instrumentation. Compare the final
configuration and extracted FIT payloads with the accepted baseline; record
every deliberate change. Do not apply the unrelated untracked `0002` patch.

## Recovery identities already checked offline

`python3 tools/hdmi/check-uboot-migration-inputs.py` verifies the durable
October 28 checkpoint's checksums, the retained current proper's hash/FIT
header, active environment hash/CRC and all four audited startup-policy values,
the installed SPL backup and FEL rescue SPL. It prints no environment values.
It requires local ignored recovery inputs; it is not a clean-checkout builder.

| Role | Location and extent | SHA-256 |
| --- | --- | --- |
| Current diagnostic proper / exact rollback | LBA `0x49ac00`, 1877 sectors, 961024 padded bytes; FIT 960817 bytes | `1b1f702fc7b52adf8246b124b8fbe209b7dadc651a37e53a600689810c45302e` |
| Active environment to preserve | LBA `0x32ec00`, 128 sectors / 65536 bytes | `6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc` |
| Intended environment preimage | LBA `0x49ec00`, 128 sectors, all zero in audit | `de2f256064a0af797747c2b97505dc0b9f3df0de4f489eac731c23ae9ca9cc31` |
| Installed SPL backup | LBA `0x10`, 64 sectors | `cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec` |
| FEL rescue SPL | Host file `build/out/h713-rescue-spl.bin`, 32768 bytes | `dab3b1585a8d05d30d87a57795fa505409304ce7287cfa58d5c8deed1bcf75f0` |
| Historical rescue proper prefix | LBA `0x4a0c00`, 1798 sectors | `c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7` |

The current proper rollback bytes are
`build/hdmi-reset-controls-2026-10-20/trial-package/proper-controls.bin`.
The active environment backup is
`build/hdmi-reset-baseline-2026-10-20/trial-package/active-environment-backup.bin`.
Both are also covered by the durable checkpoint inventory/archive under
`local/recovery/2026-10-28-production-cleanup/`. Preserve raw files privately.
Do not run historical install scripts: their preconditions and rollback target
belong to earlier generations. The rescue prefix identity still needs fresh
readback and a full header-derived extent check.

## Transaction design

1. Build/test the source correction offline and produce a separate proper FIT,
   padded to an explicit sector extent. The combined SPL+proper build output is
   not an image for this split layout. Define a transaction region covering the
   larger of candidate and current proper extents, retaining the exact tail
   preimage so rollback restores every byte changed if the candidate is larger.
   Reject overlap with the intended environment or rescue slot. Verify GPT
   ownership/reservation of both destinations against a fresh backup; the old
   environment remains inside `super` and must not be erased or reclaimed.
2. Generate a private, identity-pinned package with source/config/toolchain/BL31
   provenance, candidate and rollback hashes, all protected ranges, exact
   full-region before/after hashes, and a bounded installer/rollback tool.
   Rehearse on a sparse host disk: success, no-op, wrong disk/capacity/GPT,
   changed preimage, corrupt payload, interrupted/short writes, loss after each
   phase and rollback from every partial state. Deliberately mutate each new
   guard/test to show that the suite can fail. No simulated failure on hardware.
3. Before requesting installation, complete read-only live preflight and obtain
   fresh private backups on persistent host storage. Pin board model, eMMC CID,
   capacity, sector size, user hardware partition, GPT, boot ID, full proper
   region/tail, both environment regions, SPL, rescue image and boot FAT assets.
   Check filesystem health, HDMI generation/calibration and current GP6/GP7
   without changing latches. If any historical identity differs, stop and
   reconcile; never overwrite a newer environment with the October 20 backup.
4. After explicit approval and operator readiness, copy the **fresh verified
   active environment bytes unchanged** to the intended 64-KiB slot. Flush and
   verify direct readback, full CRC, policy values, and unchanged old environment
   and protected ranges. No `saveenv`, key regeneration or environment editing.
   This first phase leaves the old proper reading its original location.
5. Only after phase 4 verifies, write the candidate proper's planned extent,
   flush and verify its full region and all protected ranges. Record a durable
   completion marker only after readback succeeds. The old environment remains
   intact for exact rollback. Never auto-reboot after a failed or partial write.
6. Capture UART and perform the separately approved first cold boot, then
   ordinary warm boots and managed HDMI-source checks. Establish that corrected
   U-Boot actually loads the intended environment: instrument/report the selected
   storage address in the candidate or use an equivalently reviewed read-only
   command. Identical environment contents at two locations cannot prove which
   one was loaded. Check GP6 health ack/GP7 semantics, audio/video, saved 40-ms
   delay and operator picture/colour/tone; do not infer acoustic success from
   PCM flow. Preserve logs and actual boot IDs using host time.

There is no storage-level atomic write of both components. Staging the new
environment first makes a completed first phase bootable with the old proper;
a torn proper still requires recovery. Do not claim this ordering eliminates
power-loss risk. Do not test `saveenv` as part of initial boot acceptance:
future save-path qualification needs a separately reviewed bounded sequence
and fresh backup.

## Interruption and rollback

| Observed state | Recovery policy |
| --- | --- |
| No write, or torn intended environment; old proper intact | Keep old proper/active environment. Inspect readbacks; restore or finish only the explicitly approved intended-slot phase. |
| Intended environment verified, proper not changed | Old boot behavior remains; an explicit rollback may restore the intended slot's fresh preimage. |
| Proper partial, wrong hash, or boot fails | Do not reset repeatedly. Use the preserved FEL rescue path, restore the full proper transaction preimage and verify before boot. |
| Candidate booted, functional failure | Restore exact old proper/full tail first, retain the old active environment, verify, then restore the intended-slot preimage if rollback scope requires it. |
| Unexpected bytes outside known transaction states | Stop for inspection. Do not force through a generation guard or erase either environment. |

The [FEL procedure](uboot-lamp-flash-plan.md#recovery) previously reached the
rescue prompt; the new rollback is not yet rehearsed. Pin the rescue SPL hash
and freshly read rescue-slot identity before relying on it. Only one serial
owner may run during YMODEM; resume passive logging afterward. Transfer the
**current diagnostic rollback**, verify RAM hash and filesize before writes,
select the verified eMMC user device, then restore/read back/compare the exact
transaction extent. For the current 1877-sector rollback alone, size is
`0xeaa00` and count is `0x755`; older examples using `0xe9600`/`0x74b` or
`0x706` restore different images. Any larger candidate requires the full-region
preimage, not just these 1877 sectors. Generate executable recovery instructions
from the final package; this plan is not authorization to issue raw writes.

Preserve GP6 startup/health policy, GP7 reboot/stop handoff and PB5 lamp/fan
policy throughout. Never access ARM MMIO `0x07091000`–`0x07091fff` or
`0x06940000`. No prolonged PB5-low diagnostic sequence.

## Next implementation gate

This section records the earlier gate; implementation and offline rehearsal
are now complete as recorded above. Live finalization remains outstanding.

The recovery-input checks and seven host tests pass; all eight deliberate
validation faults are caught. Evidence is under
[`hdmi-evidence/2026-10-30-uboot-migration-plan/`](hdmi-evidence/2026-10-30-uboot-migration-plan/README.md).
This checks retained artifacts, not a candidate build or transaction rehearsal.
Next: implement/test the width-preserving source correction, build the normal
DDR3 candidate, and implement/rehearse the pinned migration package above.
Installation approval follows that reviewable package, not this planning step.
Physical shutdown guard qualification, reproducible release assembly, stale
output ledger, clocks and remaining packaging/docs cleanup remain open.
