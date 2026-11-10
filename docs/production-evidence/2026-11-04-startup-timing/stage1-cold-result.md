# Stage 1 cold startup: backend initialization improves by 5.21 seconds

Chris confirmed power and board-side UART/USB were disconnected for more
than a minute, then UART was reconnected before power-on. The same HDMI
desktop source returned, with operator confirmation. Only the two stage-1
scripts and their manifest entries changed; parallel capture remains absent
and the original capture unit hash still matches the measured RC.

Baseline boot: `60f461e3-b6a5-461c-af32-9d9bcfceb1fe`.
Stage-1 boot: `5110ffb9-3fd4-4ee5-9bb5-131fd2d9e828`.
[Machine-readable comparison](stage1-cold-01-result.json).

| Measurement | Original RC | Stage 1 | Improvement |
| --- | ---: | ---: | ---: |
| Capture process initialization duration | 11.042 s | 5.829 s | **5.213 s (47.2%)** |
| Capture ready, Linux monotonic | 22.625 s | 17.559 s | 5.066 s |
| EDID / HPD ready, Linux monotonic | 22.958 s | 17.902 s | 5.055 s |
| Speaker process active, Linux monotonic | 23.124 s | 18.073 s | 5.052 s |
| systemd startup total | 24.364 s | 19.344 s | 5.020 s |
| Renderer active, Linux monotonic | 36.711 s | 19.310 s | 17.400 s, including detection difference |
| SPL output → starting-kernel UART message | 14.811 s | 14.854 s | No firmware improvement |

Capture started 0.147 s later than in the baseline, making its own duration
the clearest comparison. All five completion-aware MIPS checks passed. Their
measured reply intervals were 0.438307, 0.427779, 0.430446, 0.435093 and
0.445271 seconds, totaling **2.176896 seconds**, versus at least 7.5 seconds
of fixed reply collection before. Each returned the complete 66-byte pinned
reply. The first discarded eight stale startup bytes; the remaining stale
counts were zero. These are reply-collection intervals, not interpreter and
whole-command durations.

## Keep host detection separate

The baseline did not detect the source on its first advertisement; its
ready-to-render interval was 13.753 s and included the ten-second retry
schedule and two-second HPD hold. This boot locked on the first advertisement:
ready-to-render was 1.408 s and there was no retry request or HPD re-advertise
log. That accounts for another 12.345 s of the renderer difference.

Therefore, attribute about **five seconds of backend improvement** to the
script change. Do not attribute the full 17.4-second renderer difference to
it or claim that first-advertisement detection is fixed from one successful
boot. Firmware timing stayed essentially unchanged.

UART/kernel correlation estimates renderer startup at **34.7 seconds after
the first SPL output**, versus approximately 52 seconds in the baseline.
The physical power switch and first displayed pixel were not instrumented;
the user's visible-desktop report is functional confirmation, not an exact
timestamp. The framebuffer console still appeared around SPL +17.27 s.

## Functional and lifecycle checks

All four HDMI bundle manifests, both stage-1 script hashes, updated backend
manifest and unchanged capture unit passed. The five sampled HDMI services
were active with zero restarts. Signal was locked 1280x720; frame rejects and
audio period xruns were both zero at the final sample. HDMI capture and codec
playback PCMs were RUNNING. No separate audible-content confirmation was
obtained on this run.

The preceding boot's persistent journal also verifies shutdown using the new
helper: two teardown checks completed in 0.447352 and 0.408553 s, all 22 DSP
and 15 TVFE clock/bus words were restored, firmware was parked, receiver
removed, and capture deactivated successfully before the recorded Power down.

The first two read-only SSH attempts timed out; a later retry connected
without any network/service changes. A read-only UART diagnostic confirmed
the same boot and active SSH. This collection does not establish an exact
network-readiness time. Failed attempts are preserved, not discarded.

The recorder was stopped after preservation. No service restart, module
reload, source-mode change or further board reboot was performed during this
measurement. The board remains on with stage 1 installed. Private raw logs
and checksums are under `local/recovery/2026-11-04-startup-ipc-install/`.

This is one before/after cold comparison plus verified prior shutdown,
not repeated cold/warm qualification or a new full-system release acceptance.
Parallel capture remains deferred for separate review and installation.
