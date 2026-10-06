# WP5 Phase 1: the hardware mirror on the glass, 2026-10-06

One operator session ([../mirror-plan.md](../mirror-plan.md)), in three runs. Each step was register pokes from the recipe (`letterbox-recipe.py --mirror`), applied by `letterbox-apply.py` with exact timed restores; it ran on kernel 0165.

| Run | What | Video |
| --- | --- | --- |
| 1 | `letterbox-test.sh mirror` | `local/lcd-photos/test_99/IMG_1030.MOV`. It stopped at the mid-run console (the holder switch), so it missed the primary half. |
| 2 | `letterbox-test.sh mirror-primary` | by eye only |
| 3 | `HOLD_S=15 letterbox-test.sh mirror-primary` | `local/lcd-photos/test_100/IMG_1032.MOV` |

Logs: `local/h713-lab/mirror-phase1-20261006{,-p2}/`.

**Mechanics.**
- Every write stuck; every mid-hold and end-of-hold recheck read 50/50 registers as written; every restore was exact.
- The board finished in its native state: selector RGB, OSD `03001901`, panel `80000000`, comp `+040` `02090208`.
- No kernel messages, no IOMMU faults, no wedge, no power cycle.

## Result: every prediction held, and the console route is decided

**Video plane** (NV12 card on AFBD source 0, the recipe in hardware terms; run 1):

| Step | Writes | Seen |
| --- | --- | --- |
| h | panel `0x0a0[0]` and vde −1 (comp 80c/840/858, proc +050, vblend 010/024) | flipped left/right, card intact |
| v | AFBD `0x010[3:2]=2`, comp `0x040[3]=0` (inside the NR hold) | flipped top/bottom |
| hv | both | rotated 180° |
| ch | 852x480 at hardware (0,0), plus H | at the **top right**, mirrored, black bars left and below. **So the vblender is upstream of the panel mirror**, and installation H needs no x remap |
| abv | 1280x536 at hardware (0,184), plus V | at the bottom, flipped, intact, **no magenta**. AFBD's ALIGN16 padding rows do not flip into view at a height that is not a multiple of 16 |

**Primary plane** (XRGB card from `letterbox-card --primary` on the OSD channel `0x05600140`, selector RGB; run 3):

| Step | Writes | Seen |
| --- | --- | --- |
| pv | OSD ctrl `[3:2]=2` (bit 3) and READY | flipped top/bottom |
| php | panel `0x0a0[0]=1` only | flipped left/right; top and bottom white frame lines intact |
| pho | OSD ctrl `[3:2]=1` (bit 2) and READY | **no effect**: the card stayed upright for the whole window |

**So the console route mirrors exactly as stock's design implies.**
- V comes from the fetch, through OSD control bit 3 (as stock `ge2d_dev.ko` sets it).
- H comes from the one global panel bit, which sits after the selector.
- OSD bit 2 is dead, despite U-Boot's 2-bit `mirror_mode` field.
- The RGB route gets no vde shift. In the photos, both frame lines looked intact under H. **The histogram later showed one row is lost** (see below); the photos could not resolve it.

## Measured afterwards: the panel histogram (2026-10-06)

There is no downstream frame CRC (`tools/display/panel-signature.sh`, read-only). There is, however, a luminance histogram at `lvds+0x378–0x3fc` whose bins count pixels. A correct mirror leaves it unchanged; a lost or garbage row moves 1280 pixels between bins.

| Case | Histogram |
| --- | --- |
| OSD V (bit 3), primary card | identical: **pixel-exact** |
| panel H, primary card (the RGB route) | `+0x380` gains 1280, `+0x3fc` loses 1280: **one white frame row turns black**. The photo verdict above ("no visible row loss") is **withdrawn**. |
| video H, recipe with vde −1 | identical to native (2 px in one bin: chroma pairing at patch edges) |
| video H without the vde shift | the same one-row loss |

The firmware's vde −1 is necessary and sufficient on the video route. **The RGB route needs an equivalent one-line advance**, which Phase 2 must find. The histogram tests each candidate without an operator.

## Consequences for Phase 2 (kernel)

- **Video plane:** transcribe the recipe as it stands. The kernel writes proc instance 0 only.
- **Primary plane:**
  - V = OSD ctrl bit 3 in the value `set_source()` writes each flip (`rgb_ctrl_active | BIT(3)`).
  - H = the panel bit while the primary owns the mux.
  - **One-line compensation needed** (histogram above). Its register is not yet known.
- **The panel bit is shared.** Whoever owns the mux writes it; `video_stop` hands it back to the primary's value.
- **No height rule for V.** A non-16 height flips cleanly, so `check` needs no `h % 16` refusal and the `h713-play` fit rounding stays.
- **Still open, for the Phase 2 gate:**
  - P010 under V (the card is NV12-only);
  - whether the panel bit latches on vsync or at once.

## Tooling notes

- **The mid-run console fooled the operator.** The holder switch shows the console for a few seconds, which looked like the "stop recording" cue. `mirror` now says so in its help, and `mirror-primary` runs the primary half alone.
- **`letterbox-measure.py --mirror` found every window at its log time**, but on real footage its edge finder lost the far edges (a 1280-wide card measured 717–910 wide). It also read the patches relative to those edges, so it read none. It now samples the patches at the expected rectangle. The run 1 verdicts above come from inspecting frames (contact sheet plus close-ups), not from the tool.
