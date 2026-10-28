# GP7 SysRq-b trial, October 27: functional warm recovery PASS with limitations

**Final state:** warm moving video, correct colour and audible tone confirmed
by operator after the single SysRq-b and one RAM startup. Digital checks pass.
Final checked poweroff confirmed; board is powered down. This was an explicitly
authorized held-prompt continuation after truncated reset acknowledgement,
with a six-minute U-Boot pause and an earlier cold speaker restart. It is not
an unattended-runner PASS or clean cold-audio-startup PASS. UART-drain fix still
needs live validation; cold audio silence needs diagnosis. Detailed chronology
and interventions are retained below.

Operator authorized this trial. Initial power-on preceded runner arm, so no
trial/reset was attempted from that baseline. Checked poweroff subsequently
approved and confirmed; see ../2026-10-27-warm-shared-gp7-sysrq-poweroff/.
Fresh source/tool/FIT/script pins match preparation manifest. Sole UART reader
now OPEN; reviewed wrapper saved alongside. Host console log:
build/hdmi-warm-shared-sysrq-source-2026-10-27/runner.log.

Operator must disconnect board power, serial and USB >=1 minute to avoid
backpower, then reconnect serial first/mains second, USB stays disconnected.
Reader waits through this interval. Cold source confirmation + digital health
precede the one synced abrupt GP7-armed reset. Warm source routing gate also
retained. No GP7 arm, reset or RAM launch yet; no result claimed.
Full approved sequence: ../2026-10-27-warm-shared-gp7-sysrq-preparation/README.md.

Operator confirmed >=1 minute unplugged, serial-first/mains reconnect and USB
still disconnected. Complete cold boot UART captured; early census/re-latch/
handoff/login passed, cold boot ID 0ab8fbc0-9cfe-43b4-992e-6349864d4537.
Host spirits Wi-Fi needed explicit reconnect after cold power-on; Ethernet
retained. HDMI auto-enabled at 1280x720 60 Hz. Test pattern/tone now playing;
host-source-cold.json records HDMI-A-1 and projector sink 453 RUNNING with
actual routed stream. Runner paused at cold-host-source-confirmed; waiting
operator picture/colour/tone report. No GP7 arm/reset or health PASS yet.

Cold operator report: moving video and correct colour, **no tone heard**.
Cold gate stays closed; no GP7 arm/reset. Read-only host diagnostic shows
mpv unmuted at 100%, correct projector routing, but HDMI sink at 35%
(-27.36 dB); see host-audio-missing-diagnostic.json. Read-only board logs show
speaker active, both PCMs RUNNING, startup mixer 43/15 with switches on.
Board lacks amixer, so those read commands failed; no mixer writes performed.
Changed only host projector HDMI sink to 100% for the existing 0.3-amplitude
source tone; prior 35% recorded for restoration. Await operator audibility
report; attenuation is a possible cause, not yet proven. No board change.

Operator still heard no tone with host HDMI sink at 100%. Host sink monitor
measurement (host-hdmi-monitor-level.json) has RMS 0.20984 and peak 0.29999;
there is nonzero source audio near the prepared tone's expected RMS. This
proves host software output content, not physical reception at the board.
Current board mixer read-only list confirms DAC=43, Line Out=15, both line
switches and Speaker Switch=1. Both PCM pointers advance at approximately
48 kHz across the two-second read-only snapshot; no audibility established.
Board has no arecord/amixer but has gst-launch and Python.

A direct HDMI sample-content check would require briefly stopping the speaker
consumer (it exclusively owns capture), capturing via the installed GStreamer
ALSA plugin, then restoring the speaker in a finally path. This changes board
service state and has NOT been performed or authorized yet. Cold gate remains
closed; no GP7 or reset. Need operator approval before that diagnostic.

## Approved incoming-audio diagnostic

Operator explicitly approved stopping speaker briefly, capturing samples and
restoring it, while keeping SysRq-b paused. Exact boot-ID-guarded detached
helper is audio-diagnostic.py.txt; staged only in /run. It used a finally
block to restore speaker after bounded GStreamer capture. No module changes,
mixer writes, GP7 arm or reset. Speaker stopped at uptime 475.87, capture
finished 478.01, then restored; active with both PCMs RUNNING at 480.22.
See audio-diagnostic-result.log. The source/capture modules stayed loaded.

Captured 307200 bytes (1.6 s, S16LE stereo 48 kHz), copied from board RAM to
incoming-audio.s16le on host. Analysis incoming-audio-analysis.json: both
channels RMS 0.204677, peak 0.289490, 76796 nonzero samples; strongest tone
in 400–480 Hz scan is 440.0 Hz. This matches prior successful capture content.
The host tone therefore reaches the ALSA HDMI capture path; absent sound is
not explained by silent input samples. Downstream consumer/codec/amp/speaker
cause remains unresolved. Await operator report after service restoration.
Cold gate remains closed and SysRq-b paused. Do not count audio audibility
or the abrupt trial as passing from digital sample content alone.

Operator subsequently confirmed tone audible after speaker-service restoration. This restores the current audible baseline but does not establish the root cause of initial cold-boot silence. The diagnostic interrupted only the audio consumer; capture backend stayed loaded. SysRq-b remains paused per latest instruction; no cold gate release or GP7/reset. Need explicit resume before proceeding, with fresh health checks.

## Abrupt attempt outcome: STOPPED at U-Boot, incomplete acknowledgement

After operator confirmed restored tone and explicitly authorized resume, fresh
cold checks passed (cold-evaluation.json): capture/playback 48003 Hz, zero new
xruns, all DSP/startup/video checks passed. One detached GP7/SysRq-b request at
09:15:08.935 UTC. No orderly HDMI teardown occurred for this reset; the earlier
approved audio consumer diagnostic remains recorded as a baseline deviation.

Raw UART contains `H713_WARM_SHARED_SYNC_DONE gp7=b` immediately interrupted by
`[  671.808515] sysrq: Resetting`, then one warm SPL and complete proper_preboot
with GP6=48444d49, GP7=b007c0de and MIPS clock/reset/status all zero, then =>.
See abrupt-reset-uart-excerpt.txt. The GP7 boot stop and abrupt reset reached
U-Boot, but the runner requires the **complete** acknowledgement containing
GP7/GP6 and boot ID. That marker was incomplete, so no census, transfer or
source occurred. No script-transfer.log or launch-attempted exists.

Stopped only host runner PID 22754 and source player. Board remains at the
observed U-Boot prompt, untouched since. No second reset, GP7 clear, shutdown,
manual interrupt or RAM launch. No warm recovery PASS claimed.

Likely cause: stream flush only hands bytes to tty; reset can overtake queued
UART transmission. Added termios.tcdrain before SysRq-b offline; see
../2026-10-27-warm-shared-sysrq-uart-drain/. 46 tests pass; omitting the drain
fails its regression test. New manifest pins the fixed tools; original trial
manifest is preserved. This fix has NOT been run on hardware. Further board
census/continuation/retry requires explicit approval; no automatic recovery.

## User-authorized continuation, no further reset: warm digital PASS

User explicitly approved verifying the held U-Boot prompt/census and proceeding
with the first RAM-only launch, without another reset. Saved one-use harness
continue-from-held-prompt.py.txt revalidated original reset counts/early census
and cold health, refused any prior transfer/launch/continuation marker, then
verified the live prompt. continuation-manifest.json pins current fixed host
tools; original reset manifest remains preserved. Drain fix was not exercised
by another reset. Full reset acknowledgement remains truncated as recorded.

Fresh prompt at 09:21:00 UTC; GP6=48444d49, consumed GP7=0, MIPS status=0,
PPU bus=0, preboot/bootcmd unchanged, volatile bootdelay=-1. FIT size/CRC passed;
RAM script 4062 bytes / CRC32 b4a0cbfa passed. One source at 09:21:31.472;
720p re-latch and warm handoff at 09:21:38; kernel 09:21:39; login 09:21:54.
There was approximately six minutes of U-Boot hold after the single SysRq-b;
this is not an unattended or prompt-recovery timing measurement, and the
extra settling time may matter to panel-black behavior.

Warm boot ID 6039e2f0-b763-4362-b96f-760c72bedbda. Host Wi-Fi reconnected;
pattern/tone restarted explicitly at host HDMI volume 100%. Actual projector
routing saved in host-source-warm.json. Warm health and cold/warm comparison
passed: DSP 0000/0000 -> 1/1, ~48000 Hz capture/playback, zero new audio xruns,
locked 1280x720, video NRestarts=0, zero rejects, 184 delivered / 3.0791 s
(~59.76 fps), video service start 22.000 s after kernel start. Full status,
bridge dmesg/journal and counters in warm-health.json. Awaiting operator warm
picture/colour/tone report. No second reset, install or persistent changes.


## Operator acceptance and final shutdown

Operator answered yes to moving warm video, correct colours and audible tone;
see operator-warm.txt. No warm speaker restart/mixer write was needed after
the RAM startup. Functional recovery after this single abrupt reset is proven,
with the hold/ack/cold-audio caveats above. Cold startup audibility was restored
only by the approved diagnostic restart, so its root cause remains open.

Restored host projector HDMI volume to its prior 35% before stopping test
player (host-hdmi-volume-restored.log). One checked final production poweroff
completed: UART reboot: Power down at board uptime 150.155760 s, host
2026-10-27 09:24:09.933 UTC (02:24:09 PDT). Serial reader closed normally.
Board powered down, test player stopped. No production install, GP6 change,
saved environment change, commit or push. Host Ethernet retained; spirits
Wi-Fi was used for board access.

Next: validate the UART-drain fix in a fresh operator-approved abrupt trial
without a long U-Boot hold, investigate initial cold-audio silence, then
production shared branch/GP6 health-ack and installation/soak approvals.
