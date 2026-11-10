# Current RC startup timing: initial baseline

**Installed optimization results:** [completion-aware MIPS checks](stage1-cold-result.md)
reduced capture initialization by 5.21 seconds;
[parallel capture preparation](stage2-cold-result.md) moved HDMI readiness
another 3.15 seconds earlier. Combined EDID/HPD readiness moved from Linux
22.958 s to 14.748 s. The subsequent five warm checks and three matched cold boots per arm
are recorded in the [matched comparison](../2026-11-05-matched-startup-trace/README.md).
Chris accepted both changes for continued development; the earlier rejected-copy
evidence remains preserved. The [zero-countdown update](../2026-11-05-autoboot-countdown/README.md)
is installed; its first cold boot measured a 4.996-second saving before Linux
and passed the five-minute stability window and RC audit. The original baseline analysis follows.

Analysis date: November 4, 2026 (America/Los_Angeles). No board configuration,
firmware, production service state or boot environment was changed. An initial
SSH attempt timed out while the board was off. The user subsequently powered
on with passive UART recording armed; fresh read-only collection is complete.

## Fresh cold startup: console first, HDMI later

Boot ID: `60f461e3-b6a5-461c-af32-9d9bcfceb1fe`. The user clarified the first
visible screen was the Linux console, then confirmed the HDMI desktop later.
The SSH key matched the saved RC installation key; the older global host-key
entry was not changed. Installed session and MIPS shell script hashes match
tracked source exactly. Startup health passes and the sampled HDMI units have
zero restarts. Raw UART, service timing, dependency and journal records are
private under `local/recovery/2026-11-04-startup-timing/`; the passive recorder
was stopped after collection. [Parsed results](cold-01-result.json).

| Milestone | Clock / measured time |
| --- | ---: |
| Boot logo committed | SPL UART receipt +12.868 s |
| Starting kernel message | SPL UART receipt +14.811 s |
| Framebuffer console handover logged | SPL UART receipt +17.213 s |
| Serial autologin banner | SPL UART receipt +29.511 s |
| User manager ready | Linux monotonic 11.576 s |
| Capture initialization starts | Linux monotonic 11.582 s |
| Capture initialization completes | Linux monotonic 22.625 s |
| EDID / HPD ready | Linux monotonic 22.958 s |
| Speaker process active | Linux monotonic 23.124 s |
| systemd startup complete | Linux monotonic 24.364 s |
| No-source retry requested | Linux monotonic 33.277 s |
| Two-second HPD hold completes | Linux monotonic 35.408 s |
| 720p source lock | Linux monotonic 36.663 s |
| HDMI renderer active | Linux monotonic 36.711 s |

The systemd total is **2.384 s kernel + 21.979 s userspace**, not time to HDMI
picture. `critical-chain` reports activation offsets relative to userspace
startup; `systemctl show` monotonic properties and journal/kernel timestamps
above use time since Linux boot. Do not mix those origins.

There was no source on the first advertisement. The existing readvertise
service logged its ten-second no-source threshold at 33.277 s and the kernel
confirmed its two-second HPD pulse at 35.408 s. Lock followed 1.255 s later;
the renderer started another 48 ms later. The initial-ready-to-render interval
was **13.753 s**. This supports the observed late desktop, without diagnosing
why the host missed the initial advertisement or declaring the retry removable.

Correlating the framebuffer log's kernel timestamp (1.890804 s) with its host
UART receipt gives approximately **52 s from first SPL output to renderer
start**. This is a single boot, with UART buffering uncertainty, and excludes
pre-SPL power-on time and renderer-to-first-photon latency. Audio process/PCM
readiness does not establish when audible source content began.

### Parallel startup opportunities from the fresh critical path

* **Capture and the media user session:** capture starts just 6 ms after
  `user@1000` becomes active. Its startup code uses module/sysfs, firmware and
  MIPS ownership checks; it does not contact PipeWire or the user runtime.
  PipeWire is needed by the separate speaker service. Starting capture as soon
  as its actual prerequisites are ready could overlap user-session startup.
  The current `basic.target` completes near Linux 7.955 s, so removing only
  `After=user@1000.service` exposes about **3.6 s of overlap** on this boot,
  before accounting for contention. This requires a lifecycle review: the
  session's ordinary teardown queries/stops WirePlumber, and changing `After`
  also changes shutdown ordering. It is not a one-line validated production fix.
* **Wi-Fi module loading and HDMI:** modules-load spends 2.91 s, mainly on
  AIC8800 Wi-Fi. It is upstream of sysinit/basic and therefore delays both
  capture and the user session. Investigate moving independent network
  initialization out of that global blocking chain, preserving module order,
  network readiness and the display/IPC modules actually needed by HDMI.
  This is a second design change, not an additional saving to assume blindly.
* **Already parallel:** after signal readiness, ring initialization and speaker
  startup overlap. Keep that structure. Signal/EDID activation currently
  requires the verified DSP graph; receiver clock stages require sequential
  IPC checks. Do not run these hardware/ownership transitions concurrently.
* **Shorten serial checks before adding concurrency:** the five MIPS commands
  still contain at least 7.5 s of fixed reply collection. A bounded completion
  detector preserves staged ordering while avoiding idle time, with less
  lifecycle complexity than parallelizing the clock stages themselves.

Recommended preparation order: (1) completion-aware MIPS IPC with stale and
partial-response negative cases, (2) capture/user-session overlap with explicit
shutdown ordering, (3) shorter recoverable autoboot countdown, (4) investigate
first-advertisement detection separately with fixed source conditions. Prepare
offline and keep the accepted RC intact until an exact change/test package is
ready. No implementation or live optimization has been performed.

## Firmware measurements from the installed RC

Five preserved installed-candidate UART captures cover three cold and two warm
boots. All use rebuilt SPL/U-Boot identity
`2026.07-rc5-g320a17f71d41-h713-b3b5f2d2`. Captures and SHA-256 hashes are
listed in [firmware-timings.json](firmware-timings.json). Host receive-chunk
timestamps were parsed with Python `ast.literal_eval`; all seven milestones
were present and ordered in each capture.

| Milestone | Seconds after first SPL message, range |
| --- | ---: |
| Autoboot countdown begins | 2.060–2.194 |
| Startup script begins | 7.083–7.217 |
| Panel supply-off wait begins | 8.073–8.207 |
| Boot logo committed | 12.780–12.914 |
| HDMI firmware handoff verified | 14.270–14.398 |
| Starting kernel message | 14.724–14.862 |

The countdown-to-script interval is 5.023 seconds in every capture. The
script-to-kernel interval is approximately 7.64 seconds. This includes a
three-second supply-off/reset-held wait, the stock 550-ms panel power
pre-delay, logo initialization, a second firmware load/launch for HDMI,
source selection, timing re-latch and kernel verification/decompression.

These are UART receipt timings, rounded to milliseconds for comparison, not
millisecond-accurate physical measurements. They exclude time from the power
switch to the first SPL output. The kernel-entry message precedes actual Linux
execution; use a fresh correlated capture for end-to-end latency.

## Linux / HDMI startup sample

The preserved `local/recovery/2026-11-03-candidate-hdmi-regressions/`
`reconnect-board-diagnostics.log` records the accepted RC HDMI cold session
(boot `b1592dff-0165-4071-8c9e-0b7a97a19691`). Its journal monotonic times show:

| Event | Seconds on journal monotonic clock |
| --- | ---: |
| Receiver clock 0 enabled | 12.880 |
| Receiver clock 1 enabled | 14.644 |
| Receiver clock 2 enabled | 16.416 |
| Receiver clock 3 enabled / EDID clock held | 18.176 |
| TVFE parent clock setup logged | 21.736 |
| DSP patch verified | 22.672 |
| DSP graph verified | 22.700 |
| EDID / HPD ready | 23.121 |
| 720p source locked | 24.449 |
| Video service started | 24.513 |

Early kernel messages in this saved journal were ingested in a burst around
3.913 seconds; their journal receipt times must not be interpreted as original
kernel execution timestamps. The later milestones above provide a useful
startup sample, but systemd service start is not proof of the first visible
frame or audible sample. Together with firmware timing this suggests roughly
39–40 seconds from first SPL output to renderer start, not a measured
power-switch-to-picture result. The older ~21-second startup descriptions do
not constitute the current RC end-to-end baseline.

## Ranked opportunities

1. **Autoboot countdown: about five seconds of explicit waiting.** Review
   reducing the production countdown while preserving a practical UART
   interrupt and the qualified reboot-to-bootloader/FEL recovery paths. This
   is the clearest isolated candidate, not an already-validated saving.
2. **MIPS shell health checks: at least 7.5 seconds of fixed reply collection.**
   `tools/hdmi/h713-hdmi-session.py` calls `ipc()` after each of four staged
   receiver clock enables and once after owner readiness. Each invokes
   `tools/mips/mips-shell.py --cmd 'help win'`, whose default `--wait` is 1.5
   seconds. Its loop runs until the deadline even if the prompt is already
   complete. Observed clock gaps of 1.764/1.772/1.760 seconds match that
   fixed wait plus process/command overhead. The post-clock-3 interval also
   includes owner readiness IPC and audio-probe work. Investigate bounded
   prompt/completion-based return, keeping every stage check, stale-output
   drain, response validation and failure latch. Measure actual response time
   before selecting a deadline or claiming reclaimable seconds.
3. **Start capture earlier / remove unnecessary dependency waiting.** The
   receiver only appears near 12.88 seconds; capture is ordered after
   `systemd-modules-load.service` and `user@1000.service`. Collect unit
   monotonic activation timestamps and per-service critical chains to determine
   which dependency dominates and what the capture backend actually needs.
   PipeWire speaker startup still requires the user session. Do not infer a
   removable dependency from ordering alone.
4. **Firmware logo-to-HDMI duplication and diagnostic output.** Two firmware
   load/launch sequences occur before Linux, with roughly 1.5 seconds from
   logo commit to final handoff. Profile load, console, readiness and source
   work separately before designing a combined path. Preserve the visible
   logo, ownership guards and panel timing correctness.
5. **Panel power waits: three seconds plus stock sequencing.** Review their
   provenance and minimum requirements separately. They protect panel power
   sequencing; the full delay is not an assumed safe saving. Keep lamp/fan
   behavior intact.

Items 1 and 2 expose about 12.5 seconds of explicit configured waiting, but
that is not a promised additive speedup: recovery time, actual MIPS responses
and qualification requirements constrain how much can be reclaimed.

## Fresh measurement procedure

First read the live boot ID, installed identity and startup state. Collect
`systemd-analyze time`, `blame`, `critical-chain` for capture, signal, video,
speaker and user@1000, plus `systemd-analyze dump`/`plot` where supported.
Collect unit `ExecMainStartTimestampMonotonic`,
`ExecMainExitTimestampMonotonic`, `ActiveEnterTimestampMonotonic`,
`InactiveExitTimestampMonotonic`, dependency lists and unit/drop-in contents.
Save `journalctl -b -o short-monotonic` for those units and `dmesg` with
original kernel timestamps. Preserve boot IDs before/after collection to
reject mixed-boot results. Save private raw logs on the host.

Then arrange a passive UART capture and fixed HDMI source/cable conditions
before an authorized measured boot. Record physical power-on separately;
mark boot logo, first usable picture and first audible test content with
their measurement uncertainty. Separate cold power-on, warm reboot downtime,
Linux readiness, HDMI readiness, local-playback readiness and SSH reachability.
Repeat at least three cold and three warm baselines, then test one change at
a time with the same source and existing functional/identity checks. A warm
reboot measurement includes shutdown time as well as the next startup.

The fresh cold baseline above now supplements these archived measurements.
No agent-triggered reboot or live optimization has been performed.
