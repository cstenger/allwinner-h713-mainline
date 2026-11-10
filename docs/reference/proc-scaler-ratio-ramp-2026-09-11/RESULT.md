# ratio_h isolated — it MAGNIFIES. The block is an upscaler.

> ## CONFIRMED AND EXPLAINED 2026-09-12 — the clip window was `0x34`
>
> The hypothesis at the end of the clipping refinement below was right. The
> **input window at `0x34`** is the whole of it: left at `0x050002D0` = {1280,720}
> while the ratio commands magnification, the block confines its output to a
> hard-edged rectangle with flat grey outside. Set it to the true input size and
> the magnified picture fills the panel cleanly — operator-confirmed:
> [../ve-scaledown-2026-09-11/UPSCALE-GEOMETRY-CONFIRMED.md](../ve-scaledown-2026-09-11/UPSCALE-GEOMETRY-CONFIRMED.md).
>
> This block is now **stage 2 of the surviving 1080p route** (960x544 → 1280x720
> at 1.333x): [the handoff](../../handoff-2026-09-12-ve-scaledown.md).
>
> Also worth carrying forward: `0x05180000`'s registers hold **live upper bits**
> (`0x08` reads `0x43010000`, `0x00` reads `0x0F008000`), so every field write
> must be read-modify-write, and the V phase at unity is **0**, not `0x10000` —
> `(unity+unity)>>1` overflows the 16-bit field.

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

## REFINEMENT — it is magnification AND clipping, not either/or

Added after the operator asked whether the slivers might be the face *clipped*
rather than magnified. Re-examined at full resolution instead of on 520 px
thumbnails, and the answer is **both**, which is a better model than the one
above.

**Clipping is real, and it is hard-edged.** In
[zoom-step3-0.500x.jpg](zoom-step3-0.500x.jpg) the visible blob's right boundary
is a perfectly straight vertical cut with flat grey on both sides; its left
boundary is an organic jaw curve. In
[zoom-step5-0.250x.jpg](zoom-step5-0.250x.jpg) the content sits inside a clean
**rectangular window** roughly 295x320 px with straight edges on all four sides.
Those are not content boundaries or soft falloff — the output is being confined
to a rectangle.

**Magnification is also real, and quantitative.** Measured against the baseline
crop, both at the same scale:

| step | ratio_h | predicted 1/ratio | measured | from |
| --- | --- | --- | --- | --- |
| 2 | 0.625× | 1.60× | **1.45×** | face width 340 vs 235 px |
| 5 | 0.250× | 4.00× | **4.17×** | eye slit 250 vs 60 px |

Vertical extent is essentially unchanged throughout, as expected with `ratio_v`
left at unity — face height 340 → 315 px at step 2, within the drift of a moving
subject.

So `0x05180000` magnifies horizontally by `1/ratio_h`, and the result is then
**clipped to a hard rectangular window** that shrinks and shifts right as the
magnification grows. At step 2 the whole (enlarged) face still fits; by step 5
only a small fragment of a 4×-enlarged face survives the clip.

**The slivers were never evidence against magnification** — they are a clipped
view of a magnified image. And the 09-11 "collapse to a sliver at the right edge"
was the same thing: ratio `0x8000` is 2× magnification, not a failed downscale.

**What the clip window most likely is:** the geometry registers this run
deliberately left untouched — `0x2c` (out_w), `0x30` (out_h), `0x34` (in size),
`0x40`. The firmware never sets a ratio without deriving matching geometry
(`ReCalcInOutWin`), so a self-consistent pair is probably what produces a clean
picture. That is the experiment after the next one.

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

The refinement above makes this prediction sharper and easier to read: if the
scale factor is `1/ratio_h`, then `ratio_h = 0x18000` (1.5) should give **0.67×**
— a horizontally squashed face, narrower than baseline, with **no clipping at
all**, because a compressed image cannot overflow the clip window. A clean
unclipped narrow face is the unambiguous positive to look for.

Geometry stays untouched again, so the comparison is clean against this run.

## Note on an earlier correction

On 2026-09-10 I inferred `src/dst` (ratio > unity to downscale) from the 22-bit
field width, then withdrew it in favour of `dst/src` after reading
`CalcScalingRatio_2`. That function is the **panel down-scaler's** producer, not
this block's. This block's producer is `ProcWinNode::CalcScaleRatio`, which has
a different convention (`min/max` plus a direction flag). The withdrawal was
applied too broadly — the field-width argument was never tested against this
block, and this run is the first evidence bearing on it.
