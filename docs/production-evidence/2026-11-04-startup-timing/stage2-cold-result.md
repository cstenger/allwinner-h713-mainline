# Parallel capture: HDMI readiness improves by another 3.15 seconds

Chris confirmed supply and board-side UART/USB were disconnected for over
one minute, then reconnected UART and powered on. The HDMI desktop returned
and was operator-confirmed. No service restart or other recovery was needed.

Stage-1 boot: `5110ffb9-3fd4-4ee5-9bb5-131fd2d9e828`.
Parallel-start boot: `4943b6a8-a036-4f03-95a1-f2f778f1238d`.
[Machine-readable result](stage2-cold-01-result.json).

All times in the first table are seconds on the Linux monotonic clock.

| Milestone | Stage 1 | Stage 1 + parallel startup | Earlier |
| --- | ---: | ---: | ---: |
| Backend initialization starts | 11.729 | 7.834 | 3.895 |
| Capture service ready | 17.559 | 14.411 | **3.148** |
| EDID / HPD ready | 17.902 | 14.748 | **3.154** |
| Speaker process active | 18.073 | 14.947 | 3.125 |
| Renderer process active | 19.310 | 16.118 | **3.192** |

Both compared boots detected the source on the first advertisement; neither
requested an HPD retry. Their EDID-ready-to-render intervals were 1.408 s
and 1.369 s. Thus this comparison does not contain the large detection/retry
difference seen between the original RC and stage 1.

## The overlap is measured, not inferred from unit ordering

Preparation ran from Linux 7.834 s until its process exited at 13.966 s.
The media user manager initialized from 8.432 s to 12.012 s, entirely within
that interval: **3.580 s of actual user-session initialization overlap**.
PipeWire started at 12.018 s and WirePlumber at 12.029 s while preparation
was still working.

All five MIPS checks ran once in prepare, with complete 66-byte responses;
their reply intervals totaled 2.176333 s, essentially the same as stage 1.
The first discarded eight stale startup bytes and subsequent stale counts
were zero. Capture then reported `already_ready: true`, validating/adopting
the same-boot backend without another clock sequence or DSP/module load.

Do not treat capture's new 0.440-second process duration as the total backend
initialization cost: the work has moved into prepare. Prepare's process took
6.132 s, compared with 5.829 s for stage-1 initialization, and capture adoption
adds another 0.440 s. Earlier start and overlap still yielded a measured
3.148-second improvement in backend readiness. One boot cannot isolate how
much of the per-process variation comes from concurrency or other startup
conditions.

## End-to-end context

| EDID / HPD readiness, Linux monotonic | Seconds |
| --- | ---: |
| Original RC | 22.958 |
| Completion-aware MIPS checks | 17.902 |
| Completion-aware checks + parallel capture | 14.748 |

Together, the two changes move HDMI readiness **8.209 seconds earlier** than
the original measured RC. UART/kernel correlation estimates renderer startup
at **31.4 seconds after first SPL output**, versus 34.7 s with stage 1. Firmware
time is essentially unchanged: the starting-kernel UART message is SPL
+14.751 s. These are not instrumented physical power-switch or first-pixel
timestamps.

`systemd-analyze time` reports 2.273 s kernel + 15.309 s userspace = 17.582 s
for all startup work, compared with stage 1's 19.344 s. Graphical target was
reached at approximately Linux 16.168 s. These are separate milestones from
HDMI readiness and first visible content, so they should not replace the
application-specific comparisons above.

## Health and lifecycle

Both stage-1 scripts, both copies of each stage-2 unit and the updated backend
manifest match their expected hashes. All four HDMI bundle manifests pass.
Prepare is active and static, with no independent enablement. All six sampled
HDMI services are active with zero restarts. Source lock is 1280x720; frame
rejects and audio period xruns remained zero through the final sample. Capture
and codec playback PCMs were RUNNING. The user confirmed the desktop, but no
separate audible-content confirmation was obtained in this run.

The preceding shutdown, after the new definitions were loaded, restored
signal/DDC ownership, all 22 DSP and 15 TVFE words, parked MIPS, removed the
receiver and stopped capture successfully. Prepare was inactive on that prior
boot; a shutdown/warm boot following actual parallel initialization has not
yet been measured or qualified.

SSH connected for both timing and health collection without intervention.
The passive UART recorder is stopped, evidence hashes are finalized, and the
board remains on with both stages installed. No additional service restart,
module reload or reboot occurred during this measurement. Private raw evidence
is under `local/recovery/2026-11-04-startup-parallel-install/`.

This is one cold measurement per stage. The results establish a functional
cold-start improvement; they do not constitute repeated cold/warm or complete
release requalification.
