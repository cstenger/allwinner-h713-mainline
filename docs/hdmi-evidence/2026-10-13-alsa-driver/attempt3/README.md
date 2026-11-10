# Successful ALSA capture acceptance, 2026-10-13

After the user's physical cold boot and manual U-Boot stop, the guarded source3
launch and preserved FIT with RAM-only IRQ correction booted Linux 6.18.38.
The current driver loaded successfully. The known volatile DSP patch and all
22 graph words verified before enabling `graph_ready`.

Three separate ALSA captures passed, reopening the device for each input:

| HDMI input | ALSA output | Frames | Result |
| --- | --- | --- | --- |
| 48 kHz | 48 kHz stereo S16_LE | 768,000 | PASS |
| 32 kHz | 48 kHz stereo S16_LE | 768,000 | PASS |
| 44.1 kHz | 48 kHz stereo S16_LE | 768,000 | PASS |

Each WAV is 16 seconds. Host hardware rates were positively verified with
resampling disabled. Three settled windows contained left 1 kHz/right 2 kHz
tones; each final second was entirely zero. Playback, capture and signal
helper exits succeeded, no overruns were reported, and ALSA status was closed
after each trial. A preliminary ordinary 2-second capture also passed without
external polling. Final counters: 9,232 owned active interrupts, 9,219 period
notifications, 9,601,600 observed bytes of progress and zero XRUNs.

[Capture summary](capture-test/summary.json) and trial subdirectories retain
WAVs, host hardware parameters, ELD, capture logs and bounded signal-helper
evidence. [Continuity analysis](continuity-analysis.json) screens the settled
3–9 second interval in 960-frame blocks: maximum residual phase increment was
less than 0.00088 radians, with relative amplitude above 0.99998. Its companion
[tool](../../../../tools/hdmi/check-continuity.py) now accepts explicit input
WAVs and a new report path; its separate
[offline tests](../../../../tools/hdmi/test-continuity.py) include clean-tone,
phase-step and silence-gap controls. See the [helper guide](../../../hdmi-capture-test-helpers.md).
The historical report above is unchanged. Periodic tones
cannot detect every possible dropped/repeated sample; this is a short bench
acceptance result, not proof of long-term continuity.

[Graph restoration](dsp-graph-restored.log) verified all 22 saved words.
[Cleanup](cleanup.log) confirms DSP/ALSA/TVFE module removal, peripheral
restoration and responsive MIPS. Receiver power/EDID holds remain, as does the
volatile patch until physical cold boot. No serial listener remains. No boot
artifact was flashed and no U-Boot environment was saved.

[Build manifest](build-manifest.json) identifies the validated module. The
fixes are clock ordering before AudIf access and accepting a positive ALSA
constraint-helper success return before attaching the capture stream.
Manual receiver/DSP prerequisites remain; source changes during open capture,
XRUN recovery, suspend and long-term recording still need validation.
