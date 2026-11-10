# Matched startup rejection trace experiment

Chris accepted both startup changes for continued development on November 5,
2026 and authorized moving to the next optimizations. See
[acceptance record](USER-ACCEPTANCE.json). Historical rejection evidence remains
intact. Next: [remove the autoboot countdown](../2026-11-05-autoboot-countdown/README.md).


Completed three alternating cold boots per arm, with a fixed five-minute
window per boot and the same desktop source. All six observations and runtime
audits passed; zero rejected copies, audio xruns, bad guards, invalid pairs or
service restarts. Same trace binary/build-ID and accepted kernel for every run.

| Result | Original startup | Both optimizations |
| --- | ---: | ---: |
| Cold boots | 3 | 3 |
| Fixed observation exposure | 15 minutes | 15 minutes |
| Mean video-service activation, Linux seconds | 24.426 | 16.239 |
| Activation range, Linux seconds | 24.372–24.467 | 16.105–16.358 |
| Rejected copies | 0 | 0 |
| Produced counts at window ends, summed | 53,700 | 53,707 |

Mean service-readiness improvement: **8.187 seconds**. This milestone is not a
direct measurement of the first visible pixel. No rejection was reproduced,
so there is no new trace reason to relate to the historical events and startup
causality remains unresolved. The original strict failure is preserved.
Transport/reconnection timing varied, as recorded per run. No matched warm
trace series is included; the earlier five warm checks used the uninstrumented
optimized RC. Longer exposure may be needed to reproduce the rare event.
[Combined structured results](RESULT.json).

The trace module is installed on disk; no live module reload was performed.
The original RC startup was selected for the first cold boot. The accepted RC
kernel remains installed. Three cold boots per arm are planned, alternating
original and optimized. All six observations completed. The board remains running optimized-03 with both startup changes and the diagnostic trace installed.

The unchanged baseline module rebuilt byte for byte as
`0daa1916414cf3c7c7c9aeb8a76bc490adc400b56f89d7622cd88773caa81aea`.
Exact kernel configuration and Module.symvers match the accepted production
pins. The release file-prefix mapping was required to reproduce the embedded
kernel header path; initial unmapped trial binaries were not installed.
The diagnostic module SHA-256 is
`03332147690daae6e3881171a2bd532265f7f95cac5e004a991b00e07e8f5548`,
with loaded version `reject-trace-v1`. See [build proof](build-proof.json).

The copy guard and short-circuit pair-read order are preserved. Logging occurs
only after the original rejection decision/accounting. Actual-source C tests
verify identical delivery/rejection decisions and hardware-read counts for
stable, source-hash-race and pair-advance cases, with a guard-bypass negative
control. Logging can perturb subsequent timing. Rate-limited messages are
reason samples; cumulative counters remain the outcome measure.

Both startup arms use the same trace binary. Original restores both original
scripts, both capture unit copies, original backend manifest and absence of
both prepare unit copies. Optimized restores the two accepted optimizations.
The installer pins all nine target states, verifies both complete bundles,
backs up all originals, writes with readback checks and rolls back partial
writes. Three installer tests pass, including injected post-write failure.
Before installation the 73-file optimized RC audit passed; afterward the
71-file original arm audit passed with the explicit trace/module manifest
substitution. Kernel, packages, raw boot regions and storage remain pinned.

Each observation ends 300 seconds after the video service becomes active.
The same desktop source content will remain visible, as confirmed by Chris.
Boot-wide monotonic kernel journal includes early rejection events before SSH
returns; live sampling records counters, audio, service identities and source
state until the fixed deadline. A missed deadline, source interruption,
service restart, hard guard/audio error or insufficient sampled frame rate
invalidates the observation. Rejections are recorded as experimental outcomes;
this does not waive the existing strict zero-rejection qualification failure.
The observer must verify the trace version on each new boot.

The host reboot did not reboot the board (boot f410f943-cb9a-4e72-8ee7-2c8a9c2cc650).
Its HDMI source disappeared and returned. Kernel logs preserve the previous
stream ending with two unstable copies, followed by new stream counters.
The post-host-reboot zero counter is therefore not a reclassification of the
historical two rejections and is excluded from matched-test exposure.

Raw evidence and packages: `local/recovery/2026-11-04-matched-startup-trace/`.
On-board committed backup:
`/var/lib/h713-hdmi-startup/matched-trace-c0d3ec1d17ab4cbebf6fbcc6bc63a77e`.
The host also holds its complete archive. Original RC module and both exact
startup arms are retained. Observer and UART capture are armed for original-01.

## Original-01 result

Boot `12438d54-2226-478c-9fcf-8a642d65d885`: valid fixed-window observation,
zero rejected copies and zero audio xrun/bad-guard/invalid-pair counters.
Video service active at Linux 24.467087 s; window ended at 324.467087 s,
last counter sample 324.65 s. Live samples began at 37.28 s and averaged
59.707 fps; the boot-wide kernel journal contains no rejection messages,
stream interruption or HPD re-advertisement. Loaded module build-ID note
matches the exact diagnostic binary. Seven services remained active with
zero restarts, both PCM devices RUNNING. User reported HDMI desktop visible
and committed to keeping the same desktop showing.

The 71-file original-arm runtime audit passed after the window. The prior
shutdown journal confirms consumers before signal/capture, 22 DSP and 15 TVFE
words restored, receiver removed/parked, and capture before user-manager stop.
See [structured original-01 result](original-01.json). One clean run does not
establish absence of the rare rejection or settle startup causality.

The optimized startup files were then selected without a live service/module
restart. Its 73-file audit passed. The switch package was restaged because
`/tmp` is cleared on boot; the initial missing-package attempt changed nothing.

## Optimized-01 result and first pair

Boot `f1a3574e-0347-48ae-9739-ea4631f58a34`: valid fixed-window observation,
zero rejected copies and zero audio xrun/bad-guard/invalid-pair counters.
Video service active at Linux 16.358156 s; observation ended at 316.358156 s,
last counter sample 316.55 s. Live samples began at 26.97 s and averaged
59.711 fps. No rejection trace, stream interruption or HPD re-advertisement.
Eight services retained their identities with zero restarts; both PCM devices
remained RUNNING. The loaded diagnostic build-ID matches original-01 exactly.
Post-window 73-file optimized-arm runtime audit passed.

All five completion-aware IPC checks passed in 0.415–0.447 s each. Prepare
started at 8.013247 s, overlapped user startup by 3.254760 s, and capture
adopted the prepared backend successfully. Automatic HDOK acknowledgement
and zero GP7 passed. The preceding original-arm shutdown restored 22 DSP and
15 TVFE words, removed/parked the receiver, and retained consumer → signal →
capture → user-manager stop order.
[Structured optimized-01 result](optimized-01.json).

| First pair | Original | Optimized |
| --- | ---: | ---: |
| Video service active, Linux seconds | 24.467087 | 16.358156 |
| Fixed observation window, seconds | 300 | 300 |
| Rejected copies at window end | 0 | 0 |
| Sampled fps | 59.707 | 59.711 |

Optimized video service was 8.108931 seconds earlier in this pair. This is
service readiness, not a directly timestamped first displayed pixel. Both
runs were clean, which does not resolve a rare-event startup dependency.
The next original arm is installed and its 71-file preboot audit passed.

## Original-02 result

Boot `607d1932-aef2-4d18-a5a7-a5722f17168f`: valid fixed-window observation,
zero rejected copies and zero audio xrun/bad-guard/invalid-pair counters.
Video service active at Linux 24.371631 s; fixed deadline 324.371631 s and
last counter sample 324.56 s. Sampled frame rate 59.707 fps. No rejection trace,
stream interruption, HPD re-advertisement or service restart. Same loaded
trace build-ID; both PCM devices RUNNING. Post-window original-arm 71-file
runtime audit passed, and automatic HDOK with zero GP7 was recorded.
The preceding shutdown restored 22 DSP and 15 TVFE words and parked/removed
the receiver with the required consumer/signal/capture/user stop ordering.
[Structured original-02 result](original-02.json).

The host Wi-Fi initially remained disconnected, routing SSH attempts toward
the wired default gateway. UART at Linux 75.10 s confirmed the diagnostic
version, zero rejections and active SSH. Reactivating the host's most recently
used saved hotspot profile restored access without changing board networking
or restarting any board service. The observer's first live sample was 91.17 s;
the fixed end deadline was retained, and boot-wide kernel logs/cumulative
counters preserve earlier rejection outcomes. Transport/reconnection load
varied between runs, a limitation for rare-event causal comparisons.

The optimized arm is now selected and its 73-file preboot audit passed.

## Optimized-02 result and second pair

Boot `ce0753a3-0497-4d44-a073-792e546af7c0`: valid fixed-window observation,
zero rejected copies and zero audio xrun/bad-guard/invalid-pair counters.
Video active at Linux 16.254371 s; fixed deadline 316.254371 s, last sample
316.44 s. First live sample 33.32 s; sampled frame rate 59.710 fps. Same loaded
trace build-ID, no stream interruption/HPD re-advertisement/restarts, both PCM
devices RUNNING. All five IPC checks passed in 0.416–0.448 s; prepare began
7.961113 s, overlapped user startup by 3.281556 s, capture ready at 14.513458 s.
Prepared-backend adoption, HDOK acknowledgement and zero GP7 passed.
Host hotspot connection was available without intervention. Post-window
73-file runtime audit passed. Previous shutdown restored 22 DSP/15 TVFE words,
parked/removed the receiver and retained consumer/signal/capture/user stop order.
[Structured optimized-02 result](optimized-02.json).

| Second pair | Original | Optimized |
| --- | ---: | ---: |
| Video service active, Linux seconds | 24.371631 | 16.254371 |
| Fixed observation window, seconds | 300 | 300 |
| Rejected copies at window end | 0 | 0 |
| Sampled fps | 59.707 | 59.710 |

Optimized video service was 8.117260 s earlier in pair two. Both pairs remain
clean, with no new rejection reason to diagnose. This does not establish the
absence of a rare race or resolve startup causality. Original-03 is selected
and its 71-file preboot audit passed.

## Original-03 result

Boot `4d51db35-a29f-480a-b032-549e65225ce5`: valid fixed-window observation,
zero rejected copies and zero audio xrun/bad-guard/invalid-pair counters.
Video service active at Linux 24.440095 s; fixed deadline 324.440095 s and
last counter sample 324.62 s. Sampled frame rate 59.705 fps. No rejection trace,
source interruption/HPD re-advertisement or service restart; both PCM devices
RUNNING, loaded trace build-ID identical. Post-window original-arm 71-file
runtime audit passed. HDOK/zero GP7 and ordinary backend initialization passed.
Previous shutdown restored 22 DSP/15 TVFE words, parked/removed the receiver,
and retained the required consumer/signal/capture/user-manager stop order.
[Structured original-03 result](original-03.json).

Host Wi-Fi again required reactivating its saved profile; no board network or
service changes were made. First live sample 83.00 s. The original fixed end
deadline was retained, with boot-wide kernel journal/cumulative counters for
early rejection events. This transport/load variation remains a comparison
limitation, as in original-02. All three original fixed windows are clean;
this is not proof that the earlier rare race is absent. Optimized-03 is
selected and its 73-file preboot audit passed.

## Optimized-03 result and completion

Boot `4ecfc48d-32bb-41eb-81e6-bd1c0522dcd8`: valid fixed-window observation,
zero rejected copies and zero audio xrun/bad-guard/invalid-pair counters.
Video active at Linux 16.105314 s; deadline 316.105314 s, last sample 316.31 s.
First live sample 55.73 s, sampled frame rate 59.709 fps. No rejection trace,
source interruption/HPD re-advertisement or service restart; both PCMs RUNNING.
Same loaded diagnostic build-ID. All five IPC checks passed in 0.415–0.449 s;
prepare started at 7.921375 s, user overlap 3.302799 s, capture ready 14.388959 s.
Backend adoption and automatic HDOK/zero GP7 passed. Previous shutdown restored
22 DSP/15 TVFE words, parked/removed receiver and retained required ordering.
Post-window 73-file RC runtime audit passed.
[Structured optimized-03 result](optimized-03.json).

Host Wi-Fi required saved-profile reactivation, without board network/service
changes. End deadline remained fixed; boot-wide kernel journal and cumulative
counters cover early rejection outcomes. The board is left running this boot
with both startup optimizations enabled and trace version `reject-trace-v1`.
The passive UART recorder and host observer were closed after collection.
No guard relaxation, live module unload/reload or further optimization occurred.
The trace is temporary diagnostic instrumentation; restore the original module
through a guarded boot before claiming byte-identical uninstrumented RC state.
