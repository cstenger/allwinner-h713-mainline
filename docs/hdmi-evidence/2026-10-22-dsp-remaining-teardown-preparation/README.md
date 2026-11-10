# Remaining teardown/reset preparation and Claude takeover

**Design/source review only. Board fully unplugged, user confirmed.**
No new executable candidate, module build, board staging, capture or live
operation. [Next diagnostic design and acceptance gates](../../hdmi-dsp-remaining-teardown-design-2026-10-22.md)
are prepared for Claude to implement before asking for power.

The completed matched classifier was rechecked against the exact exported
sham and boundary records: `matched_tested_shutdown_boundaries_preserved_patch`.
Graph/AudioTop tested sequence preserved `1/1`; omitted SPDI/bridge,
clocks/demod reset, terminal MIPS reset, domain release and CPU reset/boot
remain distinct brackets. The source-reviewed next implementation is
SPDI/Audio Bridge normal-order teardown inside a new sole-owner bench.

`source-review.json` records immutable source hashes, completed boot IDs,
next/later targets and explicit unbuilt status. `existing-owner-tests.log`
records the current owner framework's regression checks; these validate the
existing implementation only, not future operations. No claim of next-bench
readiness or clock/reset safety qualification is made.

Production sources and the completed candidate remain untouched. See the
[handoff](../../handoff-2026-10-21-hdmi-reset-for-claude.md) for current state,
proven evidence paths, cold power/capture requirements and Claude's first
implementation task.
