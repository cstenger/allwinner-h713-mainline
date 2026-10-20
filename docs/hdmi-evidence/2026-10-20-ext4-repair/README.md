# Offline ext4 repair — October 20, 2026

The HDMI reset baseline exposed a persistent root-filesystem error:
`ext4_mark_recovery_complete: Orphan file not empty on read-only fs`.
The error predates the reset instrumentation and prevented online root
resizing. The user authorized fixing ext4. This record tracks the offline
repair and verified writeback. Linux mounted cleanly, root growfs succeeded,
and an orderly reboot left a clean unmounted superblock.

## Offline isolation and backup

Starting Linux boot: `fedfb946-1ce2-4617-b809-89ef2c8f53c0`, with HDMI capture,
signal and speaker services active and zero capture XRUNs. An ordinary
`systemctl reboot --reboot-argument=bootloader` stopped Linux and reached the
maintenance prompt. The existing GP7 bootloader mode prevented autoboot;
GP6 remained latched. No firmware launch, guard bypass or saved environment
change was needed.

The installed U-Boot supports partition-only USB mass storage. Command
`ums 0 mmc 1:1a` exported only partition 26 (`1a` is hexadecimal): start
`0x54c400`, count `0x580000` sectors. Linux was not running. The host identified
USB `1f3a:1010`, device `/dev/sda`, size **2952790016 bytes**, ext4 UUID
`956d9901-0eb3-4d75-bb44-e37a46ba9f40`, with no mountpoint. Boot firmware,
environment and the other eMMC partitions were outside the export.

The user granted temporary access to this device node. The backup helper
verified USB ancestry, size, UUID and mount state, then opened the device
exclusively. The full original image is retained locally:

- `build/ext4-repair-2026-10-20/root-before.ext4`
- SHA-256 `3b403159e64b0876f465504e3c64e57c95fa21b25ff5fc58bc986de47db73bfe`
- 2952790016 bytes; backup completed in about 375 seconds.

Raw images contain board data and remain local. Preparation scripts, command
outputs and manifests are retained in the same ignored build directory.

## Repair on a working copy

A reflink working copy preserved the original backup. Initial `e2fsck -f -n`
returned 4, explicitly skipping journal recovery in read-only mode. It found
12 zero-link deleted inodes with zero deletion time, bitmap differences and
a non-clean orphan-file block. These findings were assessed with that skipped
recovery limitation, not as an independent diagnosis of every reported block.

`e2fsck -f -p` on the working copy replayed the journal, fixed those deletion
records and cleared the non-clean orphan-file block. It returned 1 (repairs
made). A subsequent `e2fsck -f -n` returned 0 through all five passes.
`dumpe2fs` reports `clean`. The `orphan_file` feature remains enabled; the
error was not hidden by disabling it or manually clearing filesystem flags.

The checked working image is:

- `build/ext4-repair-2026-10-20/root-repaired.ext4`
- SHA-256 `391a026c736ca6a0f95eaeeaa0bf27babccc3614e86d49207c4d5a9baf1f079c`
- **61440 changed bytes in 12 ranges**, at 4096-byte block granularity.

One inspected deleted inode has group 999, which the saved `/etc/group`
identifies as `systemd-journal`, zero links, a 4-MiB logical size and one
remaining block. This is consistent with unfinished deleted-journal cleanup;
it does not establish why the kernel failed to finish orphan cleanup.

## Guarded writeback and validation

The prepared helper verifies the unchanged backup and checked image hashes,
requires a clean read-only image check, revalidates the USB target and mount
state, and exclusively opens the device. It compares the entire device to
the original backup before writing. Only the 12 changed ranges are written;
each range also has an immediate preimage check. A full direct-I/O readback
must match the checked image hash before the board may boot.

Temporary-file fixtures passed changed-block writeback/full readback,
wrong-size refusal, refusal after a device-preimage change, and refusal after
a checked-image change. No fixture accessed a real block device.

The full direct-I/O readback matched the repaired image SHA-256. Ending the
export removed `/dev/sda` and its temporary ACL. Linux boot
`24274ba0-41cc-458c-a54b-61054934f2e5` mounted root read-write without recorded
ext4 errors. `systemd-growfs-root.service` returned `Result=success`,
`ExecMainStatus=0`; the partition was already at its target size.

An orderly `systemctl reboot --reboot-argument=bootloader` returned to U-Boot
without the previous orphan-file warning. A read-only MMC read of the primary
superblock (root start `0x54c400` plus two sectors) confirmed magic `0xef53`,
state `0x0001` (clean, no error), incompatible features `0x22c2`
(`needs_recovery` clear), and read-only-compatible features `0x046b`
(`orphan_present` clear). The persistent `orphan_file` feature remains enabled.
See [shutdown-superblock.json](shutdown-superblock.json) and the captured
[superblock read](superblock-after-orderly-reboot.txt).

A second Linux boot, `66f84444-13e2-47af-930b-388059812113`, also mounted
cleanly and returned growfs success; see [second-boot-health.txt](second-boot-health.txt).

This closes the observed filesystem-repair prerequisite for reset trials.
It does not establish the original cause or prove the problem cannot recur
under active HDMI load. Both maintenance boots use the existing GP6 warm
policy: brief logo initialization followed by parked firmware, with sustained
HDMI capture skipped. No latch was cleared, startup guard bypassed, firmware
installed, environment saved, or abrupt reset performed. A fresh instrumented
cold HDMI baseline is still needed before the paired reset trials.

Curated command output and [result.json](result.json) record the repair and
validation. Full images and one-off device helpers remain local under the
ignored build directory.

Curated UART text removes terminal escape sequences and carriage returns;
trailing whitespace is trimmed. Raw-capture hashes are retained in the result manifest. Board wall-clock
timestamps were not synchronized; boot IDs identify the validation runs.
