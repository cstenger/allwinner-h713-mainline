# Hardware first, GPU fallback, stock applications — plan (2026-10-02)

## Why

The 2026-10-01 stock capture
([reference/stock-capture-2026-10-01.md](reference/stock-capture-2026-10-01.md))
settled what the vendor does:
- **On the GPU:** downscaling at 1080p (every codec, AV1 included), upscaling, letterboxing, rotation and keystone.
- **In hardware, only two things:** the VE scaler for sources *above* 1080p, and the installation-mode mirror.

Our stack already uses every scaling block the silicon has. Without a GPU it
cannot do:
- 1080p AV1;
- rotation for VP9/HEVC/AV1;
- letterboxing and keystone;
- OSD or subtitles over video (the video and OSD planes switch; they don't blend).

**Decisions (operator, 2026-10-01).** These replace "the GPU is the last resort":
- Use the specialised hardware first and the GPU as the fallback.
- Build the GPU fallback first.
- Letterboxing goes through the GPU now; [letterbox-plan.md](letterbox-plan.md) becomes a later optimisation.
- Aim for **stock applications (mpv, ffmpeg, GStreamer) on our drivers** (kernel and VA driver), with no application patches.

## Goal: stock applications, our drivers

- **mpv.** Patches 0001-0004 exist only for the no-GPU direct path:
  - `vo=drm` scanning VA frames onto the video plane;
  - PRIME frames being dropped;
  - refusing a source that isn't the mode size;
  - asking the VE to shrink.

  Debian's `/usr/bin/mpv --vo=gpu|gpu-next --hwdec=vaapi` works unpatched, but **only on a kernel with 0092** (a render node on the display device). That patch was out of series until 2026-10-02; without it stock mpv silently decodes in software. Odd widths also need libva 0020 plus kernel 0154 (see WP2 findings below).
  - The VE pre-shrink moves to a launcher, using libva's scale/crop environment (libva 0008/0010).
  - 10-bit AV1 moves into the VA driver plus a stock-mpv `--glsl-shader`.
  - Stock mpv cannot do the GPU-free direct path until FFmpeg's v4l2-request hwaccel and mpv's `v4l2request-overlay` land (see the watch list).
- **ffmpeg.** Already stock; there is no `patches/ffmpeg`.
- **GStreamer.** `patches/gstreamer` 0001-0003 serve only `v4l2codecs → kmssink`. The stock GPU path is `v4l2sl*dec` or `va*dec ! glimagesink`, and it needs Debian's `gstreamer1.0-gl`.
  - 10-bit AV1 goes through `vaav1dec`, a linear-P010 export and the stock `glshader` element.
  - GStreamer's `va` elements have never been tried against our VA driver.
- **Decision rule.** If measurement shows the direct path is not worth its cost, retire `patches/mpv` and `patches/gstreamer`. If it is worth it, keep them as an opt-in "direct" mode until the upstream v4l2-request path makes them unnecessary.

## Routing

| Content | Path |
| --- | --- |
| Any codec, exactly 1280x720 | Direct video plane (patched `vo=drm`) *if* the GPU path costs enough to matter; otherwise stock `vo=gpu` |
| H.264 / HEVC above 720p | **Hardware**: VE TOP1 pre-shrink (aspect-fit); then direct if exactly 1280x720, otherwise GPU |
| VP9 above 720p | GPU now; VE pre-shrink once ported |
| AV1 above 720p | **GPU** (no hardware exists; stock agrees) |
| Below 720p, non-16:9, letterbox | **GPU**; hardware letterbox later |
| Rotation (any codec) | **GPU**; 180° later via the hardware H+V mirror |
| Subtitles / OSD over video | **GPU** |
| Rear/ceiling projection | **Hardware** mirror, on both paths |
| Keystone | **GPU**, later |

Where the VE can shrink first, it does, so the GPU (a Mali-G31 **MP1**, one
shader core) does as little as possible.

## Vulkan Video: no

Recommendation: **do not implement it.** Revisit only if a consumer we need speaks only Vulkan Video.

- **No consumer gain.** Applications decode through VA-API or V4L2 and hand dma-bufs to GL. That is proven zero-copy here (`tools/video/gles-play.c`, 59.7 fps). The GPU's job is post-processing, which GLES 3.1 already covers.
- **No foundation.**
  - PanVK on Bifrost v7 still needs `PAN_I_WANT_A_BROKEN_VULKAN_DRIVER=1`, and it reports Vulkan 1.0 until Mesa 26.3 (about 2026-11-04). libplacebo needs 1.2.
  - No Mesa driver implements Vulkan Video on top of V4L2 stateless decoders, and there is no merge request for one. Only RADV and ANV decode (NVK H.264 is in progress).
- **Cost.** It would mean video queues in PanVK, translating the std parameter sets into cedrus/hantro controls for five codecs, and cross-device DPB and synchronisation. That is months of work duplicating the VA driver.
- **It is not the route to stock mpv.** GL already gets there. `--gpu-api=vulkan` only changes the renderer, and `--hwdec=vulkan` would replace VA-API, which works.
- **Revisit after Mesa 26.3:** try `vo=gpu-next --gpu-api=vulkan --hwdec=vaapi` once, as a renderer comparison only.

## Upstream survey (2026-10-02)

| Area | Finding | Consequence |
| --- | --- | --- |
| VA driver | bootlin `libva-v4l2-request` is dormant (no merges since 2019; we build on PR #38). **megi's `libva-v4l2_request` v1.2** (2026-07-14, https://xff.cz/git/libva-v4l2_request/) is maintained: MPEG-2/H.264/HEVC/VP8/VP9/AV1, `vaExportSurfaceHandle` with modifiers, VPP scale/transpose, GStreamer `va` compatibility, tested on cedrus | Evaluate rebasing onto it (WP3) |
| Cedrus | Jernej Skrabec's VP9, secondary-engine P010 and AFBC series is in LibreELEC (PR #11799, merged 2026-09-25). VP9 was reverse-engineered from the same `libawvp9HwAL.so`. The H616 VE series is at v3 and unmerged | Read it before porting VP9 scaling (WP6) |
| FFmpeg | The V4L2-request hwaccel is unmerged (PR #20847, draft). AV1 resize renegotiation is still broken (fix in PR #21316, open). trixie stays on 7.1.5 | Stays stock; AV1 mid-stream resize remains a known gap |
| mpv | 0.41.0 is not in trixie. PR #14690 (`v4l2request`, `v4l2request-overlay`) waits on FFmpeg #20847. No VA-API overlay, no LSB 10-bit | Stock 0.40 on the GPU path |
| Mesa | trixie-backports has **26.1.6** (arm64), carrying the Panfrost planar-YUV and import work from 25.2–26.1 | A/B it in WP2; it is still stock Debian |
| Kernel | Nothing upstream replaces our work: no LSB P010 (only 3-plane S010), no H713. verisilicon "export only needed pixel formats" (7.2, stable-tagged) changes AV1 P010 enumeration. A Panfrost devfreq divide-by-zero fix is pending. LibreELEC carries an H6 GPU OPP patch | Feeds WP1; check 6.18.y |
| GStreamer | 1.28.7 is not in trixie. No new v4l2codecs features. 1.26.4 (MR 9305) fails when cropping under DMABuf caps | Test 1.26.2 as shipped |
| libplacebo | trixie's 7.349 is fine. 7.360+ has an unconfirmed LINEAR-modifier dma-buf regression on Mali | Don't chase it |

**Watch list:**
- FFmpeg PR #20847 together with mpv PR #14690. Both landing gives a stock GPU-free direct path.
- FFmpeg PR #21316 (AV1 resize).
- Mesa 26.3 (PanVK 1.3 on v7).
- The H616 VE series.
- The verisilicon format change in 6.18.y.

## Facts the work packages rest on

- **The GPU:**
  - Panfrost is bound to `1800000.gpu`, a Mali-G31 MP1.
  - **Corrected 2026-10-02.** It ran at a fixed **432 MHz**, not 864, with no OPP table and no devfreq. PLL_GPU's bit 0 is an output ÷2 that the CCU driver did not model. Measured with Panfrost's own counters (fdinfo `drm-cycles` / `drm-engine` with `profiling` on).
  - Stock runs a flat **600 MHz**: PLL_GPU = `0xb8001800` in every CCU capture, DVFS off. Its OPPs for this die are 600 MHz / M (150/200/300/600). The 700 MHz points belong to the other speed bin.
  - The GPU clock at `0x670` has a real 2-bit M divider (M = 0/1/3 measured 431/216/108 MHz). The H616's PLL-relock bypass clock at `0x674` reads zero here.
  - `gpu-thermal` has no trips or cooling map.
- **The software:**
  - Mesa 25.0.7: EGL/GBM on `card0` pairs with Panfrost automatically.
  - `libplacebo` 7.349 is installed; `gstreamer1.0-gl` is not.
  - The rootfs is 92% full, and the board's apt has no package lists.
- **The old 1080p `vo=gpu` result is stale.** "0.83x realtime, 481 dropped" ([handoff-2026-09-03-video-playback.md](handoff-2026-09-03-video-playback.md)) predates the 2026-09-03 zero-copy fix.

## Work packages

**WP0 — record the direction (done 2026-10-02).** This document,
[reference/stock-capture-2026-10-01.md](reference/stock-capture-2026-10-01.md),
and notes in [letterbox-plan.md](letterbox-plan.md), [roadmap.md](roadmap.md) and
[status.md](status.md).

**WP1 — make the GPU safe to lean on.**
- ~~Add a GPU OPP table capped at 700 MHz~~ Done as **0152** (clk: model PLL_GPU's ÷2 and the 0x670 M divider) and **0153** (DT: PLL_GPU pinned at 600 MHz, OPPs 150/200/300/600 = 600/M, so no PLL relock). These are new patches at the end of the series, not edits to 0024. Stock's third clock (`clk_parent`) is not needed: `assigned-clock-rates` sets the PLL.
- Enable `DEVFREQ_THERMAL` and give `gpu-thermal` a cooling map. Done in 0153 and the defconfig: passive at 85 C, critical at 105 C.
- Pick the pending Panfrost devfreq divide-by-zero fix if it reproduces. Not picked: the division (`total_time / 100`) is only an argument to a `dev_dbg`, so it needs that callsite enabled to trigger.
- Soak with `GPU_MIN_HZ=600000000`, because simple_ondemand may never reach the top point under this load. `gpu_mhz=` in the heartbeat is the proof.
- Gate: 45 minutes clean with `tools/video/soak-display-only.sh`, as in `reference/expS-0055-validation-45min-clean.log`.
  - **Passed 2026-10-02** ([reference/wp1-gpu-600mhz-45min-clean.log](reference/wp1-gpu-600mhz-45min-clean.log)). The run was 2709 s with `GPU_MIN_HZ=600000000` and stock `/usr/bin/mpv`. `gpu_mhz=600` was reported in all 90 heartbeats.
  - Clean on every counter: 0 mpv deaths, 1.30 M GPU IRQs (457–486/s), 161 k display commits, `mmu_delta=0`, nothing in dmesg.
  - The GPU peaked at 78.3 °C, so its 85 °C trip never fired.
  - **Cost:** the hotter die held the CPU below its 1296 MHz ceiling for most of the run, via the CPU's own 75 °C trip: 1104 MHz in 47 heartbeats, 1200 in 39. The 0055 reference held 1296 throughout. Account for this when WP2 measures CPU-heavy paths.
  - Each OPP was checked against Panfrost's cycle counters: 599/299/199/150 MHz. simple_ondemand reaches 600 under `vo=gpu` load.
  - Not run: `gles-play` (not built on this rootfs).
- Build from a fresh tree.

**WP2 — measure before building.**
- Run stock `/usr/bin/mpv --vo=gpu` and `--vo=gpu-next` (`--gpu-context=drm --hwdec=vaapi`, `LIBVA_DRIVER_NAME=v4l2_request`) over the capture media set (`tools/stock/make-capture-media.sh`): 1080p H.264/AV1/AV1 10-bit/VP9, 4K H.264, 852x480, 352x288, the rot90 set and native 720p.
- Record dropped frames, A/V sync, GPU IRQ/s, CPU, temperature, the DRM debugfs plane state, and an operator photo per clip (`tools/display/measure-panel-photo.py`).
- **Direct vs GPU at 720p**, 10 minutes each. This decides whether `patches/mpv` and `patches/gstreamer` survive.
- A/B Mesa 25.0.7 against the 26.1.6 backport.
- GStreamer: `v4l2slh264dec`, `vah264dec` and `vaav1dec ! glimagesink`.
- `tools/video/va-regress.sh` in both modes.
- **Expected failure:** 10-bit AV1 (P010 + LSB10) does not import into GL. Record what happens.
- Gate: AV1 and VP9 1080p in realtime with at most a few drops. If not, try mpv's cheap settings first (`--scale=bilinear --dscale=bilinear --dither=no --deband=no`, HDR off).

**WP2 findings so far (2026-10-02).** Raw results are in `local/h713-lab/wp2-20261002/`, from `tools/video/gpu-path-run.sh`. Every run used stock `/usr/bin/mpv` 0.40 on Mesa 25.0.7, with hardware decode confirmed by decoder interrupts and the GPU at 600 MHz unless noted. Each run is 60 s, about 1800 frames.

Three blockers had to be fixed before any number meant anything:
- **No hardware decode at all without kernel 0092.** Stock mpv found no VA display and decoded in software, with no error at the default log level. 0092 is now in series.
- **Widths that are not 64-aligned never reached the screen.** Panfrost rejects R8/GR88 imports whose pitch is not 64-aligned. Fixed by libva 0020.
- **0020 broke VP9 inter frames at those widths.** Fixed by kernel 0154, which also fixes a VP9 bug that predates 0020 (330 wide through GStreamer, 1/30 frames → 30/30).

Results:

| Content | `vo=gpu` default | `vo=gpu-next` default | Cheap settings |
| --- | --- | --- | --- |
| 1080p H.264 / HEVC / VP9 / AV1 | ~850 dropped, GPU saturated | 920–1065 dropped | **0 dropped, GPU 38% busy at 150 MHz** (both VOs) |
| Native 720p H.264 | 0 dropped, 66% busy | 243 dropped | 0 dropped, 38% busy at 150 MHz |
| 720p rotated 90° (all four codecs) | 0–1 dropped, 83% busy | ~610 dropped | 0 dropped, 18% busy at 150 MHz |
| 852x480 (H.264 / VP9 / AV1) | ~145 dropped, 100% busy | **0.3× real time** | 0–1 dropped, 38% busy at 150 MHz |
| 352x288 | 1 dropped | 13 dropped | 1 dropped, 28% busy |
| 720x576 | 0 dropped, 93% busy | 1210 dropped | 0 dropped, 30% busy |
| 10-bit AV1 1080p | **No picture.** P010 import refused (`EGL 12297`), as expected (WP4) | Same | — |
| 4K H.264 | Software decode: the VA driver caps cedrus at 2048 (unproven above that) | Same | — |

What the table says:
- **The cheap settings are the answer for scaling.** "Cheap" is bilinear scale, dscale and cscale, no dither, no deband, no linear or sigmoid scaling, no HDR peak detection. With them, 1080p→720p in every codec is real time with headroom, at the lowest OPP.
- **`gpu-next` is consistently worse than `gpu` on this GPU.** It should not be the default.
- **Default-quality upscaling is too heavy:** 852x480 drops frames on `gpu` and plays at 0.3× on `gpu-next`.
- The launcher (WP4) should pass the cheap settings, or an mpv profile carrying them.

**Direct vs GPU at 720p, 10 minutes each:**

| | Direct (patched mpv, `vo=drm`, video plane) | GPU (stock `vo=gpu`, cheap settings) |
| --- | --- | --- |
| Playback | 20,801 frames at 29.9 fps, 0 dropped | **Froze after ~347 s** (10,405 frames in 634 s). mpv stayed alive, the GPU went idle, and the flip burst read 1/20 |
| GPU | Idle (0 IRQ/s) | 21% average busy at 150 MHz |
| CPU, all cores | 8%; mostly at 1008 MHz | 8%; mostly at 1008 MHz |
| Peak temperature (GPU / CPU) | 59 / 59 °C | 62 / 62 °C |

- **The GPU path has an intermittent freeze.** This is its third sighting, after two short cheap-settings runs that played below real time with the GPU nearly idle. It blocks making the GPU path the default.
- On cost alone, the GPU path is cheap with these settings: 21% of one shader core at the lowest OPP, the same CPU load, and +3 °C. The direct path's advantage is efficiency, not feasibility.
- `tools/video/gpu-stall-catch.sh` loops this playback and, when decode interrupts stop, dumps thread stacks, dma-buf fences, the DRM state and dmesg to `/var/tmp/stall/`.

**GStreamer GPU path (2026-10-02).** Stock GStreamer 1.26.2 with `gstreamer1.0-gl` (now in the rootfs build), `glimagesink` drawing through GBM (`GST_GL_WINDOW=gbm`). Runs were 30 s; `tools/video/gst-path-run.sh`.

| Decoder | Clips | Result |
| --- | --- | --- |
| `v4l2slh264/h265/vp9/av1dec` | 720p, 1080p, 852x480 | **Zero-copy** (`memory:DMABuf`, `DMA_DRM` NV12), 0 dropped, 29.97 fps, 6–8% CPU, every codec |
| `vah264dec`, `vaav1dec` | 720p, 1080p, 852x480 | Zero-copy, 0–1 dropped, 5–7% CPU, after libva 0021–0023 and `GST_VA_ALL_DRIVERS=1`. Before: no frame decoded |
| `vah265dec` | 720p | **Does not decode**: `vaEndPicture` reports a decoding error before the VE runs. Deferred to WP3 |
| `vavp9dec` | — | Not registered by GStreamer |
| 10-bit AV1 | 1080p | Not run on GStreamer yet. mpv's GPU path refuses the P010 import (WP4) |

- **GStreamer's `v4l2sl*` path is the cleanest result in WP2.** It needs no VA driver, no tuning and no patches, and it is zero-copy for every codec.
- The `va` path now matches it for H.264 and AV1.

Not yet measured:
- A/B against Mesa 26.1.6;
- an operator photo per clip.

Also open:
- Two cheap-settings `vo=gpu` runs (HEVC and AV1 1080p) once played below real time with the GPU 10% busy at 150 MHz. They did not recur in six reruns. The cause is unknown.
- Lift the 2048 cap only after cedrus is proven bit-exact at 4K (clips 50–52).

**WP3 — VA driver base.**
- Diff megi's v1.2 feature by feature against our `patches/libva-v4l2-request` 0001-0019: multi-device, codec backends, DMA-BUF heap capture, renegotiation, scale/crop, export modifiers, GStreamer `va`.
- Build it off-target, install it side by side, and run `va-regress.sh` plus `vah264dec ! glimagesink`.
- Decide whether to rebase our remaining delta onto it, and record the decision in the patch README.

**WP4 — the launcher and 10-bit for GL.**
- In the VA driver, export 10-bit AV1 as linear P010 for GL consumers; KMS keeps LSB10.
- Add `tools/video/shaders/lsb10.glsl` (×64).
- Add `tools/video/h713-play FILE`. It probes codec, size, rotation and bit depth, applies the routing table, prints its decision, then runs stock mpv with the VE pre-shrink environment (aspect-fit, even, never upscale) or the 10-bit environment and shader, or the direct mode if WP2 keeps it.

**Later.**
- **WP5, the hardware mirror** as `REFLECT_X`/`REFLECT_Y` on the DRM planes, from the recipe in the stock reference.
- **WP6, VP9 VE scaling:** read Jernej's patches, then the stock 4K VE pages, then extend `cedrus_can_scale()`.
- Keystone as a GL warp.
- The hardware letterbox plan as an optimisation.

## Verification

- **WP1:** devfreq frequencies are ≤700 MHz and `cur_freq` moves, the soak runs clean, and `gles-play` stays at about 59.7 fps.
- **WP2/WP4, per clip:**
  - the launcher's route matches the table;
  - drops are under the gate;
  - the expected plane carries a changing framebuffer;
  - the photo geometry is correct;
  - 10-bit levels match the software decode.
- **WP3:** `va-regress.sh` passes in both modes, and `va*dec ! glimagesink` plays.
- **Regression:** native 1280x720 NV12/P010 still scans out zero-copy on the video plane.
- **Operator steps** get their own turn, announced before the clip starts.
