# 0x05180000 is an UPSCALER — it cannot downscale. Route closed.

2026-09-11, cold boot, static test card on the DECD video plane, five stills
(`local/lcd-photos/test_85/`). Gates verified before any ratio was written;
all five readbacks confirmed; restore verified against pre-run values.

Geometry untouched throughout — `0x2c`/`0x30`/`0x34`/`0x40`, `ratio_v` and the
V phase were never written. Only bypass, `ratio_h` and the H phase moved.

## The result

| commanded | `ratio_h` | observed |
| --- | --- | --- |
| 1.000× | `0x10000` | baseline: digits 0–9 across the full width |
| 0.800× | `0x14000` | **identical to unity** |
| 0.667× | `0x18000` | **identical to unity** |
| 0.500× | `0x20000` | **identical to unity** |
| 2.000× | `0x8000` | **2× horizontal magnification**, ~4 digits fit, ticks twice as far apart |

- [digit-band-unity-vs-0x14000-vs-0x18000.jpg](digit-band-unity-vs-0x14000-vs-0x18000.jpg)
  — three bands stacked; digit positions, widths and the top-right corner marker
  are the same in all three.
- [digit-band-unity-vs-0x20000-vs-0x8000.jpg](digit-band-unity-vs-0x20000-vs-0x8000.jpg)
  — `0x20000` is indistinguishable from unity; `0x8000` is unmistakably doubled.
- [all-six-shots.jpg](all-six-shots.jpg), [card-reference.png](card-reference.png).

**`ratio_h` below unity magnifies by `1/ratio`. Above unity it does nothing.**
The field clamps at unity, so the block only ever enlarges.

> **`0x05180000` is an upscaler. It cannot produce 1920→1280, and it is not the
> lever for 1080p on a 720p panel. This route is closed.**

## Which the firmware said all along

- The stage table names them **`proc-vs_upscaler`** and **`proc-vde_upscaler`**.
- `ProcWinNode::CalcScaleRatio` only ever yields `unity × min/max`, i.e. **≤
  unity** — it has no way to express an above-unity ratio.
- So the firmware never asks this block to shrink anything, and the hardware
  does not implement it. The six integer bits above unity in the 22-bit field
  are unused, which is why arguing from the field width was never sound.

## A correction to my own method, not just my conclusion

The automated metric (digit width / row-digit height, chosen to cancel camera
distance) scored **m2 `0x14000` at 0.824× against 0.800× commanded — a false
positive**, and it would have been reported as a partial success. The visual
comparison refutes it: m2 is pixel-for-pixel the same framing as unity.

The metric's digit segmentation was unstable — run counts came out 10, 16, 15,
16, 8 across the five images, because the 7-segment glyphs break into separate
runs at different thresholds, so the medians were computed over different
feature sets. **The number agreed with the hypothesis by coincidence.**

What saved it was that the card carries redundant, independently readable
features. Digit *positions* and the corner marker are categorical — either
digit 9 is at the right edge or it is not — and they agreed across all three
above-unity shots. A single scalar metric would have produced a wrong answer
with a plausible-looking number attached.

## The card worked, and that is worth keeping

`0x8000` measured 1.913× against 2.000× commanded — a known-answer control that
validates both the card and the method. Compare that with the previous rounds,
where the factor had to be estimated from the width of a face and of an eye
slit, and where magnifying into a dark passage of the clip read as "nothing".

The cue frame also did its job: no timing model, no luminance trace, no
alignment reconstruction. Each still stands alone.

## Where that leaves the scaler search

| block | what it is | status |
| --- | --- | --- |
| `0x05000000` | composition / NR | **no scaler at all** (static, settled) |
| `0x05180000` | proc, two-axis, on our raster | **upscale only — closed today** |
| `0x051c0120` | panel down-scaler, **vertical only** | RGB path negative with the stage on; **video side never tested with the stage on** |
| `0x050c0000` | DETN block, 51 registers, 50 written | **never characterised** |

So there is no confirmed hardware *downscaler* on our path. Two things remain
before the no-GPU options are exhausted:

1. **`0x050c0000` is the largest uncharacterised block in the display pipeline**
   and has never been read for ratio-shaped registers. That is static work.
2. **The panel down-scaler's video-side test with the stage actually enabled.**
   It is vertical-only, so it cannot do `1920→1280` by itself — but a genuine
   `1080→720` vertical downscale would still be the first real downscale found,
   and it is one run.

Neither is a route to 1080p on its own. Worth saying plainly: if both come back
empty, the no-GPU downscale options are exhausted and the GPU path is what is
left.
