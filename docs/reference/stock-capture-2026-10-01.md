# What stock does for scaling, letterboxing, rotation and orientation (2026-10-01)

Captured read-only on the vendor stack, following
[vendor-capture-plan.md](../vendor-capture-plan.md) and
[stock-capture-operator-sheet.md](../stock-capture-operator-sheet.md). The raw
captures (registers, VE/AV1 pages, firmware elog rings, logcat, SurfaceFlinger
dumps, UART, photos) are in `local/h713-lab/stock-capture-20261001/` (not
tracked). The tools are in `tools/stock/`, `tools/mips/elog-parse.py` and
`tools/display/hidtvreg-raw.c`.

## Verdicts

| Question | Answer |
| --- | --- |
| How does stock show 1080p (any codec, AV1 included) on the 720p panel? | **The GPU.** It decodes full-size; SurfaceFlinger/HWC scales on the Mali |
| When does the VE scaler run? | **Only for sources above 1080p.** cedarc gates it on 1920x1080 |
| Upscale, letterbox, rotation? | **The GPU** (SurfaceFlinger client composition) |
| Keystone? | **The GPU** (a GL warp inside SurfaceFlinger) |
| Rear/ceiling projection? | **Hardware**: the MIPS window layer mirrors H, V or both |

Stock *file playback* therefore never uses the display's scaling hardware.
The firmware's window-layer recipes (proc upscaler, border overlays,
composition line buffers) serve the capture inputs (HDMI-in, CVBS, DTV).

## Cases

**1080p AV1 (`05-av1-1080.mp4`).**
- The VE stayed silent (`cedar_dev` 0.0/s) while the AV1 core decoded (`sunxi_go_ctx` 30/s).
- The core decodes the full 1920x1088: core `+0x278 = 0x438`, secondary output Y at `0x0D200000`, luma `0x1FE000` bytes.
- AFBD scans a *different*, 1280x720 buffer (Y `0x09D00000`, C at `+0xE1000`) at unity scale. Proc is 1.0, the panel down-scaler is in BYPASS, and the window layer logged nothing new.
- logcat shows the 1920x1088 layer handed to SurfaceFlinger (`setLayerParam nWxH(1920x1088)`) and 1280x720 gralloc buffers allocated for the composer.
- `hwcomposer.ares.so` carries `sunxi::VideoTunnel::scaleDownRequired` and `sunxi::GpuScaler::perform`.
- There is no hidden display or VE downscaler for AV1.

**1080p VP9 and H.264 (`04`, `01`).**
- The VE decodes; cedarc logs `scaler open flag = 0` with ratio 0, and the FBM is 1920x1088.
- The display shows a 1280x720 GPU-produced buffer at unity.
- cedarc's `getScreenSize` reports `prop_value = 0, nWidthTh = 1920, nHeightTh = 1080`, which feeds `ConfigExtraScaleInfo`.

**Upscale (`11-h264-852x480.mp4`).**
- `dumpsys SurfaceFlinger` shows the video SurfaceView as a **CLIENT** layer (`forceClientComposition=true`), `sourceCrop 852x480 → displayFrame [1 0 1279 720]` (×1.50).
- SurfaceFlinger GLES-composites video and UI into a 1280x720 client target.
- The HWC (`svp-device`) hands that frame to the display; its own GPU scaler stayed unused (`GPU scale Commit : 0`).

**4K (`50-vp9`, `51-hevc`, `52-h264` -2160).**
- cedarc opens the VE scaler (`scaler open flag = 1`, `realScaleW:1920 realScaleH:1080`), and the GPU composites the rest.
- VE `+0xf10 = 0x07800438` (1920x1080 out), `+0xf14 = 0x1FFF1FFF`, `+0xf18 = 0x07FF07FF`, `+0x40 = 0xF` in all three.
- H.264 uses a second FBM pool (1920x1088) for the scaled output.
- The snapshots fell between frames, so per-frame words may read 0. Confirm with a timed capture before porting.
- Full VE pages: `out/5x-*-{1,2}/ve.txt`.

**Rotation.** Files with rotate 90/180/270 display matrices are honoured. 90 and 270 appear as a centred portrait picture with **lit grey** side bars: GPU composition, not a hardware fill. These are photos only (unattended playlist run); see `photos/INDEX.md`.

**Keystone (one corner, `ltx = 10`).**
- `/system/lib/libsurfaceflinger.so` reads `persist.display.keystone_*` ("keystoneRendering").
- `/system/lib/libkeystone.so` builds the GL matrix and shader (`getKeyStoneMatrix`, `createKeystoneShader`).
- No window-layer records; the display words that differed are frame statistics.

## Installation mode: the hardware mirror

Set through `com.htc.magcubicos` → Projection settings → Installation mode,
which calls Softwinner's `AwTvDisplayTypes.EnumPanelMirror` /
`PANEL_CONFIG_MIRROR`. Each change makes the MIPS window layer redo
`SetWindow`.

| Mode | `mirror_mode` | Firmware log |
| --- | --- | --- |
| Front | 0 | reference |
| Rear | 1 (H) | proc `+0x50` line window moves; NR `m_v_mirror_on: FALSE` |
| Rear ceiling | 2 (V) | NR `m_v_mirror_on: TRUE` (bottom-up fetch) |
| Front ceiling | 3 (H+V) | both; panel `video_win` y 22 → 21 |

Register words that are stable within each capture and differ from native
(diffed against two native and two keystone captures):

- **V flip (rear ceiling), 4 words:**
  - `0x05600010` `0x03000013 → 0x0300001B`: **AFBD source control bit 3**
  - `0x05000040` `0x02090208 → 0x02090200`
  - `0x050c0940` `0xA00800F0 → 0xA0080040`
  - `0x05140e08` `0x020000F0 → 0x02000336`
- **H mirror (rear), 22 words:**
  - panel `0x051c00a0` `0x80000000 → 0x80000001` and `0x051c0164` `0 → 1` (bit 0)
  - proc `+0x50` in all four instances, `0x001B02D0 → 0x001A02D0`
  - one-pixel/one-line offsets in composition (`0x0500080c/0840/0858/0a0c/0aa8/0aac`), `0x05040014`, DETN (`0x050c0950/0970`), route (`0x05140e04/0e18`) and panel (`0x051c0154/0184/0198/01a0/01b4`)
- **H+V (front ceiling):** the union of the two.

The full `WriteReg` sequences are in `out/orient-*/elog.bin` (decode with
`tools/mips/elog-parse.py --tags 'wce_|win_mgr'`). This is the recipe for
ceiling and rear projection on our stack.

## Method notes

- **The elog costs stock about 3 minutes of boot.** Enabling it on the vendor FAT (`tools/stock/vendor-elog-cfg.sh on`, mode 2 / level 5) made stock's CPU_COMM handshake take 184.7 s, logging every spinlock step. Android sat at the logo, then recovered by itself. The ring then wraps, so `elog-parse.py` sorts by timestamp. Reverted afterwards (`off`, verified by hash).
- **The stock player auto-advances** through `/sdcard/Movies` at the end of each clip.
- **The restore SPL was not stale.** Board LBA `0x10` matched the restore payload before and after; `build/out`'s newer SPL was never installed.
