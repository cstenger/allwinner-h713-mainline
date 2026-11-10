# H713 speaker-last cold-boot candidate

Operator requested installation and another physical cold cycle, preserving
computer output selection and Cider routing. Prior board boot:
`d6738bc2-939e-4522-80cb-0bd583e9f95e`.

Patch 0180 gives only H713 its own Speaker DAPM callback. It preserves the
existing 700 ms delay but moves it before external amplifier assertion at
POST_PMU. PRE_PMD disables the amplifier before analog source power-down.
No register programming, GPIO ownership, codec gain or HDMI consumer routing
is changed. DAC gain remains 43 and the existing software pre-roll/fade remains.

The kernel is built through the normal content-addressed build workflow with
patch 0180 added to the series. Configuration matches the previously running
kernel. Existing HDMI modules, firmware, units and boot guard logic are
preserved; only the guarded script's FIT size/bounds and the installed kernel
checksum pin need updating. Prior kernel and startup script backups are kept.

Startup-script and kernel-rebaseline tests passed (7 and 3 tests). Installation,
shutdown and acoustic cold-boot results will be recorded below. The previously
recorded impulse precedes estimated consumer startup; this remains a candidate
ordering correction, not a proven explanation of that impulse.

## Installed, awaiting physical cold cycle

New FIT SHA-256:
`2d4be9cd6fde26440440c710996d03c19f99be1476510c13a653d9fd88ba34e4`.
FIT size 7,790,368; board FDT byte-identical to the prior image (34,037 bytes).
`kernel-install.log` records FAT readback verification and outgoing image backup
`/mnt/media-data/h713-kernel-fits/replaced-20261015-212950.fit`.
`startup-install.log` records the backed-up pin and guarded script replacement;
`startup-script.diff` contains only the two FIT size/bounds literal changes.

`pre-shutdown.log` verifies the kernel pin, FAT script matching the installed
script, both HDMI/speaker bundle manifests, active services and mixer gain 43.
The board still ran the old kernel until poweroff; the new callback can only be
verified after the requested cold cycle. Host default remained unchanged before
shutdown (`host-before.json`, `host-after-install.json`); neither snapshot had an
active Cider stream. No host audio-setting or application-routing commands were
issued. Board `systemctl poweroff` returned success. Awaiting operator lamp/fan
shutdown confirmation, physical cold cycle and acoustic result.

## First cold-boot result: partial improvement, clicks remain

Operator reported two cleaner clicks, with incomplete suppression. Board boot
`4ac2f154-7bf3-45ee-a55a-1e2512ae57c7` runs the new kernel built
Oct 15 at 21:29:07 PDT. The consumer started automatically, restored gain 43,
and has NRestarts=0. This establishes deployment and automatic gain, not click
elimination. Speaker fade-ready was logged at uptime 21.648861; later readback
of codec PCM status showed trigger_time 26.737585844 despite no process restart.
A consumer-only stop/start with temporary GStreamer ALSA logs and amplifier/
PCM observations is being used to determine whether playback recovery causes
another transition. No further production settings have been changed.

## Amplifier / PCM transition trace

`restart-diagnostic.log` records one consumer-only stop/start with the installed
0180 kernel. PA remained high for about 5.05 seconds after the playback PCM
closed, then PA and HP Amp switched off together. On start, HP Amp enabled
while PCM was SETUP; 700 ms later PA enabled at PREPARED, before RUNNING.
No second PCM trigger or GStreamer underrun warning was observed during this
24-second trace. Thus the later cold-boot trigger timestamp is not proof of an
underrun or the second audible click's cause.

Candidate 0181 ties PA to both powered Speaker and playback START. A delayed
work item enables it after 200 ms of running playback; STOP disables it before
DRQ is cleared, independently of the later DAPM timeout. A shared spinlock and
latest-enable deadline prevent stale work from enabling PA after STOP or too
early after a rapid STOP/START. The quirk is H713-only, uses the existing GPIO
owner, and rejects sleeping GPIOs because ALSA triggers may be atomic. Work is
cancelled/drained on device teardown. Translation-unit compilation passed;
full kernel build and acoustic testing are pending. Runtime diagnostic drop-in
was removed after the observation; no persistent debug configuration remains.

The deterministic C helper tests in `tools/hdmi/test-speaker-pa.py` compile the
actual helper functions extracted from the candidate kernel source. They pass
Speaker/PCM gating, immediate STOP, stale callbacks after STOP, rapid restart
settling deadlines, Speaker power-down, jiffies wraparound, teardown and
non-H713 isolation. These tests check state behavior, not physical waveforms or
real scheduler timing. The full ARM64 translation-unit compilation also passes.

## Playback-gated amplifier candidate installed, board remains on

Full normal kernel build passed. Candidate 0181 is installed for the next cold
cycle, FIT SHA-256
`855e06e85602c78e3bcefff882ace77d36330234bd7080d84fe1e3110d3613cd`,
size 7,790,520. Configuration and bench DTB are byte-identical to 0180.
`playback-gate-kernel-install.log` records FAT readback and outgoing backup
`/mnt/media-data/h713-kernel-fits/replaced-20261015-214638.fit`; the earlier
pre-0180 backup remains retained as well. The script-only update changed only
FIT size/bounds (`playback-gate-startup.diff`) and preserved installed HDMI
modules, firmware and units. Kernel-pin, startup-script, speaker-bundle and
service/mixer readback checks passed; diagnostic drop-in is absent.

The board remains on the 0180 kernel until the next physical cold cycle. The
new runtime gate is not yet verified on hardware and has no acoustic pass.
The source-helper tests passed against the full built 0181 kernel tree.
No computer output-selection, volume or Cider-routing commands were issued.
Waiting for operator readiness before another orderly poweroff.

Operator did not listen to the consumer-only diagnostic restart, so that trace
has no acoustic result. Operator then authorized shutdown for the 0181 cold
test. `systemctl poweroff` returned success; see
`playback-gate-shutdown-command.log`. Awaiting physical cold cycle, lamp/fan
shutdown confirmation and startup click count. No host audio commands were
issued during shutdown.

## 0181 cold-boot result: startup acoustic pass

Boot `2418550f-0c8b-4d96-8845-65df709c9574` runs the 0181 kernel built
Oct 15 at 21:45:30 PDT. Capture, signal and speaker services are active;
NRestarts=0. Automatic startup reapplied DAC gain 43, Line Out 15 and both
switches on, Speaker on. Both PCM endpoints are RUNNING under PID 403;
codec trigger time is 21.304390425, capture trigger time 21.277764467, and
fade-ready was logged at 21.585248. Readback is in
`playback-gate-cold-start.log`. Verification did not restart the route or
change mixer settings.

The operator confirmed a clean lamp/fan shutdown, no audible clicks during
this physical cold boot, and successful music after selecting the board as
the computer output themselves. This is one user-confirmed startup acoustic
pass, not a guarantee for every source/hotplug/recovery condition.

The operator heard a click during the preceding shutdown. That shutdown
ran kernel 0180, because 0181 was installed on disk but only loaded by this
cold boot. Therefore it does not test 0181's immediate playback-STOP muting.
Shutdown-click behavior on 0181 remains unverified; no additional poweroff
was performed during this verification. Computer output selection was changed
by the operator, not the agent. Cider routing was untouched.

## 0181 shutdown and repeat cold-cycle test requested

Operator explicitly authorized orderly shutdown to listen for a click on the
new kernel, followed by another physical cold cycle. The shutdown command
returned success; kernel/boot identity and command output are recorded in
`playback-gate-shutdown-test.log`. Awaiting operator acoustic shutdown/startup
results and board return. No computer audio-setting or Cider-routing commands
were issued.


## Commit cleanup validation, October 18

The repeat-cold-start log contains an SSH timeout; it adds no acoustic result.
The confirmed scope remains one click-free 0181 startup. Shutdown-click
suppression remains unverified.

The startup builder now pins the later October 16 panel/shared-DT image, which
includes 0180/0181 and 0182–0187: FIT 7,795,668 bytes, board FDT 34,666 bytes.
Local FIT SHA-256 is
`0877293b3a71b9ccd28c0f0ef9725752a86dffd243851a5213eb023cd3a51c70`;
local board FDT SHA-256 is
`4c4fe0c55fd0d3498af8e10d5f850321e5b56121a06ceee31ea22a204aae4940`.
The existing October 16 [installation log](../2026-10-16-uboot-kernel-dts/stage2-kernel-install.log)
records that FIT's FAT readback and installed checksum pin. These later size
guards supersede the October 15 sizes above; they do not imply another acoustic
test or kernel rebuild during cleanup.

Local checks passed: all 11 startup-script tests, all three kernel-rebaseline
tests, PA helper state/deadline tests, and startup bundle generation against
those local FIT/FDT sizes. Applying the codec patches in series order to the
pristine 6.18.38 codec source produces exactly the previously compiled 0181
codec source. Rootfs and ACL changes are outside this commit.
