# Two-second HDMI startup variant staged for the next boot

**PASS: fresh read-only preflight, backups, staging and read-back verification.**
The temporary 2,000 ms override is on disk for the next boot. No candidate code
was executed, systemd reloaded, service restarted, HPD changed, cable reseated or
board rebooted. The current failed HDMI state remains intact.

## Checks and backups

Board model, eMMC identity/capacity, kernel build notes and boot ID match the
fresh failure evidence. Boot remains
`afe48e93-6604-44de-a220-acb9416e8363`. All 56 production file content and metadata
pins pass. All eight protected raw-storage ranges and the installed environment
and U-Boot write regions match their expected hashes before and after staging.

The original signal unit had no drop-ins and remains enabled. The backup captures
56 pinned HDMI files plus its enablement symlink, including content, mode,
UID/GID, nanosecond mtime and xattr inventory (all empty). The verified PAX tar
and full metadata record exist both on the workstation and on the board at:

```
/var/backups/h713-hdmi-start-delay-20261101-01/baseline.tar
/var/backups/h713-hdmi-start-delay-20261101-01/baseline-metadata.json
/var/backups/h713-hdmi-start-delay-20261101-01/stage-receipt.json
```

Backup tar SHA256:
`bbd1df2f3a23355061c9a5d7cdb82010755253578204abedafe860a6da41bcbb`.
The backup was written, synced and verified before publishing the override.

## Staged files and effective behavior

The exact [offline-tested package](../2026-11-01-startup-delay/README.md) supplied
the private wrapper, helper, manifest, runbook and 2,000 ms override. Runtime files
and their own SHA256SUMS are under `/usr/lib/h713-hdmi-delay-bench/`. The sole new
drop-in is:

```
/etc/systemd/system/h713-hdmi-signal.service.d/90-start-delay.conf
```

It replaces only ExecStart. Production ExecStop, capture dependencies, ordering,
oneshot behavior, restart policy and timeouts are inherited. The board's actual
on-disk unit passed `systemd-analyze --generators=no --man=no verify`; the Python
files were compiled for syntax checking without importing or executing them.
All nine new runtime/drop-in/backup files have the expected hashes and root
ownership; runtime/drop-in files are 0644 and backup files 0600.

The current manager still holds its original ExecStart, ExecStop and invocation
IDs. Only `NeedDaemonReload` changed from `no` to `yes`, as expected for a future
boot configuration staged without a reload. All existing unit files and the
enablement link retain their original metadata. The active signal owner stays
ready, with no failure/recovery, receiver clients 2, graph ready, signal `none`
and video transitions/frames zero. Ownership markers, session state, service
start identities and recorded HDMI kernel log are unchanged.

Before live staging, the exact transaction passed eight workstation filesystem
rehearsals: success, changed boot, changed pin, unexpected drop-in, existing
target, interruption before publication, interruption after publication and
service drift. Failure cases published no override or removed only the new
override. The live transaction repeated boot/identity/kernel/file/configuration,
ownership and service-identity guards around file publication.

## Next boot and reversion boundary

Arm passive UART and cached host observation before a separately authorized boot.
Keep the cable and host output conditions fixed. Look for `delay-start` and
`delay-complete` JSON records separated by at least two seconds, followed by the
existing EDID/HPD-ready and Linux startup evidence. The present boot is explicitly
excluded by the private wrapper and must not be used for a service-restart test.

After the validation run, remove the exact temporary drop-in before another
boot and verify the production merged unit against this backup. The drop-in
directory did not exist before staging, so it can be removed when empty. The
private runtime directory is also new and can be removed once no longer needed;
retain the backup and evidence. No original production file needs replacement
for this normal reversion. If original configuration has drifted, inspect it
against the backup rather than broadly extracting the tar over the system.
Do not restart/stop a live owner merely to revert its configuration. Any later
reversion or boot remains a separate authorized action. No automatic reversion
has been installed; the persistent override otherwise applies to later boots.

This remains an experiment, not a qualified HDMI fix. It delays initial signal
setup and does not change SCP code, EDID, modules or the DDC-enable-to-HPD interval.

Evidence: [result](RESULT.json), [staging receipt](stage-receipt.json),
[eight-case rehearsal](REHEARSAL.json). Full pre/post snapshots, verified backups,
transaction sources/plan and checksum-sealed archive are in
`local/recovery/2026-11-01-hdmi-delay-stage/` and its sibling archive.
