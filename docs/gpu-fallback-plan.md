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

**WP2 — measure before building. CLOSED 2026-10-02.**
- **Outcome:** stock mpv on the GPU path with audio through PipeWire, and the direct path retired.
- **Gate:** passes with the cheap settings.
- **Fixed along the way:** kernel 0092/0152–0154, libva 0020–0025, and the audio deadlock (PipeWire).
- **Carried forward:** the CPU-gap profiling (needs a `perf` cross-build), and the `kmssink` size limits, which move to WP4.
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

- **The freeze was in the audio path, not the GPU path (root-caused 2026-10-02).** The catcher caught it after a direct-path prelude, 9 min in. mpv's last words were "Audio device underrun detected" then "restarting audio after underrun". At the freeze:
  - every mpv thread was idle in a futex;
  - the ALSA PCM sat **PREPARED with a full buffer** (`avail 0`), never started;
  - video, paced by the audio clock, waited forever.

  `tools/video/xrun-hammer.sh` reproduces it on demand: forced underruns, and the 32nd froze. `--ao=null` recovered from 40 of 40. The kernel logs nothing. So the bug sits between mpv's `ao_alsa` underrun recovery and the H713 codec PCM, and it **affects every mpv path, direct included**. It does not block the GPU path. **Fixed in our mpv by `patches/mpv/0005`** (480 forced underruns, 0 freezes; [audio-underrun-deadlock.md](audio-underrun-deadlock.md)); Debian's mpv keeps it, which bears on the WP4 launcher's choice of binary.
- On cost alone, the GPU path is cheap with these settings: 21% of one shader core at the lowest OPP, the same CPU load, and +3 °C. The direct path's advantage is efficiency, not feasibility.
- `tools/video/gpu-stall-catch.sh` loops this playback and, when decode interrupts stop, dumps thread stacks, dma-buf fences, the DRM state and dmesg to `/var/tmp/stall/`.

**Direct vs GPU at 720p, rerun (2026-10-02).** 10 minutes each. The first GPU leg had frozen at 347 s from the ALSA deadlock, so this replaces it. **Correction:** only the GPU leg was on PipeWire. The patched mpv was built without PipeWire support (only alsa, null and pcm), so the direct leg drove ALSA directly, with 0005. Its video and CPU numbers stand; its audio stack differed.

| | Direct (patched mpv, `vo=drm`) | GPU (stock mpv, `vo=gpu`, cheap settings) |
| --- | --- | --- |
| Playback | 20,842 frames at 30 fps, 0 dropped | 18,998 frames at 30 fps, 0 dropped, no freeze |
| GPU | Idle | 38% busy at 150 MHz |
| Whole-board CPU | 9% | 17% |
| mpv's own CPU (one core) | 17% | 41% |
| CPU clock | Mostly 1008 MHz | More time at 1104–1296 MHz |
| Peak temperature (GPU / CPU) | 58 / 57 °C | 59 / 58 °C |

- The loop-seek freeze (an underrun at a `--loop-file` seek, seen only on ALSA) did not occur on PipeWire: 120 of 120 forced underruns on stock `vo=gpu`, with a 10 s clip so the underruns kept crossing loops. **Correction:** the "120/120" for the direct path is void. That run passed `--ao=pipewire` to a build without it, so it most likely played with no audio and nothing to underrun.
- **Recommendation:** keep the direct path for content that is already exactly 1280x720, and the GPU path for everything else. For native-720p content the direct path does the same job at about half the CPU, with the GPU idle.
- **DECISION (operator, 2026-10-02): retire the direct path; stock mpv on the GPU path, audio through PipeWire.**
  - `patches/mpv` and `patches/gstreamer` are retired (banners in their READMEs).
  - On the bench board the patched binary is renamed to `/usr/local/bin/mpv-direct`, kept for the HDMI-in preview tool only. Plain `mpv` is `/usr/bin/mpv` and picks `[pipewire]` by itself. `tools/video/check-video-stack.sh` now checks for exactly that.
  - **Follow-up: close the CPU gap by other means** (9% vs 17% on native 720p). See "WP2 follow-up" below.

**GStreamer GPU path (2026-10-02).** Stock GStreamer 1.26.2 with `gstreamer1.0-gl` (now in the rootfs build), `glimagesink` drawing through GBM (`GST_GL_WINDOW=gbm`). Runs were 30 s; `tools/video/gst-path-run.sh`.

| Decoder | Clips | Result |
| --- | --- | --- |
| `v4l2slh264/h265/vp9/av1dec` | 720p, 1080p, 852x480 | **Zero-copy** (`memory:DMABuf`, `DMA_DRM` NV12), 0 dropped, 29.97 fps, 6–8% CPU, every codec |
| `vah264dec`, `vaav1dec` | 720p, 1080p, 852x480 | Zero-copy, 0–1 dropped, 5–7% CPU, after libva 0021–0023 and `GST_VA_ALL_DRIVERS=1`. Before: no frame decoded |
| `vah265dec` | 720p, 1080p | Fixed by libva 0024. GStreamer sends the slice's entry-point count, which VA-API cannot back with offsets, and cedrus refused (`-ERANGE`); now 0 is sent, as ffmpeg always did |
| `vavp9dec` | — | Not registered by GStreamer |
| 10-bit AV1 | 1080p | No GL path, as expected (WP4). Mesa 26.1.6 refuses cleanly (`Unsupported pixel format`). **Mesa 25.0.7 segfaults** in `driBindContext` instead |

- **Bit-exactness** (`tools/video/gst-va-check.sh`, 60 frames against ffmpeg software): **60/60** for each of
  - `vah264dec` at 720p and 852x480,
  - `vah265dec` at 720p and 1080p,
  - `vaav1dec` at 720p,
  - `v4l2slh264dec` and `v4l2slvp9dec`.
- Download to system memory needed libva 0025. A decoded surface reported `VASurfaceDisplaying`, and GStreamer will not read a surface that is not `Ready`.

- **GStreamer's `v4l2sl*` path is the cleanest result in WP2.** It needs no VA driver, no tuning and no patches, and it is zero-copy for every codec.
- The `va` path now matches it for H.264 and AV1.

**Mesa 26.1.6 vs 25.0.7.** The backport was unpacked into tmpfs and selected per process (library and driver paths), with no system change; same session, same clips.

| | 25.0.7 | 26.1.6 |
| --- | --- | --- |
| 1080p, default settings | 844 dropped | 878 dropped |
| 852x480, default settings | 143 dropped | 184 dropped |
| Cheap settings, 5 clips | 0 dropped, ~38% busy at 150 MHz | 0 dropped, ~31% busy at ~200 MHz (slightly more cycles) |

**Decision: stay on trixie's 25.0.7.** 26.1.6 has the same pitch rule (from source) and no performance gain. Its one advantage is failing cleanly instead of crashing on an unimportable 10-bit format.

**Geometry, from the scanout instead of photographs.** `tools/display/scanout-grab.c` reads back the framebuffer the display is scanning out. `tools/video/geometry-grab.sh` compares the picture's bounding box with aspect-fit (display aspect from size, SAR and rotation, centred in 1280x720). All 12 clips matched exactly:
- 1080p and 640x360 fill the screen;
- 2560x1080 is letterboxed to 1280x540;
- 1440x1080 and 720x576 (SAR 16:15) are pillarboxed to 960x720;
- 1000x600 lands at 1200x720;
- 852x480 lands at 1278x720;
- 352x288 lands at 880x720;
- 90° and 270° rotation give 405x720 portrait, and 180° is full screen.

A visual check of the grabs tells 90° from 270° and 180° from 0°, and matches the display-matrix convention. Stock honours the same tags (with grey bars where ours are black). Photographs are therefore needed only as a final look at the panel itself, not for geometry.

Not yet measured:
- A/B against Mesa 26.1.6;
- ~~one operator look at the panel~~ Done 2026-10-02 on the 1080p card, stock `vo=gpu`, cheap settings:
  - the marker moves smoothly;
  - the border is visible on all four edges;
  - greys are neutral and the detail blocks look clean.

  The operator saw the side borders as slightly thinner than top and bottom. The scanout grab of the same frame has a 6 px border on every edge (the card's 9 px x 2/3), so the difference is in the projector (keystone, optics or panel overscan), not the pipeline.

Also open:
- Two cheap-settings `vo=gpu` runs (HEVC and AV1 1080p) once played below real time with the GPU 10% busy at 150 MHz. They are almost certainly the same audio-underrun stall (see the direct-vs-GPU notes).
- Lift the 2048 cap only after cedrus is proven bit-exact at 4K (clips 50–52).

**WP2 follow-up: close the direct-vs-GPU CPU gap without a patched player.** The GPU path costs about 8 points more whole-board CPU on native 720p (mpv itself 41% of one core against 17%). Candidates, cheapest first:
- **Measured (2026-10-02, 720p, 60 s each; `local/h713-lab/wp2-20261002/gap-*.txt`).**

  | Run | Whole-board CPU | mpv (one core) |
  | --- | --- | --- |
  | GPU path, PipeWire | 16% | 39% |
  | GPU path, no audio | 13% | 32% |
  | Direct path, ALSA | 8% | 17% |
  | Direct path, no audio | 8% | 15% |

  - About **3 points are audio** (PipeWire against ALSA direct).
  - About **5 points are video**, nearly all mpv's own GL path: 32% against 15% of one core.
  - **Stock knobs do not touch it.** `--gpu-dumb-mode=yes`, OSD/scripts/stats off, and both together all left mpv at 32%. The cost is not in shaders or overlays. It is per-frame overhead: the EGL dma-buf import of each decoded surface, Mesa/Panfrost CPU per draw and flush, and the GBM page flip.
  - **Next step: profile it.** There is no `perf` on the board and tracefs is not reachable. Cross-build `perf` from the kernel tree (`tools/perf`) and record `mpv` on both paths; that says which of the three it is and whether anything stock can avoid it.
- **Stock mpv knobs:** `--video-sync`, `--opengl-swapinterval`, `--interpolation=no`, `--hwdec-interop`, OSD off, and the cheap scale settings already in place.
- **Stock `kmssink`: measured 2026-10-02** (`local/h713-lab/wp2-20261002/kmssink-matrix.txt`), with stock GStreamer `v4l2sl*dec ! kmssink driver-name=sun50i-h713-afbd`, no patches.
  - **Native 1280x720, every codec (H.264, HEVC, VP9, AV1):** zero-copy NV12 onto the video plane, **2–3% whole-board CPU, GPU idle, 0 dropped.** Better than the retired direct path (8%). AV1's padded 1280x768 buffer is accepted.
  - **Every other size fails.**
    - 1080p, 2560x1080: `kmssink` resource error at commit.
    - 852x480, 352x288, 720x576: no caps negotiation at all (the driver offers the plane for 1280x720 only).
    - `can-scale=false` changes neither.
  - **720p rotated 90°:** plays unrotated (`kmssink` ignores the orientation tag).
  - **10-bit AV1:** crashes (stock has no LSB10 P010 path).
  - **What a size-independent `kmssink` would need, all kernel-side:**
    - smaller than the panel: the display driver must accept a small framebuffer and either letterbox it ([letterbox-plan.md](letterbox-plan.md)) or upscale it with the `0x05180000` upscaler, whose driver patches were retired on 2026-09-23;
    - larger than the panel: no display downscaler exists, and the VE's decode-time scaler needs a userspace request that stock GStreamer never makes, so it stays on the GPU path;
    - 90/270° rotation: GPU only (the hardware mirror covers 180°).
  - **Usable today:** stock `kmssink` for exact-720p content, the stock GPU path for the rest. The choice belongs in the WP4 launcher.
- **Stock direct paths that already exist:** FFmpeg #20847 + mpv #14690 (`v4l2request-overlay`, the stock version of what `patches/mpv` did), and GStreamer `kmssink` without our patches where the plane takes the decoder's buffer as is.
- **A compositor:** a Wayland compositor that puts the video dma-buf on the overlay plane (e.g. `vo=dmabuf-wayland`), stock end to end.

**WP3 — VA driver base. CLOSED 2026-10-03.**
- **Outcome:** the board runs megi's `libva-v4l2_request` v1.2 plus six patches ([patches/libva-v4l2_request/README.md](../patches/libva-v4l2_request/README.md)), replacing bootlin PR #38 and its 25. As shipped, megi passed everything except AV1 (a thread race: SIGSEGV), 10-bit AV1 (no `PL10`) and resolution changes (frames freed with their context). With the series, `va-regress.sh` has 0 failing lines and the scaler output is byte-identical. The GPU path is at parity, and 12/12 damaged AV1 streams survive.
- **Kernel 0155:** cedrus refuses VP9 Profile 2 in `try_ctrl`, so the driver stops advertising it.
- **Carried to WP4:** unscaled exports report the padded height (1088); AV1 10-bit on GL now falls back to software; decode errors reach clients only through the AV1 gate.
- Diff megi's v1.2 feature by feature against our `patches/libva-v4l2-request` 0001-0019: multi-device, codec backends, DMA-BUF heap capture, renegotiation, scale/crop, export modifiers, GStreamer `va`.
- Build it off-target, install it side by side, and run `va-regress.sh` plus `vah264dec ! glimagesink`.
- Decide whether to rebase our remaining delta onto it, and record the decision in the patch README.

**WP4 — the launcher and 10-bit for GL.**
- **Operator idea (2026-10-02): put the VE's polyphase scaler in front of stock `kmssink`** so sizes other than 1280x720 reach the video plane with the GPU idle (stock `kmssink` takes only exact 1280x720; see the WP2 follow-up).
  - The VA driver already exposes the scaler through `V4L2_REQUEST_SCALE` (libva 0008/0010), and GStreamer's `va*dec` now work (libva 0021–0025). So `vah264dec`/`vah265dec ! kmssink` with the variable set may need no GStreamer patch at all.
  - Limits: the decode-time scaler exists for H.264 and HEVC only. VP9 scaling is unported (WP6), and AV1 has none; those stay on the GPU path.
  - It also needs aspect-fit: a non-16:9 source still has to be letterboxed, which the plane cannot do yet ([letterbox-plan.md](letterbox-plan.md)).

**WP4 findings so far (2026-10-03): the plane routes work, with stock GStreamer and one pad probe.**

| Route | Clips | Rendered vs position | GPU | Whole-board CPU (with audio) |
| --- | --- | --- | --- | --- |
| plane-native: `v4l2sl*dec ! kmssink` | 720p H.264, HEVC, VP9, AV1 | 30 fps; a constant ~10 frames at start, 1 drop | 0 IRQs | 4.8–5.6% |
| plane-ve: `va*dec` + VE scaler `! kmssink` | 1080p H.264, HEVC → 1280x720 | same | 0 IRQs | 5.0–5.3% |
| gpu: stock mpv `--vo=gpu`, cheap settings | the rest | (WP2) | busy | ~17% |

The scanout grab of the 1080p card through plane-ve is the full card, 1280x720, with all four borders. Three things stood in the way, and each one had been reported as working, or was invisible:
- **`va*dec` into DMABuf caps showed solid green, at a steady 30 fps.** megi's driver treated GStreamer's export-at-allocation as probing and decoded elsewhere. This applied to native 720p and to `glimagesink` alike, so the WP2 "`va*` zero-copy" result does not hold on megi's driver. WP3 had checked GStreamer only through readback. Fixed by **libva 0007**, which decodes into the client's exported dma-bufs and exports at the scaled size when `V4L2_REQUEST_SCALE` is set. `va-regress.sh` passes with 0 failing lines; GStreamer DMABuf output is bit-exact (H.264 ×5, HEVC ×4); stock mpv is unchanged.
- **GStreamer believes the SPS, not the surface.** Caps and every buffer's `GstVideoMeta` say 1920x1080, and kmssink sizes the framebuffer from the meta ("bad pitch 1280"). `capssetter` cannot fix the meta, and it breaks DMABuf negotiation upstream. The fix is a pad probe that rewrites both: `tools/video/gst-plane-play.c`, stock elements otherwise.
- **kmssink dropped about one frame a second** (decoder QoS, 30 in 30 s, even without audio). After its plane commit, which already waits for the flip on this driver, kmssink waits for a vblank of its own. That makes up to a whole 30 fps frame per render. The fix is stock `skip-vsync=true`, which brings the drops to 0. The WP2 `kmssink-matrix` numbers (29.7 fps average) carry this loss.

Built:
- `tools/video/gst-plane-play FILE CODEC DECODER [WxH] [SECONDS]` plays onto the video plane with audio (PipeWire) when the file has any. It prints rendered, dropped and position, and stops cleanly on Ctrl-C or SIGTERM.
- `tools/video/h713-play [--dry-run] [--route=auto|plane|gpu] FILE [-- MPV-ARGS]` probes the file, prints one decision line and runs the route. Every capture clip routes as intended: 1080p H.264/HEVC → plane-ve; native 720p ×4 → plane-native; AV1/VP9 1080p, 10-bit, rotated, and anything not 16:9 → gpu.

Limits of the plane routes, all set by the plane taking exactly 1280x720:
- no letterbox or pillarbox, so only 16:9 content;
- no upscaling (the VE scaler only shrinks);
- no 90/270 rotation;
- VE scaling for H.264 and HEVC only, at most 2048 wide (the VA cap);
- 10-bit goes to the GPU route.

Still open in WP4:
- the three items below;
- an operator look at the panel (plane-ve 1080p);
- a 10-minute soak of each plane route;
- installing `h713-play` and `gst-plane-play` from the rootfs build instead of by hand.

- In the VA driver, export 10-bit AV1 as linear P010 for GL consumers; KMS keeps LSB10. With megi's driver (WP3) stock mpv currently falls back to software for 10-bit AV1 on `vo=gpu`.
- The scaler variables are megi patch 0005 now, not libva 0008/0010. Unscaled exports report the padded CAPTURE height (1088), which `kmssink` would show as 8 extra rows.
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
