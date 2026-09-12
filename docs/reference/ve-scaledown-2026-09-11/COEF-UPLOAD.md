# Coefficients uploaded, enable retried — the new scaler still does not engage

2026-09-11, headless. Follow-on from [BLOCK7-FOUND.md](BLOCK7-FOUND.md).

**Outcome: negative.** Everything the vendor's `H264ConfigNewScaler` writes has
now been reproduced on hardware — geometry, both ratio forms, a working buffer,
and the polyphase coefficients — and verified by readback. The arbitrary-ratio
unit still produces no output under any enable I could identify. The
power-of-two `SDROT` path remains the only one that ever writes.

## The SRAM port is group 7's own, not the AVC one

Correcting the premise of the previous document. The coefficients do **not** go
through the AVC SRAM port at `0x2e0/0x2e4`. `H264ConfigNewScaler` ends:

```
vmov  r0, s18 ; mov   r1, r4          ; ScaleCopyCoef(h_ratio, buf)
vmov  r0, s16 ; add.w r1, r4, #0x80   ; ScaleCopyCoef(v_ratio, buf+128)
ldr.w r0, [r5, #0xf8]
mov.w r1, #0x340
bfi   r0, r1, #2, #0xa                ; SRAM address in bits [11:2]
str.w r0, [r5, #0xf8]                 ; group7 + 0xf8 = VE + 0xff8
loop 32x: str.w r1, [r5, #0xfc]       ; group7 + 0xfc = VE + 0xffc, auto-increments
loop 32x: str.w r1, [r5, #0xfc]       ; second axis, NO re-seek
```

So: **`VE+0xff8`** is the offset register (address in `[11:2]`, vendor uses
`0x340`) and **`VE+0xffc`** the data port, 32 words per axis, 64 total, the
pointer auto-incrementing across both. The AVC port is never touched, so the
harness's refusal of `0x2e0/0x2e4` stays in place — and `0xff8/0xffc` were added
to that refusal list, because the previous full-window snapshot had been
*reading* `0xffc`, which advances the pointer.

## The register values, derived exactly

With `r1 = dst_w`, `r2 = src_w`, `r7 = dst_h`, `r3 = src_h` (fixed by the fact
that `ScaleCopyCoef` buckets `src/dst` ratios at or above 1.125):

```
0xf10 = (dst_w << 16) | dst_h
0xf14 = high: src_w*4096/dst_w - 1    low: src_h*4096/dst_h - 1
0xf18 = high: dst_w*4096/src_w - 1    low: dst_h*4096/src_h - 1
0xfe4 = working buffer address >> 8, placed at bit 2
```

For 1920x1088 -> 1280x720:

| reg | value | meaning |
| --- | --- | --- |
| `0xf10` | `0x050002d0` | dst 1280 x 720 |
| `0xf14` | `0x17ff182d` | ratios 1.5000 and 1.5112, in 12 fractional bits, minus 1 |
| `0xf18` | `0x0aaa0a96` | inverses; **`0xAAA` is 2731/4096 = 0.6667** |

`0xAAA` is a quiet corroboration: the display-side scaler notes independently
use `0xAAAA` for 1920->1280 in 16.16. Two unrelated blocks agreeing on 2/3 is a
good sign the field interpretation is right.

## What was uploaded, and proof it landed

Bucket 4 (the `<1.625` class, covering both 1.5000 and 1.5112) for both axes,
from [ve-scaler-coefficients.bin](ve-scaler-coefficients.bin):

```
sd: 1920x2176 buffer 6266880 bytes at 0x00000000fe800000, ctrl 0x0, stage 1
sd: uploaded 64 coef words to SRAM 0x340, work buf 0x00000000fe7c0000
sd: poke 0xf10 = 0x050002d0 (reads 0x050002d0)
sd: poke 0xf14 = 0x17ff182d (reads 0x17ff182d)
sd: poke 0xf18 = 0x0aaa0a96 (reads 0x0aaa0a96)
```

A working buffer is allocated and `0xfe4` pointed at it, because a vertical
polyphase filter needs somewhere to keep lines and leaving that register at zero
would aim its DMA at physical address 0.

## Every enable tried

Secondary buffer always poisoned with `0xa5` first; "nothing" means not one byte
of 6.2 MB changed.

| configuration | frames | timeouts | secondary output |
| --- | --- | --- | --- |
| group 7 fully configured + coefficients, `SDROT = 0` | 25 | 0 | **nothing** |
| same + `SDROT = 0x500` | 25 | 0 | only the power-of-two 960x544 result |
| + `0xf20 = 0x800` (bit 11, the vendor's `orr`) | 25 | 0 | **nothing** |
| + `0xf20 = 0xf00` | 25 | 0 | **nothing** |
| + `0xf00 = 1` | 25 | 0 | **nothing** |
| + group 7 output addresses at `0xf44`/`0xf48` | 25 | 0 | **nothing** |
| + `0x220 = 0x807` (bit 11 on `VE_H264_CTRL`) | **1** | 2 | nothing — *decode failed* |

Two corrections fall out of that table:

- **`0xf20` bit 11 is harmless** — no timeout, 25 frames. Only `0x220` bit 11
  breaks the decode. So `[r5,#0x18]` in `ConfigNewScaler` is the H.264 engine
  base after all (as the fixratio path established), and bit 11 there genuinely
  disrupts H.264 control rather than enabling a scaler. The "bit 11 is the
  enable" lead is dead in both locations.
- Putting the output addresses in group 7 (`0xf44/0xf48`) changes nothing, so
  those are not the new scaler's destination registers either.

## Where that leaves it

The honest reading, and it is the one I flagged as a risk when the registers
first latched: **a register file latching values is not proof that the datapath
behind it exists.** Group 7 accepts and holds every write, but nothing observable
happens, and the leading explanation is now that the H713 does not implement the
arbitrary-ratio scaler even though the register block is decoded.

Supporting that:

- `libawh265.so` carries the string `this hardware not support fixratio scale`,
  so per-SoC scaler capability differences are a thing this vendor codebase
  handles explicitly.
- `libVE.so` gates on `ic_version` (`*** ic_version = 0x%llx`) and asserts
  `You should know ic version!`.
- `VE_VERSION` (`0x0f0`) reads **`0x00000000`** on our part, where mainline
  expects a version field at bit 16.

Not proven, though. The alternative is simply that the enable is somewhere I
have not looked, and there is a concrete place left to look: **the selection is
not made in `libawh264.so` at all.** Both scaler functions are exported plugin
entry points, `H264DecoderSetExtraScaleInfo` merely stores its arguments into
the context, and no branch in that library chooses between the two paths.
Whatever decides — and whatever else it programs — lives in `libvdecoder.so`,
around `ConfigExtraScaleInfo`. That is the next static step.

### A correction to the earlier documents

`H264JudgeScaleMode`, cited in
[ve-decode-time-scaledown-2026-09-11.md](../ve-decode-time-scaledown-2026-09-11.md)
as the function that "picks between them", **does not exist**. There is no such
symbol in `libawh264.so`. It was invented in an earlier session's notes and then
cited as fact. That document has been corrected.

## Practical consequence

For 1080p on the 720p panel the composite route from [RESULT.md](RESULT.md)
remains the only measured no-GPU option: VE power-of-two to 960x544, then the
proc upscaler at `0x05180000` with `ratio_h = 0xC000` for 1.333x. Both halves
are confirmed working; it is lossier than a single-pass 1.5x would have been.
