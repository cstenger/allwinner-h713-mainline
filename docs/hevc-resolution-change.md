# Mid-stream resolution change — NOT our bug, and the earlier write-up was wrong

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

## What is genuinely broken, and it is not the picture

Each mismatched picture stalls the engine until the 2-second watchdog fires. A
short vector survives that — `r01` finishes, the engine recovers, and the
follow-up decode is bit-exact. A long one does not: `r02` (H.264, 150 frames)
put the board into the state where ssh answers but no command completes, and
only a **power cycle** recovers it.

That is the same robustness gap recorded in
[`decode-production-readiness.md`](decode-production-readiness.md): repeated
stalls, or a client dying mid-decode, take the video engine down for every
client. It is the bug worth fixing next, and fixing it would make this one
merely annoying instead of expensive to investigate.

## Where that leaves things

- **`r01`/`r02` and `decode-reinit-test.sh` stay** as a regression test for a
  known-failing case, with the attribution recorded here.
- **`WIP-0007` stays out of `series`.** It is more correct than a process-wide
  latch and fixes nothing observable, which by this project's own standard is
  not a shipping change.
- **Iterate on `r01`, never `r02`**, if this is picked up again: one fails
  safely and the other costs physical access to the board.
