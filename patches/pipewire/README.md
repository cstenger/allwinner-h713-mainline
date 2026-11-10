# pipewire patches (the GStreamer plugin only) — RETIRED 2026-10-03

> **Retired, not installed.** Stock `alsasink device=pipewire` (packages
> `gstreamer1.0-alsa` + `pipewire-alsa`) measured better with no patch:
> −2..+12 ms on av-sync-probe against +43..+60 ms here, and +10 against
> +60 ms after a forced underrun; both survive 30/30 forced underruns.
> `tools/video/gst-plane-play.c` uses it. Debian's plugin was restored on the
> bench board (divert removed, `dpkg -V` clean). The patch stays as the record
> of two upstream `pipewiresink` defects worth reporting: no start gate, and
> no alignment to the clock at all.
>
> **Correction:** the "unexplained start stall" below was not this plugin.
> `av-sync-probe` opened the DRM device before the player and became DRM
> master; `kmssink` was then refused every commit (EACCES). The probe now
> drops master.

`pipewiresink`, the GStreamer element WP4's plane routes play audio through
(`tools/video/gst-plane-play.c`). Only `src/gst/` is rebuilt; the PipeWire
daemon, libraries and every other plugin stay Debian's.

| | |
|---|---|
| base | Debian trixie `pipewire 1.4.2-1` (the version on the board), checksummed against its `.dsc` |
| build | `tools/video/build-gst-pipewire.sh [--install]`, compiled **on the board** against its own `libpipewire-0.3.so.0` and GStreamer |
| install | over Debian's `libgstpipewire.so` with `dpkg-divert`; Debian's is kept as `libgstpipewire.so.distrib` |
| undo | `rm /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstpipewire.so && dpkg-divert --rename --remove /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstpipewire.so` |

Not pushed upstream (this project pushes only to its own forks). The defects
are generic, not H713-specific, and worth reporting.

## 0001: start audio when the graph pulls, and keep it aligned to the clock

Measured with `tools/video/av-sync-probe.c` on `make-avsync-clip.sh`'s clip,
1080p H.264 through the VE scaler (plane-ve). The probe times the flash at
scan-out and the beep at the sound card, on one clock. A positive value means
the audio is late.

| | after the sink was idle | warm |
|---|---|---|
| stock `pipewiresink` | **+768 ms** | +78 to +83 ms |
| 0001 | +42.6 to +54 ms | +45 to +47 ms |
| stock mpv `--vo=gpu` (different video path, for scale) | −25 ms | −25 ms |

Two stock defects:
- **The start.** STREAMING only means the stream is linked. After idle, the
  suspended device took ~740 ms to pull its first buffer. Everything queued
  meanwhile played late, and once supply matched consumption the backlog
  never drained. Audio is now dropped until the graph's first process
  callback, as it already was before STREAMING.
- **No alignment, ever.** The stream plays continuously, so its first samples
  fix the alignment for the rest of the stream. Nothing compared where a
  sample will be heard with where it belongs. Each buffer is now checked
  before queueing:
  - heard at `pw_time.now + delay + (queued + buffered) / rate`, in the
    pipeline clock;
  - beyond 30 ms, late samples are skipped and early ones get silence;
  - `render-delay` = graph delay + one quantum, which gives the alignment
    lead time.

Also fixed: `pw_buffer.size` was `bytes / 4` whatever the format. It is now
in frames, which is how `pw_time.queued` is read.

## What is left, and why it is not chased

- **About +45 ms remains on the probe**, and it is mostly the probe's own bias:
  - flash times are taken when the plane commit is applied, which is up to
    one vblank (16.7 ms) before scan-out, plus ~8 ms to mid-screen;
  - the projector's processing delay is unseen;
  - ALSA's delay swings by a quantum within each cycle.

  PipeWire's ALSA node reports its latency as 1 quantum. Its unreported ring
  fill can be declared with the node property `latency.internal.ns`, or at
  runtime with `latencyOffsetNsec`. 0001 then accounts for it automatically,
  through `pw_time.delay`. That is calibration, so it should be judged by ear
  on the panel before it is configured. **Judged 2026-10-03: the operator
  heard the plane-ve route in sync with 0001 alone, so it stays unset.**
- **An unexplained start stall.** Twice, a run straight after replacing the
  plugin never reached PLAYING (0 frames, position 0). It has not
  reproduced in 8 runs since, idle or warm.
- **Drift** over a long film is corrected by skip/insert at the 30 ms
  threshold, which is audible as a click. `slave-method=resample` is the
  smooth alternative; it is untested here.
