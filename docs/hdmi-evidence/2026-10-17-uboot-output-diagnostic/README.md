# Black output reproduced and recovered entirely in U-Boot

Historical October 16/17 investigation, curated October 19.
[Chronology and interpretation limits](../../panel-investigation-history/README.md); [current build/rollback runbook](../../uboot-panel-initial-state.md).

Attempt 1 stayed good, but interception added about 12 s before initialization;
it is not a recovery or proof that Linux was required. Attempt 2 matched normal
initialization timing and was visibly black before Linux ever started in that
warm boot. The previous Linux shutdown could still have created inherited state.

Good/black snapshots compared 382 addresses with only a free-running counter
difference. Equal digital readbacks do not prove correct clocks, LVDS waveforms
or physical panel state. The old scanrate-derived pixel-clock labels were not
valid measurements.

On the black state, latch-only, forced FIFO/latch, and active-output reset-only
interventions each remained black. A compound output-rest/reset/supply cycle
restored the logo. Its recovered snapshot unexpectedly read 1080p timing;
timing had not been sampled after every earlier intervention, so that change
cannot be attributed to the supply cycle or treated as a necessary recovery.

The later isolated controls below preserved 720p throughout: LVDS-only and
quiet-output reset-only failed; the staged supply cycle recovered. Pre-init
normalization then passed once. Those are the useful progression toward the
later October 18 validation, not independent proof of exact hardware causality.

The [original evolving timeline](README.original.md.txt) is preserved exactly
as historical text, including stale plans and superseded interpretations. It
is not a current test procedure. Scripts beside the evidence are `.py.txt` or
`.sh.txt` snapshots and were syntax-checked only, never executed in cleanup.

Selected records in this directory:

- [attempt1-timing-comparison.txt](attempt1-timing-comparison.txt)
- [attempt2-initialized-snapshot.txt](attempt2-initialized-snapshot.txt)
- [attempt2-timing.txt](attempt2-timing.txt)
- [black-clock-witness.txt](black-clock-witness.txt)
- [black-vs-recovered-diff.txt](black-vs-recovered-diff.txt)
- [cold-verification-serial.txt](cold-verification-serial.txt)
- [cold-verification.txt](cold-verification.txt)
- [cold2-verification.txt](cold2-verification.txt)
- [fifo-baseline.txt](fifo-baseline.txt)
- [fifo-reset-test.txt](fifo-reset-test.txt)
- [good-vs-black-register-diff.txt](good-vs-black-register-diff.txt)
- [initial-good.txt](initial-good.txt)
- [initialized-snapshot-good-attempt1.txt](initialized-snapshot-good-attempt1.txt)
- [initialized-snapshot.txt](initialized-snapshot.txt)
- [intercept-autologo-host.py.txt](intercept-autologo-host.py.txt)
- [latch-only-test.txt](latch-only-test.txt)
- [panel-power-cycle-baseline.txt](panel-power-cycle-baseline.txt)
- [panel-power-cycle-test.txt](panel-power-cycle-test.txt)
- [panel-reset-only-test.txt](panel-reset-only-test.txt)
- [recovered-ownership.txt](recovered-ownership.txt)
- [recovered-snapshot.txt](recovered-snapshot.txt)
- [serial-timestamped.txt](serial-timestamped.txt)
- [lvds-only summary](lvds-only/README.md)
- [preinit-validation summary](preinit-validation/README.md)
- [quiet-reset summary](quiet-reset/README.md)
- [staged-supply-cycle summary](staged-supply-cycle/README.md)
