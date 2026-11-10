# Shared-DT deployment and early panel controls

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

The shared-DT stage-1 and stage-2 installations/readbacks and selected later
controls are historical precursors to the current initial-state fix. The usable
warm capture is `warm-boot-serial-2.txt`; the garbled earlier capture stays local.
The already tracked `stage2-kernel-install.log` identifies the October 16 FIT.

Trials 9–28 include receiver/audio/TVFE bisects, forced warm-path controls,
cable/source/pattern comparisons and the R_WDOG experiment. Reported successes
were intermittent. R_WDOG trial 27 was good, but its trial 28 repeat was black;
this does not establish a consistent reset-source fix.

The original narrative's strong conclusions about HDMI pin 18, “only” cable
removal clearing the state, exonerated display blocks and an analog-only fault
are not established conclusions. Subsequent no-disconnect/reboot-only controls
recovered the panel, and later ordered panel/output tests changed the evidence.
Equal register snapshots do not establish equal physical output or rail state.

Selected before/after display and boot records are retained. Earlier trials
1–8 and repeated broad R-domain sweeps remain local, with their hashes in the
manifest. The original handoff note records their reported outcomes; no raw
sweep here is a recommended present-day MMIO read allowlist.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [precheck.txt](precheck.txt)
- [stage2-boot-serial.txt](stage2-boot-serial.txt)
- [stage2-teardown-serial.txt](stage2-teardown-serial.txt)
- [stage2-write.txt](stage2-write.txt)
- [warm-boot-serial-2.txt](warm-boot-serial-2.txt)
- [write.txt](write.txt)
