# Projector-end unplug/replug control

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

Recorded result: no immediate visible change after unplug or replug; a later
warm reboot with HDMI connected restored logo and console. The checkerboard
was enabled/restored and additional time elapsed in the same sequence.

This single trial does not identify pin 18 or establish that unplugging caused
recovery. The later matched no-disconnect and reboot-only controls also
recovered a black panel. The growfs failure was recorded, not repaired.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [after-reboot-services.txt](after-reboot-services.txt)
- [after-reboot.txt](after-reboot.txt)
- [after-unplug.txt](after-unplug.txt)
- [before.txt](before.txt)
- [host-pattern-time.txt](host-pattern-time.txt)
- [pattern-on.txt](pattern-on.txt)
- [reboot-host-time.txt](reboot-host-time.txt)
- [restored-before-reboot.txt](restored-before-reboot.txt)
- [serial-timestamped.txt](serial-timestamped.txt)
