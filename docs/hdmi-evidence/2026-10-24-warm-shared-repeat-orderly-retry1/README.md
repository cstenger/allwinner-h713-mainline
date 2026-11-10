# Orderly warm shared-startup retry 1, October 24: in progress

Operator explicitly approved a fresh orderly retry and confirmed board power,
serial and USB disconnected for over one minute, still unpowered. Serial
adapter was free (fuser found no owner); host HDMI disconnected.
New build/hdmi-warm-shared-repeat-orderly-retry1-2026-10-24 manifest pins
the EAGAIN-fixed runner and unchanged RAM startup image. 33 offline tests
pass (offline-tests.log); no production startup changes or installation.

Detached runner armed; see events.log for OPEN. Wrapper saved alongside
this file pauses before each cold/warm health check until a corresponding
local cold-host-source-confirmed or warm-host-source-confirmed file exists.
Each pause has a 900 s deadline; no automatic reset/launch retry. Assistant
will verify host source routing on each boot; cold confirmation also needs
operator picture/tone report before releasing the single orderly reset.
Warm gate lets the assistant restore explicit projector routing if PipeWire
moves audio to host speakers when the projector sink disappears. The existing
checker still requires advancing video and healthy audio before digital PASS;
operator warm picture/audio confirmation remains mandatory for acceptance.

Next: after OPEN confirmation, operator connects serial first then mains,
leaves USB disconnected; host source starts after projector HDMI hotplug.
No boot result yet; this record is not a PASS.

Cold UART markers passed through login, with cold handoff and timing re-latch.
Host automatically enabled HDMI-A-1 at 1280x720 60 Hz. Started mpv with explicit
projector screen/audio-device selection. host-source-cold.json records unpaused
fullscreen HDMI-A-1 playback, 48 kHz stereo audio and sink 602 RUNNING with
stream 609 routed to it. One supplemental read-only SSH check timed out;
runner is still polling read-only SSH reachability before its cold source gate.
No reset requested and no cold health result yet. Awaiting operator picture
and tone confirmation; this is not a digital PASS.

## Outcome: INCONCLUSIVE — missed warm catch with incomplete UART capture

Operator confirmed cold moving picture, correct colours and tone. Cold digital
health passed: capture 47995.8 Hz, playback 48006.5 Hz, zero new xruns. Video
produced/delivered both advanced by 184 in 3.0923 s (~59.5 fps), zero rejected,
NRestarts=0; video service start 20.908 s after kernel start.
One orderly reboot was requested at 06:13:21.772 UTC; UART captured
`reboot: Restarting system` at 06:13:29.518. Host player was deliberately
stopped during reset to prevent PipeWire fallback; no audio was left playing.

The fixed reader did not report EAGAIN as fatal. However, warm serial bytes
are visibly incomplete: after restart the raw file starts `Trying to boot
from MMC2`, with no `U-Boot SPL` or `stage=proper_preboot`, yet contains five
`Hit any key to stop autoboot` countdown strings and later `stage=post_logo`.
See warm-uart-excerpt.txt and the raw log. Runner therefore never sent an
interrupt, never performed census/transfer/source and the installed logo-only
warm fallback ran. Operator reported no visible prompt to stop at U-Boot;
manual interruption was not part of the approved sequence or expected of them.

Assistant stopped only host runner PID 102815 after Linux login appeared,
preventing any delayed actions. Snapshot fuser showed just this runner owning
/dev/ttyUSB0; this does not prove there was no transient competing reader.
A read-only host kernel-journal filter for USB/serial errors in the interval
returned no matches. Byte-loss cause is **unresolved**; do not assume cabling,
a second reader or board firmware is responsible without evidence.

Read-only SSH (after-missed-catch-readonly.log) confirms a new boot ID
4e82b014-0c3f-4645-be99-8ec69bed9ed4, no h713,hdmi-boot-v1 property and all
five HDMI services inactive: consistent with the installed warm fallback.
No warm shared-startup result, no image install, no subsequent reset/poweroff.
Board left running. No automatic retry. Diagnose capture reliability before
requesting another operator cold-cycle trial.
