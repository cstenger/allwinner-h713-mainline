# HDMI audio/video sync calibration — completed

**PASS with qualifications:** the board saves a 40 ms PipeWire target delay,
matched to the supplied projection/speaker recording, and retains it across
an orderly warm reboot. Absolute camera/export bias, absolute glass-to-glass
latency and long-run drift remain unqualified.

## Installed setting and result

`/etc/default/h713-hdmi-speaker` contains
`H713_HDMI_AUDIO_DELAY_SEC=0.040`. Its exact content is archived as
`installed-speaker-defaults.conf`. The previous file was absent. The trial
override under `/run/systemd/system/h713-hdmi-speaker.service.d/` was removed.
A speaker-only restart reads the saved environment and runs
`pw-loopback --latency=20 --delay=0.04`. Video remains direct NV12 KMS with
`sync=false skip-vsync=true`; no video buffering was added. This setting
applies to this HY200 QZ713DF_A1 bench board, 720p60 HDMI and its internal
codec/speaker with DAC 43 / Line Out 15. No universal default or installer
behavior was changed.

The 40 ms verification recording (`test2.mov`) matched all 15 flash/beep
events over 14.50 real seconds. Recorded audio-minus-flash median was
**−2.44 ms**, p05/p95 **−15.07/+3.03 ms**, min/max −15.14/+5.06 ms. Positive
means audio late. A nine-way video/tone onset-threshold sweep gives median
−9.13..−0.35 ms. The phone was approximately one foot from the speaker,
adding ~0.9 ms sound flight time. These offsets include camera/export bias.

[Machine-readable verdict](CALIBRATION-RESULT.json) and
[camera method, pairs, thresholds and qualifications](camera/README.md).

## Source, tools and validation

The host used a lossless 1280×720 60 fps / stereo 48 kHz PCM clip, 42 seconds
per loop, with irregular simultaneous full-screen flashes and 1 kHz beeps.
`source-manifest.json` identifies the actual clip in
`build/hdmi-avsync-2026-10-27/source-v2/`. Generate a new clip with
`python3 tools/hdmi/make-avsync-source.py NEW_OUTPUT_DIRECTORY`.
Independently decoded video/audio onsets agree within one audio sample; a
deliberately shifted source (16.67 ms) fails the alignment gate
(`source-validation-v2.json`). `source-validation.json` describes the
superseded 45-second preparation clip, which was not used for the hardware
measurements. Original source and camera movies remain local.

The target probe was built under `/run` with `-O2 -Wall -Wextra -Werror` and
GStreamer/libdrm, and rebuilt after reboot. It explicitly targeted
`alsa_output.platform-2030000.codec.stereo-fallback` and
`/proc/asound/Codec/pcm0p/sub0/status`, with fallback disabled. Live snapshots
verify both active Codec monitor channels during baseline and 45/60/70 ms
trials. The warm graph snapshot was taken after the probe exited;
`warm-persistence/graph-snapshot-note.txt` records that limitation.
The probe rejects incomplete audio/delay sampling and emits monotonic
`PAIR_CSV` records. `tools/hdmi/analyze-avsync.py` checks pairing/coverage
before summarizing offset, spread and within-window slope.

Validation: eight electronic-analysis checks and eight deliberately faulty
variants pass/caught (`analysis-tests.log`); three independent synthetic
camera checks and three faulty variants pass/caught
(`camera/analysis-validation.txt`). Invalid probe durations are rejected
before hardware access (`probe-preflight.txt`). Both host and target builds
passed with warnings treated as errors (`target-compile.txt`). Camera
analysis validates eightfold time scaling against irregular source cadence
and detects the retimed 125 Hz tone, excluding normal-speed/ramp ends.
Reproduce the camera results from the repository root with
`python3 docs/hdmi-evidence/2026-10-27-avsync-calibration/camera/analyze-recordings.py`.

## Measurements and selection

Fresh cold boot ID: `e0d594d9-32e8-458e-b674-2c19121eb64b`. The operator
completed the disconnected cold cycle; serial was open before mains, HDMI
was connected and USB stayed disconnected. The host required a PC-end HDMI
reseat to enumerate its endpoint. No board service was manually restarted
for either zero-target baseline. The operator confirmed flashes/beeps
looping. Host playback reported 60 Hz, zero frame drops and near-zero
internal player A/V error. Live board flow was 59.64 fps with no sampled
rejects/capture xruns.

| Run | Electronic median (ms) | Matched flashes |
| --- | ---: | ---: |
| Zero target, baseline 1 | −42.39 | 38/38 |
| Zero target, baseline 2 | −46.98 | 39/39 |
| 45 ms target | −16.44 | 38/38 |
| 60 ms target | −10.70 | 38/38 |
| 70 ms target, window 1 | +9.65 | 38/38 |
| 70 ms target, window 2 | −2.57 | 38/38 |
| 40 ms target, temporary | −29.36 | 37/38 |
| 40 ms target, saved/restarted | −27.79 | 38/38 |
| 40 ms target, warm reboot | −32.35 | 38/38 |

These are display-plane/codec-monitor estimates, not projected-picture
sync. The framebuffer state can precede scanout by up to one vblank; the
probe does not measure panel/acoustic latency. Its disagreement with the
camera is not attributed to a separately measured panel latency. Do not
force the software estimate to zero as a substitute for the recording.

Retiming-aware camera medians were −23.74 ms at zero target (five retained
events), +43.37 ms at 70 ms (twelve events), and −2.44 ms at 40 ms (fifteen
events). The 70 ms recording overcorrected across all tested thresholds;
40 ms matched the recording more closely. The slow-motion audio onset at
70 ms was substantially smeared; its threshold-sweep medians ranged
+28.78..+61.93 ms. Full results and hashes are in `camera/*-slow-analysis.json`.

The target is not a simple additive offset: PipeWire 1.4.2
[`recalculate_delay()`](https://github.com/PipeWire/pipewire/blob/1.4.2/src/modules/module-loopback.c#L309)
subtracts reported capture/playback stream latency from `target.delay.sec`.
The analyzer reports a timing correction separately and does not infer a
target directly from the zero-target baseline. All candidates were measured.
Only speaker routes were deliberately restarted between delay trials.

Retained diagnostics: a staging syntax error preceded the 45 ms installation
and made no board changes; the corrected attempt is retained. The immediate
60 ms route check ran before asynchronous node creation and failed; the
settled check passed with no automatic restart. Speaker release emitted a
`pw-cli send-command` usage line, but services deactivated successfully and
capture reopened. No continuity claim is made across these intentional
speaker restarts.

## Warm-reboot persistence and qualifications

One synced orderly reboot reached
`c8f3308e-5c02-4be1-bc0e-3ee5991761e8`. The saved target and actual
`--delay=0.04` returned without a temporary override. Video, speaker and
automatic startup health acknowledgment were active with no recovery
restarts or board service intervention. The live sample measured 59.64 fps,
zero rejected-frame increment and zero capture xruns. The operator confirmed
correct projected flashes and clear, normally repeating beeps.
`warm-persistence/` contains configuration, flow, timing, serial and operator
evidence.

Host mpv lost its outputs during hotplug. Recorded host-only `ao-reload`,
video output recreation and clip reload restored the source. This is
managed-source persistence; uninterrupted-client hotplug and unassisted
first reconnection are not qualified.

The phone recordings have no visible physical/acoustic reference: the
operator needed both hands to film. Camera/export timing bias remains
unmeasured. The 40 ms result is calibrated to the recording, not certified
absolute optical/acoustic zero. A visible one-handed hard-surface tap could
refine this qualification later. The clips do not include the host monitor,
so absolute glass-to-glass latency was not measured. Their useful real-time
spans are too short to qualify long-run drift; within-window slope is not
a drift verdict.

## Reproduction, rollback and final bench state

After a deliberate reinstall, restore `installed-speaker-defaults.conf` as
`/etc/default/h713-hdmi-speaker` before starting the speaker. To restore the
pre-calibration state, remove only this newly created defaults file and
restart the speaker; its default target is zero.

Cleanup restored the host HDMI output to original raw 22937/35%, unmuted;
the timing player and passive UART recorder stopped. The board was left
powered on with the saved 40 ms target active (`cleanup.json`). No push is
part of this calibration commit.
