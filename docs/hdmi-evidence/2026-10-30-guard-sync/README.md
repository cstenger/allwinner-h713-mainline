# Shutdown guard synchronization — installed and verified, October 30

**Installation PASS.** Chris explicitly authorized installation, powered on
the board and confirmed it had booted. The fresh preflight matched the pinned
generation and all four installed bundle manifests passed. The default updater
preview reported `would-install`; the approved install completed successfully.

Both guard copies now match the candidate hash `96f37655…`, remain root:root
0755, and the backend manifest is `4373e9ec…`, root:root 0644. All **18 backend
entries** and all four bundle manifests verify. Exactly the three intended
existing files changed. Service states/start identities/restart counters,
boot ID, captured error counters, playback tools and 40 ms audio configuration
are unchanged. No service restart, reboot, shutdown or firmware action occurred.
HDMI had no input signal before installation (`none`); video was inactive
before and after. No picture/sound or physical shutdown test was performed.

Board boot ID: `7ca604ba-a805-4f0a-9bd4-2df936f50479`.
Rollback backup:
`/var/lib/h713-hdmi-startup/guard-sync-537cfedf47f7420cb08aad5dbc323e21`.
Its original payload hashes and committed/complete state verify on the host.
Rollback **preview** passes; no actual restoration was performed.
See [installation result](INSTALLATION-RESULT.json), `install-preflight.json`,
`target-install.json`, `post-install.json` and `installed-backup.json`.

The earlier offline preparation and evidence below remain valid. Chris first
asked to resume the October 28 handoff and prepare this change before installing
it. During that preparation there was no board contact. The October 28 recovery
checkpoint hashes were verified and the uncommitted audit files preserved.

## Exact change

The repository guard already checks both cold-only diagnostic modules
`h713_hdmi_dsp_observe` and `h713_hdmi_dsp_access_audit`. The October 28 audit
found that neither installed copy has those checks. The candidate is an exact
copy of the existing repository guard; no new shutdown behavior was added.

The package modifies only these three existing files:

1. `/usr/lib/h713-hdmi/h713-hdmi-hold-guard`
2. `/usr/lib/systemd/system-shutdown/h713-hdmi-hold-guard`
3. `/usr/lib/h713-hdmi/SHA256SUMS` — replace only the guard entry.

Backups/transaction markers are created under
`/var/lib/h713-hdmi-startup/guard-sync-<uuid>/`. UUID naming avoids dependence
on the board's incorrect clock. File modes and ownership are preserved.
No other manifest entry, module, unit, boot image, environment, GP register,
panel/lamp hook or 40 ms audio calibration is changed. No daemon reload is
needed because the late shutdown hook is a plain executable file.

| Identity | SHA-256 |
| --- | --- |
| Both audited installed guards | `9140e3104042cd291496f3c238d1c3ef151184d362f32752c7179f9b25483db7` |
| Existing repository/candidate guard | `96f37655b33bf78d95b33fa4f431721be5a7506c73c12dcd4df58032cad27113` |
| Audited backend manifest | `5c57391a0b4e7acde446bf4e2b52319aeca8314693f183095abc08ae960a6631` |
| Resulting backend manifest | `4373e9ecb77e087a1d26c00637c135028942ae84912fb8dbf57ac0c51cc2feac` |

The behavior remains: retained HDMI owners or either diagnostic module make
`reboot`/`kexec` invoke the existing lamp-off hook followed by poweroff.
Normal clean teardown leaves those verbs alone. Requested poweroff/halt are
not redirected. This copy operation introduces no new register access.

## Package and transaction

`tools/hdmi/build-guard-sync.py` produces a small checksummed package containing
the guard, `sync-shutdown-guard.py` and a before/after manifest. It pins the
audited old generation and reviewed candidate. No kernel/module/firmware
binary needs to be shipped with this narrow update.

`sync-shutdown-guard.py` defaults to a read-only preview. It checks the exact
DDR3 board model, expected guard/mode identities, package checksums, the
backend manifest identity and **every recorded backend file**. Unknown,
partially updated or externally edited generations are refused. Persistent
path symlinks and overlapping transactions are refused. The kernel-provided
`/proc/device-tree` identity symlink is explicitly allowed for that read.

Install uses an exclusive directory lock without creating a lock file, saves
verified original bytes/metadata and a durable `INCOMPLETE` marker, replaces
the two guards atomically, and activates the new checksum manifest last.
Staging files are in the destination directories; writes and directory changes
are fsynced. Each replacement checks that its destination has not changed.
On failure the exact backup path is reported; another install is refused
until rollback completes. Do not shut down during an incomplete transaction.

Rollback validates location/scope, backup hashes, each current target's old/new
identity and all out-of-scope backend files before changing anything. It
restores the active hook first, then the backend guard and manifest. Foreign
edits or corrupt recovery data are refused. Repeating a successful install
does not create another backup; repeated rollback has the same restored state.
There is no claim that three filesystem replacements are atomic as a group;
the durable backup/marker provides explicit recovery between replacements.

## Offline verification

* **12 updater/builder tests pass** (`sync-tests.txt`): read-only/default CLI
  preview, exact write scope, modes/backups, idempotence, wrong board, package
  and installed-generation tampering, symlink/permission guards, directory
  locking, concurrent destination edits, interrupted writes at all three
  replacement boundaries, committed rollback, recovery tampering and builder
  pins.
* **3 guard behavior tests pass** (`guard-tests.txt`): unrelated/absent modules,
  each of all seven held modules on reboot/kexec, and poweroff/halt behavior.
  The harness redirects the guard's kernel-log/console writes into temporary
  files as well as substituting lamp/poweroff command stubs. Nothing invokes
  a real poweroff or writes the host's log devices.
* **22 deliberately faulty variants are caught** (`mutations.txt`). Every
  updater/builder/guard test and the exact-generation rehearsal has a failing
  implementation variant. Mutation copies live only in host temporary files.
* **Exact audited-generation rehearsal passes**
  (`audited-generation-rehearsal.json`): reconstructed all 18 recorded backend
  files from audit text and retained host artifacts, verifying their actual
  hashes. Preview writes nothing; install changes exactly the three paths;
  repeat install is a no-op; rollback preview writes nothing; actual rollback
  restores original bytes and modes. No synthetic module contents substitute
  for the recorded blobs in this rehearsal. Fixture ownership uses the host
  user, so live preservation of root ownership remains unverified.
* Python/shell syntax and whitespace checks pass. The existing production
  guard bytes remain unchanged. No kernel rebuild or physical shutdown test
  was performed or is claimed.

Reproduce from the repository root:

```sh
python3 tools/hdmi/test-guard-sync.py
python3 tools/hdmi/test-hdmi-hold-guard.py
python3 tools/hdmi/test-guard-sync-mutations.py
python3 tools/hdmi/build-guard-sync.py NEW_EMPTY_OUTPUT_DIRECTORY
python3 tools/hdmi/rehearse-guard-sync.py NEW_EMPTY_OUTPUT_DIRECTORY
```

The builder needs the preserved October 28 audit. The exact rehearsal also
needs the retained October 20 backend and host FAT script snapshot. The built
target package is self-contained and does not need those host inputs on board.
The older broad `update-signal-owner.sh` was intentionally not used: its scope
includes modules and wrappers beyond this guard-only task.

## Authorized installation procedure — completed

Prepared package: `build/hdmi-guard-sync-2026-10-30/`.
A durable copy, sources and hashes are under
`local/recovery/2026-10-30-guard-sync/`. Keep local vendor/recovery checkpoints
out of Git. `package-manifest.json` and `prepared-SHA256SUMS` identify this
candidate independently of the stale general `build/out` ledger.

Chris authorized and completed board startup, then the following sequence was
executed. The recovery step was previewed only; the update remains installed:

1. Take read-only preflight hashes/service state. The old audit is a baseline,
   not a substitute for checking the current boot/installation. Unknown current
   generation means stop and reconcile; never relax the pins automatically.
2. Transfer this package to an unused board directory and verify `SHA256SUMS`.
   Run `python3 -B sync-shutdown-guard.py` there. This default preview must say
   `would-install` (or verified `already-current`) without target file changes.
3. Run `python3 -B sync-shutdown-guard.py --install`. Save its JSON result and
   exact backup path. This changes files only and neither stops nor restarts
   any service. Keep the session available until final checks pass.
4. Read back both guard hashes, modes/ownership and all backend manifest
   entries; compare HDMI service start identities/health with preflight.
   Preserve a host copy of the resulting recovery backup and transaction log.
   Do not invoke the real guard with `reboot`/`kexec` to test a refusal.
5. If needed, preview recovery with
   `python3 -B sync-shutdown-guard.py --rollback BACKUP --dry-run`, then use
   the same command without `--dry-run` to explicitly restore the old files.
   On interrupted install, finish/rollback before any shutdown. A rollback
   intentionally restores the older guard, including its two missing checks.

This sequence did not reboot or power-cycle the board and does not establish
electrical shutdown behavior. A later physical shutdown test is a separately
approved operator sequence. The audit's guard-drift finding is resolved for
this verified installed generation; its original October 28 snapshot remains
unchanged. Sources, offline tests, production audit and installation evidence
are included in the requested audit/guard-sync commit; no push. The repository
state fields in saved verdicts describe the time of preparation/installation.
