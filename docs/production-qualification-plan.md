# Qualification of a rebuilt DDR3 system

Status: hardware checks complete for the documented candidate/scope, with the
specific guarded-discard finding closed by
[engineering disposition](production-evidence/2026-11-04-guarded-discard-disposition/README.md).
The original strict-test failure remains recorded. See the
[live installation evidence](production-evidence/2026-11-03-candidate-installation/README.md).
The accepted installation is preserved as the rollback baseline. This plan is for the
HY200 QZ713DF_A1 DDR3 board, not the LPDDR3 projector.

The fresh November 3 maintenance inventory supersedes older flash notes:
Linux is **p26, GPT label `linux`, 2952790016 bytes**. The remaining Android
data filesystem is **p27, GPT label `UDISK`, 2021113344 bytes**. There are 27
partitions. Never select the Linux destination by the historical UDISK name.
This candidate preserves that split; reclaiming Android space is a separate
partition-table/filesystem operation, outside this installation scope.

## Before entering a maintenance window

1. Verify the candidate's SHA256SUMS, boot-image checksum, source/gitlink locks,
   explicit private inputs, and independent build comparison. Record its new
   kernel/module hashes; the shared version string is insufficient identity.
2. Collect a fresh read-only board inventory and startup/health/file checks.
   Confirm the storage geometry and partition table against preserved evidence.
   The November 3 inventory still found the November 2 accepted environment
   SHA `89862e4ba5304fcae54affe09d87ff7da026316c80c8b4a5a17d7a44eb3ce206`.
   Do not reuse an older environment's hash or overwrite device identity.
3. Prepare UART capture, OTG, physical power/FEL access and an operator-ready
   check. Verify the rehearsed rescue SPL and rescue-slot proper from private
   recovery storage. A rebuild of that rescue binary requires its own trial.
4. Obtain and verify a consistent offline rollback copy of the current rootfs,
   boot FAT, SPL, proper, partition table, environment and surrounding protected
   regions. A live rootfs raw read is not a consistent rollback backup. The
   [November 3 offline backup](production-evidence/2026-11-03-offline-backup/README.md)
   now passes two full direct device reads and host-copy verification. The Linux
   filesystem is clean; existing boot FAT inconsistencies are preserved and
   documented. Reverify its sealed hashes before constructing any write packet.

The historical [flash notes](flash.md) document USB gadget retention after
Linux and unreliable sustained UMS transfers. Enter USB maintenance from a
cold power-on interrupted before Linux, then set/read back `gpio set PB5` at
the held prompt for the shared lamp/fan line. Resolve the enumerated storage
by identity, exact geometry and GPT; ensure the host has not automounted it.
Use bounded, checked reads and compare a second read for rollback evidence.
If transport is unstable, stop before writing and prepare a verified rescue
environment for offline backup instead. An exit status alone is insufficient.

## Permitted installation scope after the backup gate

| Payload | Existing destination | Required bounds |
| --- | --- | --- |
| Packet `payloads/install/root.simg` | GPT `linux`, Linux p26 | All-RAW logical coverage, exact 2 GiB raw alias; fresh GPT/identity/getvar gates. Preserve Android p27 `UDISK`. |
| Packet `payloads/install/fat.simg` | GPT `bootloader_b`, Linux p2 / U-Boot `mmc 1:2` | All-RAW coverage of exactly 32 MiB; verify declared boot files offline. |
| Packet `payloads/install/proper.bin` | LBA `0x49ac00` | FIT checked and padded to exactly 1867 sectors; CRC checkpoint and final SHA readback. |
| Packet `payloads/install/spl.bin` | LBA `0x10`, 64 sectors | Exactly 32768 bytes; eGON checked; install last. |

The [prepared installation/rollback packet](production-evidence/2026-11-03-installation-packet/README.md)
supplies exact aliases, commands, payloads, CRC checkpoints and full-device
SHA-256 expectations. Live installation passed all four phase checkpoints and
the complete preboot device SHA comparison. The documented hardware checks and
non-writing recovery entry/access trial are complete; a full rollback write
trial was not performed. The GF1 disposition and remaining scope limits are
recorded in the linked evidence.
Use its all-RAW images, rather than the original sparse image's
skipped blocks, for exact before-boot byte comparison. Historical raw aliases can point at superseded
locations. Never flash the combined SPL+proper image as one installed extent.
Preserve the SPL stash at `0x49cc00`, environment at `0x49ec00`, older rescue
proper at `0x4a0c00`, old `super` environment, vendor chain, GPT and calibration.
Do not change or save the boot environment merely to install a replacement
FIT/startup file: compare the candidate's boot-environment.json with the current
semantics first. Do not use the historical boot_a standalone installer.

Read back each written extent before proceeding. Compare protected regions
before and after. A failed guard/readback stops the sequence. Rootfs growth
and first-boot state change its whole-image hash; verify raw installation
before first boot and file/package/configuration identity afterward.

## Acceptance gates

- UART boot chain identifies the candidate; no new storage/kernel errors;
  four CPUs, matching loaded modules, Wi-Fi/hotspot, Bluetooth and SSH work.
  Verify newly generated SSH host-key fingerprints through UART.
- All four HDMI bundle manifests and startup checks pass using candidate
  hashes. Confirm source detection, EDID, 720p desktop, speaker audio and
  measured calibration without intervention or service restarts.
- Cold boot and repeated ordinary warm boots restore the panel and HDMI.
  Verify the current shared startup handoff; do not bypass retention guards or
  force a module reload to obtain a pass.
- Host reboot while board stays on, continuous-input session, and a physical
  unplug/reconnect recover normally. Capture timed transitions prospectively.
- File playback, hardware decoder checks, keystone/mirror controls, keys,
  standby and clean shutdown pass. Supply test media/tools temporarily from
  the host; remove them afterward.
- Exercise the chosen rollback/recovery route with exact accepted artifacts
  before marking the release qualified. Preserve both success and failure
  evidence; do not replace accepted rollback material with new candidates.

Only then update qualification metadata and documentation. Keep the source
repository's tests, fixtures and investigation evidence: production stripping
applies to the installed image.
