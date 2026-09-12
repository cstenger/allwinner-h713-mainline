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
| codec plugin | `libawh264.so` exports `H264DecoderSetExtraScaleInfo`, `H264ComputeScaleRatio`, `H264ConfigNewScaler`, `ScaleCopyCoef` and **`H264ConfigureScaleRotateRegister`** |

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

`new scale not support rotation` says the two are mutually exclusive with
rotate.

> **CORRECTION (2026-09-11):** an earlier revision of this document claimed a
> `H264JudgeScaleMode` "picks between them". **That symbol does not exist** --
> `readelf --dyn-syms` on `libawh264.so` has no such entry. It was invented.
> The selection is not made in `libawh264.so` at all: both scaler functions are
> exported plugin entry points, `H264DecoderSetExtraScaleInfo` only stores its
> arguments into the context, and nothing in this library branches between the
> two paths. Whatever chooses lives further up, in `libvdecoder.so`.

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

---

## Probed on OUR board: the scale/rotate register file is REAL and reachable

No vendor boot, no operator, no display involved — just a headless decode plus
`devmem`. `ffmpeg -hwaccel vaapi -i leota-1080p.mp4 -f null -` decodes 1080p at
~1.05x on our stack, and the VE runtime-PM state goes `suspended` → `active`.

**Read the VE only while a decode is actually in flight.** When the device is
runtime-suspended the whole 4 KiB window reads `0x00000000`, which looks exactly
like "the block is not there" — the first attempt raced the start of the decode
and read all zeros for that reason.

During an active 1080p decode, `0x01c0e000`–`0x01c0efff`:

```
+0x000 = 0x00130001     VE_MODE
+0x004 = 0x00000300
+0x01c = 0x00010000
+0x030 = 0x00000200
+0x040 = 0x0000000F     <-- sd_rotate_ctrl_reg40, NON-ZERO
+0x080 = 0x00001C55     +0x084 = 0x000FFFFF     +0x088 = 0x00008000
+0x0a0 = 0x000B2600     +0x0a4 = 0x00007720
+0x0c4 = 0x0007F800
+0x0c8 = 0x03C00780     <-- {0x03C0, 0x0780} = {960, 1920}
+0x0e0 = 0x00033110     +0x0e4 = 0x00012011
```

Two things follow:

1. **`+0x0c8` = `{960, 1920}`** for a 1920-wide frame — luma width and chroma
   width (1920/2). That confirms the window really is the VE's register file and
   that we are reading it coherently, not sampling noise.
2. **`sd_rotate_ctrl_reg40` reads `0x0000000F`** — the register exists and
   decodes on this silicon. Mainline cedrus has no knowledge of scale-down, so
   whatever is in there is a reset default or incidental; the point is that the
   address is live rather than reading back as zero or bus-error.

`+0x0e4` also appears in `H264ConfigNewScaler`'s write set, and it is populated.

### What this does and does not prove

It establishes the **register file is present and addressable on the H713**. It
does **not** yet show the scaler produces a scaled output — that needs a second
buffer allocated and the registers programmed per frame, which is a cedrus patch
rather than a `devmem` poke, because cedrus rewrites its register set on every
job and would immediately overwrite anything we wrote by hand.

### The next step is driver work, not probing

Patch cedrus to, on each H.264 job: allocate a second output buffer, write
`VE+0x44`/`0x48` with its luma/chroma addresses, set the mode in `VE+0x40`, and
see whether scaled pixels land in it. That is the experiment that settles it, and
it needs no display, no MIPS, no operator — the output can be dumped to a file
and inspected off-board.
