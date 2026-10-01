# Mid-stream resolution change — NOT our bug, and the earlier write-up was wrong

> **Superseded for HEVC and VP9 on 2026-10-01 (ffmpeg 7.1.5).** Re-measured
> with per-frame hashes against a calibrated software reference
> (`-noautoscale`, see below). ffmpeg now **does** ask for the new geometry,
> and the shim is what refuses it:
>
> | stream | what ffmpeg does at the first change | result |
> | --- | --- | --- |
> | `r01` (HEVC 640x480 → 320x240 → 640x480) | `get_format` → new surfaces → `S_FMT 320x240` = **EBUSY** | first 25 frames hardware (VE irq +25), then software |
> | `vp9-rc.ivf` (640x360 → 720p → 352x288 → 640x360) | same, `S_FMT 1280x720` = **EBUSY** | first 60 frames hardware, then software |
> | `rc.ivf` (AV1, 8 sizes) | **nothing** — no second `S_FMT`, no new surfaces | new-size frames decoded into the old 640x384 queue: hantro `cannot set up the frame: -22`, decode errors, 19 of 37 frames out |
> | `av1-depth.ivf` (AV1 720p 8 → 10 → 8 bit) | **nothing** | 34 decode errors, 26 of 60 frames out |
>
> mpv (`--hwdec=vaapi-copy`; with `--vo=null`, plain `vaapi` cannot create a
> device at all) behaves identically. The EBUSY is because the old surfaces
> still hold the queues (patch 0009).
>
> **FIXED the same day for VP9 and HEVC** by libva-v4l2-request 0018/0019
> (capture memory from a DMA-BUF heap, queue generations) and kernel 0151:
> `vp9-rc.ivf` 210/210 and `r01` 75/75 bit-exact through VA-API, every frame
> on the VE, mpv on hardware throughout; `r02` (H.264, 1280x720 -> 320x240 ->
> 1280x720) 150/150, VE +150, and the board stayed healthy.
>
> **AV1 is ffmpeg's**: `get_pixel_format()` in `libavcodec/av1dec.c` returns
> early (keeps the hwaccel) whenever the hwaccel pix_fmt is still in the
> candidate list, so a new sequence header never reaches `ff_get_format`. In
> 7.1 that covers size *and* depth changes; master adds a `sw_pix_fmt` check
> that renegotiates on a depth change only. No driver memory model can fix a
> renegotiation the client never asks for.
>
> **Calibrating the harness:** ffmpeg's rawvideo/framemd5 output auto-scales
> every frame to the first size unless given `-noautoscale`; with it, a
> libdav1d decode reproduces `rc.ivf.md5` exactly. Score per frame, not with
> one stream MD5, so the first bad frame is visible.
>
> The 2026-08-24 text below is kept as the record of what the earlier ffmpeg
> did.

Investigated 2026-08-24 with `tools/video/decode-reinit-test.sh`. This document
replaces two earlier explanations, both of which were wrong. The corrections
are kept visible because each one cost real board time.

## What actually happens

A stream whose resolution changes mid-way (`r01`: 640x480 → 320x240 → 640x480)
decodes correctly in software and through GStreamer, and fails through our
VA-API shim at 26 frames of 75 with `Timeout when waiting for media request`.

The tempting conclusion — ours, since GStreamer works — is wrong. Tracing what
the client actually asks the driver to do:

```
TRACE CreateSurfaces2 640x480 count=1 (current 0x0)
TRACE   re-setting coded format
TRACE CreateContext 640x480
TRACE CreateSurfaces2 640x480 count=1 (current 640x480)   <- and again, and again
v4l2-request: Timeout when waiting for media request
```

**Every surface is requested at 640x480, for the whole stream. No context is
ever destroyed or recreated. The SPS geometry handed to the driver never
changes** — a trace comparing `pic_width_in_luma_samples` against the
programmed format never fires once.

Meanwhile the same ffmpeg, decoding the same file in software, says:

```
Reconfiguring filter graph because video parameters changed to yuv420p, 320x240
```

So ffmpeg's *software* path handles the change and its *hwaccel* path does not
propagate it: the decoder keeps the original geometry, feeds 320x240 slice data
to an engine programmed for 640x480, and the VLD stalls. **The shim is never
given the information it would need to renegotiate.** GStreamer succeeds
because it drives V4L2 directly and renegotiates itself — that comparison does
not implicate the shim, which is what the first version of this document got
wrong.

## The two wrong explanations, and why they looked right

**"It is `SET_FORMAT_OF_OUTPUT_ONCE`."** PR #38 latches the coded format with a
process-wide flag, so a genuine resolution change could never reach the driver.
The reasoning is sound and the latch is a real latent bug — it just is not what
fails here, because no client ever asks for the second geometry. Replacing it
with a geometry comparison (`WIP-0007`) is a **no-op for this stream**: the
comparison fires once at startup and never again.

**"The fix causes heap corruption / wedges the board."** Two runs were scored
against a driver that was never loaded: the variable is `LIBVA_DRIVERS_PATH`,
not `VA_DRIVERS_PATH`, so every "WIP build" test until the last one silently
exercised the installed shipping driver. One heap corruption did happen with
the fix installed, but on a device already poisoned by an earlier crash.
**Neither observation supported the conclusion drawn from it.**

## The wedge blamed on this — a third correction

Each mismatched picture stalls the engine until the 2-second watchdog fires,
and `r02` (H.264, 150 frames) once put the board into the state where ssh
answers but no command completes. That was written up as a separate robustness
bug: "a client that stalls or dies mid-decode takes the engine down for
everyone".

**It does not reproduce on the shipping stack.** Measured on a clean boot:

| provocation | result |
| --- | --- |
| 12 watchdog timeouts from stalled decodes | healthy after every one |
| 5 clients SIGKILLed mid-decode | healthy after every one |
| 3 clients SIGKILLed while a stall was pending | healthy after every one |
| 2 clients SIGKILLed out of three running concurrently | healthy after every one |

Zero `Failed to setup decoding job` in dmesg across all of it. **Every
observation behind the original claim came from runs with the WIP
resolution-change driver installed** — the one that re-sets the coded format
mid-life. That driver poisoned the engine, not the client crashes.

The fragility it was written for is nonetheless real by inspection:
`cedrus_h265_setup()` reads the engine's own bit reader while building a job
and returns `-EINVAL` if it reads back zero, so a genuinely stuck VLD would
fail every later job for every client. `patches/kernel/0062` hardens that by
resetting from `device_run()` — the one context where a device-wide reset is
safe by construction, and the alternative patch 0040's own comment named. It is
**out of `series`**: it fixes nothing that can be shown to happen.

## Where that leaves things

- **`r01`/`r02` and `decode-reinit-test.sh` stay** as a regression test for a
  known-failing case, with the attribution recorded here.
- **`WIP-0007` stays out of `series`.** It is more correct than a process-wide
  latch and fixes nothing observable, which by this project's own standard is
  not a shipping change.
- **Iterate on `r01`, never `r02`**, if this is picked up again: one fails
  safely and the other costs physical access to the board.
