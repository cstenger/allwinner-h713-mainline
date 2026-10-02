> **Scaler integration next (2026-09-17):** Cedrus now supports arbitrary even
> NV12 CAPTURE dimensions for H.264/HEVC, with full-size private reconstruction.
> This VA shim does not yet negotiate and propagate those scaled surfaces for
> playback. Preserve coded SPS/DPB geometry and early Main10 declaration. See
> [the current handoff](../../docs/handoff-2026-09-17-shared-scaler.md).

# libva-v4l2-request patches

The VA-API driver that lets **stock** mpv and ffmpeg decode on the H713's VE.
It is a translator, not a decoder: ffmpeg parses the bitstream and hands over
picture and slice parameters, and this shim converts them into V4L2 Request API
controls for cedrus. Nothing upstream of it is patched — that is the whole
point of choosing this route (see [../../docs/vaapi-scope.md](../../docs/vaapi-scope.md)).

## Base

| | |
|---|---|
| upstream | <https://github.com/bootlin/libva-v4l2-request> |
| branch | **PR #38**, `refs/pull/38/head` — *not* `master` |
| pinned base | `1c5f2cad21dff3b56d35355082867c24e4f191c6` ("Don't advertise broken profiles") |
| license | MIT |

`master` is a red herring: its last commit is 2019-05-17 and it uses the
pre-stabilization `V4L2_CID_MPEG_VIDEO_H264_*` controls, whose structs no
longer match the 6.18 uAPI. **PR #38 already did that port** — it uses all
eight `V4L2_CID_STATELESS_H264_*` controls, precisely the set cedrus registers,
and assumes slice-based decode, which is the only mode cedrus offers.

Getting the tree:

```
git clone https://github.com/bootlin/libva-v4l2-request
git -C libva-v4l2-request fetch origin refs/pull/38/head:pr38
git -C libva-v4l2-request checkout pr38
tools/video/build-va-driver.sh --install --test
```

The build script applies exactly the filenames listed in `series`; the
directory also contains explicitly out-of-series investigation patches that a
wildcard must not apply.

Build it **on the board**, not on the host. The driver's entry-point symbol is
`__vaDriverInit_<major>_<minor>` derived from the *libva pkg-config version* at
build time, so a host build against libva 1.24 produces a `.so` that the
board's libva 1.22 loader will not call.

## The patches

| # | What | Why |
|---|------|-----|
| 0001 | `#include "utils.h"` in `h264.c` | `request_log()` is called but never declared; implicit declarations have been an error since GCC 14 |
| 0002 | Build H.264 only; advertise only what `RequestCreateConfig` accepts | see below |
| 0003 | Create the bitstream buffer with the surface, not with the context | the one that actually blocked decoding — see below |
| 0004 | Port HEVC: PR #44's `h265.c` on this base, plus the four sites it needs | HEVC on the stabilized uAPI. Neither upstream PR decodes here alone: #38 has the format ordering cedrus requires, #44 has the modern port |
| 0005 | `h265`: pass the scaling matrix | `V4L2_CID_STATELESS_HEVC_SCALING_MATRIX` was never set by *either* upstream tree, so any stream with `scaling_list_enabled_flag = 1` decoded against flat matrices — see below |
| 0006 | Advertise HEVC Main10, and declare the bit depth before capture buffers exist | Main10 was refused outright; now it decodes on the engine (`ve+10`, 57 dB PSNR, byte-identical to GStreamer). Output is 8-bit — see [`docs/hevc-10bit-findings.md`](../../docs/hevc-10bit-findings.md) |
| 0007 | Release throwaway interop buffers and track the programmed queue format | mpv probes with 128x128 surfaces before creating 1280x720 decoder surfaces; leaked V4L2 allocations made Cedrus read beyond a 24 KiB buffer and fault. Also accommodates libavutil's 16x16 helper surface while the decoder queue is streaming |

Patch 0002 does two things that look separate and are not:

- **The bundled `include/hevc-ctrls.h` is deleted.** It is a 2019 snapshot of
  HEVC controls that have since been stabilized into `linux/v4l2-controls.h`,
  so every file including it redefines five structs the kernel headers already
  define — 5 errors across three files. `h265.c` cannot simply use the new
  definitions either: PR #38 ported H.264 and left HEVC on the old uAPI, using
  3 of the 8 controls cedrus registers. So `h265.c` drops out of the build and
  stays in the tree as the starting point for that port, which
  `docs/vaapi-scope.md` costs at ~400 lines with a reference-picture-set
  restructure.
- **`RequestQueryConfigProfiles` no longer advertises MPEG-2 or HEVC.**
  `RequestCreateConfig` already refuses both, so advertising them made `vainfo`
  report profiles that fail at `vaCreateConfig` — and `vainfo` is exactly the
  tool used to decide whether this driver works at all.

Patch 0003 is the one that mattered, and it is a good example of a failure that
points at the wrong half of the system. The symptom was

```
v4l2-request: Unable to enable stream: Invalid argument
[h264] Failed to create decode context: 1 (operation failed).
```

which reads as a codec problem. `strace` says otherwise:

```
VIDIOC_CREATE_BUFS {count=0, type=VIDEO_OUTPUT} = 0 ({count=0})
VIDIOC_STREAMON [V4L2_BUF_TYPE_VIDEO_OUTPUT] = -1 EINVAL
```

The shim sized the bitstream queue from the render targets handed to
`vaCreateContext`. ffmpeg allocates VA surfaces on demand and hands over none,
so the queue was created empty and `STREAMON` was correctly refused. The buffer
now belongs to the surface, which is where the OUTPUT format was already being
set for the same underlying reason.

Patch 0005 is worth reading for how it was found rather than for its size. The
control was simply never set — by either upstream tree, which corrects patch
0004's "#44 dropped the iqmatrix handling": PR #38's own pre-#44 `h265.c`
mentions `iqmatrix` three times, all in the declaration block of
`h265_set_controls()`, and then sets three controls that do not include a
scaling matrix. #44 merely removed the unused declarations. And **the gate
could not see that**: h01, h02 and
h03 all have `scaling_list_enabled_flag = 0`, and cedrus writes its scaling-list
SRAM only when that SPS flag is set, so a driver that fills nothing at all
scores bit-exact on all three. Two vectors were added to close the blind spot
(`h04`, implicit HEVC default lists; `h05`, explicit custom lists that are
non-flat at 4x4 and whose DC coefficients differ from their own matrix), and
they showed `MISMATCH (va) ve+25` — the engine decoding all 25 frames, to the
wrong answer — before the fix and bit-exact after it.

No scan conversion is needed, which is the opposite of what the bitstream syntax
suggests. HEVC codes scaling lists in up-right diagonal order, but **both APIs
specify raster**: `va_dec_hevc.h` says "Matrix entries are in raster scan order
which follows HEVC spec" and the V4L2 control's kernel doc says "expected in
raster scan order". ffmpeg's parser already undoes the scan
(`scaling_list_data()` in `libavcodec/hevc/ps.c` stores at the raster position;
`vaapi_hevc.c` copies across unchanged), so the shim's job is a straight copy.
`h05` is the evidence — its lists are non-flat at every size, so a wrong
permutation could not have come out bit-exact.

Patch 0007 fixes a lifetime mismatch between VA surfaces and their V4L2
backing allocations. `vaDestroySurfaces` freed the VA objects and mappings but
left every `CREATE_BUFS` allocation alive, while a process-global boolean kept
the first coded format forever. mpv's 128x128 VA/EGL interoperability probe
therefore poisoned the later 1280x720 decoder allocation. The first decode
request queued correctly, then the VE crossed the end of the undersized buffer,
raised a master-0 IOMMU read fault, and timed out.

The fix releases both queues when the last pre-context surface disappears and
tracks the actual programmed pixel format and geometry. Once a context is
streaming, small auxiliary VA surfaces use its active backing geometry because
a V4L2 mem2mem queue cannot be reformatted in flight. That last case is needed
for libavutil's 16x16 upload probe; otherwise decode works but mpv falls back to
a CPU hwdownload during filter negotiation.

## Status — validated on hardware 2026-08-16

`vainfo` loads the driver (`__vaDriverInit_1_22`) and advertises the five H.264
profiles with `VAEntrypointVLD`. All five vectors of the M1 ladder decode
**bit-exact** against the host-generated references, through stock ffmpeg with
no patches to it:

| vector | result |
|---|---|
| `v01-320x240-baseline` (8 frames) | bit-exact |
| `v02-1280x720-baseline` (60) | bit-exact |
| `v03-1280x720-main` (60) | bit-exact |
| `v04-1280x720-high` (60) | bit-exact |
| `v05-1920x1080-high` (60) | bit-exact |

The VE's interrupt count rose by exactly 60 across a 60-frame decode, so the
hardware did the work — decode-only cost **1.233 s wall / 0.637 s CPU** for
60 frames of 1080p, against 2.72 s of CPU for the software decoder.

One measurement worth carrying forward: adding `hwdownload` to copy those
frames back to system memory costs *more* than the decode does (1.8 s extra for
186 MB), because V4L2 MMAP buffers are uncached. That is a cost of
decode-to-file validation, not of playback — a display path that maps the
surface as a dma-buf never pays it.

Reproduce with [`tools/video/va-decode-test.sh`](../../tools/video/va-decode-test.sh),
which scores a software control first so a hardware mismatch cannot be confused
with a broken yardstick.

## HEVC — validated on hardware 2026-08-22

`vainfo` additionally advertises `VAProfileHEVCMain` with `VAEntrypointVLD`, and
every HEVC vector decodes **bit-exact** through stock ffmpeg, with the GStreamer
oracle scoring the same 5/5 on the same run:

| vector | what it adds | result |
|---|---|---|
| `h01-640x480-main` (25 frames) | HEVC Main, WPP on | bit-exact |
| `h02-1280x720-main` (25) | panel-native size | bit-exact |
| `h03-640x480-nowpp` (25) | WPP off | bit-exact |
| `h04-640x480-scaling` (25) | scaling lists, implicit defaults | bit-exact |
| `h05-640x480-scaling-custom` (25) | explicit custom lists + DC coefficients | bit-exact |

Reproduce with [`tools/video/hevc-decode-test.sh`](../../tools/video/hevc-decode-test.sh).
The H.264 ladder is unregressed at 5/5 in the same session.

Main10 reaches the engine, but the exported surface is its 8-bit component
because mainline cedrus exposes no capture fourcc for Allwinner's separate
8-bit-plus-2-bit layout. The two inert PPS flag bits noted in patch 0004 are
still wrong. Tiles, `transquant_bypass` and long-term references have no vector
yet.

## Zero-copy mpv — validated on hardware 2026-09-03

With patch 0007's functional change installed, stock mpv used VA decode and
passed the decoded dma-bufs directly to the Panfrost GPU:

```text
Using hardware decoding (vaapi).
VO: [gpu] 1280x720 vaapi[nv12]
```

A 20-second paced loop displayed moving video and completed 300 capture
QBUF/DQBUF cycles with no decode failure or hwdownload. An independent
300-frame untimed run produced the same 300/300 balance and no new IOMMU fault
or Cedrus timeout. See
[`docs/handoff-2026-09-03-video-decode.md`](../../docs/handoff-2026-09-03-video-decode.md)
for the trace that distinguishes the root cause from the discarded surface
state and request-fd hypotheses.

## Decode errors reach the client — validated on hardware 2026-09-22

Patch 0012. The kernel flags a badly decoded picture with `V4L2_BUF_FLAG_ERROR`
on its CAPTURE buffer, and cedrus carries that flag across the jobs sharing a
held buffer specifically so it survives to the dequeue. This shim read the
dequeue's return value and nothing else, so the flag died here and a
half-decoded frame reached the client marked good.

**Which VA-API channel** is the whole question, and `nm` answers it. ffmpeg's
`libavcodec` and `libavutil` import `vaSyncSurface` and **neither
`vaQuerySurfaceStatus` nor `vaQuerySurfaceError`** — so recording the failure in
`VASurfaceStatus` (which has no value meaning "damaged" anyway) would have been
a fix no client could see, the same shape of mistake as advertising a VA profile
without its entrypoints. `VA_STATUS_ERROR_DECODING_ERROR` is what va.h specifies
and what ffmpeg reads.

It arrives via `vaEndPicture`, not `vaSyncSurface`: decode here is synchronous,
so `RequestEndPicture` returns what `RequestSyncSurface` returns and
`ff_vaapi_decode_issue()` checks exactly that. The map-time `vaSyncSurface` that
`libavutil` calls keeps returning success on purpose — failing there would break
`av_hwframe_transfer_data()` for a picture libavcodec had already accepted.

| stream | software decoder | VA-API before | VA-API after |
|---|---|---|---|
| `field-shortfirst.m2v` (truncated) | `ac-tex damaged` ×2 | silent | 2 errors |
| `field-firstfield-damaged.m2v` (truncated) | `ac-tex damaged` | silent | 2 errors |
| `field.m2v` | `ac-tex damaged` ×1 | silent | 1 error |
| `testcard-mpeg2.m2v`, `testcard-mpeg2i.m2v` | clean | clean | clean |

The counts track the damage rather than merely being non-zero — one file reports
one error and another reports two — and they match `strace`, which shows 2 of 62
CAPTURE dequeues flagged on `field-shortfirst.m2v`.

ffmpeg logs `Failed to end picture decode issue: 23 (internal decoding error)`
and `hardware accelerator failed to decode picture`, then **carries on**: exit
status 0, the rest of the stream decodes. The damaged pictures are dropped
rather than emitted, so hardware output is two frames shorter than software's,
which emits them flagged `AV_FRAME_FLAG_CORRUPT`. There is no third option —
ffmpeg's hwaccel path has no way to accept a frame and mark it corrupt.

No regressions: H.264 5/5 and HEVC 6/6 still bit-exact, Main10 57.07 dB and
byte-identical to the GStreamer oracle, robustness 16/16 with the engine
recovering from every malformed input, and a clean MPEG-2, H.264, HEVC or Main10
stream reports zero errors.

## VP9 and AV1 — validated on hardware 2026-09-30

Patches 0014–0016. The H713 has **two** stateless decoders: cedrus
(`/dev/video0`, MPEG-2/H.264/HEVC/VP8/VP9) and a separate Google AV1 core behind
hantro (`/dev/video1` + `/dev/media1`, multi-planar API).

| # | What | Why |
|---|------|-----|
| 0014 | Drive more than one decoder device | every stateless decoder is found at init (media device paired through sysfs); a config picks the first device offering its format; per-device queue state is swapped in by `request_use_device()` at each entry point; "release the queues when nothing refers to them" is asked per device |
| 0015 | VP9 backend | VA-API's VP9 parameters are a digest meant for decoders that parse headers in hardware, so the backend parses the uncompressed header and (through the boolean decoder) the compressed header itself; VA-API's two header sizes are a cross-check of the parse |
| 0016 | AV1 backend | a translation (VA-API carries nearly the whole header); per-surface order hints, derived skip mode and tile_size_bytes; film grain displays through `current_display_picture`; multi-planar NV12; AV1 advertises its device's real size range (4K); DRM PRIME export gives the picture size, not hantro's padded allocation; after a decode error, frames are refused until the next key frame |

Results (ffmpeg `-hwaccel vaapi` against libvpx/libdav1d, per-frame MD5,
interrupts ≥ frames — `tools/video/va-gate.sh`):

- **AV1:** 15/15 basic streams, 35/37 of the coding-tool matrix
  (`tools/video/make-av1-streams.sh`), 4K, soaks of 900/1199/2318 frames, seeks.
  Monochrome is refused by ffmpeg itself (no hardware path for 4:0:0); the two
  reference-scaling clips are the resolution-change limitation below.
- **VP9:** 12/13 vectors plus a 900-frame clip. `v13-resize` changes size on an
  **inter** frame (scaled references); cedrus cannot, and now refuses those
  frames (kernel 0143) instead of reading past its buffers.
- **Panel:** mpv `--vo=drm --hwdec=vaapi` plays both; the video plane takes a new
  framebuffer every frame, zero failed flips, A-V 0.000. Before the export fix
  every AV1 flip failed with EINVAL: hantro pads 720 lines to 768 and the H713
  plane takes exactly 1280x720.
- **Damaged streams:** 12 damaged AV1 streams survive with the engine healthy
  after each. Before the error gate one of them **hung the SoC** through
  VA-API but not through GStreamer: ffmpeg abandons the rest of a temporal unit
  when one frame fails, but has already parsed all of it, so the headers it
  sends afterwards are read against reference state that does not match what
  was decoded. Established by tracing both paths on the same frames
  (`local/h713-lab/av1-work/wedge/`).
- No regressions: VA1 5/5, H1 14/14, P1 12/12, M2 6/6.

**Was open:** a mid-stream resolution change failed at `S_FMT` (EBUSY) while
old surfaces existed. Fixed for VP9 and HEVC by 0018/0019 below; AV1 is
ffmpeg's.

## DMA-BUF capture and mid-stream renegotiation — validated on hardware 2026-10-01

| # | What | Why |
|---|------|-----|
| 0018 | Allocate capture buffers from a DMA-BUF heap | each surface owns its pixels: a `/dev/dma_heap/system` buffer queued as `V4L2_MEMORY_DMABUF` (same fd, same index, every time), exported by `dup()`, read back inside `DMA_BUF_IOCTL_SYNC`. MMAP stays as the fallback; `V4L2_REQUEST_CAPTURE_MEMORY=mmap\|dmabuf` forces either, and the choice is logged (`Capture memory: ...`) |
| 0019 | Renegotiate while old surfaces are still referenced | with DMABUF capture, new-geometry surfaces release both queues and bump a per-device generation instead of meeting EBUSY; retired surfaces stay readable and exportable, are refused as decode targets, and no longer keep the device in use. Readback lays images out per surface and copies row by row across pitches. `RequestDestroySurfaces` no longer leaves another decoder active (that broke HEVC's frame threads once surfaces were destroyed mid-stream). One recursive driver-wide lock around every stateful entry point: ffmpeg's filter thread could otherwise read back an old frame while the decode thread re-set the format (1 `vp9-rc` run in 4 failed `vaCreateImage`) |

Needs kernel 0151 (cedrus maps capture buffers read-write; without it the
first inter frame faults on its reference) and the DMA-BUF heaps in the
defconfig. Measured with ffmpeg 7.1.5 and mpv 0.40.0:

- **Resolution changes through VA-API:** `vp9-rc.ivf` (640x360 → 720p →
  352x288 → 640x360) **210/210** frames bit-exact against libvpx, VE +210;
  HEVC `r01` (640x480 → 320x240 → 640x480) **75/75**, VE +75; H.264 `r02`
  (1280x720 → 320x240 → 1280x720) **150/150**, VE +150. mpv
  (`--hwdec=vaapi-copy`) stays on hardware through every change. Before:
  60/210 and 25/75, then software.
- **AV1 is not fixed, and cannot be from here:** libavcodec's AV1 decoder keeps
  its hwaccel across a new sequence header whenever the hardware pixel format is
  still offered, for size and (in 7.1) depth changes, so it never asks for new
  surfaces. See [`docs/hevc-resolution-change.md`](../../docs/hevc-resolution-change.md).
- **No regressions, in both memory modes:** VA gate 7/7 (5 AV1, 2 VP9), 10-bit
  AV1 10/10 and 300/300 frames against libdav1d, H.264 5/5, HEVC H1 14/14,
  MPEG-2 5/5 against GStreamer, loops stay on hardware for all four codecs,
  concurrency 15/15. In-process fds, live dma-bufs and RSS flat over a 30 s loop.
- **Soak, 45 min, DMABUF:** `soak-decode.sh` 1946/1946 iterations bit-exact
  (68,912 frames on the VE, no fallbacks, no timeouts, CmaFree unchanged), and a
  parallel 10-bit AV1 VA loop 249 iterations, all identical. No IOVA or IOMMU
  messages -- the `ve_scanout_iova` failure seen after ~35 min did not recur.


## GPU import pitch — validated on hardware 2026-10-02

| # | Patch | What it does |
|---|---|---|
| 0020 | Request a 64-byte capture pitch so the GPU can import the frame | NV12/NV21 CAPTURE formats ask for `bytesperline = ALIGN(width, 64)`. Panfrost (Bifrost v7) rejects any linear R8/GR88 plane import whose pitch or offset is not 64-aligned, which is how mpv and GStreamer bring NV12 into GL. That is the same in Mesa 25.0.7 and 26.1.6. cedrus's default `ALIGN(width, 32)` therefore put nothing on screen for 352, 720 or 852 wide streams on stock `mpv --vo=gpu --hwdec=vaapi`; mpv then stalled past `--end` |

**Needs kernel 0154.** The VP9 engine reads references at a pitch it derives
from the width (field `LAST_SCALE1 [30:28]`), not the programmed stride. With
0020 and without 0154, every VP9 inter frame at a width that is not 64-aligned
is wrong. The VA gate caught it in the `vp9-rc` resolution-change vector and
now carries `v10-odd-350x286` so it cannot recur silently.

Measured per frame against software decode:
- H.264 852x480 and 352x288: 90/90 each.
- HEVC h10-656x480: 25/25.
- VP9, all 13 vectors v01–v13: bit-exact.
- Full gate in both memory modes: 0 failing lines.
- Stock mpv `--vo=gpu --hwdec=vaapi`: 852x480, 352x288 and 720x576 import with
  no `rejecting image` errors.

## GStreamer `va` elements — 2026-10-02

These are the first patches to target GStreamer's `va` decoders rather than
ffmpeg. Before them, every `va*dec` pipeline failed. GStreamer also needs
`GST_VA_ALL_DRIVERS=1`: it registers `va` elements only for allow-listed
drivers. That is an environment variable, not a patch.

| # | Patch | What it does |
|---|---|---|
| 0021 | Allow a context before its surfaces | GStreamer creates its context with no render targets, before any surface. The context now starts unstreamed and starts its queues at the first BeginPicture |
| 0022 | Serve a surface created before any config | GStreamer's dma-buf probe creates and exports a 64x64 NV12 surface with no config. It is now served from the first H.264 decoder instead of failing |
| 0023 | Honour `VA_EXPORT_SURFACE_SEPARATE_LAYERS` | Export NV12 as R8 + GR88 (P010 as R16 + GR1616), one layer per plane, when asked. GStreamer's probe rejects a single composed layer, and without this `va*dec` offered GL system memory only |

Result, with `va*dec ! glimagesink` on GBM, 30 s per clip:
- H.264 at 720p, 1080p and 852x480: zero-copy (`memory:DMABuf`, NV12), 0
  dropped, 5–7% CPU.
- AV1 at 720p and 1080p: the same, with 0–1 dropped.

**Known gap: `vah265dec` does not decode.** `vaEndPicture` returns
`DECODING_ERROR` with zero VE interrupts and nothing in the kernel log.
GStreamer's HEVC submission differs from ffmpeg's somewhere this driver
does not handle. `v4l2slh265dec` (stock GStreamer, straight to the kernel)
decodes HEVC zero-copy into GL with 0 drops, so HEVC on GStreamer is
covered. Deferred to WP3: megi's `libva-v4l2_request` claims GStreamer
`va` compatibility tested on cedrus.

Also not registered: `vavp9dec` and `vavp8dec`. GStreamer registers no VP9
or VP8 `va` element, although the driver advertises VP9 Profile 0. Not
investigated; `v4l2slvp9dec` covers VP9.
