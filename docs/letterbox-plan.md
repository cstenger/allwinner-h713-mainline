# Letterboxing on the video plane — plan (2026-10-01)

## Goal

Show any decoded picture **up to 1280x720** on the panel with the right
aspect ratio. Sub-720p 16:9 content should fill the panel (scaled up), other
aspects should fit with black bars, and a mid-stream size change should follow
on screen. No GPU ((memory note `gpu-path-is-last-resort`)).

Today the decoders follow size changes (libva 0018/0019), but the video plane
takes exactly one geometry: `h713_afbd_video_atomic_check` accepts a 1280x720
source at the origin and nothing else. A 640x360 or 352x288 frame, or any
change mid-stream, is refused. AV1 above 720p stays out of scope: the AV1 core
cannot downscale, and the display can only scale **up**.

## What is already established (do not re-derive)

| Fact | Source |
| --- | --- |
| The MIPS firmware letterboxes by itself: given 852x480 it programmed AFBD source size `0x05600030 = 0x01E00354`, composition line buffers `0x05000174/0x274 = 0x002B002B`, and panel border overlays `top 0 bottom 240 left 0 right 428` (picture top-left) | `docs/reference/scaler-engaged-2026-09-05.md`, `composition-ratio-registers-are-line-buffers-2026-09-10.md` |
| Borders are drawn by `PanelWinNode::WriteBorderOverlay1/2` in the panel block `0x051c0000`; `PanelWinNode` keeps `m_video_win`, `m_video_win_2`, `m_crtc_panel_win`, `m_21_9_scaler_win`, `m_border_overlay_win` | `docs/reference/mips-wce-window-layer-2026-09-04.md` |
| The composition block `0x05000000` holds the AFBD fetch **line-buffer descriptors** (Rowbyte / LineBufLevel / LineNumber, Y and C), written only by `NRWinNode::WriteReg`, formula in `FrameBuffer::GetPsuPfuWin` (`0x8b1a2668`). Mis-sizing them starves the fetch and wedges the panel until reboot | `composition-ratio-registers-are-line-buffers-2026-09-10.md` |
| The proc block `0x05180000` (instances 0/1) is an **upscaler** on the video raster: input window `+0x34`, output `+0x2c/+0x30`, ratios `+0x08/+0x3c`, phases, V line-enable window `+0x50 = [27, max(in_h,out_h)]`. Hardware-clean 960x544/1280x544/960x720 → 1280x720. Live upper bits: always read-modify-write | (memory note `two-axis-scaler-0x05180000`), retired kernel patches 0098/0103/0105/0106/0108/0111 |
| Outside the proc input window the panel shows a **flat grey fill** | `proc-scaler-video-2026-09-11/RESULT.md` |
| With the composition descriptors **left at 1280**, a smaller AFBD raster wraps the picture three times and fills green; 0106 therefore kept AFBD at a native 1280x720, pitch-1280 raster and moved only the proc input window | `patches/kernel/0106-*.patch`, `handoff-2026-09-14-video-scaler-and-rotation.md` §4 |
| The plane state in debugfs can say `crtc=(null)` while video is on the glass; gate on registers and the operator, not DRM accounting alone | (memory note `two-axis-scaler-0x05180000`) |

The open question that decides the architecture: **0106's negative was taken
with the composition descriptors still sized for 1280.** The firmware's
852x480 recipe changed them. If a small AFBD raster works once they match,
producers need no panel-sized canvas.

## Phase 0 — desk work, no board writes

1. **`PanelWinNode` static RE** (`display.bin`, MIPS address = ARM + `0xB5000000`,
   (memory note `mips-firmware-address-map`)): `WriteBorderOverlay1/2` register offsets in
   `0x051c0000`, the width/colour encoding, how `CalcWindow` derives
   `m_video_win_2` and whether any register **positions** the picture (centred
   vs top-left). Find the log lines that print each field first — that method
   cracked the composition block.
2. **`NRWinNode::WriteReg` / `GetPsuPfuWin`**: the full composition
   descriptor set (`0x0f0, 0x174, 0x178, 0x1b4, 0x1b8, 0x210, 0x274, 0x278,
   0x2b4, 0x2b8`) as a function of width, height and format, NV12 and P010.
   Check the formula reproduces both known points: 1280 → `0x40`, 852 → `0x2B`.
3. **Proc fill colour**: find the register behind the grey field outside the
   input window, and whether proc's output window has an **offset** (that
   would centre a pillarboxed picture without the panel block).
4. **Recover the retired chain** (0098–0111 + `docs/handoff-2026-09-23-retire-display-scaling.md`)
   into a register recipe, re-based on today's driver (0149 formats, P010
   budgets).
5. **Read-only baseline on the board**: dump `0x05000000`, `0x05140000`,
   `0x05180000`, `0x051c0000`, `0x05600000` (the known-safe ranges only —
   never `0x07091000` or `0x06940000`) with the panel showing native 720p
   video, and check every value against what the recovered formulas predict
   for 1280x720. **A formula that does not reproduce the live native state is
   not ready to drive a write** ((memory note `diff-against-known-good-first`)).

Deliverable: `docs/reference/letterbox-recipe-<date>.md` — for a source W×H and
a destination rect, every register and value, with the provenance of each.

## Phase 1 — decide the source contract (one bounded panel test)

Test H1 on a static card with the firmware's full 852x480 recipe: AFBD source
size, **matching composition descriptors**, borders off. Driven by a devmem
script in the style of `tools/display/composite-route-test.sh`, against a
heap buffer holding an 852x480 NV12 card at pitch 852 (fill tool:
`kms-p010-plane-test` grows `W=`/`H=`).

- **Pass (H1):** the plane can fetch a raster of the picture's own size.
  Producers stay as they are; every decoder's natural output is usable.
- **Fail (H2):** AFBD only walks 1280x720 at pitch 1280 (0106's contract). The
  picture then has to arrive in a panel-pitch canvas: the VA driver allocates
  1280-pitch surfaces (it owns capture memory since 0018); cedrus writes there
  through its scaler's COMPOSE (kernel 0107/0120, ratio 1:1 to be proven);
  hantro needs its unused `lu/cb_stride` registers; anything else gets one CPU
  copy into the canvas (cheap since 0018 — heap pages are cached).

Safety: operator look in its own turn, positive control (console visible)
first, one write sequence with a timed restore, and a power cycle budgeted.
`decd-scale-test.sh PHASE=scale` wedged the panel twice by mis-sizing exactly
these descriptors, so values come only from the Phase 0 formula, never hand-
picked.

## Phase 2 — scale to fit (the common case)

16:9 below 720p (640x360, 852x480, 960x540) fills the panel through proc with
**no borders and no positioning**. Port the retired chain onto the Phase 1
contract: proc input window = source, output 1280x720, ratios and phases from
the recipe, `+0x50` window, route windows (0111 order). Upscale only; the VE
does every downscale (mpv 0004 keeps asking for it).

Gate: card at 640x360 (exact 2x) and 852x480 (1.5x, non-integer), luma
geometry measured off the panel with `tools/display/measure-panel-photo.py`,
no grey streak, P010 at one size.

## Phase 3 — borders and centring (other aspects)

4:3 and other non-16:9 sources fit by height with bars left and right (or by
width with bars top and bottom). Program `PanelWinNode`'s border overlays
(black, limited range), and centre the picture by whichever Phase 0 found:
panel video-window position, proc output offset, or (worst case) top-left
placement with asymmetric borders, which is what the firmware itself did.

Gate: 352x288 (4:3 → 880x720 + 2×200 bars), 720x576 PAL, 1000x600; borders
measured on the panel; RGB/console restored cleanly afterwards.

## Phase 4 — the KMS contract

`atomic_check` accepts any NV12/P010(+LSB10) framebuffer up to the panel
size, with a source rect and a **destination rect that may be larger and
offset**. It rejects downscaling (that is the decoder's job), non-even sizes,
and anything the recipe cannot express, so a bad commit fails in check, never
in hardware. `atomic_update` programs AFBD, composition, proc and borders as
one transaction, in the order the firmware uses, with the same
read-modify-write discipline; a geometry change mid-stream is just a commit
with a different rect. Advertise the plane as scalable (`DRM_PLANE_NO_SCALING`
replaced by the real upscale range).

## Phase 5 — userspace

- **mpv:** patch 0003 refuses any source ≠ mode. Replace it with: compute the
  aspect-fit destination (mpv already does — `vo_get_src_dst_rects`) and pass
  it as the CRTC rect; keep the bounded-retry half of 0003. 0004 (ask the VE
  to shrink above 720p) stays. A size change re-runs `reconfig`, which must
  re-derive the rects.
- **kmssink:** probes plane scaling itself and letterboxes when the plane
  allows it — likely no patch; verify.
- **VA driver:** no change under H1. Under H2, panel-pitch capture surfaces
  (0018 makes that a local change).

## Phase 6 — end to end

- Panel, operator: `vp9-rc.ivf` (640x360 → 720p → 352x288 → 640x360) and HEVC
  `r01` through `mpv --vo=drm --hwdec=vaapi` — every segment fitted, the
  transitions clean, no refused commits in `dmesg`, fb id changing throughout.
- `rc.ivf` (AV1) is excluded: ffmpeg never renegotiates AV1, and its 1080p
  segments cannot be shown without a downscaler.
- Regression: `va-regress.sh` in both modes; native 1280x720 NV12/P010 still
  scans out unchanged (the same debugfs + `0x05600010` gate as 2026-10-01).

## Decisions for the operator

1. **Fit vs native size.** Recommended: aspect-fit with upscale (Phase 2/3).
   The alternative — native size, centred, black around it — skips proc but
   leaves 352x288 as a postage stamp on a projector.
2. **If H1 fails**, accept the panel-pitch canvas route (VA driver + cedrus
   COMPOSE + a CPU copy for the rest), or stop at 1280x720-only for AV1 and
   VP8.

## Risks

- Display wedges need a power cycle (USB unplugged); warm reboots kill this
  display. Budget one per panel session.
- Mis-sized composition descriptors starve the fetch — the reason Phase 0's
  formula must reproduce the live native state before anything is written.
- A refused-commit storm once faulted IOMMU master 2 and blacked the panel:
  Phase 4 rejects in `atomic_check`, and mpv's retry stays bounded.
- Never enable the video source with no frame behind it.
- `0x07091000` hard-locks the SoC on a read; nothing here touches it.
