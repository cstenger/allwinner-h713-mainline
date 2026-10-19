# Ordered supply/reset/output cycle with 720p retained

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../../panel-investigation-history/README.md); [current build/rollback runbook](../../../uboot-panel-initial-state.md).

The twelve staged operations restored the logo in the same previously black
session where LVDS-only and quiet-reset controls failed. Every sampled timing
boundary remained 720p. Output values were restored and MIPS stayed reset;
there was no Linux boot, SoC reboot, HDMI interruption or firmware reload.

UART receipt timestamps report supply-control low-to-high 3.253 s and reset
low-to-high 4.761 s. These are not rail-voltage or physical discharge measurements.
Longer reset hold and supply switching were not isolated. This is the second
reported local compound recovery, not proof that supply alone or a three-second
minimum explains the panel. The earlier 1080p readback is unnecessary for recovery.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [BASELINE.txt](BASELINE.txt)
- [FINAL.txt](FINAL.txt)
- [S5_RESET_ASSERT_AFTER.txt](S5_RESET_ASSERT_AFTER.txt)
- [S6_SUPPLY_OFF_AFTER.txt](S6_SUPPLY_OFF_AFTER.txt)
- [S7_SUPPLY_ON_AFTER.txt](S7_SUPPLY_ON_AFTER.txt)
- [S7_SUPPLY_ON_BEFORE.txt](S7_SUPPLY_ON_BEFORE.txt)
- [S8_RESET_RELEASE_AFTER.txt](S8_RESET_RELEASE_AFTER.txt)
- [host-staged-test.py.txt](host-staged-test.py.txt)
- [observed-gpio-timing.txt](observed-gpio-timing.txt)
- [recovered-snapshot.txt](recovered-snapshot.txt)
- [stage-summary.txt](stage-summary.txt)

All staged before/after/write captures remain in this directory; see the
central manifest for the complete file list and original/export hashes.
