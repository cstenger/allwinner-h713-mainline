# Panel investigation history — October 16–17

Curated October 19, 2026. This is the historical evidence leading to the
[panel initial-state fix and current runbook](../uboot-panel-initial-state.md).
It adds no hardware experiment or validation pass. Operator visual reports,
UART/software observations and hypotheses are distinguished below; commit
messages and equal register values alone do not prove a working physical image.

## Chronology and useful controls

| Record | Recorded observation | Limit on interpretation |
| --- | --- | --- |
| [Shared-DT stack and early bisects](../hdmi-evidence/2026-10-16-uboot-kernel-dts/README.md) | Deployment/readback records; forced warm-path and receiver/audio/TVFE comparisons | Exploratory/intermittent outcomes; not a demonstrated single-block cause |
| [R_WDOG controls](../hdmi-evidence/2026-10-16-uboot-kernel-dts/README.md) | Trial 27 good, repeat trial 28 black | No consistent reset-source fix established |
| [Projector-end unplug/replug](../hdmi-evidence/2026-10-17-unplug-replug/README.md) | No immediate change; logo/console after subsequent warm reboot | Pattern/restore, time and another initialization were co-interventions |
| [PC-end disconnect](../hdmi-evidence/2026-10-17-pc-end-disconnect/README.md) | Attempt 1 failed to reproduce black; attempt 2 recovered after the compound sequence | Not evidence that the projector connector or a specific HDMI conductor caused recovery |
| [Connected pattern control](../hdmi-evidence/2026-10-17-matched-no-disconnect/README.md) | Recovery with HDMI connected throughout; 114.01 s pattern hold, reboot at 238.07 s | Cable removal unnecessary; pattern, time and another boot still confounded |
| [Reboot-only control](../hdmi-evidence/2026-10-17-reboot-only-control/README.md) | Recovery at 238.07 s without diagnostic TCON accesses or cable changes | Diagnostic pattern writes also unnecessary; normal shutdown/init still runs |
| [Prompt second and delayed third reboot](../hdmi-evidence/2026-10-17-prompt-second-reboot/README.md) | Second reboot at 54.58 s remained black; later third at 695.23 s recovered | Missed 238.07 s target; third reboot is not a delayed-second replicate |
| [Independent delayed-second repeat](../hdmi-evidence/2026-10-17-delayed-second-repeat1/README.md) | Another second reboot at 238.07 s recovered; initial cold UART absent | Two independent delayed-second successes in the notes, one prompt failure; small, non-randomized sample |
| [U-Boot-only reproduction](../hdmi-evidence/2026-10-17-uboot-output-diagnostic/README.md) | Matched-timing attempt black before Linux started on that warm boot | Prior shutdown could still supply inherited state; delayed good interception is not a recovery |
| [LVDS-only isolation](../hdmi-evidence/2026-10-17-uboot-output-diagnostic/lvds-only/README.md) | Three attempts stayed good; attempt 4 black and remained black after eight output-rest/restore stages | The first three are failed reproductions, not successful recoveries |
| [Quiet-output reset](../hdmi-evidence/2026-10-17-uboot-output-diagnostic/quiet-reset/README.md) | Same black state persisted through ten stages with supply control high | Reset alone insufficient in this sequence; physical rail state unmeasured |
| [Ordered supply cycle](../hdmi-evidence/2026-10-17-uboot-output-diagnostic/staged-supply-cycle/README.md) | Logo returned; all staged timing readbacks stayed 720p | Supply switching and longer reset duration not isolated; no measured discharge/minimum hold |
| [RAM-only pre-init normalization](../hdmi-evidence/2026-10-17-uboot-output-diagnostic/preinit-validation/README.md) | One pre-init normalization/logo success | Not a prevention rate; generic teardown had additional side effects |

The [later October 18 validation](../hdmi-evidence/2026-10-18-panel-initial-state-trial/README.md)
is a separate set: its cold/warm visual pairs, sampled video, digital audio,
clean-start listening and immediate-reset results are not added to these
October 16/17 counts. The current three-second hold is a conservative bench
interval, not an electrically measured minimum or an explanation of every
panel-internal mechanism.

## Interpretations superseded by the controls

- HDMI pin-18/back-power explanations were hypotheses. Connected reboot-only
  recoveries mean removal of that supply was not established as necessary;
  no selective pin isolation or physical rail measurement established it.
- A checkerboard working on a good boot and not on a black boot is useful
  discrimination, but does not exonerate every upstream block or prove correct
  LVDS clock/waveforms. The 382-register comparison was digital readback.
- The first local compound recovery had unexpected 1080p readbacks, with no
  snapshots after every preceding intervention. A later local recovery stayed
  720p throughout. Neither the cause nor necessity of that earlier transition
  was established.
- A successful R_WDOG reset followed by a black repeat is not a dependable
  fix. The notes' informal “one in five” language is not an acceptance rate.
- Prompt/delayed and second/third-reset arms must remain separate. These data
  do not establish a magic boot age, spontaneous recovery or a delay threshold.
- Growfs/orphan-file and Bluetooth/watchdog messages are preserved where
  captured. No filesystem repair or unrelated service remediation was part
  of this archival cleanup, and those messages do not identify the panel cause.

## Provenance and curation

[manifest.json](manifest.json) accounts for all 425 reviewed original files,
including the three notes. It records original path, byte length and SHA-256,
committed path/hash where selected, and reasons for local-only entries.
Every original is also retained in the ignored local backup at
`build/panel-history-review/originals/`.

The curation retains 305 evidence records, 12 original timeline snapshots,
16 one-session script snapshots and three note snapshots. Eighty-nine raw or
repetitive files remain local: duplicate continuous UART streams, the known
garbled capture, early rail-cut/off-time exploratory transcripts and broad
R-domain sweeps. Their hashes preserve provenance without presenting those
sweeps as a current safe register-read list. Firmware/backups and media already
ignored before this review were outside this inventory and stay local.

Selected `.log` files are exported as readable `.txt`. Conversion decodes
UTF-8 with backslash escapes for invalid bytes, converts CRLF to LF, and
represents remaining non-printing controls visibly. No transcript lines are
filtered; original/export hashes are both recorded. This is particularly
important for host-timestamped data: target April wall clocks were wrong, and
host report receipt times are not exact physical cable-operation times.

Each directory's `README.md` is a concise curated result. Its
`README.original.md.txt` preserves the original evolving timeline exactly,
including obsolete “pending” phases, procedures and stronger early claims.
Python/shell controllers are exact `.py.txt` / `.sh.txt` snapshots; they were
syntax-checked without execution, are not current authorized launchers, and
retain their session-specific assumptions and historical assertion guards.
Reviewed reusable tooling is documented in [panel-bench-tools.md](../panel-bench-tools.md).

## Historical notes

- [Original outside-review handoff](notes/handoff-2026-10-17-panel-black-for-chatgpt.md.txt): includes the early exploratory trial table and then-current causal claims.
- [Mechanism-focused plan](notes/panel-black-root-cause-plan-2026-10-17.md.txt): proposed observations after the timing controls; a plan is not an executed trial.
- [Evolving review/fix note](notes/review-2026-10-17-panel-black-chatgpt.md.txt): reverse-chronological updates extend into October 18; superseded hypotheses and instructions remain historical text.

Original root-level drafts remain local. The current runbook, rather than a
“next” paragraph in any snapshot, defines the present build/recovery procedure.


## Curation checks

[consistency-checks.json](consistency-checks.json) records offline verification
of all 425 original hashes, all 60 staged before/after timing/MIPS boundaries,
and selected supply/reset GPIO control readbacks. Original script snapshots
parse without execution, and curated navigation links resolve. These checks
only establish consistency of the retained records; they add no rail-voltage,
waveform, reliability or visual measurement.
