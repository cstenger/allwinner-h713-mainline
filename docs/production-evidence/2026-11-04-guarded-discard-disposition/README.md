# GF1: disposition of the single guarded frame discard

**Resolved as an intended protective discard.** No production driver, kernel,
guard or installed setting was changed. The exact historical timing trigger
was not logged and is not claimed to have been reproduced or fixed.

The extended stream recorded one unstable copy in 1,211,737 completions
(0.000083%). The defined 2 h 57 min strict soak had already passed with zero
errors. There was no renderer restart, invalid-pair event, bad signal guard
or audio xrun at the later discard. The guard prevented that copy from being
queued as a completed buffer; it retained the buffer for the next attempt.

The pair-mode worker has exactly one reject increment: a changed source
(hash/full-copy check) or a changed/invalid pair at the end of the copy.
That branch increments the diagnostic count and continues without submitting
the buffer, stopping the queue or restarting a service. Its next stable copy
can be delivered normally. This matches the original [Route B acceptance
contract](../../hdmi-panel-source-design-2026-10-23.md#10255-route-b-check-on-the-board-2026-10-24-597-fps-nothing-rejected),
which specified near-zero rejects. The later observer's strict zero-error
snapshot failure remains a real failure of that stricter check, not evidence
that a corrupt frame reached the display. We retain it unchanged and close
this individual release hold with this explicit disposition; no new reject
budget or blanket waiver for future events is introduced.

The actual C copy and worker bodies are compiled into a host test with
controlled producer races. Stable copies deliver; both a source-hash change
and an end-of-copy pair advance discard the attempted copy and deliver the
next valid frame, without queue/buffer errors. Bypassing the guard makes both
race cases fail the test. This verifies control flow, not hardware coherency.
The source hash matches the candidate source lock. The kernel is
CONFIG_PREEMPT_NONE, so ordinary kernel task preemption is not an established
explanation; IRQ, memory or cache timing was not captured for the old event.

An unchanged-candidate load diagnostic used four bounded CPU/memory workers.
It stopped at the configured 73C thermal condition after 26.45 observed
seconds, rather than completing the planned 90 seconds. It added no guarded
discards, invalid pairs, bad guards or audio xruns. Load workers were removed;
20 seconds of subsequent video measured 59.69 fps and temperature returned to
about 56C. Five core HDMI service identities were unchanged; all seven units
remained active with zero restarts. This was not a reproduction of the old event.

All 71 runtime identity/file checks and the package/kernel/raw-boot/environment,
bundle and startup gates passed again. The strict monitor still rejects any
nonzero rejection count, with a clearer review-required message. Its six test
groups and the actual-C guard/negative-control test pass. No test framework was
installed on the board. Raw diagnostic evidence remains in private local
recovery storage.
