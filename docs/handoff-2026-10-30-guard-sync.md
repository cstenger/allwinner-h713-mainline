# Shutdown guard preparation handoff — October 30, 2026

## Latest endpoint — installed and verified

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
