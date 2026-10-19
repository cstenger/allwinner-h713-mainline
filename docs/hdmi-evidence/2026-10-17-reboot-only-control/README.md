# Reboot-only recovery control

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

Recorded result: another warm reboot at black-boot uptime 238.07 s restored
logo/console without diagnostic TCON accesses or HDMI interruption. Normal
shutdown and U-Boot initialization still programmed the display.

Neither cable removal nor diagnostic pattern writes were necessary for this
recovery. Elapsed time, repeated shutdown/initialization and intermittent state
remain confounded. A good recovery with FIFO reset skipped and another good
control with reset applied make that log an unreliable good/black classifier.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [black-baseline.txt](black-baseline.txt)
- [cold1-verification.txt](cold1-verification.txt)
- [control-execution.txt](control-execution.txt)
- [control-target.py.txt](control-target.py.txt)
- [initial-good.txt](initial-good.txt)
- [serial-timestamped.txt](serial-timestamped.txt)
