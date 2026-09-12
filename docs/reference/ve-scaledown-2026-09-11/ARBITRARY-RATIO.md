# The arbitrary-ratio VE scaler: real, but not reachable from our side

2026-09-11, headless. Follow-on from [RESULT.md](RESULT.md), which settled the
power-of-two path. Driven by `tools/video/ve-newscaler-probe.sh`.

**Outcome: negative, with a specific and named blocker.** The arbitrary-ratio
scaler exists and genuinely is not power-of-two limited, but its geometry and
ratio registers live in a register block that is not mapped anywhere we can
reach.

## First: a correction to my own method

Every disassembly in the previous write-up, and in the 2026-09-11 static doc,
was read at the wrong address.

```
libawh264.so  .text   Addr 0x00007558   Off 0x006558
```

A **0x1000 skew** between virtual address and file offset. I had been indexing
the file by `st_value`, so every function was disassembled 4 KiB away from where
it actually lives. Thumb is dense enough that misaligned bytes decode into
plausible-looking code: `H264ConfigNewScaler` disassembled as a *bitstream
reader*, and I drew a conclusion from it ("the new scaler is also power-of-two,
because `lsl r0, r6` computes `1 << mode`"). **That conclusion is withdrawn.**
It was read from bytes belonging to a different function.

Correct rule: `file_offset = vaddr - 0x1000` for this library. Check the section
header before disassembling a stripped .so by symbol address.

What survived the correction: the `0x240/0x244/0x248` result, because it never
came from the disassembly. It came from the vendor symbol *names* plus mainline
naming `VE_H264_SDROT_CTRL` at 0x240 — and it is confirmed on hardware.

## What the corrected disassembly says

`H264ComputeScaleRatio(src, dst)` — now read correctly, and it does say
power-of-two:

```
if (!dst || src <= dst) return 0;
q = (uint8)(src / dst);
return q < 3 ? 1 : 2;          /* 1 = half, 2 = quarter */
```

`H264ConfigNewScaler` is a different animal. It computes its ratio in floating
point and converts to fixed point with 12 fractional bits:

```
0x00dcfe  vcvt.f32.s32 s0, s0
0x00dd02  vcvt.f32.s32 s2, s2
0x00dd14  vdiv.f32     s16, s2, s0      <- ratio = src/dst, a FLOAT
0x00dd4e  vdiv.f32     s18, s2, s0      <- the other axis
...       lsl.w r7, r7, #0xc            <- 12 fractional bits
```

**A float divide and a 12-bit fraction is not a power of two.** So the hardware
does have an arbitrary-ratio mode. The question was only whether we can drive it.

### Two register bases, and that is the whole problem

```
0x00dc2e  movs r1, #0     ; getRegBase(0)
0x00dc32  mov  r6, r0     ; r6 = top-level VE base
0x00dc3a  movs r1, #7     ; getRegBase(7)
0x00dc3e  mov  r5, r0     ; r5 = register block SEVEN -- a different block
```

Writes then split across the two:

| base | offsets written | what |
| --- | --- | --- |
| `r6` = top-level VE | `0x00`, `0xcc`, `0xe8`, `0xec` | stride, secondary format/length |
| `[r5+0x18]` = H.264 engine | `+0x20`, `+0x44`, `+0x48` | ctrl, output addresses |
| `r5` = **block 7** | `+0x10`, `+0x14`, `+0x18`, `+0xe4`, `+0xf8`, `+0xfc` | **sizes and ratios** |

`+0x10` and `+0x18` are built with `bfi ..., #0x10, #0xe` and `bfi ..., #0, #0xe`
— pairs of **14-bit** fields, i.e. sizes up to 16383. `+0x14` carries the
12-fractional-bit ratios. Those are exactly the registers that would let us ask
for 1280x720, and they are all in block 7.

## Measured on hardware

| test | result |
| --- | --- |
| poke top-level `0x10` / `0x14` / `0x18` with sizes and 1.5x ratios | **no effect** on output geometry |
| poke `0xcc = 0x02800500` (stride 1280) | **live** — see below |
| `0xcc` with `sd_ctrl = 0` | nothing written; `SDROT_CTRL` is still the enable |
| `VE_H264_CTRL` bit 9 set or cleared | no effect |
| `VE_H264_CTRL` bit 11 set (the vendor's `orr r1, r1, #0x800`) | **`frame processing timed out!`** — breaks the decode |
| full 4 KiB register snapshot during an active decode | **`0x300`..`0xfff` all read zero** |

Poking top-level `0x10/0x14/0x18` did nothing because block 7 is not the
top-level base — the same class of mistake as programming `VE+0x40` instead of
`VE+0x240` in the previous round, caught this time before it became a
conclusion.

### `0xcc` is the secondary line stride

This one is a positive result and worth keeping. With the scaler at `0x500`
(960x544 output) and `0xcc` low half set to 1280, the luma span grew to
≈1280x544 and the picture stayed 960 wide:

```
mean of columns 0..959    =  15.88   (picture)
mean of columns 960..1279 = 165.00   (= 0xa5, untouched poison)
```

So `0xcc = {chroma << 16, luma}` — the same packing as
`VE_PRIMARY_FB_LINE_STRIDE` at `0xc8`, which it sits immediately after. It sets
the row pitch of the secondary output and **does not change the ratio**.

### Bit 11 breaks the decode, it does not switch modes

Worth stating plainly because the raw numbers invite the opposite reading: with
bit 11 set, the secondary buffer came back untouched, which looks like "the
scaler switched to a mode that needs block 7 and therefore wrote nothing". It is
not that. `dmesg` shows `frame processing timed out!` and ffmpeg emits one frame
instead of 25. The output was empty because **the decode failed**, not because a
mode changed.

Recovery needed no reboot: with the harness disarmed the next decode ran 60
frames at 3.17x and CMA came back fully free. That re-confirms that a VE timeout
does not wedge this device.

## Where this leaves it

The blocker is exactly one fact: **the physical base of VE register block 7.**

- It is not at `0x01c0e000 + anything` — the VE's mapped window is
  `01c0e000-01c0efff` (4 KiB, confirmed in `/proc/iomem`) and everything above
  `0x300` reads zero during an active decode.
- `/proc/iomem` shows no other VE-adjacent region.

Resolving it means following `getRegBase` out of the vendor libraries. The chain
is `libawh264.so` -> `GetVeOpsS` (defined in `libVE.so`) -> `.plt` -> another
library (`libvideoengine.so` is the likely one; `libVE.so`'s `GetVeOpsS` is a
two-entry dispatcher that tail-calls through the PLT). The ops struct member at
`+0x20` is the base getter, and somewhere behind it is a table of physical
addresses. That is static work, free, and it is the next step if this route is
worth continuing.

If block 7 turns out not to exist on the H713 — plausible, since the H.265
library carries `this hardware not support fixratio scale` and `libVE.so` gates
on `ic_version` — then the decoder cannot produce 1280x720 at all, and the
composite route in [RESULT.md](RESULT.md) (VE to 960x544, then the proc upscaler
at `0x05180000` at `ratio_h = 0xC000` for 1.333x) is the remaining no-GPU
option.

## Harness notes

`sd_poke` takes `off=val` pairs so a candidate register costs a sysfs write
rather than a rebuild; `cedrus_sd_regs` dumps the whole 4 KiB at the decode
trigger. Both refuse the SRAM access ports (`0x1e0/0x1e4`, `0x2e0/0x2e4`,
`0x5e0/0x5e4`) — those walk an internal pointer, so reading or writing them while
sweeping would corrupt the decode rather than observe it.
