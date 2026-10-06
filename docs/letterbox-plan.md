# Letterboxing on the video plane — plan (revised 2026-10-04)

> **Phase 1, first run (2026-10-04): H1 HOLDS.** A sub-panel raster fetches
> cleanly at its own size and stride. Horizontal placement and the vertical
> start are right, the bars are black, and there is no magenta. All restores
> were exact, with no wedge. The vertical clip (b lost 73 lines, c 89) was
> bisected over three runs to **`comp+858[31:16]`, which must be the picture
> height, not 720** (fixed in the recipe, 2026-10-05). **The confirmation
> run PASSED (2026-10-05): a, b and c all whole and correctly placed. Phase 1
> is DONE; next is Phase 2 (kernel).**
>
> **Phase 2 (kernel 0161) VERIFIED ON HARDWARE, 2026-10-05.** Stock kmssink
> letterboxes scope, ultrawide, 4:3 and native-fit pictures on the plane,
> centred with black bars and correct colour, still and moving. A VE scaler
> chroma-placement bug is worked around by rounding scaled heights to 16
> (h713-play); the proper fix and an audio start-up click are separate tasks.
> **Next: Phase 3 (proc upscale for sources below 720p) and Phase 4 (the
> green flash on geometry changes, mid-stream size changes).**
> Details: [reference/letterbox-phase1-2026-10-04.md](reference/letterbox-phase1-2026-10-04.md).
>
> **Status 2026-10-04: Phase 0 done.** Desk RE and a read-only baseline:
> [reference/letterbox-recipe-2026-10-04.md](reference/letterbox-recipe-2026-10-04.md),
> `tools/display/letterbox-recipe.py` and `tools/display/letterbox-baseline.py`.
> The operator took all four recommended decisions (below). **Next: Phase 1**,
> one operator session.

> Replaces the 2026-10-01 version, which was deferred on 2026-10-02 behind the
> GPU fallback ([gpu-fallback-plan.md](gpu-fallback-plan.md)). **What changed:**
> WP4 put stock `kmssink` on the video plane (`h713-play` plane-native and
> plane-ve). That route uses about 8% of the whole board's CPU with the GPU
> idle; the GPU path uses about 17%. Every source the plane refuses *only
> because of its geometry* therefore costs about 9 points of CPU plus the GPU.
> This plan removes that refusal. The GPU path stays the fallback for
> everything listed here as out of scope.

## Goal

Show any decoded picture up to 1280x720 on the video plane at its aspect-fit
rectangle, with black bars, so that **stock `kmssink` letterboxes unpatched**.
It already computes a centred aspect-fit destination. If the plane refuses that
destination, it permanently drops scaling and retries centred at native size
(`gst_kms_sink_show_frame`, gst-plugins-bad `sys/kms/gstkmssink.c`). All of the
missing work is on the kernel side.

**In scope:** NV12 and P010 (+LSB10), sources up to the panel size, placement
anywhere on the panel, magnification through the proc upscaler.

**Out of scope:**
- downscaling in the display. None exists; the VE downscales H.264/HEVC and the GPU does the rest;
- 90/270° rotation;
- OSD or subtitles over video;
- keystone.

## What it buys

| Content | Today | After Phase 2 (placement) | After Phase 3 (upscale) |
| --- | --- | --- | --- |
| H.264/HEVC above 720p, not 16:9: scope films (1920x800), 1.85:1, 4:3 (1440x1080), 2560x1080 | GPU | **plane-ve**: the VE scales to the fit size, the plane centres it | — |
| Any codec below 720p: 480p/576p DVD (anamorphic SAR included), 360p web | GPU | GPU (native size would be a postage stamp) | **plane-native**: proc magnifies to fit |
| 720 lines high, not 16:9 (960x720) | GPU | plane-native, centred | — |
| VP9/AV1 above 720p, 10-bit above 720p, 90/270° rotation, subtitles | GPU | GPU | GPU (VP9 moves when WP6 lands) |

Phase 2 is the first shippable step. It covers the commonest case, because
most films are not 16:9.

## Established facts (do not re-derive)

| Fact | Source |
| --- | --- |
| **Production boot parks the MIPS** (`auto 0x34 logo` quiesces it). Our driver programs AFBD directly, and the composition, proc and panel blocks stay as U-Boot left them for 1280x720. Nothing letterboxes for us: our driver must write every register this plan needs. | `docs/status.md` (boot-mode table), `docs/mips-window-layer-plan.md` |
| The plane today: `h713_afbd_video_atomic_check` accepts a src of exactly 1280x720 at the origin, an identical dst, and pitch 1280. The fb may be taller (hantro's 1280x768). | `drivers/gpu/drm/tiny/sun50i-h713-afbd.c` (0078, 0149) |
| `mode_config.min_width/height` are set to the panel size (0063). DRM therefore refuses to create a smaller framebuffer at all, and kmssink's caps (`res->min_width..max_width`) exclude it. **Lowering the minimum without accepting the result in `atomic_check` only moves the failure from negotiation to commit** (0063's own comment), so the two changes ship in one patch. | `patches/kernel/0063-*` |
| The DT node maps `afbd` `0x05600000+0x400`, `route` `0x05140000+0x1000` and `lvds` `0x051c0000+0x100`. **Composition `0x05000000` is unmapped, proc `0x05180000` is unmapped (0098 added it), and `lvds` stops at `+0x100`**, so the panel down-scaler (`+0x120`) is outside it, and the border overlays may be too. Any of these changes the DTB, which means a FIT flash and a power cycle. | `patches/kernel/0098-*` (DT hunk) |
| The firmware's 852x480 numbers (2026-09-05): AFBD `0x05600030 = 0x01E00354`, composition `0x05000174/0x274 = 0x002B002B`, borders `top 0 bottom 240 left 0 right 428`. NR logged `y:1280, c:1280` next to `y_width:852`, so stride and width are separate inputs. **This state was computed with the MIPS alive and never reached the glass:** the LVDS selector stayed on RGB. It is the firmware's arithmetic, not a known-good picture. | `docs/reference/scaler-engaged-2026-09-05.md` |
| In the same capture, `m_video_win_2 = [49, 22, 852, 480]`. The firmware itself put this one top-left. **Resolved 2026-10-04:** (49, 22) is the panel-timing origin. Placement is an offset added to the NR output origin; proc follows it; the panel's program window stays fixed; the bars are a border overlay in the vblender `0x05200000`. | `letterbox-recipe-2026-10-04.md` |
| The composition block holds the AFBD fetch line-buffer descriptors (Rowbyte / LineBufLevel / LineNumber, Y and C). Only `NRWinNode::WriteReg` writes them, with the formula in `FrameBuffer::GetPsuPfuWin` (`0x8b1a2668`). **Mis-sizing them starves the fetch and wedges the panel until a power cycle**: `decd-scale-test.sh PHASE=scale` did it twice. | `docs/reference/composition-ratio-registers-are-line-buffers-2026-09-10.md` |
| Proc `0x05180000` (instances 0/1) is an **upscaler only**: input window `+0x34`, output `+0x2c/+0x30`, ratios `+0x08/+0x3c`, phases, V line-enable window `+0x50 = [27, max(in_h, out_h)]`. It was hardware-clean at 960x544, 1280x544 and 960x720 → 1280x720. Its upper bits are live, so always read-modify-write. Outside its input window the panel shows a **flat grey fill**. | (memory note `two-axis-scaler-0x05180000`), `proc-scaler-video-2026-09-11/RESULT.md` |
| With the composition descriptors **left at 1280**, a smaller AFBD raster wraps the picture three times and fills green. 0106 therefore kept AFBD at a native 1280x720 raster and moved only the proc input window. **That negative was never tested with matching descriptors.** The 09-12 shear ("the consumer steps 1280 pixels per line") matches NR's fetch window, `0x05000804/0844/085c`, which reads 1280 live. The 09-12 dump stopped at `comp+0x2ff`, so those registers were never dumped or poked (2026-10-04). | `patches/kernel/0106-*`, `handoff-2026-09-14-video-scaler-and-rotation.md` §4, `letterbox-recipe-2026-10-04.md` |
| The retired chain (0098, 0103, 0105, 0106, 0108, 0111) is still in `patches/kernel/`, out of series. Each patch has a reopen header, and all six were hardware-clean when they were dropped. They come back together or not at all. | `docs/handoff-2026-09-23-retire-display-scaling.md` |
| The AFBD fetch budget (the high halves of `+0x30/+0x48/+0x4c`) derives from pitch × rows. **A budget larger than the buffer reads past its end**, which means an IOMMU master-2 fault and a black panel. | driver comment at `H713_VIDEO_FMT_SHIFT`, (memory note `iommu-master2-flip-ordering`) |
| **`scanout-grab` and `geometry-grab.sh` cannot see this work.** They read the framebuffer, so on the video plane they show the source picture whatever the hardware does with it. Hardware placement is visible only on the glass. | `tools/display/scanout-grab.c` header |
| `measure-panel-photo.py` rectifies on the *card's* border, which it assumes is the whole panel. A letterboxed card breaks that assumption. | its docstring |
| Stock never letterboxes in hardware for file playback; it does so on the GPU, with grey bars. The window layer's aspect handling (`TWindowManager::SetAspectRatio`) serves the capture inputs (HDMI-in, CVBS, DTV). Those are the only place a centred hardware letterbox is known to ship. | `docs/reference/stock-capture-2026-10-01.md`, `mips-wce-window-layer-2026-09-04.md` |

## Approach

**Primary route: display-side placement.** One mechanism serves every codec
and every producer, and stock `kmssink` letterboxes by itself once the plane
accepts a destination rectangle. The risk sits in the composition
descriptors, which is why Phase 0 exists.

**Fallback, if Phase 1 shows AFBD cannot fetch a raster smaller than the
panel: a decoder-side canvas.** The VE writes the fit-size picture into a
black-filled 1280x720 buffer at the centring offset; 0107 already separates
COMPOSE from the capture canvas.
- **Gain:** it carries no display risk, and the plane contract stays exactly as it is today.
- **Costs:**
  - H.264/HEVC only;
  - the VA driver must fill the borders black in every capture buffer;
  - the offset is bounded by the VE's output-address granularity. The TOP1 block takes `(addr >> 10) << 2` at `+0xe4`, which may allow only row offsets, i.e. letterbox but no pillarbox (Phase 0 checks);
  - it does nothing for content below 720p. Upscaling would then need the canvas plus 0106's native-raster proc route.

## Phase 0 — desk work and read-only baseline (no writes)

1. **Composition formula** (`NRWinNode::WriteReg`, `GetPsuPfuWin`). Derive all
   ten descriptors (`0x0f0, 0x174, 0x178, 0x1b4, 0x1b8, 0x210, 0x274, 0x278,
   0x2b4, 0x2b8`) as a function of width, height, stride and format (NV12 and
   P010). It must reproduce 1280 → `0x40` and 852 → `0x2B`, with the stride
   (1280) and width (852) entering separately, as NR logged them.
2. **Placement and borders** (`PanelWinNode::CalcWindow`,
   `WriteBorderOverlay1/2`, `m_video_win_2`). Find:
   - which registers carry the window origin;
   - border width and colour encoding, and whether black is RGB `0,0,0` or limited-range YUV at that stage;
   - whether a centred window is expressible.

   Follow `SetAspectRatio`'s path for the capture inputs, the centred case the
   firmware actually ships. Method: find the log line that prints each field
   first (that cracked the composition block). MIPS address = ARM + `0xB5000000`
   (memory note `mips-firmware-address-map`).
3. **Proc.** Find the register behind the grey fill colour, any output offset,
   and the window *start* fields: `+0x50`'s high half and the 0111 route
   windows. The stock H-mirror recipe moves `+0x50` by one line
   (`stock-capture-2026-10-01.md`), which shows how a start is expressed.
4. **AFBD.** Work out:
   - `SIZE_M1`/`BLOCK_M1` semantics for sizes that are not multiples of 16 (the firmware programmed 852 wide);
   - the budget formula for a source rectangle;
   - stride ≠ width: cedrus pitch is `ALIGN(w, 32)` (0125), and hantro has its own.
5. **Alignment table.** For each stage (VE scaler output, cedrus capture, AFBD,
   composition, proc, panel borders), the W/H/x/y granularity it accepts. The
   result is the single rule that `atomic_check` enforces and that `h713-play`
   rounds fit sizes to: 1920x800 fits as 1280x533.3, so 536 or 544 (about 0.5%
   aspect error, invisible).
6. **Recover the retired chain** into the recipe, re-based on today's driver
   (0149 formats and P010 budgets).
7. **Read-only baseline.** With native 720p on the panel, dump `0x05000000`,
   `0x05140000`, `0x05180000`, `0x051c0000` and `0x05600000` (known-safe
   ranges only; never `0x07091000` or `0x06940000`). Check every value against
   what the formulas predict for 1280x720. **A formula that does not reproduce
   the live native state does not drive a write**
   (memory note `diff-against-known-good-first`).
8. **Tooling.**
   - `tools/display/letterbox-recipe.py SRC_WxH DST_X,Y,WxH FMT` prints every register and value with its provenance. The kernel patch transcribes the same arithmetic, and the tool is self-tested against the known points (native 1280x720, firmware 852x480).
   - **Geometry from photos.** For measurement runs, program the border fill to a visible test colour, so the panel edge and the picture edge appear in one photo. Teach `measure-panel-photo.py` to rectify on the panel corners. If the fill colour turns out to be fixed, use a tripod and a full-panel control shot instead.
   - **Register self-check.** A driver debugfs file, `video_geometry`, dumps the committed src/dst and every geometry register; a script diffs it against the recipe after each commit.

**Deliverable:** `docs/reference/letterbox-recipe-<date>.md`. For a source W×H
and a destination rectangle, it lists every register and value, each with its
provenance.

**Exit gate:** the recipe reproduces the live native state, and it names a
placement mechanism, or shows that there is none. "None" selects the canvas
fallback for Phase 2.

**Outcome (2026-10-04).** The exit gate is met. The full record is in
[reference/letterbox-recipe-2026-10-04.md](reference/letterbox-recipe-2026-10-04.md).

| Item | Result |
| --- | --- |
| 1 Composition | Formula with flag-gated groups, A = B descriptors; Rowbyte = LineBufLevel = `ceil(W/20)`. It fits the live 1280 and the firmware's 852, but is not derived for P010. NR's **fetch window** `0x804/808/80c/840/844/858/85c` is new, and its width is the 1280-pixel line step the 09-12 shear measured. |
| 2 Placement and borders | Placement = an offset added to the NR output origin (49, 22); proc and panel follow. The bars are the vblender border overlay `0x05200000/004`. **The colour is not programmable from anything the firmware writes; Phase 1 observes it.** |
| 3 Proc | At unity it carries the stream position (`+044`, `+02c[31:16]`, `+050[31:16]`). Every route window starts at (0, 0). The grey fill is irrelevant when the windows match. |
| 4 AFBD | Firmware formula confirmed. **The stride must be a multiple of 16 samples, and the buffer must cover `ALIGN16(W) × ALIGN16(H)`.** |
| 5 Alignment | Even W/H, even x; the stride rule above. Fit sizes need not be multiples of 16, provided the buffer covers the block-aligned read. |
| 6 Retired chain | Deferred to Phase 3 (upscaling only). |
| 7 Baseline | 1182 words, console and native 720p, no faults. The model reproduces all 42 registers, and five mutations each fail the self-test. **DETN `0x050c0000` holds a 720-wide capture configuration, so it is bypassed for our raster.** |
| 8 Tooling | `letterbox-recipe.py` and `letterbox-baseline.py` are done. The bar colour cannot be set, so measurement became handheld video rectified on the control-card frames either side of each step (`letterbox-measure.py`, Phase 1). The debugfs `video_geometry` file moves to Phase 2. |

The firmware's **write protocol** is: NR hold (`comp+040[25]=0`,
`+860[17]=1`, `+138[27]=1`), then geometry, then NR release (the reverse, plus
`+82c=1`), then proc, then panel. `decd-scale-test.sh PHASE=scale` wrote no
bracket.

**The stock HDMI-in capture is not needed** (decision 1). Placement is
resolved; only the bar colour is open, and Phase 1 shows it.

## Phase 1 — the source contract (one bounded panel test)

> **Tooling ready, 2026-10-04; no step has written to hardware yet.**
>
> | Piece | Role |
> | --- | --- |
> | `letterbox-test.sh` | host orchestrator |
> | `letterbox-card.c` | holds the control card through KMS, with the step cards pre-rendered in the same buffer; magenta padding |
> | `letterbox-apply.py` | on-board executor: preflight, firmware order, read-back, detached timed restore |
>
> On the board, `prep`, `card` and `plan a|b|c` passed:
> - the control card is on the plane, and all 42 recipe registers match the reference baseline;
> - all three dry runs pass preflight;
> - the plane was released afterwards.
>
> Raw output is in `local/h713-lab/letterbox-phase1-20261004/`.
>
> **One "ready" runs the whole session** (operator request: one person, holding the phone, cannot go back to the keyboard between steps). `letterbox-test.sh all` does the following:
> 1. brings the card up and runs the checks;
> 2. gives `LEAD_S`=30 s to get into position;
> 3. runs z, a, b and c back to back in one detached `letterbox-apply.py --sequence` (10 s each, 5 s of control card between). The sequence stops at the first refusal, failure or incomplete restore;
> 4. releases the plane, so the console coming back is the cue to stop recording.
>
> `plan all` dry-runs the sequence and passes on the board. `letterbox-measure.py VIDEO` segments the single video **by time order** (not by best template, which would pass a misplaced b as a correct a). It calibrates its edge bias on each control frame. Self-test: all edges within 1.8 px; a misplaced b is reported −92 px.

`tools/display/letterbox-test.sh`, in the style of
`composite-route-test.sh`. It writes a recipe from
`letterbox-recipe.py --live native-720p.txt` against a heap buffer holding a
static card (`kms-p010-plane-test` with `W=`/`H=`). One axis changes per step:

| Step | Picture | Stride | Placement | What changes |
| --- | --- | --- | --- | --- |
| z | 1280x720 | 1280 | (0, 0) | nothing: every value rewritten as it is. It exercises source off/on, the NR bracket and the restore, so it runs first and the card should blink and come back identical |
| a | 1280x536 | 1280 | (0, 0) | height only: AFBD, descriptors, fetch h, borders bottom 184 |
| b | 1280x536 | 1280 | (0, 92) | vertical offset: NR y, proc `+050` start, borders 92/92 |
| c | 852x480 | 864 | (214, 120) | width and horizontal offset: fetch w and x, proc x, borders 214/214/120/120 |

Each step works like this:
1. Save every register the recipe touches.
2. Stop source 0.
3. Write in the firmware's order: NR hold, AFBD, comp, NR release, route+proc, lvds, vblender.
4. Start source 0 with the card's frame queued.
5. Hold 10 s.
6. Restore every saved register in reverse order, then restore native 720p.

The buffer covers `ALIGN16` rows, so steps a and b allocate 544 lines.

- **H1 (pass):** the card is intact and placed where the recipe says. Phase 2 goes ahead as written.
- **H2 (fail, wrapped, sheared or green):** check `0x05000858[31:16]` first (open item 2 in the reference). Then take the canvas fallback for Phase 2, and 0106's native raster plus the proc input window for Phase 3.

**Operator questions, asked before each window opens:**
- Is the card intact, with circles round and no shear?
- Where does it sit?
- What colour are the bars, and do they match the card's black?

**Measurement: handheld video, no tripod** (`tools/display/letterbox-measure.py`).
Film each step from a few seconds of control card, through the window, to a
few seconds after the card returns.
- The control-card frames just before and just after the window are tens of milliseconds from the first and last step frames, so the hand has not moved.
- Each step frame is rectified on the panel corners from its neighbouring control frame, and the picture's white frame is measured in panel pixels.
- The before and after estimates disagree by the hand-motion error.

The synthetic self-test resolves about ±3 px. The tool also reports magenta
padding (validated on the card renders: exact, no false hits) and the bar
brightness, and saves rectified frames for inspection.

**Safety:**
- the operator look gets its own turn, and the operator is prompted before each window;
- confirm the logo is visible first, then the positive control (native 720p card);
- one write sequence per step, each with a timed restore;
- stop at the first wedge;
- budget one power cycle, with serial and USB unplugged and the board off for at least a minute (memory note `cold-boot-means-serial-unplugged`).

## Phase 2 — placement at unity (first shippable)

**Kernel** (one patch, plus the DT ranges named above):
- Lower `mode_config.min_width/height` to the smallest size the recipe supports, in the same patch as the `atomic_check` change.
- **`atomic_check`** accepts:
  - NV12 or P010 (+LSB10);
  - a src rect covering the visible picture, no larger than the panel;
  - **a dst the same size as the src (still `DRM_PLANE_NO_SCALING`), anywhere fully on the panel**;
  - sizes and positions on the alignment rule;
  - a stride the recipe can express;
  - a fetch budget that fits inside the buffer object.

  It rejects everything else with `-EINVAL` in check, never in hardware.
- **`atomic_update`:**
  - **A geometry change** stops the source, programs AFBD, composition, placement and borders in the firmware's `WriteReg` order, then starts again with the new frame already queued. Never enable the source with no frame behind it.
  - **Same-geometry flips** keep today's address-only path.
- **Borders are black.**

**Userspace:**
- `h713-play`: any H.264/HEVC source whose fit is no larger than the panel takes plane-ve, with `V4L2_REQUEST_SCALE` set to the rounded fit size. `gst-plane-play`'s probe already rewrites caps, meta and PAR (1:1). A 720-line non-16:9 source takes plane-native.
- `kmssink` stays unpatched. For a VE-fit size, its scaled attempt *is* the unscaled one, so its fallback never runs.
- `patches/mpv` is untouched. The direct mpv path is opt-in and a retirement candidate.

**Gate:**
- Clips:
  - 1920x800 H.264 → 1280x536, bars 92/92;
  - 1440x1080 HEVC → 960x720, bars 160/160;
  - 2560x1080 → 1280x540;
  - a 960x720 native card.
- Geometry measured from handheld video with `letterbox-measure.py`, then one operator look at the bars.
- Native 1280x720 NV12/P010 unchanged: debugfs, `0x05600010` and a changing fb id.
- Zero refused commits and zero IOMMU faults.
- A 10-minute `plane-soak.sh` run on a scope clip, then its CPU against the GPU path on the same clip.

## Phase 3 — upscale to fit (sources below 720p)

Port the retired chain (0098, 0103, 0105, 0108, 0111, plus 0106 only under H2)
onto Phase 2's contract:
- proc input window = src, output = dst size;
- ratios and phases from the recipe;
- `+0x50 = [27, max(in_h, out_h)]`;
- read-modify-write throughout.

`atomic_check` then allows magnification only. DRM's scale factor is src/dst
in 16.16, so `min_scale = 0x10000 / (proc's largest magnification)` and
`max_scale = 0x10000`.
Anamorphic SAR is just unequal H/V ratios, which proc has.

Routing: sources below 720p take plane-native through stock
`v4l2sl*dec ! kmssink`. kmssink's first, scaled `SetPlane` now succeeds.

**Gate:**
- 640x360 (2x);
- 852x480 (1.5x, non-integer);
- 352x288 → 880x720 with 200-pixel bars;
- 720x576 SAR 16:15 → 960x720;
- 720x480 SAR 32:27 → 1280x720;
- P010 at one size;
- no grey streak, and photo geometry within one pixel row/column of the recipe.

## Phase 4 — mid-stream changes and hardening

- **Size changes mid-stream:** `vp9-rc.ivf` (640x360 → 1280x720 → 352x288) and HEVC `r01`.
  - Each transition is one geometry commit.
  - At most one black frame per transition, and no refused commits.
  - AV1 `rc.ivf` is excluded: ffmpeg never renegotiates AV1.
- **Geometry stress:** a script that alternates sizes every few frames for 10 minutes. Pass is zero IOMMU faults with the panel still alive.
- **Refusals:** too-small buffers, odd sizes and off-panel offsets are all refused in check.
- **The WP5 hardware mirror:** placement is computed in panel coordinates and mirrored by the driver (an H mirror maps x to 1280 − x − w). Design the state now; test it when WP5 lands.
- **2-hour soak** of a scope film through plane-ve.

## Phase 5 — routing, documents, rootfs

- `h713-play`'s routing table, the routing table in `gpu-fallback-plan.md`, `roadmap.md` and `status.md`.
- Regression:
  - `va-regress.sh`;
  - the native NV12/P010 scanout gate;
  - the GPU path, which uses the primary plane and must be unaffected.

## Verification on this path

- **Geometry comes from handheld video, never from `scanout-grab`** (see the facts table). `letterbox-measure.py` rectifies each step frame on the control-card frames either side of the switch, so no tripod is needed. Then one operator look at the bars.
- **Registers:** after each commit, diff debugfs `video_geometry` against the recipe.
- **Liveness:** debugfs, a changing fb id and `0x05600010`, never DRM plane accounting alone (memory note `two-axis-scaler-0x05180000`).
- **Every playback check records** the route, decoder IRQs and GPU IRQs. GPU IRQs must stay at 0; anything else means the run silently fell back to the GPU (memory note `passing-suites-that-cannot-fail`).

## Decisions (operator, 2026-10-04: all recommendations taken)

1. **Known-good stock capture:** only if Phase 0 left placement or the bar
   colour open. **Outcome:** not needed. Placement is resolved, and Phase 1
   shows the colour.
2. **Sources below 720p:** fit with upscale (Phase 3).
3. **Bar colour:** black. The firmware writes no colour, so Phase 1 decides
   whether the hardware default is black. If it is not, finding a fill
   register is a precondition for Phase 2.
4. **If H1 fails:** the canvas fallback for H.264/HEVC.

## Risks and standing rules

- Display wedges need a power cycle; warm reboots kill this display. Budget one per panel session.
- Composition values come only from the Phase 0 formula, never by hand.
- The fetch budget never exceeds the buffer. A refused-commit storm once faulted IOMMU master 2 and blacked the panel. Kernel 0158's master reset is called only by cedrus, so nothing recovers the display's master.
- Never enable the video source with no frame behind it.
- Proc registers have live upper bits, so read-modify-write them. `busybox devmem` prints uppercase hex.
- Never read `0x07091000` (hard-locks the SoC) or `0x06940000`.

## Cost

| Phase | Work | Operator looks | Power cycles budgeted |
| --- | --- | --- | --- |
| 0 | Desk RE and tooling, 1–2 sessions | 0 | 0 |
| 1 | One script | 1 | 1 |
| 2 | Kernel patch, DT, `h713-play` | 2 | 1 (FIT flash) |
| 3 | Port the retired chain | 2 | 1 |
| 4 | Stress and soaks | 1 | — |
