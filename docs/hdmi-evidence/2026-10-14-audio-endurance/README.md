# HDMI audio endurance and drift, 2026-10-14

**PASS:** one hour of48kHz stereoS16_LE input/output, host-streamed capture,
all120 unique markers and120 settled tone windows, exact172,800,000 frames
(691,200,000 raw bytes), zero recorder overruns/new driver XRUNs, stable PID1402,
zero-filled final second and clean HPD/SCP/DDC restoration. The90-second
qualification also passed. All playback/capture/signal-helper exit codes0.

Source-relative sample drift: **18.891ppm**, equivalent to about68.0ms per hour
between the independent source/capture clocks. Minimum marker correlation is
.99836; maximum adjacent marker-interval change2.07 frames; maximum linear-fit
residual13.80 frames (0.288ms). This is measured relative drift, not calibrated
absolute oscillator accuracy or a claim of gap-free audio at every sample.

[Full result](bench/hour/result.json), [summary](summary.json),
[drift plot](bench/hour/drift.png), [plot data](bench/hour/drift.csv),
[teardown](bench/audio-unload.log), [hour build snapshot](hour-build-manifest.json).

The119 board CLOCK_MONOTONIC_RAW samples fit47,999.9983 frames per raw second
(-0.035ppm relative to that board clock). Maximum bracketed read uncertainty
is0.445ms and fit residual19.02 frames. This separate measurement is not a
calibrated clock-accuracy specification.

The managed driver and firmware-lifetime receiver owner are prepared from a
physical cold boot/manual U-Boot stop with the guarded single MIPS launch,
verified source3 transition and preserved FIT with RAM-only IRQ115/113 fix.
No boot artifact or module is installed persistently.

The runner writes private capture PCM directly over SSH to the host, avoiding
board RAM/disk growth. Source WAV generation and raw analysis use bounded
chunks. A90-second qualification precedes the3600-second run on the same
initialized audio instance. Both use48kHz stereoS16_LE input/output.

Unique filtered-noise markers in the left channel every30 seconds establish
source-frame positions. Normal left1kHz/right2kHz tones between markers verify
channels and output format. Normalized matched filtering locates every marker;
a linear fit estimates relative source-to-capture sample drift. Residuals
expose missing/repeated blocks or timing discontinuities. Acceptance bounds
are correlation>=.65, absolute drift<=1000ppm and maximum adjacent marker-interval change<=48
frames (1ms). Smooth clock wander may curve the fitted line; accumulated fit
residual is reported separately and does not itself fail the test. These are explicit bench acceptance limits, not calibrated
oscillator specifications. Exact recording byte count, zero final silence,
no recorder overruns/new driver XRUNs, stable capture owner and clean helper
restoration are also required.

A separate30-second sampler reads capture hw_ptr bracketed by board
CLOCK_MONOTONIC_RAW timestamps and reports cadence relative to that clock,
including read uncertainty. Neither measurement establishes absolute UTC or
oscillator accuracy. The broad FFT tone-rate classifier alone is not used as
a drift measurement.

The SCP helper's ordinary150-second maximum and10-second default remain.
Only explicit `long_hold=1` permits up to3660 seconds, validated by the actual
native hold predicate. The host `--audio-endurance` mode gates long holds and
rejects concurrent diagnostic probes/daemon/video options. No new peripheral
writes or changes to the fixed SCP save/restore payload are introduced.
The reader and HPD hold have independent bounds. Cleanup preserves DDC holds
if SCP initialization/removal has not completed successfully.

Native controls recover a known125ppm marker offset and75ppm board cadence,
and reject missing/replayed/displaced markers, short capture and nonzero tail.
Module build uses the exact6.18.38 kernel with LLVM W=1. Raw PCM/source WAVs
remain local; compact logs, results and build snapshots are retained here.

## Qualification and analysis refinement

The90-second qualification passed with three markers and19.42ppm relative
sample drift. Before starting the hour, the acceptance check was refined to
allow smooth clock wander: maximum adjacent interval change is gated, while
accumulated linear-fit residual is reported separately. This avoids treating
normal slow curvature as a missing block. Native controls still reject a
300-frame displacement. The qualification raw file was reanalyzed successfully
with this rule (`bench/qualification/reanalysis.json`). Original and hour build
snapshots are retained separately; no analysis/runner/helper change was made
during the one-hour recording. Progress/plot wrappers added during recording
only read host files and did not touch board state.

A transient initial SSH connection attempt preceded Wi-Fi readiness; staging
was retried after connection activation. A read-only counter-check approval
review timed out mid-run; its permitted single retry succeeded. Neither event
changed DSP, capture ownership or recorded audio.

## Final state and remaining limits

Audio unload restored all22 DSP graph words with readback, SPDI1/bridge/
AudioTop/IHB, and15 TVFE clock words plus bus/reset. Receiver clients0,
firmware_pinY, edid_readyY, clock_count4, init_error0; both receiver domains
remain active, MIPS responds and WirePlumber is active. The original empty
firmware path is restored. Audio and transient SCP/DDC helpers are absent.
No recorder, source player, listener or delayed task remains.

The volatile DSP patch remains1/1 until physical cold boot. A new managed audio
initialization requires cold versions0/0; do not reload to bypass a DSP error
or force receiver removal while firmware is live.

This validates one hour at48kHz input/output. Prior work separately validated
32/44.1kHz input, source-rate transitions and one physical hotplug, but not
hour-long captures at those rates. Repeated hotplug endurance, automatic
source3 boot, parked shutdown and suspend remain unvalidated. Raw recordings,
source WAVs and built modules remain local; compact records/plot/CSV are the
reviewable results. The prior checkpoint71dca46 predates this endurance work.
