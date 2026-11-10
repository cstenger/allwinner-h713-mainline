# Production installation audit — October 28, 2026

Audited **155 installed file/path records**, 19 boot display assets and the
documented bootloader/environment regions on the **HY200 QZ713DF_A1 DDR3**
board against repository commit `d64aab0946dd09c32dda63485f1a4efee8bfeb3b`.
The result is an inventory and comparison, not a production release declaration.

**The installed HDMI stack is internally consistent, but the accepted board
cannot yet be recreated by one clean-checkout production recipe.** All four
HDMI bundle checksum manifests pass. Most active scripts/units match current
sources; the important exceptions are the old shutdown guard, the diagnostic
bootloader and its unresolved environment-address defect.

Board access was read-only: no installation, configuration/clock change,
mount, service restart, firmware call, MMIO access, reboot or functional test.
The boot FAT was copied to a host-only image and inspected offline. No raw
firmware images or environment/credential dumps are included in this folder.
The machine-readable [production manifest](production-manifest.json) contains
every path's hash, comparison status, source/artifact references and limits.
[Raw inventory](board-inventory.json) preserves the supporting observations.

## What matches, what differs, and the rebuild limits

| Component | Observed comparison | Recreation status |
| --- | --- | --- |
| HDMI backend, health, video and speaker bundles | All four installed `SHA256SUMS` manifests pass, including recorded firmware/modules. All six HDMI services active, zero automatic restarts. | Existing installed generations are identifiable; complete backend installation is not supplied by the current delta builder alone. |
| HDMI runtime sources and service units | Current capture/session/signal/health/video/PipeWire scripts and units match repository sources; renamed capture and mixer files are mapped explicitly. | Source matches established by SHA-256. Separate installers still assemble the accepted configuration. |
| Startup script | FAT, installed backend and current generator agree exactly: script `fcea3a95…`, command text `9be0cbe3…`. The health bundle manifest regenerates exactly too. | Demonstrated host regeneration **with** ignored October 20 baseline and pinned `build/out` inputs present. Clean-checkout reconstruction remains incomplete. |
| Kernel FIT on boot FAT | `0877293b…`, 7,795,668 bytes: exact match to the retained host FIT and startup kernel pin. | Exact retained artifact identified. Current `KERNEL_CONFIG=sysrq` input-addressed tree is absent; `/proc/config.gz` unavailable. No fresh kernel rebuild or independent running-kernel hash was performed. |
| Kernel/HDMI/Wi-Fi modules | 12 installed modules match retained build artifacts, including all five HDMI modules, Cedrus, Panfrost and the three AIC modules. Another 27 `.ko` files have fingerprints but no exact retained match in the searched build trees. | Artifact identity is established where matched. The 27 unmatched files are **unproven**, not demonstrated source defects; build timestamps, stripping and compiler inputs were not reconstructed. |
| Playback priority | Launcher matches current source; installed arm64 player hash matches the accepted October 28 target build (`f50f679b…`). | Source and previous build/installation evidence retained. No board compilation during this audit. |
| 640×480 policy | Ring unit matches source with explicit `allow_480p=0`; live parameter is `N`. | Matches the selected policy. No physical 480p test in this audit. |
| Audio calibration | Installed defaults exactly match recorded board configuration: 40 ms. | Recoverable from committed calibration evidence; generic installer does not recreate this board-specific defaults file. |
| Shutdown hold guard | Both installed copies are identical to each other and to their older bundle record, but differ from current repository source. | Concrete source drift: repository adds detection of `h713_hdmi_dsp_observe` and `h713_hdmi_dsp_access_audit`; installed copies lack both. [Exact diff](hold-guard-difference.diff). |
| U-Boot proper | Actual FIT header says 960,817 bytes, padded to 1,877 sectors. Hash `1b1f702f…` exactly matches the October 20 reset-controls diagnostic artifact and installation record. | Recoverable retained diagnostic image. It differs from the normal pinned DDR3 build; no fresh diagnostic or production U-Boot rebuild performed. |
| SPL | Raw 64-sector hash `cb9da874…` matches the documented installed SPL baseline. | Identified historical artifact, not evidence that the current full U-Boot image can replace it unchanged. |
| Saved U-Boot environment | Configured LBA `0x49ec00` remains all zero. Actual saved environment at LBA `0x32ec00` has valid CRC, expected hash `6eb7b795…` and current guarded boot commands. | Existing narrowing/address-conversion defect remains. Correcting source handling requires an explicit environment migration preserving boot guards; no migration was attempted. |
| VA driver and retired mpv | VA series stamp `4daa2b3628930def` matches the current 15-patch series. Retired `mpv-direct` stamp `8e52f2d7e35feebc` matches its current series. | These are **stamp matches**, not fresh binary rebuilds. Active `/usr/bin/mpv` is Debian's package, not the retired patched binary. |
| Vendor display and Wi-Fi/DSP firmware | Nineteen FAT display/configuration assets fingerprinted. Eight Wi-Fi files plus the HDMI DSP payload match repository pins. | Local vendor/proprietary inputs remain necessary; matching hashes do not provide public-source firmware builds. |
| Rootfs-generated files | Eleven paths match literal recipe templates; six paths differ bytewise, including duplicate service symlinks. | Keystone and BT-helper differences are comments only where compared. BT unit carries its timeout through a separate installed 10-second drop-in rather than the current unit template. Wi-Fi recovery helper template mismatch remains semantically unreviewed. [Template diffs](rootfs-recipe-differences.json). |
| Timekeeping | System reports April 13, 2026; RTC reports January 2, 1970. `CanNTP=no`, `NTP=no`, `NTPSynchronized=no`; no installed timesyncd/chrony unit was found. | Clock initialization/synchronization remains production work. This is not a new measurement of RTC rate or proof of a rate-driver regression. |

The manifest also records compiler/package versions, symlinks/modes, historical
backup files, generated Python caches, board-local configuration and absent
optional paths. Status counts are **path counts**, including duplicate copies
and symlinks, not independent subsystem pass counts. No path is silently
discarded as a mismatch or assumed to match because its filename is familiar.

## Findings that change the cleanup order

1. **Reconcile the shutdown guard first as a small, reviewable source/install
   correction.** Its two missing diagnostic-module checks are concrete and
   isolated. Plan/tests and explicit installation approval are still needed;
   this audit did not update either copy or its recorded bundle manifest.
2. **Treat U-Boot production integration and environment migration together.**
   The actual environment is in the old `super` area, not the configured
   reserved area. The cause and addresses were already documented in the
   [October 20 baseline](../../hdmi-evidence/2026-10-20-reset-baseline/README.md#confirmed-environment-address-defect).
   Do not replace proper/SPL or change offset arithmetic as an isolated cleanup.
   First prepare identity-pinned backups, an exact migration/recovery plan and
   offline tests. The current diagnostic image is a known installed artifact,
   not unexplained corruption.
3. **Make full assembly independent of ignored baseline bundles.** Preserve
   the accepted kernel/firmware identities while providing source-based
   backend/video/speaker/player packaging and explicit restoration of the
   per-board calibration. The current startup builder is a guarded update
   transaction, not a fresh production image builder.
4. **Restore reliable calendar initialization and time synchronization**, then
   qualify cold/warm persistence. Use host timestamps for evidence until then.
5. **Resolve kernel/speaker release packaging and refresh current docs.**
   Patches 0180/0181 remain `EXPERIMENT` entries in the shipping series; the
   PipeWire speaker installer still compiles/ships the retired GStreamer
   consumer. **All seven entries in `build/out/SHA256SUMS` are stale**, including
   the older recorded kernel FIT (`c5729b28…`) versus the actual
   `build/out/h713-kernel.fit` (`0877293b…`). See `local-build-ledger-check.json`.
   Generic artifact checksum files therefore cannot be treated as the release
   manifest without validating their contents. No files were deleted or pins moved.

## Evidence and exact identity boundaries

* `board-inventory.json`: target file metadata/content hashes, package inventory,
  selected service state, RTC/system time and validated environment values.
* `production-manifest.json`: classifications and explicit recreation gaps.
* `module-artifact-matches.json`: exact retained module matches, including empty
  arrays for files without a match. No empty array means a proved code defect.
* `boot-files.json`, `boot-directory.txt`, `boot-display-assets.json`: offline FAT
  observations. The FAT has zero heads/sectors geometry; mtools needed
  `MTOOLS_SKIP_CHECK=1` on the host snapshot. The first ordinary mdir attempt
  refused that geometry; no FAT repair was performed.
* `regenerated-startup-manifest.json`: successful current generator result.
* `local-build-ledger-check.json`: recorded versus actual output hashes, all
  seven differing; no output files or checksum ledgers were repaired.
* `hold-guard-difference.diff`, `rootfs-recipe-differences.json`: actual text
  differences, with comment/effective-timeout qualifications in the manifest.

The early historical 1,798-sector U-Boot prefix read was insufficient to
identify the newer installed image. The final collector reads the FIT header
first and hashes all 1,877 sectors; that final result supersedes the prefix.
The intermediate `bootloader-environment.json` independently confirms that
header and the empty configured environment location. The final inventory
additionally validates the documented active environment location.

The source revision is `d64aab0`; board boot ID remains
`c8f3308e-5c02-4be1-bc0e-3ee5991761e8`. No software, clock or service state was
changed. Runtime remained locked at 1280×720, with zero capture xruns and
rejected frames in the saved snapshot. No visual/acoustic, suspend/resume,
physical 480p, LPDDR3-board or reboot-persistence claim is added by this audit.
Disk file hashes do not independently authenticate the already-running kernel
or loaded module memory.

Host-only recovery material is under `build/production-audit-2026-10-28/`:
raw boot FAT snapshot, extracted vendor assets and regenerated startup bundle.
These are ignored artifacts and are not substitutes for a clean-checkout
recipe. Rootfs package versions are captured, but there is no Debian snapshot
or complete toolchain/dependency lock demonstrating a byte-identical image.
Hotspot credentials, SSH keys, unrelated user files and raw environment data
were deliberately excluded.

## Reproducing the comparison

`collect-board.py` reads inventory to stdout and is suitable for SSH stdin; it
never creates a target file. Only the explicitly documented raw storage ranges
are read. `analyze-inventory.py` is offline and compares saved observations
with the audited checkout and retained artifacts. Retained artifact discovery
includes ignored kernel output (`rg --files --no-ignore`), rather than assuming
ordinary rg output lists all generated `.ko` files.

The successful startup regeneration used:

```sh
python3 tools/hdmi/build-shared-startup.py build/production-audit-2026-10-28/regenerated-startup
python3 docs/production-audit/2026-10-28/analyze-inventory.py
```

The builder refuses an already-existing output directory; use a new empty
output location for another regeneration. Comparison needs the saved module
match list, FAT observations and additional utility text included here, plus
the ignored artifacts referenced by their paths. The report explicitly marks
what cannot be verified if those local inputs are lost. No commit/push was
requested or performed for the audit.
