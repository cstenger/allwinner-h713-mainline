# Orderly warm trial, October 24 (in progress)

Operator approved this trial and reported board power/serial/USB disconnected
for over a minute. No host HDMI video/audio source was playing initially.
Prepared a 10 s looping-source clip on the host: moving testsrc2, 1280x720
60 fps H.264, 440 Hz stereo sine amplitude 0.3 at 48 kHz PCM, stored under
build/hdmi-warm-shared-source-2026-10-24/moving-720p-tone.mkv.

Host HDMI output and projector audio sink are absent with board unpowered.
Use a wrapper (saved alongside this file) to pause before cold health until
host-source-confirmed exists in this evidence directory. Assistant will
create that local marker only after playback starts and operator confirms
cold moving picture and audible tone. No reset can occur before this gate;
900 s deadline stops without requesting one. UART runner remains sole reader.

Armed detached with setsid nohup; host log:
build/hdmi-warm-shared-source-2026-10-24/runner.log.
OPEN confirmed 2026-10-25 06:03:18 UTC (October 24, 23:03:18 PDT).
Next: operator connects serial first then mains, USB stays disconnected;
assistant starts host playback when HDMI display/audio reappear.
No outcome yet; this is not a passing test record.

Cold boot reached Linux; UART census was all-zero and the installed cold
handoff/re-latch markers passed. Runner reached its source-confirmation gate.
Read-only SSH showed boot ID `6eaa62dc-f965-4a62-a31e-44bdf30fd0f1`,
`locked 1280x720`, and capture/signal/speaker/ring/video all active.
Host automatically enabled HDMI-A-1 at 1280x720 60.000 Hz.
Started detached mpv looping the prepared clip with explicit screen and
projector audio-device selection. `host-source-cold.json` records fullscreen
HDMI-A-1, unpaused playback, stereo s16/48 kHz audio, and the projector sink
RUNNING. Awaiting operator moving-picture/colour/tone confirmation before
creating the source-confirmation marker. No reboot requested yet.

## Outcome: INCONCLUSIVE, host UART runner failure

Operator confirmed cold moving video and audible tone. `cold-evaluation.json`
passed: capture 48004.9 Hz, playback 47994.2 Hz, zero new xruns; video checks
also passed. One orderly reboot requested 06:05:31 UTC. UART recorded
`reboot: Restarting system` at 06:05:39, followed by one warm SPL.
Reader then raised BlockingIOError EAGAIN from os.read after select indicated
readiness. See runner-error.log. No autoboot interrupt was logged, no census,
no YMODEM transfer, no launch-attempted file, no `source` sent by runner.
Operator reported "Caught uboot"; current prompt state is operator-reported,
not independently verified. No automatic reconnect, resume or reset attempted.
This is not evidence of a warm firmware or panel failure and not a warm PASS.

Offline fix: catch BlockingIOError in Uart.loop and continue reading; real
I/O errors still fail. 33 tests pass (offline-tests-after-eagain-fix.log).
Regression test exercises transient EAGAIN then subsequent bytes plus fatal
EIO; reverting the fix fails it (eagain-mutation.log). Historical manifests
remain unchanged to preserve what actually ran; a retry needs new tool pins.

During reset the projector HDMI sink disappeared and PipeWire migrated the
source audio to the host SoundSticks despite explicit player device selection.
Stopped only the test player through its IPC socket. A retry must monitor
and re-establish the source on projector reconnect before judging warm audio.
Board left untouched after failure; no poweroff or recovery command sent.
