# Combined cold-start and speaker calibration recording

Historical run: October 15, 2026, before the speaker-last kernel candidates.

The operator started one continuous phone recording before orderly shutdown,
then physically cold-cycled the board and kept recording through automatic
startup and direct HDMI test playback. Cider was paused by the operator.

Fresh boot: `d6738bc2-939e-4522-80cb-0bd583e9f95e`. The experimental silent
pre-roll/fade consumer started automatically with DAC gain 43, Line Out 15,
both Line Out switches and Speaker on. The speaker unit reached its fade-in
without a manual route restart. The prior transition still had an audible
click, so click elimination is not established; this recording is diagnostic.

Regenerate the test signal from the repository root:

```sh
python3 tools/hdmi/make-speaker-calibration.py build/hdmi-speaker-calibration.wav
```

The generator writes a WAV and a sibling `.json` schedule. It requires a `.wav`
output name so the sidecar cannot overwrite the audio. It creates files only;
playback and recording are separate operator actions.

Test WAV: `build/hdmi-speaker-calibration.wav`, 48-kHz stereo S16_LE, 56 seconds.
Both channels carry the same signal with raised-cosine edges. Relative to the
start of the WAV (not the start of the phone recording):

| Seconds | Signal |
|---|---|
| 0–10 | Digital silence, while the host HDMI stream is active |
| 10.00–10.15, 10.30–10.45, 10.60–10.75 | Three 600 Hz markers, −30 dBFS peak |
| 14–18 | 1 kHz, −36 dBFS peak |
| 20–24 | 1 kHz, −30 dBFS peak |
| 26–30 | 1 kHz, −24 dBFS peak |
| 32–36 | 1 kHz, −18 dBFS peak |
| 38–42 | 1 kHz, −12 dBFS peak |
| 44–48 | 1 kHz, −6 dBFS peak |
| 48–56 | Silence |

During the historical run, playback targeted the detected `H713 HDMI IN`
output. The recorded player targeted its own test stream; it did not set the
system default, change output-device volume, or move Cider. The selected
output, its 100% device volume, matching before/after defaults and playback
timing are recorded in [playback.json](playback.json). This generator does not
provide that playback/routing step.

## Phone recording analysis

Analyzed `/home/chris/Downloads/Sound test.m4a` (AAC, 48 kHz stereo,
approximately 199.6 seconds). The original was left untouched. Generated
analysis artifacts are under `build/speaker-recording-analysis/`:
`analysis.png`, `analysis.json`, and `startup-candidate.wav` (original seconds
61–68, preserving recorded level). A copy of the historical numeric
[analysis summary](analysis.json) is retained here; the original recording,
plot and audio excerpts remain local. The summary preserves the prior
analysis, not a new measurement or a complete analysis program.

The test WAV starts at approximately recording second 109.37; the three
600 Hz markers and the six 1 kHz level steps are identifiable. Strong brief
transients occur near 26.40, 32.84, and 64.22 seconds. The impulse at 64.22
lasts roughly a few tens of milliseconds. The operator confirmed the
64.22-second impulse comes from the board and that the phone was stationary,
excluding phone handling as its source. This
does not by itself establish which board circuit produces the impulse.

An approximate host-time/board-uptime correlation places speaker service
startup near recording second 66.28, codec PCM trigger near 67.35, and fade
readiness near 67.63. The 64.22-second impulse therefore precedes the
consumer's estimated startup; earlier HDMI backend initialization is nearby.
This is not proof of causation. The estimate includes unknown playback
latency, SSH timing uncertainty, and possible clock adjustments.

The louder test steps do not show a clear, monotonic increase in measured
harmonic ratio or a hard output ceiling. Phone automatic gain/noise reduction,
ambient sound, microphone response, speaker response, and AAC encoding prevent
calibrated THD/SPL measurements. In particular, the low-level harmonic ratios
are noise biased and must not be quoted as speaker THD. Keep DAC gain 43;
this recording alone does not justify increasing it or establish that the
startup click has been eliminated.

Analysis did not change board controls/services, the computer's output
selection, output volume, or Cider routing.

## Speaker-last sequencing candidate

Inspection found that `sun4i_codec_spk_event()` asserts the external PA GPIO
before its existing 700 ms DAC settling delay. An H713-only candidate moves
that delay before assertion in the Speaker widget POST_PMU callback. PRE_PMD
continues to disable PA before upstream analog widgets power down. Other SoCs
are unchanged. Candidate:
`patches/kernel/0180-EXPERIMENT-asoc-h713-enable-the-speaker-amplifier-last.patch`.

The modified translation unit compiled successfully at the time of this
recording. Subsequent tests are recorded separately in
[the speaker-last evidence](../2026-10-15-speaker-last/README.md): 0180 still
produced two clicks, while the first 0181 cold startup was operator-confirmed
click-free. The calibration recording predates those tests and does not prove
that either candidate fixes its measured impulse. Shutdown-click suppression
on 0181 remains unverified.

The driver already requests the PA GPIO initially low, and the speaker service
runs after both HDMI owners. Delaying service start alone is therefore not
equivalent to isolating and verifying actual amplifier startup.

## Cleanup validation, October 18

The regenerated WAV is checked offline for its header/frame count, identical
stereo channels, silent intervals, marker/tone levels and smooth edges. The
waveform and JSON schedule match the local files used by the historical run;
no new playback, recording or hardware test was performed. WAV SHA-256:
`68491731a592f093477fbefbab2f3f10689acd8c87e5c7dab39f77bc11504a21`. The target journals
retain their original unsynchronized April wall-clock labels; use boot identity
and the approximate timing method above rather than treating those labels as
host-time measurements.
