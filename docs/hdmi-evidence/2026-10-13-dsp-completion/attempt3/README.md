# Stock completion protocol validated, 2026-10-13

**PASS: 24 complete graph apply/restore cycles and three real ALSA recordings,
with no DSP timeout or driver XRUN.** Diagnostics unloaded, graph/peripherals
restored, MIPS responsive. See [summary](summary.json).

The user physically cold-cycled and manually stopped at U-Boot. The guarded
single MIPS launch, current live channel PID, source3 worker/canaries, preserved
FIT and RAM-only IRQ correction verified. Linux6.18.38 and receiver holds
verified. No listener ran, no boot artifact was flashed and no environment saved.

## Completion change

The probe now defaults to the exact stock read sequence: claim/recheck real
ownership, wait busy-clear, write the logical request, wait done-set, consume
the response, release ownership. Busy and done waits remain bounded50ms.
A failure still latches command traffic off; no automatic retry or latch reset
was added. Graph writes still require exact readback. No completion-status
register write was added.

The earlier extra done-clear observation was probe-invented. In attempt2 it
rejected a read while the port already held the expected new response8081 for
007c. Following the stock contract handles completion before the first status
sample. These results support the change; they do not establish pulse width or
claim universal hardware reliability.

The historical clear-edge paths remain available only through explicit
`stock_completion=0`; `dense_clear_poll=1` additionally selects continuous
clear sampling. They are no longer the default capture prerequisite.

## Validation

The initial test build used explicit `stock_completion=1`:

- Cold versions0/0; stock masked initialization and all724 pinned patch pairs
  verified with versions1/1.13 completed reads.
- 20 complete22-word apply/restore cycles, with every saved/applied/restored word
  read back.1,373 total reads at that point. [Kernel trace](graph-kernel.log).
- Graph reapplied for three separate16-second ALSA captures. Actual HDMI inputs
  48,32,44.1kHz each produced768,000 frames at48kHz stereoS16_LE. Expected
  left/right tones, zero silence tails, closed/reopened capture and process exits
  passed. Driver counters reported zero XRUNs. [Capture summary](capture-test/summary.json).
- All22 words restored after capture. [Readbacks](capture-graph-restored.log).
- Two more complete cycles passed through the repeatable
  `tools/hdmi/run-dsp-graph-test.py --cycles 2` runner, which also checked the
  expected68 reads per cycle. [Result](post-capture-cycles/summary.json).

The final build makes stock completion the default. After full restoration,
only the DSP helper was reloaded with audio holds retained; this was not a
failure-latch recovery. Default `stock_completion` readY and versions remained
1/1. A further full graph cycle passed, totaling70 reads in the new helper.
All diagnostics then unloaded; peripheral state restored and MIPS responded.
See [default-mode check and cleanup](default-cycle-cleanup.log).

Across both helper loads:24 graph cycles and1,647 stock-protocol reads, no
DSP timeout. Receiver power/EDID holds remain. The volatile patch remains until
physical cold boot; the current run does not require recovery or another boot.

[Initial build](build-manifest.json) SHA256
fddb6f9acea61cbd8bebb5b7c4244ed23f5259ddf852c669df8aedc6dd2d3070.
[Final default build](default-build-manifest.json) SHA256
8c6d90f8b59a8961371d29e4688f575b20ab9af14a42a6923fadb691fa07a3ae,
retained in host `build/hdmi-dsp-stock-default`. Exact-kernel LLVM W=1 passed.
The tested opt-in source snapshots and final source hashes are preserved here.
Native fake-MMIO controls cover immediate/delayed new completion, device1 mask
and timeout without consuming a response; old clear-observer controls also pass.

This validates the diagnostic prerequisite; automatic receiver/DSP ownership
inside the ALSA driver is still pending. Extended recording, source-rate changes
while open, suspend and repeated physical cable hotplug remain unvalidated.
