# Reset with quiet output and supply held on

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../../panel-investigation-history/README.md); [current build/rollback runbook](../../../uboot-panel-initial-state.md).

The ten staged operations left the same U-Boot session black. Output controls
were rested/restored, panel reset asserted/released, and supply control stayed
high at sampled boundaries. Timing stayed 720p and MIPS remained reset.

Quiet-output reset alone did not recover that state. The subsequent supply
cycle added an off/on interval and also held reset longer; those differences
must not be described as a fully isolated single-variable comparison.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [BASELINE.txt](BASELINE.txt)
- [FINAL.txt](FINAL.txt)
- [S5_RESET_ASSERT_AFTER.txt](S5_RESET_ASSERT_AFTER.txt)
- [host-staged-test.py.txt](host-staged-test.py.txt)
- [stage-summary.txt](stage-summary.txt)

All staged before/after/write captures remain in this directory; see the
central manifest for the complete file list and original/export hashes.
