# Letterbox Phase 1, first run (2026-10-04)

`tools/display/letterbox-test.sh all`, one handheld iPhone video
(`local/h713-lab/letterbox-phase1-20261004/video/IMG_0988.MOV`, not tracked),
log `local/h713-lab/letterbox-phase1-20261004/all.log`. The plan is
[letterbox-plan.md](../letterbox-plan.md) Phase 1; the recipe is
[letterbox-recipe-2026-10-04.md](letterbox-recipe-2026-10-04.md).

## Mechanics: clean

All four steps (z, a, b, c) did the following:
- preflighted against the baseline;
- wrote their whole recipe with every readback matching;
- held for 10 s;
- restored every register to its saved value.

`SEQUENCE COMPLETE`, with no kernel messages and no wedge. The console came
back and no power cycle was needed. Step z (rewrite everything as it is) left
the card unchanged. **The firmware's NR hold/release bracket, source off/on,
slot repointing and the restore all work from Linux with the MIPS parked.**

## Geometry

Each window's frames were rectified on the control-card frame just before it,
then measured with edge profiles across the card. The measurement resolves
about ±3 px.

| Step | Expected (x, y, w, h) | Measured | Verdict |
| --- | --- | --- | --- |
| a | 0, 0, 1280, 536 | 0, 4, 1278, 535 | **pass**: intact, bar below |
| b | 0, 92, 1280, 536 | 2, 92, 1277, **463** | top, x and width right; **bottom 73 lines clipped** |
| c | 214, 120, 852, 480 | 216, 122, 848, **391** | x, y and width right; **bottom 89 lines clipped** |

The pictures are intact wherever they are shown: no shear, round circles,
straight diagonals, chroma aligned. The operator saw **black bars**, and the
tool counts **zero magenta**, so the display never shows padding.

**What this settles:**
- **H1 holds.** AFBD fetches a raster at the picture's own size and the producer's stride (step c: stride 864, 852 wide), once the NR fetch window and descriptors match. 0106's "only a 1280x720 raster" contract is dead.
- **Horizontal placement works, and so does the vertical start.**
- **The bars are black by default.** No fill register is needed (decision 3).

**What is open: something clips the bottom of a vertically offset picture.**
Two points fit a bottom edge near panel line `H − 27 + dy/2`. That
half-rate dependence on dy doesn't fit any single register left unshifted
(which would clip at a fixed line), so it is not derived. Step a (dy = 0)
loses nothing.

## Also seen

**A green flash at each transition** (operator). Solid green has meant
"fetching nothing" on this hardware before, so this is the source-off
interval: about 30 ms per transition in the log. It is cosmetic, but Phase 2's
geometry change should avoid it, for instance by switching the selector to
RGB or blanking while the source is off.

## Next

`letterbox-test.sh bisect`, one recording: step b repeated with one vertical
candidate changed per window:

| Variant | Change |
| --- | --- |
| b0 | none (reproduces the clip) |
| b1 | proc `+050` length H + dy |
| b2 | proc `+050` = [27, H + dy] |
| b3 | panel video window height H + dy |
| b4 | NR fetch heights H + dy |

Every variant stays within the native configuration's last line. The dry run
passes on the board.

## Tool lessons, from real footage

- **Plain correlation failed.** The projector's brightness falloff dominated it, scoring the control card 0.29; a high-pass correlation of line structure scores it 0.81.
- **Windows must have control frames on both sides.** The walk-up at the start and the console at the end are not windows.
- **The edge-bias calibration on control frames is unreliable** under falloff, so an implausible calibration is dropped. The full-width w/h readings of `letterbox-measure.py` are not yet trustworthy on real footage. Its origins, the heights of offset pictures and the narrow-picture numbers agree with manual profiles; use those, and the rectified frames it saves.

## Bisect set 1 (2026-10-05): all negative

Video `local/h713-lab/letterbox-phase1-20261005/video/IMG_0989.MOV`. Every
variant clipped identically: top at about 93, about 461 of 536 lines visible.

| Variant | Change | Effect |
| --- | --- | --- |
| b0 | none | clip reproduced |
| b1 | proc `+050` length H+dy | none |
| b2 | proc `+050` start unshifted | none |
| b3 | panel video window height H+dy | none |
| b4 | NR fetch heights H+dy | none |

None of these fields limits the picture height here; proc at unity evidently
ignores its V window.

**New lead.** The extra black below the picture is 73 lines (b, top bar 92)
and about 88 (c, top bar 120): it grows with the TOP offset. The only thing
that paints black is the vblender border overlay, and black over black hides
any error in its top field. Set 2 (`BISECT_SET=2`, the default) reverts one
dy-shifted field per window to native:

| Variant | Field reverted |
| --- | --- |
| b1 | border overlay |
| b2 | comp `+80c` y |
| b3 | comp `+858` y |
| b4 | comp `+840` y |

## Bisect set 2 (2026-10-05): the window ends early; not the overlay

Video `IMG_0990.MOV`, with measurements and frames in `local/h713-lab/letterbox-phase1-20261005-set2/measure/`.

| Variant | Field reverted to native | Seen |
| --- | --- | --- |
| b0 | none | clip reproduced; bottom edge about panel 556 |
| b1 | border overlay (zero borders) | **same clip**. The 92 lines above the picture show striped garbage, and the whole card is green-tinted. The overlay hides junk the NR outputs before the picture, and it also affects colour. |
| b2 | comp `+80c` y | no effect |
| b3 | comp `+858` y | top unchanged; **bottom edge moves up to about 535** |
| b4 | comp `+840` y | **card scrolls**: fetching starts at the native line, so the bottom ruler shows and then a green line (AFBD out of data). The window still ends at about 555. |

**Reading.**
- `+840` y is where fetching starts.
- The picture sits inside an NR output that runs from the frame top, and that output ends early.
- `+858` y moves the end. Nothing so far explains its length.

**Set 3** (`BISECT_SET=3`) tests the remaining line counts:

| Variant | Change |
| --- | --- |
| b1 | channel-B LineNumber H+dy |
| b2 | comp `+858[31:16]` = H |
| b3 | comp `+858[31:16]` = 720+dy |
| b4 | AFBD fetch budgets H+dy (reads past the card, but stays inside the buffer object) |

## Bisect set 3 (2026-10-05): FOUND. `comp+858[31:16]` is the picture height

Video `IMG_0991.MOV`, with measurements in `local/h713-lab/letterbox-phase1-20261005-set3/measure/`.

| Variant | Change | Visible height |
| --- | --- | --- |
| b0 | none | 461 (clip) |
| b1 | channel-B LineNumber H+dy | 461–463 (no effect) |
| **b2** | **`comp+858[31:16]` = H (536)** | **533: the whole card, bottom ruler and all four patches, bars above and below** |
| b3 | `comp+858[31:16]` = 720+dy | 460 (no effect) |
| b4 | AFBD budgets H+dy | 461–465 (no effect) |

This closes open item 2 of the recipe document. `para[0]` in
`NRWinNode::CalcWindow` (`0x8b1a3934`) is the **picture height**, and equals
720 only for a native picture. `letterbox-recipe.py` now writes it (an `abs`
field), and its self-test still reproduces the live native state.

**Next:** a confirmation run of `letterbox-test.sh all` (z, a, b, c) with the
corrected recipe. b and c should now show whole.

## Confirmation run (2026-10-05): PHASE 1 PASSES

`letterbox-test.sh all` with the corrected recipe. Video `IMG_0992.MOV`, with
logs and frames in `local/h713-lab/letterbox-phase1-20261005-confirm/`. All
four steps restored exactly; no wedge.

| Step | Expected | Measured | |
| --- | --- | --- | --- |
| a | 0, 0, 1280x536 | full card at the top, bar below (by eye; the tool's edge finder fails on pictures that touch the panel edge) | pass |
| b | 0, 92, 1280x536 | y 94–96, 533–535 lines | pass |
| c | 214, 120, 852x480 | x 215–217, y 121, 478 lines (width reads 846–848; the tool shows the same shortfall elsewhere) | pass |

All three cards are whole and undistorted, the bars are black, and there is
no magenta. **H1 holds and the recipe is hardware-correct for unscaled
placement.** Phase 2 (the kernel `atomic_check`/`atomic_update` and DT
changes) can transcribe `letterbox-recipe.py`.

Carry into Phase 2:
- the border overlay must stay programmed: zero borders show garbage above the picture and turn it green;
- the source-off transition flashes green, so blank around geometry changes;
- the NR hold/release bracket and the slot/geometry ordering as in `letterbox-apply.py`.

## Phase 2 on hardware (kernel 0161, 2026-10-05)

- **Boot:** the probe snapshot matches the native model; "video plane: pictures up to the panel size, placed anywhere (letterbox)"; DRM minimum 64x64.
- **Headless:** kmssink, unpatched, centres every picture by itself.
  - scope 1920x800 → 1280x528 at (0,96);
  - ultrawide 2560x1080 → 1280x544 at (0,88);
  - 4:3 HEVC 1440x1080 → 960x720 at (160,0);
  - native 960x720 at (160,0).

  1280x720 native and 1080p plane-ve are unchanged. There were 0 drops and no kernel messages.
- **Found and fixed on the way:** VE-scaled heights that are not a multiple of 16 (534, 536, 540) put chroma in the wrong place: colour shifted up and a green band at the bottom. `scanout-grab` showed the fault is in the buffer, not the display: a native 534 is clean.
  - **My first diagnosis was wrong.** I blamed the VE ignoring its chroma address and worked around it by rounding heights in h713-play (5859c4b).
  - **The real cause** (found by its own task, e28325d): GStreamer va exports surfaces before the first decode, and the VA driver sized that export on a throwaway cedrus instance with no scaling, which padded the height to 16. So chroma was exported at pitch×544 but written at pitch×534.
  - **The fix:** libva 0015 (pre-decode export uses the decode's own CAPTURE request) plus kernel 0162 (pad the scaled sizeimage for the plane's 16-line chroma fetch). The rounding is removed.
  - **Re-verified 2026-10-05 with the real fix:** scope 1280x534 at (0,93), ultrawide 1280x540 at (0,90), 0 green rows, chroma on its luma (scanout grabs `fx-card-*.png`).
- **Operator, card re-run (with scanout references in `local/h713-lab/letterbox-phase2-20261005/rerun/`):** all four pictures look correct.
- **Moving content (2026-10-05, with the rounding workaround still in place):** operator saw all correct. Four moving `testsrc2` clips (native 1280x720 control, scope, ultrawide, 4:3) were each grabbed six times (`local/h713-lab/letterbox-phase2-20261005/move/`), with 0 drops and 0 underruns.
  - The earlier "doubled diagonal" was two things. The pattern draws its band bouncing off the edges, so it shows two segments in a software render too. And during the 534/536 fault the band's colour sat 16–20 lines above its luma, a real second diagonal, removed by the height rounding.
- **PHASE 2 VERIFIED ON HARDWARE.**
- **Open, separate task:** audio clicks at clip start.
