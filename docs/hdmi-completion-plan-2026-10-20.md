# HDMI completion plan — 2026-10-20

HDMI is a working bench implementation, but the final integrated build is not
qualified. **Automatic warm-reboot HDMI recovery is required before release**
(user decision, October 20). The present GP6 policy deliberately prevents that;
panel recovery after reboot is not HDMI recovery.

October 20 bench update: the instrumented proper is installed and its first
cold baseline passed boot/startup checks. Further clean/abrupt reset trials
are deferred because the root filesystem carries recorded ext4 errors and
failed its shutdown orphan-file check. Prepare an offline filesystem check
before continuing; see the
[current baseline and prerequisite](hdmi-evidence/2026-10-20-reset-baseline/README.md).

This plan reconciles the latest recorded evidence at repository commit
`6ce4977`. It does not report new hardware tests. Counts and durations below
are proposed qualification targets, not completed results. Historical evidence
remains valid for its recorded binaries and conditions; component passes do
not qualify a newly assembled image.

## Evidence we can carry forward

| Area | Latest useful result | Remaining qualification gap |
| --- | --- | --- |
| Panel startup/reset | October 18: three independent cold/first-warm visual pairs; one immediate SysRq-b reset returned to logo/console. About 3.007 s between panel-off log and first subsequent UART record. | Warm boots intentionally skip capture. SysRq-b is not an autonomous watchdog/hung-kernel test. The off interval is not an electrical discharge measurement. |
| Video | September 27: 360-frame native NV12 presentation run around 59.16 fps. October 18: eight distinct 720p single-copy frame IDs with correct diagnostic content. | Earlier continuous presentation used an older integration. Eight recent frames do not prove sustained cadence, every-pixel integrity, distinct physical flips, or latency. |
| Digital audio | October 14: same-open-stream 48→32→44.1→48 kHz transitions, one physical unplug/replug, ten software HPD recoveries, and one hour of 48 kHz capture with zero XRUNs. October 18: all three input rates captured again. | Some earlier recovery tests used timed/transient owners. Repeat with final persistent services, simultaneous video and speakers. Software HPD cycles are not physical cable endurance. |
| Startup/shutdown | October 14: autonomous cold startup and ordered active-recording poweroff, including DSP/TVFE restoration. | Requalify the complete final combination; warm capture startup is absent. Fault handling and update/rollback remain to qualify. |
| Audible output | One click-free startup with patch 0181; October 18 clean cold boot produced audible HDMI on the first observation without intervention. | Earlier unexplained silence remains a repeatability concern. Shutdown click suppression with 0181 lacks an acoustic pass. |
| Reproducibility/recovery | Panel fixes are integrated into normal build sources; FEL rescue reached a prompt previously. | October 18 installed U-Boot proper only, retaining other components. The rebuilt normal artifact is not the installed trial binary. Exact 1867-sector rollback was documented but not exercised. |

Sources:
[panel integration and artifact boundaries](uboot-panel-initial-state.md),
[October 18 live-media observations](hdmi-evidence/2026-10-18-panel-initial-state-trial/live-media/README.md),
[native video results](hdmi-production-roadmap.md),
[stream recovery](hdmi-evidence/2026-10-14-stream-recovery/README.md),
[HPD cycles](hdmi-evidence/2026-10-14-hpd-cycles/README.md),
[audio endurance](hdmi-evidence/2026-10-14-audio-endurance/README.md),
[normal startup and poweroff](hdmi-evidence/2026-10-14-normal-startup/README.md),
[speaker observations](hdmi-evidence/2026-10-15-speaker-last/README.md).
Later dated results take precedence over older “pending” paragraphs in these
documents; none establishes the complete release combination.

## 1. Resolve warm-reboot recovery — release blocker

Start here because this can change firmware startup, ownership, and teardown,
and therefore invalidate later integration testing.

The [current startup contract](hdmi-normal-startup.md) permits one MIPS launch
per physical power cycle. Retained RTC GP6 skips launch and capture handoff on
warm reset. The current warm branch can temporarily run MIPS for the logo,
then quiesces it; it skips the sustained source-3 capture launch. See the
[reset-state investigation](hdmi-warm-reset-investigation-2026-10-20.md).
The audio backend also latches certain failed DSP operations until
a physical cold boot. Clearing GP6 or retrying a latched MIPS/DSP launch is not
a demonstrated recovery mechanism.

Work in two stages:

1. Establish the reset contract. Record what survives an orderly reboot and
   an abrupt reset: MIPS execution, DSP/TVFE state, receiver clocks/resets,
   SCP/signal ownership, shared memory, and handoff markers. Identify a
   documented or experimentally verified way to reset all required domains,
   or safely adopt retained state. Determine whether firmware, kernel, boot
   script, or a hardware power-control change is necessary. Feasibility is
   unresolved; do not promise a software-only fix.
2. Implement a bounded, observable recovery path. For orderly reboot, stop
   consumers, restore and park firmware, release owners, and establish a
   trustworthy next-boot state. For abrupt reset, do not depend on shutdown
   having run: verify retained state or perform the proven domain reset before
   capture starts. Preserve fail-closed behavior when recovery cannot be
   verified. Review signal-init failures, concurrent stop, owner references,
   and failed ExecStop behavior as part of this contract; these are review
   targets, not established defects.

Gate: after a cold baseline, ten consecutive orderly warm reboots must each
automatically restore live HDMI video and audible audio without cable reseat,
service restart, direct-codec priming, or physical power cycling. Record boot
IDs, recovery decisions, first valid frame/audio times, and restoration state.
Then qualify an abrupt-reset path and actual watchdog expiry with active
media. If either cannot recover automatically, record the remaining release
blocker explicitly. Existing panel-only warm passes cannot satisfy this gate.

## 2. Assemble one reproducible candidate and recovery package

Define the first supported hardware/format contract: the tested HY200
QZ713DF_A1 DDR3 board, native 1280×720 near 60 Hz, HDMI PCM input at
32/44.1/48 kHz, fixed 48 kHz stereo S16_LE capture, and speaker playback.
LPDDR3 V2 has build coverage, not equivalent hardware evidence. Other modes,
compressed/multichannel audio, protected content/HDCP, and suspend/resume need
separate qualification before being advertised. EDID must match this contract.

Make assembly reproducible across the panel, audio, rootfs, and speaker work.
The [October 20 baseline](hdmi-evidence/2026-10-20-reset-baseline/README.md)
confirmed an environment-offset narrowing defect: the active saved environment
is at LBA `0x32ec00`, not configured LBA `0x49ec00`. Correct the address handling
with a controlled environment migration before qualifying the final build;
an offset-only change would lose the saved startup guards on the next boot.
The [startup builder](../tools/hdmi/build-startup.py) and
[speaker builder](../tools/hdmi/build-speaker.py) currently produce separate
bundles; neither alone constitutes a complete HDMI image. Include the managed
video path from step 3 in the eventual release package.

Record one manifest containing repository/submodule revisions, patch series,
configs/toolchains, SPL/BL31/U-Boot proper/FIT/DTB hashes and sizes, rootfs,
module hashes and vermagic, firmware hash/provenance, startup script and
environment, units, consumers, mixer policy, and install/rollback layout.
Supply proprietary firmware through the established local provision process.
Update size/hash pins only for the actual candidate; a pin change is not a
validation result. Run relevant existing builder/lifecycle checks offline.

Prepare and rehearse rollback of the exact artifacts that will be installed.
Respect the split boot layout: a normal combined SPL+proper image is not a
whole-image write recipe for this board. Preserve rescue and environment
regions. Prior FEL-to-prompt evidence does not close the exact rollback gate.
Complete recovery preparation before candidate installation.

Gate: a clean assembly produces a complete manifest and installable package,
with a verified recovery route and all required runtime dependencies. Freeze
the candidate before qualification; later changes require affected gates to
be rerun with new hashes.

## 3. Integrate continuous video with the persistent owners

Audit the V4L2 bridge's completion trace/shared-memory ABI, ring coherency,
buffer lifetime, timestamps, and receiver ownership against the final cold
and warm startup paths. The current startup bundle does not package the
V4L2 bridge or a managed panel video consumer. Adapt the native 720p harness
into a managed consumer; historical preview launchers can own HPD, prepare
source3, or pin older kernels and must not simply be run against the current
persistent session.

Use the existing receiver/signal lifetime rather than launching a second HPD
or MIPS session. Define selection, no-input behavior, client exit/crash, and
return to console. Exercise video and the speaker consumer simultaneously;
ALSA capture is exclusive, so capture-analysis runs need explicit consumer
handover and cannot also prove uninterrupted speaker playback.

Gate: at least ten minutes of native moving content on the candidate with
frame IDs/geometry checks, capture and presentation timestamps, distinct
display-flip evidence, and reported repeats/drops. Establish sustained cadence
near the actual source rate without accumulating queue delay. Verify console
restoration and clean ownership after consumer stop/crash. Recheck other
display/video functions affected by shared DRM resources.

## 4. Close audible reliability and latency/A/V acceptance

Use ten cold-start/shutdown cycles plus the warm cycles in step 1. Observe
first audible output before any remedial action, retaining source waveform,
mixer/PA state, service restart counts, PCM state, and XRUN counters. Record
startup and shutdown acoustics. If silent, collect state before restarting the
consumer or trying direct-codec audio; those interventions must not convert
a failed autonomous trial into a pass.

Measure source-to-panel optical latency and source-to-speaker latency with a
common flash/beep stimulus and external observation. Correlate source,
capture, presentation, and optical times; report median, p95, p99, maximum,
repeats/drops, and audio-minus-video offset over an hour. The existing
[A/V probe](../tools/video/av-sync-probe.c) samples plane state and a PipeWire
monitor; it does not measure panel optical delay, and its audio assumptions
need adaptation for the direct ALSA speaker path.

Gate: repeatable audible startup and click-free shutdown, with zero XRUNs
under the supported workload. Agree numeric latency and sync limits from an
initial measured baseline **before** signing off the qualification run.
No numeric latency budget has yet been accepted; fps and software timestamps
alone cannot close this requirement. Fix queueing/sync based on those results.

## 5. Qualify recovery and endurance on the frozen build

Run the following through normal installed services, retaining hashes and
machine-readable outcomes alongside operator visual/acoustic observations:

| Scenario | Proposed minimum acceptance coverage |
| --- | --- |
| Startup/source availability | Cold and warm boot with connected source, no source, and delayed source; automatic acquisition when a supported source arrives. |
| Source recovery | Ten physical unplug/replug cycles and ten software HPD cycles; source sleep/wake, reboot, and blank/unblank; fresh moving frames and audible audio after each return. |
| Audio transitions | 48→32→44.1→48 kHz during active video/playback, with channel markers and fixed capture format; no stale audio or XRUNs. |
| Client/resource lifecycle | Consumer stop/restart/crash, busy PCM, failed startup, and repeated selection/exit; no leaked owners, duplicate launch, or broken console. |
| Integrated soak | At least eight hours of simultaneous moving video and speaker playback, including all three supported audio input rates and recovery events; record memory/CPU/temperature, queue depth, frame cadence, XRUNs, and drift. |
| Update/failure handling | Missing/corrupt script or firmware, wrong module/kernel ABI, interrupted/partial bundle update, and rollback; validate inert/offline cases first and controlled hardware cases after recovery is ready. |
| Power/reset | Orderly active-media poweroff, ten warm reboots from step 1, abrupt reset, and real watchdog expiry; check panel, capture, speakers, and ownership, not just Linux reachability. |

Use bounded timeouts and explicit failure outcomes. Never turn an unverified
firmware state into an automatic retry loop. Preserve diagnostic state and
the existing protective holds until the new recovery contract proves a safe
alternative. Distinguish source absence from capture failure and do not claim
unsupported modes work merely because the GPU sees an EDID.

## Completion and suggested work order

The next implementation change should establish warm-reset state and a safe
recovery contract. Follow with separate reviewable changes for recovery,
release assembly, managed video, and measurement/reliability fixes. Recovery
package preparation and offline assembly work can proceed alongside reset
investigation; final integration testing must use the resulting frozen build.

Release requires all five gates, agreed latency/sync limits, exact candidate
and rollback manifests, reproducible installation instructions, and evidence
of automatic HDMI recovery after warm reboot. Unresolved intermittent silence,
unverified shutdown acoustics, or cold-cycle-only capture remain blockers.
The completed untracked-file audit establishes evidence curation status; it
does not establish HDMI product completion.
