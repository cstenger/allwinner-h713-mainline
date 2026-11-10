# LVDS-output-only isolation

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../../panel-investigation-history/README.md); [current build/rollback runbook](../../../uboot-panel-initial-state.md).

Three fresh reproduction attempts stayed good and must not be counted as
successful recovery tests. Attempt 4 reproduced black before Linux startup.
Its eight output disable/restore stages left the panel black, with unchanged
720p timing, panel supply/reset sampled high, and MIPS held reset.

Output rest/restore alone was insufficient on that state. This does not prove
all LVDS electrical behavior or exclude longer-delay/compound effects. The
quiet-reset and supply-cycle comparisons continued on this same black session.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [cold-verification.txt](cold-verification.txt)
- [initial-snapshot.txt](initial-snapshot.txt)
- [initialization-timing.txt](initialization-timing.txt)
- [trigger-target.py.txt](trigger-target.py.txt)
