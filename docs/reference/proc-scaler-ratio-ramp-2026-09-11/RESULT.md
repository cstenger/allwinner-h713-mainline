# ratio_h isolated — it MAGNIFIES. The block is an upscaler.

2026-09-11, cold boot, filmed (`local/lcd-photos/test_83/IMG_0823.MOV`, 35.5 s).
`proc-scaler-ratio-ramp.sh --engage`, instance 0, geometry untouched throughout,
`ratio_v` left at unity. Only `0x14[27]`, `0x08[21:0]` and `0x00[15:0]` written.

Whole run on hardware decode — no software fallback (`0` in the log), playback
reached only 28 s. Every step is on the good raster. Restore verified back to
cold-boot values.

## Alignment

Two solid anchors in the luminance trace: **collapse onset 22.8 s** and
**restore 32.4 s**. Three steps between them at 3.2 s each — exactly the step
spacing — which fixes the whole sequence:

| step | ratio_h | recording window |
| --- | --- | --- |
| baseline | unity, bypass **set** | before 13.4 s |
| 0 — control | unity, bypass **clear** | 13.4–16.4 |
| 1 | 0.750× | 16.4–19.6 |
| 2 | 0.625× | 19.6–22.8 |
| 3 | 0.500× | 22.8–26.0 |
| 4 | 0.375× | 26.0–29.2 |
| 5 | 0.250× | 29.2–32.4 |
| restore | unity, bypass set | 32.4+ |

## What the panel did — [steps-compared.jpg](steps-compared.jpg)

| step | observed |
| --- | --- |
| baseline | face centred, normal, dark surround |
| **0 — control** | **identical to baseline. No change.** |
| 1 — 0.750× | indistinguishable from baseline |
| 2 — 0.625× | face **larger and displaced right**, surround lightens |
| 3 — 0.500× | collapsed to a narrow vertical sliver, flat light field |
| 4 — 0.375× | almost nothing — a speck on a flat light field |
| 5 — 0.250× | a **grossly magnified smear**, centre-right |
| restore | face centred, normal — fully recovered |

## The two results that matter

**1. The control is clean.** Clearing `0x14[27]` with `ratio_h` still at unity
changes nothing. So the bypass bit is not the actor, and everything below is
attributable to the ratio. That distinction was unavailable in the 09-11 sweep,
which moved bypass, ratio and geometry together.

**2. `ratio_h` alone is live — and it MAGNIFIES, it does not compress.**
The picture gets progressively *bigger* and pushed right as the ratio goes
*down*. That is the behaviour of a **source sampling step**: advance `ratio`
source pixels per output pixel, so `ratio < 1` means zoom **in** by `1/ratio`.

```
0.750x -> 1.33x zoom    barely distinguishable
0.625x -> 1.60x zoom    visibly larger, displaced right
0.500x -> 2.00x zoom
0.375x -> 2.67x zoom
0.250x -> 4.00x zoom    gross smear
```

The slivers at 0.500× and 0.375× are consistent with this rather than against
it: magnifying 2–2.7× into a dark passage of the Leota clip leaves a mostly
flat field. The monotonic quantity is the *zoom*, not the visible content.

## Which makes the firmware's own name for these stages the tell

The stage table lists them as **`proc-vs_upscaler`** and
**`proc-vde_upscaler`**. Read alongside this result, that is not decoration:

- `ProcWinNode::CalcScaleRatio` always yields `unity × min/max`, i.e. **≤ unity**,
  with the direction carried separately in the geometry.
- A step of `≤ unity` per output pixel is, by construction, magnification.
- So the firmware's only use of this register is to **upscale**.

> **Working conclusion: `0x05180000` is an upscaler, and `ratio_h ≤ unity` can
> only magnify.** If that holds, this block cannot do 1920→1280 and is the wrong
> lever for 1080p on a 720p panel.

Stated as a working conclusion, not a finding — it rests on an inference about
how the hardware consumes the register, and there is one cheap test that settles
it.

## The test that settles it

**Drive `ratio_h` ABOVE unity.** The field is 22 bits with unity at bit 16,
leaving six integer bits — room for ~63×, which would be pointless in an
upscale-only block and is exactly what a downscaler needs.

```
ratio_h = 0x18000  (1.5x)   the 1920->1280 case
ratio_h = 0x20000  (2.0x)
```

- **Picture compresses horizontally** → the block downscales, the 22-bit field
  is for exactly this, and my earlier `dst/src` correction was wrong *for this
  block* (it was derived from `CalcScalingRatio_2`, which belongs to the panel
  down-scaler — a different block with a different consumer).
- **Clamped or inert** → upscale-only, and this route closes for 1080p→720p.

Geometry stays untouched again, so the comparison is clean against this run.

## Note on an earlier correction

On 2026-09-10 I inferred `src/dst` (ratio > unity to downscale) from the 22-bit
field width, then withdrew it in favour of `dst/src` after reading
`CalcScalingRatio_2`. That function is the **panel down-scaler's** producer, not
this block's. This block's producer is `ProcWinNode::CalcScaleRatio`, which has
a different convention (`min/max` plus a direction flag). The withdrawal was
applied too broadly — the field-width argument was never tested against this
block, and this run is the first evidence bearing on it.
