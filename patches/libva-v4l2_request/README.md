# libva-v4l2_request patches (megi's driver)

The VA-API driver that lets **stock** mpv, ffmpeg and GStreamer `va*dec` decode
on the H713's VE (cedrus) and its AV1 core (hantro). Since 2026-10-03 it is
**megi's driver plus this series**. It replaced bootlin's PR #38 and our 25
patches on top of it ([`../libva-v4l2-request/`](../libva-v4l2-request/README.md),
retired). The decision was WP3 of [the GPU fallback plan](../../docs/gpu-fallback-plan.md).

## Base

| | |
|---|---|
| upstream | <https://xff.cz/git/libva-v4l2_request/> (Ondrej Jirman) |
| pinned base | `cac6ece0e23ac1f944dd3af266680aff0c3184df` (v1.2 + one README commit) |
| license | **GPL-3.0-or-later** (the bootlin driver was MIT) |
| build | `tools/video/build-va-driver.sh --install --test`, on the board, as before |

Not a fork of bootlin's code. It is a 10k-line rewrite that already does most of
what our bootlin series added: every decoder on every media node, MPEG-2/H.264/
HEVC/VP8/VP9/AV1, contexts created before their surfaces, a stable dma-buf per
surface, lazy CAPTURE setup after the codec controls (so cedrus sees the HEVC
bit depth first), and a 10-bit probe for HEVC.

## Why switch rather than keep porting

Measured on the board, megi v1.2 **as shipped** against our 25-patch driver,
with `tools/video/va-regress.sh`:

| | ours (25) | megi as shipped | megi + this series |
|---|---|---|---|
| H.264 ×5, HEVC H1 14/14 (scaling lists, Main10, unaligned pitch), MPEG-2 ×5 incl. field-coded, VP9 ×3, seek loops ×4, 3 concurrent clients | pass | **pass** | pass |
| AV1 8-bit ×5 | pass | SIGSEGV / wrong frames | pass, bit-exact |
| AV1 10-bit (310 frames) | pass | refused | pass, bit-exact |
| resolution change ×3 | pass | SIGSEGV | pass, bit-exact |

Nine patches here against twenty-five there, on a maintained base that tracks
GStreamer `va` and the modern uAPI. The bugs in 0001 and 0003 are megi's own
and not H713-specific; they are worth reporting to him (this project does not
push upstream).

## The patches

| # | What | Why |
|---|------|-----|
| 0001 | A per-context lock around Begin/Render/EndPicture and the held-frame flush | AV1 defers each frame by one. FFmpeg 7.1 reads frame N on the filter thread while the decoder thread submits it. The reader fell through to the throwaway standalone backing, which the bind then `munmap`ed under the copy: SIGSEGV on 5/5 clips, garbage when it did not crash |
| 0002 | `PL10`, the AV1 core's LSB-aligned P010 | The only 10-bit format the core offers (kernel 0150). It exports as P010 + `DRM_FORMAT_MOD_ALLWINNER_LSB10`, DeriveImage refuses it, and Get/PutImage shift ×64 |
| 0003 | Decoded frames outlive their context | FFmpeg destroys the context on a resolution change while frames are still queued. DestroyContext now drains, then hands each decoded CAPTURE buffer to its surface as standalone backing (fds and mapping move over; vb2 keeps the memory alive). An rwlock keeps readers out meanwhile. This replaces bootlin 0018/0019; no DMA-BUF heap is needed |
| 0004 | Count `V4L2_BUF_FLAG_ERROR`; AV1 refuses non-key frames after an error | The SoC hang: one damaged AV1 key frame through VA-API hung the board (bootlin 0016 had the same gate). Conservative, because errors surface a frame or two late |
| 0005 | `V4L2_REQUEST_SCALE` / `V4L2_REQUEST_CROP`, and a 64-byte NV12 pitch | The VE decode-time scaler (bootlin 0008/0010) and Panfrost's import alignment (bootlin 0020), all in the one CAPTURE `S_FMT` |
| 0006 | Advertise VP9 Profile 2 only if a 10-bit frame control is accepted | cedrus is Profile 0 only. Needs **kernel 0155**, which makes cedrus refuse the control; without it the probe says yes, as before |
| 0007 | Decode into the dma-bufs a client exported before the first decode | GStreamer `va`'s dma-buf allocator creates and exports each surface in one step and keeps the fds. megi treated such exports as probing and decoded elsewhere: **every `va*dec` DMABuf consumer (kmssink, glimagesink) showed solid green** at a steady 30 fps. The CAPTURE queue now imports those dma-bufs when the first export fits the decode format (FFmpeg's AV1 probe does not, and keeps MMAP). The export-time layout honours `V4L2_REQUEST_SCALE`, which is what makes WP4's VE-scaled `kmssink` route possible |
| 0008 | `V4L2_REQUEST_LSB10_LINEAR=1` exports the AV1 core's LSB-aligned P010 as linear P010; a bare P010 surface falls back to PL10 backing | GL cannot import the LSB10 modifier, so mpv's interop probe refused P010 and 10-bit AV1 and HEVC never reached `vo=gpu` (it wanted a `scale_vaapi` conversion the driver lacks). With the opt-in, 10-bit AV1 plays in hardware with `tools/video/shaders/lsb10.glsl` (×64): 47.0 / 46.2 dB against software, 0 dropped at 1080p, ~40% GPU with `--fbo-format=rgb10_a2`. HEVC Main10 passes the probe too; cedrus delivers 8-bit NV12 there, so it needs no shader (48.8 dB). Unset, exports are unchanged (KMS keeps LSB10). `tools/video/h713-play` sets it |
| 0009 | Exports report the surface's own size, capped by the buffer, not the padded buffer size | 1080p HEVC/VP9/AV1 surfaces created as 1920x1080 were described as 1920x1088 (the decoders pad), so a consumer sizing a framebuffer from the descriptor showed 8 padding rows. Planes still follow the buffer, so the chroma offset keeps 1088. H.264 stays 1088 (FFmpeg creates it so); VE-scaled surfaces report 1280x720. GPU-path frames match software decode bit for bit (HEVC, VP9, AV1 1080p); GStreamer DMABuf stays bit-exact |

## Where each bootlin patch went

| bootlin | Fate |
|---|---|
| 0001–0003 (build fixes, advertise only what works, bitstream buffer) | not needed: megi probes per profile and sizes its own OUTPUT buffers |
| 0004–0006 (HEVC port, scaling matrix, Main10) | native |
| 0007 (probe buffers), 0009 (queues outlive surfaces across seeks) | native (standalone backing; loop gate passes) |
| 0008, 0010 (scaler, crop) | **0005** |
| 0011 (MPEG-2), 0013 (VP8), 0014 (multi-device), 0015 (VP9) | native |
| 0012 (report decode errors to the client) | **partial**: 0004 counts and logs them, but only AV1 acts. Other codecs still hand a damaged frame over as good |
| 0016 (AV1) | native, plus **0001** (race) and **0004** (gate) |
| 0017 (LSB P010) | **0002** |
| 0018, 0019 (DMA-BUF heap capture, renegotiation) | **0003**, without the heap |
| 0020 (64-byte pitch) | **0005** |
| 0021–0025 (GStreamer `va`) | native |

## Verification of 0007 (2026-10-03)

- `va-regress.sh`: 0 failing lines. FFmpeg now decodes H.264, HEVC, VP9 and
  MPEG-2 into imported dma-bufs (its probe export fits) and AV1 into MMAP, so
  the suite covers both modes bit-exact. A first version chose DMABUF for any
  pre-decode export and broke all AV1 (0/5 frames); the fit test came from that.
- GStreamer `va*dec` → DMABuf → `gst-dmabuf-dump`, against FFmpeg software:
  H.264 ×5 and HEVC ×4 (incl. 1080p, 656x480, 640x482) bit-exact, every frame.
- Stock mpv `--vo=gpu` (H.264 1080p, VP9 1080p, 852x480): identical drops, GPU
  load and clocks to 0001–0006.
- WP4's plane routes on the panel: see the WP4 section of the plan.

## Verification (2026-10-03)

- `va-regress.sh`: 0 failing lines, both side by side and as installed. The
  `mmap` mode belonged to bootlin 0018 and means nothing here: megi always uses
  MMAP capture.
- VP8, which `va-regress.sh` does not cover: all six vectors (every profile,
  multi-partition) bit-exact per frame against software through `ffmpeg
  -hwaccel vaapi`, 150/150 frames.
- Scaler: byte-identical to the bootlin driver for H.264 and HEVC 1080p at
  1280x720, 1280x720 with a 1920x1080 crop, and 852x480 (pitch 896). Captured
  with a scratch `LD_PRELOAD` that exports each surface after `vaEndPicture`.
- GPU path (stock `mpv --vo=gpu`, `gpu-path-measure.sh`, 15 s each): H.264
  1080p/720p/852x480/352x288, HEVC 1080p, VP9 720p and AV1 1080p all `hwdec=vaapi`,
  same drops, GPU load and clocks as the bootlin driver.
- Damaged AV1 through VA-API: 12/12 survived, the good clip bit-exact after
  each, no hang. The gate fired on the broken-key-frame streams.
- VP9 Profile 2: before 0006/0155, VA-API was chosen and every frame failed.
  Now it is not advertised, so ffmpeg decodes in software.

## Known differences and gaps

- ~~**Unscaled exports report the padded CAPTURE height**~~ fixed by 0009: the
  descriptor reports the created size (1920x1080 for HEVC/VP9/AV1 1080p).
- **AV1 10-bit on the GL path:** solved by 0008 plus the client's ×64 shader.
  The opt-in is per process; a client that sets it but not the shader shows a
  picture 64 times too dark.
- **Decode errors** reach no client except through the AV1 gate (see 0012 above).
- GStreamer `va*dec`: identical results on both drivers for the clips tried (VP9
  bit-exact). The H.264/HEVC/AV1-10 clips that fail do so on both, so that is
  open as a harness or clip question, not a driver one. **Answered for H.264
  (2026-10-03):** a harness question. `gst-dmabuf-dump`'s appsink queued
  without bound, GStreamer allocated a surface per queued frame, and decodes
  past the driver's 32 CAPTURE buffers failed. Bounded, all five H.264
  vectors are 60/60 bit-exact.
- **GStreamer `va*dec` into DMABuf caps was showing green, not video** (fixed by
  0007). The WP3 checks read frames back through system memory, the one path
  that was right.
- **32 CAPTURE buffers per context, hard.** A client that holds more decoded
  frames than that alive at once gets decode failures, not back-pressure.
- **GStreamer `va` AV1 into DMABuf caps still shows nothing**: its pre-decode
  export (cedrus-shaped) never fits the AV1 core's padded layout. WP4 sends AV1
  on the plane through `v4l2slav1dec` instead, and to the GPU through mpv.
