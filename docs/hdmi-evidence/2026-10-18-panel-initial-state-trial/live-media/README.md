# Live HDMI video/audio validation

Requested 2026-10-18 after three successful cold/first-warm pairs. Current
warm boot has all HDMI units inactive by design; first obtain a fresh physical
cold session. Keep HDMI connected at both ends and source enabled; serial
capture remains in the parent evidence directory and reconnects automatically.

Plan: verify patched initial-off startup and current-kernel cold handoff,
confirm managed capture/signal/speaker readiness, then test video frames and
HDMI audio using the existing live owners. Verify a moving source rather than
counting a static frame as liveness. Record digital audio and inspect content/
continuity, then verify speaker playback with operator listening. Stop only
the speaker consumer when an exclusive audio recording requires it and restore
it afterward. No firmware relaunch, competing EDID/HPD owner, RTC latch clear,
TCON writes or unrelated kernel/firmware changes. Legacy capture/preview
launchers pin older kernels and own HPD; they must not be run blindly against
the persistent current session. Read-only ring diagnostics and existing ALSA
interfaces can be evaluated after current session readiness is confirmed.

## Digital validation result

Cold boot `fe482468-f917-463c-afde-20f6baa83d3c`: patched initial-off log and
cold HDMI handoff captured. Read-only `check-startup.sh` PASS; all services
active and existing capture/speaker PCMs RUNNING before tests.

Video: eight1280x720 NV16 samples of a known moving host pattern all contain
the expected ID bands/stripe, with8 distinct IDs and no band/stripe mismatches.
These are read-only reserved DRAM samples, not a full-rate streaming test.
The double-copy attempt failed0/8 in12s (257 candidates), consistent with an
inadequate stable-copy window at720p; retain that failure in
`video-double-copy-attempt/`. The subsequent existing single-copy720p mode
passed unchanged probe-page checks and content-ID tests. Probe pages do not
prove every pixel tear-free; sampled frame IDs/stripes strengthen the result.
See `video-result.json`, `video-frame-metadata.jsonl`, `video-first-frame.png`
and reproducible `test-video.py`. Host taskbar overlays the top ID band; the
existing analyzer checks three lower bands and all three moving stripes.

Digital audio: existing persistent-owner ALSA test PASS at48/32/44.1kHz HDMI
input, with48kHz stereo S16_LE output. Each16s recording passed tone frequency,
channel separation, frame-count and post-tone digital-silence checks. Capture
XRUN delta0 for every trial. Speaker consumer alone was stopped to release the
PCM, then restored in finally. Capture/signal owners remained active.
See `audio-rates/summary.json`, recordings and `test-audio.py`.

Audible check: sent8s stereo1000/2000Hz tone with200ms fade at source peak3500
through the exact HDMI ALSA device (`hw:1,8`), return0. No default output or
application routing changed. **Operator listening confirmation pending.**
Afterward all three services active, both capture/codec PCMs RUNNING under the
restored consumer, capture XRUN counter0. See `after-audible.txt`.

Board remains in the same cold session; no further reboot or firmware launch,
no installed kernel/firmware/startup changes, no HDMI/TCON interventions.
Diagnostic reader/arecord staged only in/tmp. Serial capture continues.

This verifies sampled live video content and bounded digital audio at the
three rates. It does not establish continuous video performance, audiovisual
synchronization, long-term stability or audible sound quality without the
operator response.

## Listening replay after downtime

New cold bootb3478260… has valid handoff and all services active, but PC
reports HDMI-A-1 disconnected/disabled and no H713 HDMI IN ELD. Operator
confirms HDMI connected at both ends. No replay tone sent: exact-endpoint
check rejected playback, so no other monitor was selected. Host rescan write
requires administrator access; noninteractive sudo unavailable, no rescan
performed. Awaiting PC-end reseat. Passive UART recorder restarted; prior
recording did not survive downtime. This is separate from earlier successful
digital video/audio tests and does not invalidate their recorded results.

## No tone heard: split input/output diagnosis

After PC-end reseat, H713 endpoint reappeared and8s host playback returned0,
but operator heard no tone. Record this as audible FAIL, not an audio pass.
Cold sessionb3478260… remained unchanged. Mixer43/15/on/on/on, both PCMs
RUNNING and PA GPIO high. A fresh48kHz HDMI digital recording passes expected
1000/2000Hz channels, silence and sample count, XRUN delta0; see
`no-tone-digital/`. This demonstrates the digital input path in this session,
not the audible forwarding path.

Played the known16-bit48kHz waveform directly to `plughw:Codec,0` using a
temporary aplay executable and existing gain, bypassing HDMI forwarding only.
Direct playback returned0. Speaker consumer stopped for exclusive codec
access and restored by an EXIT trap; all three services active afterward.
No persistent changes, manual PA/GPIO writes or firmware relaunch.
Operator confirms the direct-codec tone was audible. This establishes analog
output works in the direct playback test; normal HDMI forwarding remains
unconfirmed. Replaying the identical waveform via HDMI after restoring the
consumer, with unchanged gain, as the next comparison. See
`local-codec-tone.log`, `local-codec-after.txt` and `no-tone-diagnostics.txt`.

## Audible forwarding confirmation after diagnosis

Operator heard both the direct-codec tone and the subsequent identical
1000/2000Hz waveform over normal HDMI forwarding. Source waveform unchanged
between these two comparisons; DAC43 and Line Out15 remained unchanged.
All capture/signal/speaker services active and both PCMs RUNNING afterward,
capture XRUN counter0; see `hdmi-after-direct-status.txt`.

Current normal HDMI-to-speaker path is audibly functional. This does not prove
unattended audible startup or explain the earlier silence: diagnostics stopped/
started the consumer, exercised direct codec playback and used a stronger
waveform (peak6500 vs earlier3500). PC-end reseat had also been required to
restore host detection earlier. No firmware/kernel/U-Boot/mixer-gain change
was made. A fresh cold-session listening test before any consumer restart,
using this same waveform, is the useful next repeatability check.

## Clean cold-start listening: PASS

Boot `4b89c33b-9059-47c8-afce-6aa2dbeb4eac`: operator confirmed visible
console and HDMI connected at both ends, ready to listen. Read-only checks
verified cold handoff, all three services active and both PCMs RUNNING.
Played the same previously audible peak6500 stereo1000/2000Hz waveform
(10s tone +4s silence) through the exact H713 HDMI PCM. Operator heard it
clearly from the projector speaker.

No speaker restart, direct codec playback, cable reseat or owner intervention
preceded this first listening observation. Speaker PID396 and NRestarts0
unchanged; both PCMs RUNNING and capture XRUNs0 afterward. No bootloader,
kernel, firmware, mixer gain or installed service changes. See
`cold-listening-01/result.json` and its serial/preflight/playback/after logs.

This is one successful clean cold-start audible trial. Earlier silence remains
unexplained; the weaker earlier waveform and intervening consumer/codec tests
prevent assigning its cause. Existing sampled live720p video and bounded
48/32/44.1kHz digital capture passes stand within their documented scope.
Normal playback remains running; no reboot requested.
