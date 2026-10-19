# Prompt second reboot and delayed third reboot

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

The second warm reboot was requested at black-boot uptime 54.58 s and the
panel remained black. A subsequent third warm reboot requested at uptime
695.23 s restored logo/console. The 238.07 s target had already been missed;
the third reboot is not an independent delayed-second-reboot replicate.

No HDMI changes or diagnostic TCON accesses occurred in these recovery arms.
The outcomes do not establish a minimum delay, a reliable waiting workaround,
spontaneous recovery or an independent reset-count effect.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [cold1-verification.txt](cold1-verification.txt)
- [delayed-control-target.py.txt](delayed-control-target.py.txt)
- [delayed-reboot-execution.txt](delayed-reboot-execution.txt)
- [initial-good.txt](initial-good.txt)
- [prompt-reboot-command.txt](prompt-reboot-command.txt)
- [second-reboot-execution.txt](second-reboot-execution.txt)
- [serial-timestamped.txt](serial-timestamped.txt)
