# Connected pattern/restore/reboot control

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

Recorded result: a confirmed black panel recovered after the pattern was held
114.01 s, restored, and another warm reboot requested at uptime 238.07 s. HDMI
remained connected throughout; the checkerboard itself was never visible.

This falsifies the claim that cable removal was necessary for these recoveries.
It does not isolate pattern writes from waiting and repeated initialization.
The dwell before the pattern was not exactly matched to the preceding PC-end
trial. The subsequent reboot-only control also recovered without pattern access.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [black-baseline.txt](black-baseline.txt)
- [cold1-verification.txt](cold1-verification.txt)
- [control-execution.txt](control-execution.txt)
- [control-target.sh.txt](control-target.sh.txt)
- [initial-good.txt](initial-good.txt)
- [serial-timestamped.txt](serial-timestamped.txt)
