# The VE decode-time scale-down WORKS on the H713 — and it is power-of-two only

2026-09-11, headless, no display, no MIPS, no operator. Driven by
`tools/video/ve-scaledown-sweep.sh` against a patched cedrus
(`patches/kernel/0097`).

**This is the first confirmed hardware downscaler on our video path.** It is
also, measured, unable to produce 1280x720.

## The registers

The vendor's `sd_rotate_ctrl_reg40` / `sd_rotate_buf_addr_reg44` /
`sd_rotate_chroma_buf_addr_reg48` are offsets **within the H.264 engine block**
(`VE_ENGINE_DEC_H264` = 0x200), not the top-level VE register file:

```
VE_H264_SDROT_CTRL          0x240   control          (already named by mainline)
VE_H264_SDROT_LUMA_ADDR     0x244   scaled luma out  (unnamed gap in mainline)
VE_H264_SDROT_CHROMA_ADDR   0x248   scaled chroma out
```

Corroborated three ways: the vendor symbol numbers, mainline naming 0x240
`VE_H264_SDROT_CTRL` and leaving 0x244/0x248 as a gap, and the H.265 engine
carrying the same trio as `VE_DEC_H265_SDRT_{CTRL,LUMA_ADDR,CHROMA_ADDR}` at its
own +0x50/0x54/0x58. Mainline's header even spells out `SDRT: Scale Down and
Rotate`.

Addresses go in **raw and unshifted**, confirmed by readback.

## The control encoding — two independent 2-bit fields

```
VE_H264_SDROT_CTRL[9:8]     horizontal   0 = 1:1,  1 = 1/2,  2 = 1/4,  3 = invalid
VE_H264_SDROT_CTRL[11:10]   vertical     0 = 1:1,  1 = 1/2,  2 = 1/4,  3 = invalid
```

Twelve control words swept against a 1920x1088 source. Every output size matches
the model exactly — including the two nulls and the two invalid-field partials:

| ctrl | H field | V field | predicted | luma bytes written | |
| --- | --- | --- | --- | --- | --- |
| `0x000` | 0 | 0 | (disabled) | 0 | null |
| `0x100` | 1 | 0 | 960x1088 | 1044480 | exact |
| `0x200` | 2 | 0 | 480x1088 | 522240 | exact |
| `0x300` | 3 | 0 | invalid | 0 | null |
| `0x400` | 0 | 1 | 1920x544 | 1044480 | exact |
| `0x500` | 1 | 1 | 960x544 | 522240 | exact |
| `0x800` | 0 | 2 | 1920x272 | 522240 | exact |
| `0x900` | 1 | 2 | 960x272 | 261120 | exact |
| `0xa00` | 2 | 2 | 480x272 | 130560 | exact |
| `0xc00` | 0 | 3 | invalid | 117240 | partial, malformed |
| `0xd00` | 1 | 3 | invalid | 66264 | partial, malformed |
| `0x1000` | 0 | 0 | (bit 12 alone) | 0 | null |
| `0x1100` | 1 | 0 | 960x1088 | 1044480 | bit 12 has no effect here |

Three were rendered and visually confirmed correctly proportioned:

- [sd-0x100-960x1088.png](sd-0x100-960x1088.png) — horizontal halving only,
  the picture squashed exactly 2:1.
- [sd-0x400-1920x544.png](sd-0x400-1920x544.png) — vertical halving only, wide
  and flat. The complementary case, which is what pins the field assignment.
- [sd-0x500-960x544.png](sd-0x500-960x544.png) — both axes halved, natural
  aspect.

Raw sweep output: [sweep-summary.txt](sweep-summary.txt).

This matches the static disassembly exactly: `H264ComputeScaleRatio` returns
0/1/2 for none/half/quarter. The fixratio path is power-of-two, per axis.

## What that means for 1080p on a 720p panel

Reachable outputs from 1920x1088 are only:

```
1920x1088   960x1088   480x1088
1920x544     960x544    480x544
1920x272     960x272    480x272
```

**1280x720 is not among them.** The nearest useful output is **960x544**, which
is *below* the panel in both axes rather than above it.

So this does not by itself solve 1080p playback — but it changes the shape of
the problem, because it composes with a capability we already proved:

> **VE 1920x1088 -> 960x544 (confirmed here), then the proc upscaler at
> `0x05180000` magnifies by `1/ratio` (confirmed 2026-09-11).**
> `ratio_h = 0xC000` is 1.333x: 960 -> 1280 and 544 -> 725.

That is two confirmed-working directions in series, no GPU. It is lossier than a
true 1280x720 decode — the picture goes through a halving and then a 4:3
magnification — but both halves are measured rather than hoped for.

The alternative is the **arbitrary-ratio path**, `H264ConfigNewScaler`. That was
probed next and came back negative with a specific blocker — see
[ARBITRARY-RATIO.md](ARBITRARY-RATIO.md). Summary: the mode is real and genuinely
not power-of-two (a `vdiv.f32` and a 12-fractional-bit conversion), but its size
and ratio registers are at `getRegBase(7) + 0x10/0x14/0x18`, and **register block
7 is not in the VE's 4 KiB MMIO window** — everything above `0x300` reads zero
during an active decode. Finding its physical base means following `getRegBase`
out through `libVE.so`'s PLT into another vendor library.

That document also records a correction that invalidates part of the static work
this one rests on: `libawh264.so` has a **0x1000 skew** between virtual address
and file offset, so every disassembly done by symbol address was reading the
wrong function.

## Three silent failures, each of which looked like "no such hardware"

Worth recording, because every one of them produced a confident-looking null.

1. **Wrong register file.** The first full sweep — 16 control words, all
   null — programmed the *top-level* VE+0x40/0x44/0x48 instead of the engine's
   0x240/0x244/0x248. The control register there is real and writable, so it read
   back what was written and looked fine; the address registers read back
   **zero**. The scaler had nowhere to write. Sixteen uniform nulls looked
   exactly like "this SoC does not implement it".

   *The fix that caught it was readback.* The sweep script now aborts if the
   luma address reads back zero, because a null result is only interpretable
   next to proof that the write landed.

2. **Wrong ordering.** `cedrus_sd_setup()` originally ran *before*
   `ctx->current_codec->setup()`, which is where `cedrus_engine_enable()` writes
   `VE_MODE`. Programming a disabled engine is a null that means nothing. The
   vendor configures scale/rotate as part of the decode configuration; so does
   this patch now (`sd_stage=1`).

3. **Wrong output format.** The first genuine hit rendered as horizontal
   stripes — [tiled-misread-960x1088.png](tiled-misread-960x1088.png) — and read
   naturally as "the scaler is producing garbage". It was not: the secondary
   output defaults to `TILED_32_NV12`, and the scaler was working perfectly.
   Linear NV12 needs the EXT table selected in `VE_CHROMA_BUF_LEN[31:30]` **and**
   `VE_PRIMARY_OUT_FMT[3:0] = 4`. My own `sd_fmt` code had this wrong in the
   other direction — it *cleared* those two bits, which selects the tiled default.

The general lesson, and it is the same one as the `vo=drm` black-screen: a null
result is only evidence when you can show the stimulus reached the hardware.
Two of these three were caught by adding a readback, and the third by rendering
the bytes rather than trusting a byte-difference count.

## Method notes

- The output buffer is **poisoned with 0xa5** on every change of `sd_ctrl`, so
  "wrote nothing" stays distinguishable from "wrote black" — a flat fill is
  ambiguous on this hardware, and much of this clip is near-black.
- A **shadow copy** is taken when the decoding context is released, so the
  result outlives the player that produced it and the dump does not have to race
  a live decode.
- The buffer is declared at **twice the source height** so the luma plane has a
  full frame of headroom, because the patch sets the output addresses but not
  the output geometry — the hardware decides how much to write. The invalid
  `[11:10] = 3` cases did write malformed output, and that headroom is why they
  were harmless.
- Byte-difference counts **understate** the written region: real video contains
  bytes equal to the poison value. Extent, not count, is the reliable measure.
