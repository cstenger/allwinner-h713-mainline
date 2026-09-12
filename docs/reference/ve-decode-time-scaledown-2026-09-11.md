# The VE downscales at decode time — that is how the vendor plays 1080p

Static RE of the vendor Android stack, no board time. This answers the question
the whole scaler search was really asking, and it answers it in a different
layer than we were looking.

## Where it came from

`super` is partition 9 of the board-B eMMC capture (start sector 599040 =
offset `306708480`, 2 GiB) — it is **not** a dynamic-partition super, so
`lpunpack` fails. It holds three raw ext4 filesystems, found by scanning for the
superblock magic on 4 KiB boundaries (they are **not** 1 MiB-aligned — the first
sits at `0x180000`):

```
0x000180000    921 MiB   label '/'         (system)
0x03aa80000    107 MiB   label 'vendor'    <- the VE stack
0x041880000    505 MiB   label 'product'
```

Extracted with `debugfs -R "dump /lib/<name> …"`. Libraries live in the ignored
`local/h713-lab/ve-extract/`.

## The finding

**The Allwinner VE has a hardware scale-down unit with a secondary output, and
the vendor decoder uses it.** The vendor does not downscale on the display side
at all — which is exactly why the display side has no downscaler to find.

The interface, across three layers:

| layer | evidence |
| --- | --- |
| OMX | `libOmxVdec.so` exports **`anSetScaleDownParam`** |
| decoder wrapper | `libvdecoder.so` exports **`ConfigExtraScaleInfo`** and logs `dec: codec[0x%x], scaledown[%d,%d,%d], rotate[%d,%d], …` plus `scale mode = %d`, `scale ratio = %dx%d`, **`scale wxh = %dx%d`** |
| codec plugin | `libawh264.so` exports `H264DecoderSetExtraScaleInfo`, `H264JudgeScaleMode`, `H264ComputeScaleRatio`, `H264ConfigNewScaler`, and **`H264ConfigureScaleRotateRegister`** |

`scale wxh = %dx%d` is the important one: the target is an **explicit width and
height**, not a power-of-two ratio. And `ScaleCopyCoef` / `H265ScaleCopyCoef`
copy **filter coefficients**, which is a polyphase resampler — so arbitrary
ratios, not just halving.

## The register map, free, from the symbol names

`libawh264.so` is stripped but keeps its exported symbols, and Allwinner's
naming encodes the register offset:

```
sd_rotate_ctrl_reg40              VE + 0x40    scale-down / rotate control
sd_rotate_buf_addr_reg44          VE + 0x44    scaled LUMA output address
sd_rotate_chroma_buf_addr_reg48   VE + 0x48    scaled CHROMA output address
mb_distscale_cur1_reg94           VE + 0x94
mb_distscale_cur2_reg98           VE + 0x98
```

`sd_` is scale-down. **The scaled result goes to its own output buffer** —
which matches the H.265 library's talk of a "sec out" (secondary output,
`not open sec out`, `sec out not support AW 10bit format`).

So the VE decodes 1080p and *simultaneously* writes a second, scaled output at
the size we ask for. Our VE is at **`0x01c0e000`** (`1c0e000.video-codec`,
driven by `cedrus`), so these are `0x01c0e040`/`44`/`48`.

The programming sequence is `H264ConfigureScaleRotateRegister`, at offset
`0x0000de79` in `libawh264.so` (ARM 32-bit, Thumb).

## Why this explains everything we found the hard way

The display pipeline has no downscaler because **it never needed one**:

- proc scaler `0x05180000` — upscale only, for SD → panel native
- panel down-scaler `0x051c0138` — vertical only, aspect fitting
- composition, DETN, route, AFBD — no scaler at all
- the firmware *letterboxes* undersized pictures rather than scaling them

A fixed-panel projector whose decoder always delivers frames at panel size needs
exactly that set of capabilities and no more. We were searching the wrong layer.

## What is NOT established

- **That the H713's VE supports it.** These libraries are generic across
  Allwinner parts and contain explicit capability checks —
  `this hardware not support fixratio scale` and
  `interlaced video cannot be scaled in current platform`. Which modes this SoC
  implements is unknown.
- **The exact bit layout** of `sd_rotate_ctrl_reg40`, the mode enum, and any
  ratio limits. That needs `H264ConfigureScaleRotateRegister` disassembled.
- Mainline `cedrus` implements none of this: no `VIDIOC_G_SELECTION`, no compose
  target, no second capture queue. Adding it is real driver work.

## Next steps, in order

1. **Disassemble `H264ConfigureScaleRotateRegister`** (`libawh264.so` + `0xde79`,
   ARM/Thumb) for the exact register writes, the mode encoding and the ratio
   constraints. Static, free.
2. **Probe the capability on our board** — write `sd_rotate_ctrl_reg40` on a live
   decode and see whether a second output appears. The VE is ours; cedrus is
   ours; no vendor boot and no MIPS involvement.
3. **If it works, plumb it through V4L2** — the scaled secondary output is a
   second buffer, so it maps onto either a compose/selection target or a second
   capture plane.

This also retires the vendor-boot question for scaling: we now know *where* the
vendor scales, so booting vendor to observe it is confirmation rather than
discovery. Worth doing only if step 1 or 2 stalls.

---

## Disassembly: there are TWO scalers, and only one does arbitrary ratios

`libawh264.so` is ARM32/Thumb, stripped but with exports intact. Disassembled
with capstone (`objdump` here has no ARM support); the VE register base is
`[r5,#0x18]` / `[r6,#0x18]` in these functions.

### `H264ConfigureScaleRotateRegister` (`+0xde79`) — the FIXRATIO path

Writes exactly three registers, confirming the symbol names:

```
0xdece  str r0, [r3, #0x40]     VE+0x40   control
0xdf06  str r0, [r2, #0x44]     VE+0x44   scaled luma out
0xdf3c  str r0, [r1, #0x48]     VE+0x48   scaled chroma out
```

`VE+0x40` is composed with `bfi`: **bits [2:0] = scale mode** (from ctx+0x54),
plus 4-bit fields around [11:8] derived from ctx+0x44/+0x48.

### `H264ComputeScaleRatio` (`+0x9d41`) — fixratio is POWER-OF-TWO ONLY

```
udiv r0, r2, r1      ; integer src/dst
cmp  r0, #3
movlo r0, #1         ; quotient < 3  -> 1
subs r0, #3 ...
mov  r0, #2          ; quotient >= 3 -> 2
```

Returns **0 if src <= dst** (no downscale), else a small enum: **1 = half,
2 = quarter**. So the fixratio scaler cannot do 1920→1280; it would give
1920x1080 → 960x540, *below* panel height.

### `H264ConfigNewScaler` (`+0xdb71`) — the arbitrary-ratio path

Much richer. Memsets a **256-byte** stack buffer (the coefficient table, cf.
`ScaleCopyCoef`) and writes:

```
VE+0x20   control (bit 9 cleared via `bic r1, r1, #0x200`)
VE+0x44   scaled luma out          VE+0x48   scaled chroma out
VE+0xcc   VE+0xe4   VE+0xe8   VE+0xec   VE+0xf8   VE+0xfc
```

A coefficient table plus six extra size/phase registers is a polyphase
resampler, which matches `scale wxh = %dx%d` being an explicit target rather
than a ratio. **This is the path that could do 1920x1080 → 1280x720 directly.**

`H264JudgeScaleMode` picks between them, and `new scale not support rotation`
says the two are mutually exclusive with rotate.

### Consequence if only fixratio turns out to be available

`1080p → 960x540` (ratio 1) then **upscale 960x540 → 1280x720** on the proc
scaler at `0x05180000`, which we proved magnifies by `1/ratio` and is live on our
raster. `ratio_h = 0xC000` is 1.333x, exactly the factor needed. Lossier than a
true 1280x720 decode, but it composes two confirmed-working directions and needs
no GPU.

## This is the normal playback path, not an exotic one

A video played from a USB stick on the stock firmware goes: Android media
framework → `libOmxVdec` (**`anSetScaleDownParam`**) → `libvdecoder`
(**`ConfigExtraScaleInfo`**) → `libawh264`/`libawh265` → VE. Same path, same
registers.

That matters for how much to trust it:

- The product is sold to play 1080p content on a 720p panel. If VE scale-down
  did not work on this SoC, **every 1080p file would be cropped or letterboxed**
  — an obvious defect. So the capability is very likely real and well exercised.
- It gives a **zero-risk empirical check**: play a 1080p file from USB on stock
  firmware and see whether it fills the screen at full width. That confirms
  decode-time downscale with no register work and no disassembly.

Caveat: it is conceivable the vendor player instead scales in SurfaceFlinger via
the GPU. Against that, `anSetScaleDownParam` and `ConfigExtraScaleInfo` exist
precisely to drive the decoder path, and the VE registers are there to be
driven.
