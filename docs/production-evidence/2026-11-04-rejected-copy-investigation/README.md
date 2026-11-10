# Rejected copies: same guard class as GF1; startup causality unresolved

Follow-up: the [matched diagnostic experiment](../2026-11-05-matched-startup-trace/README.md)
subsequently built/installed the unchanged-guard trace and completed three cold
boots per startup arm with zero new rejections. Startup causality remains
unresolved. The source-only/not-installed statements below describe the
initial investigation stage; current installation and evidence are in that follow-up.

The two cold-2 rejections and the earlier GF1 rejection come from the same
pre-existing capture-copy guard. The driver source SHA-256 is identical:
2fcb471c3e5f553efc557beb80b558e7640e7ec1b8c930b57d1f94f975a79b10.
The current 73-file/kernel/package/storage/bundle audit passes, and the capture
driver binary was not changed by either startup optimization.

This establishes that the optimizations did not introduce the driver path
or the existence of this rejection class. It does **not** establish that
moving startup earlier has no effect on the probability/timing of a rejection.
The timestamps and exact branches for the two historical copies were never
logged, so that causal question cannot be answered retrospectively.
[Structured findings](RESULT.json).

## Evidence compared

| Observation | Earlier GF1 | Cold 2 |
| --- | --- | --- |
| Driver/source | Same accepted capture driver | Unchanged |
| Completion mode | AFBD pair | AFBD pair |
| Rejections | One in 1,211,737 completions | Two by uptime 156.52 s / 8,372 completions |
| Exact branch/time | Not recorded | Not recorded |
| Source/session restart or hard guard/audio error at observation | None established | None; eight service identities unchanged |
| Later behavior | Normal delivery/recovery | Count still two after more than 133,000 completions |

The exposure durations, source histories and small event counts are not a
matched rate experiment. Do not infer a statistically established rate change
from these two observations.

## What the guard actually does

Pair-mode capture copies the previous completed slot of the firmware ring.
It rejects the attempted copy if either:

1. The source-plane hash changes across the copy (or full verification fails,
   when enabled).
2. The AFBD pair no longer matches the pair observed before copying.

Those alternatives share one rejection counter and neither currently logs a
per-event reason/timestamp. In this boot, verify_full=-1 (automatic, off in pair
mode), source_cached=Y, phase_from_hash=Y and use_vmalloc=N. These match the
unchanged defaults/production invocation. The ring is still copied as NV12
for the same video pipeline.

The rejected attempt increments the counter and sequence but does not queue
that buffer as completed or restart the stream. The buffer stays available
for a subsequent valid copy. The actual-source C contract test still passes:
stable copies deliver, both source-hash and pair-advance races discard, and
bypassing the guard fails both raced cases. This verifies control flow, not
physical DMA coherency or the original historical timing.

The kernel is CONFIG_PREEMPT_NONE and the capture worker is SCHED_OTHER,
nice 0. Ordinary preemptive kernel task scheduling is not an established
explanation. IRQ latency, memory/cache timing, and the phase at which the
worker observes a pair change remain possible influences, not diagnoses.

## Preserved-boot observations

Boot f410f943-cb9a-4e72-8ee7-2c8a9c2cc650 remained intact. At roughly 35 minutes
it still reported exactly two rejections. A further one-minute read-only
monitor covered Linux 2191.82–2255.89 s at 59.72 fps, adding no rejections.
The final monitor sample accounted for every production event:

- 133,722 produced
- 133,717 delivered
- Three overwritten/no-buffer events
- Two rejected copies

That accounting matched at all five monitor samples. Audio xruns, bad guards
and invalid-pair counters stayed zero, source remained locked, and all eight
HDMI service identities/restart counts stayed unchanged. A subsequent normal
73-file audit also added no rejection. This argues against continuous capture
failure; it does not reproduce or explain the two early observed events.

All five startup MIPS checks and DSP graph/readiness checks passed before
streaming. Prepare exits after initialization and capture merely adopts it;
neither startup script runs in the per-frame loop. Their direct effects are
the earlier initialization schedule and changed pre-stream waiting, rather
than a modified copy guard. A phase/initial-state effect on the existing
runtime race is still a hypothesis needing controlled evidence.

## Prepared diagnostic source, not installed

The [diagnostic patch](frame-reject-diagnostic.patch) separates the copy result
from the end-pair result, preserving the original short-circuit hardware-read
order. It logs, after a rejection decision: rejection/production counts,
copy return code, starting/ending pair and copy wall time. Pair-after -2
explicitly means it was not read because the copy guard already failed.
Logging is rate-limited; cumulative counters remain authoritative.

The builder is tools/hdmi/build-frame-reject-diagnostic.py and refuses any
baseline source other than the accepted hash. Its package contains a separate
module source tree, patch, manifest and hashes; the production source is not
edited. Two host tests compile original, diagnostic and guard-bypassed C bodies
under stable/hash-race/pair-race cases. They verify equal rejection/delivery
results and equal pair-read counts, expected reason fields and detection of
the bypassed guard.

This is **source-only preparation**. The exact accepted kernel build tree
was not retained at its former temporary path; no target module was built.
An exact production kernel/ABI rebuild is required before a live diagnostic
installation. Logging can perturb later timing and is not a retrospective
reproduction. Nothing was installed, reloaded, reset or rebooted here.

## How to establish startup causality

Use the same qualified diagnostic module, kernel, source content, cable,
temperature/off-time conditions and exposure interval for every arm:
original RC startup, completion-aware checks only, and both startup changes.
Record rejection reasons/timestamps from before first streaming, with
prospective counters and IRQ/load context. Change only the startup arm;
do not compare an instrumented optimized arm against an uninstrumented
baseline. Include repeated cold and warm runs; rare events need more exposure
than one successful boot to support an absence claim.

That separates a pre-existing copy race from a change in its incidence or
phase. No such matched experiment has yet run. The current strict failure is
retained; the earlier [GF1 disposition](../2026-11-04-guarded-discard-disposition/README.md)
closed one historical finding and did not waive new events. Repeated-boot
qualification and cold 3 remain held. The current board remains running with
both startup changes, unchanged, while the evidence is preserved.

Private raw logs, audit, prospective samples, source-only diagnostic package
and host test results: local/recovery/2026-11-04-rejected-copy-investigation/.
