# Independent delayed second-reboot repeat

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

A new cold lineage had active HDMI handoff/services verified from Linux;
cold UART startup itself was not captured. The first warm reboot requested at
cold uptime 70.00 s reproduced black. The second reboot at black-boot uptime
238.07 s restored logo/console with HDMI connected and no diagnostic TCON access.

Together with the earlier reboot-only arm, the notes record two independent
successful delayed second reboots at 238.07 s, versus one failed prompt second
reboot at 54.58 s. This is a small, non-randomized sample, not a measured timing
threshold or production acceptance rate. Keep the later third reboot separate.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [first-reboot-target.py.txt](first-reboot-target.py.txt)
- [second-reboot-execution.txt](second-reboot-execution.txt)
- [second-reboot-target.py.txt](second-reboot-target.py.txt)
- [serial-timestamped.txt](serial-timestamped.txt)
