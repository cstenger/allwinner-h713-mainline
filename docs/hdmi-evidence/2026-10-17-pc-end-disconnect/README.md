# PC-end disconnect/reconnect comparison

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

Attempt 1 did not reproduce black and is not a recovery test. Attempt 2
reproduced black; PC-end disconnect/reconnect caused no immediate visible
change. After normal pattern restoration and warm reboot, logo/console returned.
The projector-end socket remained untouched.

This shows that manipulating the projector socket was unnecessary in this
sequence. It does not isolate a conductor or establish cable interruption as
the recovery cause: pattern writes, elapsed time and another initialization
were co-interventions, and subsequent connected controls recovered too.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [after-pc-unplug-serial.txt](after-pc-unplug-serial.txt)
- [black-baseline-serial.txt](black-baseline-serial.txt)
- [cold-boot-verification.txt](cold-boot-verification.txt)
- [cold2-verification-serial.txt](cold2-verification-serial.txt)
- [initial-good.txt](initial-good.txt)
- [pattern-on-serial.txt](pattern-on-serial.txt)
- [poweroff-host-time.txt](poweroff-host-time.txt)
- [restored-before-recovery-reboot.txt](restored-before-recovery-reboot.txt)
- [serial-timestamped.txt](serial-timestamped.txt)
