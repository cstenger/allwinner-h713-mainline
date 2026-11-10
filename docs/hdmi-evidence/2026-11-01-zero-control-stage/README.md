# Matched 0 ms HDMI control staged for the next cold boot

**PASS: fresh read-only preflight, verified backups, atomic drop-in replacement
and read-back checks.** The board remains running boot
`e6ccc77a-dfb2-411c-a2cf-139c35d4dceb`, with HDMI locked at 1280×720. No daemon
reload, service restart, shutdown, reboot, HPD operation or raw-storage write ran.

This prepares the control for the
[successful two-second cold-start experiment](../2026-11-01-startup-delay-cold/README.md).
The sole configuration difference is in
`/etc/systemd/system/h713-hdmi-signal.service.d/90-start-delay.conf`:

```
--bench-delay-ms=2000  →  --bench-delay-ms=0
```

The private wrapper, helper, manifest, read-only readiness/pin checks and logging
are identical. Production modules, EDID, SCP sequence and ExecStop are unchanged.
The control removes the deliberate two-second wait; it retains the common
checking/logging overhead. No 0 ms live startup has been attempted yet.

## Preflight and backups

Model, eMMC identity, kernel notes and boot ID match the successful cold run.
All **56 production content/metadata pins**, **five private runtime files**,
**eight protected storage ranges** and **both installed migration regions**
pass before and after staging. Linux is running with no failed units. Current
signal/session state, ownership markers and service invocation/start identities
are unchanged.

A new 64-entry PAX tar captures the production files, private runtime, original
unit/drop-in configuration, its directory and enablement symlink, with bytes,
mode, UID/GID and nanosecond mtime. Xattr inventory is empty and recorded. The
tar and detailed metadata were written, synced and read-back verified before
replacing the drop-in. They exist on the workstation and on the board at:

```
/var/backups/h713-hdmi-zero-control-20261101-01/before-zero-control.tar
/var/backups/h713-hdmi-zero-control-20261101-01/before-zero-control-metadata.json
/var/backups/h713-hdmi-zero-control-20261101-01/stage-receipt.json
```

Backup tar SHA256:
`47f15a22c0a56207cbb3408e4a12d71f777cac74ad5fccc726634ca37bab1b54`.
The directory is root-owned 0700; its three files are root-owned 0600. Earlier
backups and finalized packages were preserved.

## Transaction and validation

The transaction checks boot/identity/kernel, diagnostic absence, production and
private runtime pins, unit path/configuration/metadata, ownership and running
service identities. It publishes a synced temporary file with one atomic
replacement. Failure after publication restores the prior two-second drop-in
when its replacement still matches the expected bytes.

Nine offline filesystem rehearsals passed: success, changed boot, production
pin drift, private runtime drift, unexpected unit configuration, existing backup,
interruption before publication, interruption after publication and service
drift. Failure cases refused the change or restored the old override.

The live read-back matches the exact finalized `delay-0.conf`:
`daf83a942a4630abcd748f3dc5005252bcd7aca2c77ab7b21487a03a6ba9844b`.
The previous two-second override hash is
`889987162eb9d12d32e2acca45ef39b8850c5dbfdef9a787b3c1b35e460145f1`.
Drop-in ownership/mode remain root:root 0644, and other unit configuration is
unchanged except the containing directory's modification time. The actual
on-disk unit passes `systemd-analyze --generators=no --man=no verify`.

All loaded unit properties remain unchanged, including the current two-second
ExecStart and original ExecStop. The manager reports `NeedDaemonReload=no`;
this report is not used as proof of the staged content. Direct on-disk hashes,
configuration inspection and independent unit parsing establish the next-boot
zero control. No manager reload was requested. A fresh boot will read the disk
configuration, and its actual zero-delay command and milestones must be checked.

## Next test and reversion

Arm fresh receive-only UART and cached host HDMI recordings before a separately
authorized ordinary poweroff. Match the preceding cold test: reported supply
removal for at least 60 seconds, HDMI connected throughout, host settings
unchanged, and uninterrupted ordinary U-Boot/Linux startup. Record the actual
0 ms delay milestones and both successful and failed detection outcomes. Do not
test the control by restarting the current signal owner or clearing its latches.

This persistent temporary override remains installed until explicitly changed.
To return to the two-second experiment, restore only the backed-up drop-in and
its metadata after review. To return to production, remove the temporary override
and verify the production merged unit using the
[original staging record](../2026-11-01-startup-delay-stage/README.md). Broad
extraction of the backup over the running system is unnecessary. No reversion,
recorder arming or power action was performed in this staging task.

Evidence: [result](RESULT.json), [staging receipt](stage-receipt.json) and
[rehearsal](REHEARSAL.json). Full pre/post snapshots, verified backups, plan and
transaction sources are checksum-sealed under
`local/recovery/2026-11-01-hdmi-zero-control-stage/` and its sibling archive.
