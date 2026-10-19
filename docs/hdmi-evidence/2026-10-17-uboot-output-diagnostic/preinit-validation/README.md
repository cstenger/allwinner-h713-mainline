# RAM-only pre-initialization normalization

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../../panel-investigation-history/README.md); [current build/rollback runbook](../../../uboot-panel-initial-state.md).

One fresh cold lineage underwent guarded teardown/output-rest/reset/supply-off
normalization plus a deliberate three-second hold before normal logo startup.
The operator saw the logo while Linux remained unstarted. GPIO/control state
was checked; actual rail voltage and minimum off time were not measured.

This is one pre-init success, not a measured prevention rate: normal startup
had also succeeded intermittently. Generic teardown included AFBD/MIPS/fabric
side effects. The later implementation factors the panel operation and the
October 18 runbook records its separate scoped validation.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [cold-port-status.txt](cold-port-status.txt)
- [cold-verification.txt](cold-verification.txt)
- [controlled-off.txt](controlled-off.txt)
- [final-snapshot.txt](final-snapshot.txt)
- [host-cold-hdmi.txt](host-cold-hdmi.txt)
- [host-controller.py.txt](host-controller.py.txt)
- [normal-logo.txt](normal-logo.txt)
- [off-hold.txt](off-hold.txt)
- [state-before.txt](state-before.txt)
- [timing.txt](timing.txt)
- [trigger-target.py.txt](trigger-target.py.txt)
- [visual-result.txt](visual-result.txt)
