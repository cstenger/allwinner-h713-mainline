# U-Boot/environment migration installed and verified — October 30, 2026

**PASS installed and independently verified. No reboot.** Chris confirmed the
board was powered on and booted and requested proceeding under the explicit
installation authorization. The board remains running on new boot
`3474b865-26f2-4b2d-bf37-1baddef732fe`; no service restart or clock/latch write
was issued. The running system has not executed the newly installed proper.

[Installation verdict](INSTALLATION-RESULT.json) and
[independent direct-read verification](post-verification.json).

## Installed bytes and protected storage

Fresh read-only collection confirmed the same eMMC/CID, both write preimages
and all eight protected ranges match the reviewed package. Both GPT copies,
partition ownership/use and filesystem/runtime health pass. The normal
finalizer refreshed only current-boot observations; write payloads, offsets,
protected data and tool hashes were independently confirmed unchanged.
The twenty fresh-preflight tests pass for this generation. Manifest SHA-256:
`9efcb1e7488515a1df3a5a503764efea9c46a6b11e44040c4c01d65b2bdf4da9`.

The persistent runtime subset was staged, checksummed and fsynced, with all
exact rollback payloads. The full protected-region fixtures remain on the
host, keeping target staging to about 2.1 MB. The staged direct-I/O preview
passed before any raw write. One detached installer invocation staged the
environment first, then proper; exit code zero and durable journal phase
`installed` are saved. No retry, rollback, `saveenv` or reboot was executed.

| Write region | Verified installed bytes |
| --- | --- |
| Intended environment, LBA `0x49ec00`, 65536 bytes | SHA-256 `6eb7b7958139263f88cc0a0830b4ac33f4b4ca71b096081802b2f50f2cd205bc`; valid CRC; identical to preserved old active copy |
| Proper, LBA `0x49ac00`, 1877 sectors / 961024 bytes | SHA-256 `cbd29de888e4b605e68b98de78c081525dd7d1b627abca846704efe527e8802a`; FIT header 955665 bytes |

The independent verifier opens storage read-only and uses direct I/O. All
eight protected ranges are unchanged: primary GPT/SPL prefix, backup GPT
suffix, old active environment in `super`, full rescue region, proper tail,
intended-slot prefix/suffix margins and boot FAT. The complete surrounding
2-MiB proper region and 192-KiB environment region match their expected
after-images. SPL and complete rescue FIT hashes also match independently.

All four HDMI bundle manifests pass (18/7/6/6 entries). All 56 installed
file/metadata pins, six service states/start identities/restart counts,
runtime counters/signal, session, GP6/GP7 and saved 40-ms calibration are
unchanged. HDMI has no source; video remains inactive. No optical/acoustic
or media-rate test is claimed. The read-only filesystem check still reports
clean state and no recorded errors; no repair was performed.

## Recovery and qualification

Persistent board directory and journal/rollback payloads:
`/var/lib/h713-uboot-migration/20261030-9efcb1e7488515a1/`.
Exact host copy:
`local/recovery/2026-10-30-uboot-migration-install/installed-board-backup.tar.gz`.
Archived board payload/tool/journal bytes were independently compared against
the staged files. Fresh pre-install raw collection, refreshed full package,
deployment archive, logs and source snapshot remain in that durable private
host directory. Raw environment, CID and firmware are not committed.

Boot behavior, actual corrected-address load on UART, cold/warm picture/audio,
save-path persistence and live rollback remain unqualified. New proper has
not run. The existing recovery instructions preserve the exact diagnostic
proper rollback and both environment locations. The package is bound to this
boot/runtime generation; after any future boot, recollect for Linux recovery
rather than bypassing guards. First boot/qualification requires a separately
approved operator sequence; this installation request explicitly excluded
reboot. Do not retry installation or power down as a follow-up here.

No source commit or push was requested or performed. An initial SSH attempt
timed out while host Wi-Fi was disconnected. The board Wi-Fi then became
connected without this task changing host network configuration; collection
retried successfully. The empty failed capture was removed, and its stderr
is retained privately. No board write occurred before the successful preview.

## Earlier authorization and preparation checkpoint

Chris explicitly authorized installing the finalized migration package and
verifying both write regions and all protected storage, with **no reboot**.
The board was off at that earlier checkpoint. No board contact, staging or
installation had occurred at that point. This history is superseded by the
installed endpoint above.

Offline checks pass: all durable checkpoint/package checksums, archive bytes,
manifest/tool/payload identities, unchanged environment payload, exact
1877-sector proper transaction/rollback extents and eight protected ranges.
[Preparation record](PREPARATION-RESULT.json).

Next: operator powers on normally and confirms booted. Collect fresh read-only
identity/storage/runtime state, reconcile it with the reviewed generation and
refresh the boot-bound package through the existing finalizer. Do not replace
boot IDs or weaken state checks by hand. The existing explicit installation
authorization covers the unchanged migration after this necessary preflight;
do not ask again unless a material discrepancy requires changing the action.
Then stage/install under that authorization, verify both write regions and
all protected storage with direct readback, preserve rollback/journal and
before/after evidence, and leave the board running without reboot.

Package and recovery backups remain under
`local/recovery/2026-10-30-uboot-migration-live/`. Nothing is committed or pushed.
