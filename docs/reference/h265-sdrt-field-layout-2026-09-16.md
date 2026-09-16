# H.265 secondary output: the reg50 field layout, recovered

Closes the one gap left by `upstream-survey-2026-09-15.md`. The H.265 engine's
scale/rotate registers were confirmed to EXIST by vendor symbol names; what was
missing was the field layout of `VE_DEC_H265_SDRT_CTRL` (`+0x50`). It is now
read out of `HevcSetOutputConfigReg`, and it is **identical to H.264's**.

## Source and method

```
/tmp/libcedarc/library/toolchain-sunxi-aarch64-glibc/libawh265.so
  HevcSetOutputConfigReg   @ 0x15238
```

Clone with `git clone --depth 1 https://github.com/aodzip/libcedarc.git`.

Section map — **the skew is per-segment**, as `elf-vaddr-file-offset-skew`
warns:

```
.text    vaddr 0x3260   off 0x3260    (no skew)
.got     vaddr 0x2dac0  off 0x1dac0   (skew 0x10000)
.bss     vaddr 0x2de98  off 0x1de98
```

Local `objdump` cannot disassemble aarch64; use capstone.

The code never names the registers directly. Each register has a **shadow
word** in `.bss`, reached through a GOT slot, read-modify-written field by
field, then flushed to hardware with one store. Resolve the slots from the
relocations, not by reading the GOT bytes (they are filled at load time):

```
readelf -rW libawh265.so | grep -i Extra
  0x2db00  R_AARCH64_GLOB_DAT  regHEVC_ExtraYBuf_reg54
  0x2db90  R_AARCH64_GLOB_DAT  regHEVC_ExtraCtrl_reg50
  0x2dbb0  R_AARCH64_GLOB_DAT  regHEVC_ExtraCBuf_reg58
```

so in code the ctrl shadow is `ldr xN, [xM, #0xb90]` after `adrp xM, #0x2d000`.

**Trap:** capstone's `disasm()` stops silently at the first word it cannot
decode, so a linear scan of `.text` truncates without saying so and a grep for
`#0xb90` returns nothing. Disassemble from a known function start instead, or
skip undecodable words explicitly. Same family as the linear-Thumb desync
already recorded.

## The layout

```
00015390  str   wzr, [x7]            ; clear the reg50 shadow
000153a4  ldr   w1, [x7]
000153a8  bfxil w1, w5, #0, #3       ; [2:0]  <- rotate,  w5 = ctx+0x1cc0
000153ac  str   w1, [x7]
...
00015484  ldr   w5, [x3, #0x38]      ; vertical
00015488  ldr   w3, [x3, #0x34]      ; horizontal
00015490  orr   w3, w3, w5, lsl #2
00015494  bfi   w6, w3, #8, #4       ; [11:8] <- {V<<2 | H}
...
000153f8  ldr   w6, [x4]             ; x4 = &reg50 shadow
00015400  str   w6, [x2, #0x50]      ; flush to HARDWARE, engine base + 0x50
```

| bits | meaning | H.264 equivalent |
| --- | --- | --- |
| `[2:0]` | rotate, value = degrees / 90 | `VE_H264_SDROT_CTRL_ROTATE` `[2:0]` |
| `[9:8]` | horizontal scale shift | `VE_H264_SDROT_CTRL_H_SHIFT` `[9:8]` |
| `[11:10]` | vertical scale shift | `VE_H264_SDROT_CTRL_V_SHIFT` `[11:10]` |
| `[12]`, `[13]` | cleared on the no-scale path; **never seen set** | none |

**The rotate and both shift fields sit at exactly the H.264 positions.** That
was previously an inference from symmetry; it is now read out of the vendor's
own code.

## The enable bit, confirmed

```
00015314  ldr  w8, [x3, #0x98]
0001531c  cmp  w8, #1
00015320  cset w8, eq
00015324  bfi  w6, w8, #9, #1        ; CTRL[9] = (flag == 1)
00015348  str  w6, [x2, #0x30]       ; engine base + 0x30 = CTRL
```

Bit 9 of the H.265 `CTRL` register at `+0x30`, exactly mainline's
`VE_DEC_H265_CTRL_ROTATE_SCALE_OUT_EN`. The same flag at `ctx+0x1c98` gates
both this bit and whether the shift fields are programmed at all, so they are
one switch, not two.

## The trap that would have cost a session

```
000153fc  ldr x4, [x5, #0x38]
0001540c  lsr x4, x4, #8             ; >> 8
00015410  str w4, [x3]               ; -> reg54 shadow
0001541c  str w3, [x2, #0x54]        ; luma  address

00015414  ldr x6, [x5, #0x40]
00015424  lsr x4, x6, #8             ; >> 8
0001542c  str w4, [x1]
00015434  str w1, [x2, #0x58]        ; chroma address
```

**The H.265 output addresses go in SHIFTED RIGHT BY 8.** H.264's do not —
`ve-decode-time-scaledown` records "addresses go in **raw, unshifted**" as one
of three silent failures that each looked like absent hardware. The two engines
differ here, and a port that assumes H.264's convention will write a valid-
looking register and get nothing back.

## What is still unknown

- `[12]` and `[13]`. Cleared whenever scaling is off; no path in this function
  sets them. They may belong to a mode this decoder never uses.
- Whether the H.265 shift fields accept the same values as H.264
  (`0 = 1:1, 1 = 1/2, 2 = 1/4`, 3 invalid). The packing is identical and
  `H265DecoderSetExtraScaleInfo` stores four values without validating them,
  so this is likely but unverified.
- Everything downstream: nothing has been programmed on hardware.

## Implementing this

The driver work is not large — `cedrus_sd_program()` already does the H.264
equivalent, and the H.265 path would mirror it with the `>> 8` addressing and
the `+0x50/0x54/0x58` offsets. The gating in `cedrus_video.c` is currently
hard-coded to `V4L2_PIX_FMT_H264_SLICE` in five places.

Verification needs **no bench time**: the four-quadrant card and
`tools/video/cedrus-compose-probe.c` check rotation headlessly by sampling
output quadrant centres, and `docs/reference/ve-rotation-2026-09-13.md` records
the expected values. Point them at an HEVC clip instead of an H.264 one.

---

# Implementation attempt, 2026-09-16: it hangs the VE

The layout above is believed correct; a driver written from it **does not
work**. Recorded so the next attempt starts here rather than repeating it.

## What was built

`cedrus_sd_program()` gained an H.265 branch mirroring the H.264 one: shared
top-level format/stride first, then engine-local addresses `>> 8`,
`CTRL |= BIT(9)`, and `SDRT_CTRL` with the rotate and shift fields.
`cedrus_can_transform()` replaced the five hard-coded `V4L2_PIX_FMT_H264_SLICE`
gates, and the `ROTATE` control lost its H.264 capability gate.

It compiles clean and **leaves H.264 completely unaffected** — rotation still
4/4, compliance still 48/49.

## What happens

```
  no transform (control)       dump=12288  timeouts=0
  SCALE only (1/2 both axes)   dump=0      timeouts=1
  ROTATE only (180)            dump=0      timeouts=1
  scale + rotate               dump=0      timeouts=1
```

```
cedrus 1c0e000.video-codec: frame processing timed out!
v4l2-request: Timeout when waiting for media request
```

**Any** use of the H.265 secondary output hangs the engine. Note the control
line proves nothing about the new code: with no scale and no rotation
`cedrus_transforming()` is false, so `cedrus_sd_program()` returns early.

## What that rules out

- **Not rotate-specific and not scale-specific.** Either alone hangs, so it is
  not the `[2:0]` rotate field or the `[11:8]` shift packing.
- **Not the DPB indirection.** `cedrus_dst_buf_addr()` forwards to
  `cedrus_frame_addr()`, so H.265 reference frames already go to the private
  reconstruction buffer exactly as H.264's do.
- **Not the enable being clobbered.** `cedrus_h265_setup()` ends with a bare
  `cedrus_write(VE_DEC_H265_CTRL, IRQ_MASK)`, but `cedrus_sd_program()` runs
  after it, so bit 9 survives.
- **Not the secondary chroma buffer length.** `VE_CHROMA_BUF_LEN[27:0]`
  (`VE_CHROMA_BUF_LEN_SDRT`) is never programmed by cedrus for either codec;
  setting it the way `cedrus_dst_format_set()` computes the primary's changed
  nothing.

## Where to look next

The vendor writes four top-level registers in this path from values in its own
context, and only two were replicated:

```
0001535c  str w6, [x5, #0xe8]   ; VE_CHROMA_BUF_LEN      = [ctx+0xd0] | ([ctx+0x9c] << 30)
0001536c  str w6, [x5, #0xec]   ; VE_PRIMARY_OUT_FMT     = [ctx+0x9c] | ([ctx+0x94] << 4)
00015374  str w6, [x5, #0xc4]   ; VE_PRIMARY_CHROMA_BUF_LEN = [ctx+0xb0]
00015380  str w6, [x5, #0xc8]   ; VE_PRIMARY_FB_LINE_STRIDE = [ctx+0xa4] | ([ctx+0xa8] << 16)
0001538c  str w6, [x5, #0xcc]   ; VE_SECONDARY_FB_LINE_STRIDE = [ctx+0xc4] | ([ctx+0xc8] << 16)
```

Mapping `ctx+0x94/0x9c/0xa4/0xa8/0xb0/0xc4/0xc8/0xd0` to their meanings is the
obvious next step — they are written by whatever configures the output, and
`H265DecoderSetExtraScaleInfo` (`ctx+0x3008..0x3014`, enable `ctx+0x3018[0]`)
is a different structure, so the two need relating.

Also untested: whether the `>> 8` addressing is right in *our* context. It is
unambiguous in the disassembly, but if the vendor's stored address is already
encoded differently the extra shift would be wrong. A targeted A/B of shifted
versus raw is cheap and has not been run.

`tools/video/hevc-rotation-check.sh` is the rig; it needs only a module swap,
no bench time.
