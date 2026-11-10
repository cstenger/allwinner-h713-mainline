# Block 7 is VE + 0xf00 — and the arbitrary-ratio scaler supports 1.5x

2026-09-11, static RE plus headless hardware probes. Follow-on from
[ARBITRARY-RATIO.md](ARBITRARY-RATIO.md), which named the blocker as "the
physical base of VE register block 7". **That blocker is resolved.**

Still not achieved: an actual 1280x720 frame out of the decoder. The enable and
the coefficient upload were both attempted next and came back negative — see
[COEF-UPLOAD.md](COEF-UPLOAD.md), and read the "What is still missing" section
below against the corrections at the end of this file.

## Block 7 = VE + 0xf00

Not a separate physical address, and not outside our mapping. It was inside the
4 KiB window the whole time, reading zero because nothing had programmed it.

The getter is `VeGetGroupRegAddr(_, group)`, exported from `libVE.so` at
`0x4ced` — **not** in `libvideoengine.so`, which turned out to be the decoder
plugin registry. `GetVeOpsS` resolves through libVE's own PLT to
`getVeAwOpsS`/`getVeVp9OpsS`, both defined in libVE.so.

```
cmp   r1, #8                  ; group must be < 8
ldr.w r0, [r0, r1, lsl #2]    ; r0 = index_table[group]
ldr   r2, [r2, #8]            ; r2 = the mmapped VE base
rsb   r0, r0, r0, lsl #3      ; *7
add.w r0, r1, r0, lsl #2      ; -> descriptor array, stride 28 bytes
ldr   r0, [r0, #0x18]         ; the byte OFFSET
add   r0, r2                  ; ve_base + offset
```

Decoding both tables gives:

| group | offset | what |
| --- | --- | --- |
| 0 | `0x000` | top-level VE |
| 1 | `0x100` | MPEG engine |
| 2 | `0x200` | H.264 engine |
| 3 | `0x300` | |
| 4 | `0x400` | |
| 5 | `0x500` | H.265 engine |
| 6 | `0xe00` | |
| **7** | **`0xf00`** | **the arbitrary-ratio scaler** |

Groups 1, 2 and 5 match mainline cedrus's `VE_ENGINE_DEC_MPEG` (0x100),
`VE_ENGINE_DEC_H264` (0x200) and `VE_ENGINE_DEC_H265` (0x500) exactly. That is
an independent check that the tables were read correctly, not a coincidence I
had to assume.

So the new scaler's registers are:

```
0xf10   two 14-bit size fields   ([29:16] and [13:0])
0xf14   two 16-bit ratios, 12 fractional bits
0xf18   two 14-bit size fields
0xfe4   30-bit value at bit 2
0xff8, 0xffc
```

### Confirmed writable on hardware

```
sd: poke 0xf10 = 0x050002d0 (reads 0x050002d0)
sd: poke 0xf14 = 0x182d1800 (reads 0x182d1800)
sd: poke 0xf18 = 0x07800440 (reads 0x07800440)
```

And they survive to the decode trigger — the register snapshot shows them still
held at `0xf10/0xf14/0xf18` with the rest of `0xf00..0xf3c` at zero. **Block 7 is
real silicon on the H713**, not a block that only exists on other parts.

## The scaler supports 1.5x — 14 ratio buckets, 1.125x to 5x

`ScaleCopyCoef(ratio_float, dst)` buckets the ratio and copies a 128-byte
coefficient set:

```
ratio < 1.125  -> return 0, no coefficients (too close to unity)
     < 1.25    -> bucket 1        < 2.25 -> bucket  8
     < 1.375   -> bucket 2        < 2.5  -> bucket  9
     < 1.5     -> bucket 3        < 2.75 -> bucket 10
     < 1.625   -> bucket 4        < 3.0  -> bucket 11
     < 1.75    -> bucket 5        < 4.0  -> bucket 12
     < <const> -> bucket 6        < 5.0  -> bucket 13
     < 2.0     -> bucket 7        >= 5.0 -> a separate table at +0x700
memcpy(dst, table + bucket*128, 128)
```

**1920 -> 1280 is 1.5x, which lands in bucket 4.** So the hardware does support
the ratio we need; this is not another power-of-two dead end.

### The coefficients, extracted

Table at `libawh264.so` vaddr **`0x5d88`**, 14 sets x 128 bytes. Format is
**32 phases x 4 int8 taps**, and **every phase sums to exactly 128** (unity in
Q7). Saved as [ve-scaler-coefficients.bin](ve-scaler-coefficients.bin) and
[ve-scaler-coefficients.txt](ve-scaler-coefficients.txt).

```
bucket 0, phase  0:    0  127    1    0     <- near-impulse, unity ratio
bucket 0, phase 16:   -8   72   72   -8     <- half-pixel
bucket 4, phase  0:   22   84   22    0     <- wide antialiasing kernel for 1.5x
bucket 4, phase 16:    0   64   64    0
```

All 14 buckets pass the sum check on all 32 phases. Sixty-four consecutive
groups summing to exactly 128 is not something a wrong address produces, so the
table location and packing are confirmed without needing hardware.

## What is still missing

Two things, and one of them I deliberately did not attempt.

**1. The enable.** `VE_H264_CTRL` (`0x220`) is the candidate: the vendor clears
bits 8 and 9 and **sets bit 11**. On hardware, setting bit 11 produces
`frame processing timed out!` and one frame instead of 25 — both with block 7
zeroed *and* with block 7 fully configured (sizes, ratios, stride, chroma
length). So bit 11 is not sufficient, and something else in the sequence is
missing. It is also possible bit 11 is not the enable at all and my reading of
that `bic/orr/bic` triple is picking the wrong register.

Worth stating because the numbers invite the wrong reading: under bit 11 the
secondary buffer comes back untouched, which looks like "switched to a mode that
is not configured". It is not that — the *decode itself* fails. Always check the
frame count next to the buffer.

**2. The coefficient upload.** The 256-byte stack buffer in
`H264ConfigNewScaler` is two `ScaleCopyCoef` calls of 128 bytes (one per axis),
and it has to reach the hardware through the **AVC SRAM port** (`0x2e0` offset,
`0x2e4` data). My harness *refuses* those ports by design — they walk an
internal pointer, so a stray write corrupts a decode rather than configuring
it. Enabling a polyphase resampler with an empty coefficient RAM stalling the
pipeline is a plausible explanation for the bit-11 timeout, and testing that
means lifting the refusal for the offset/data pair specifically, under a
deliberate opt-in.

## Next step — DONE, and negative

See [COEF-UPLOAD.md](COEF-UPLOAD.md). Two corrections to this document came out
of it:

- The coefficient port is **group 7's own, `0xff8`/`0xffc`** — not the AVC port
  at `0x2e0`/`0x2e4` as guessed below.
- `VE_H264_CTRL` bit 11 disrupts H.264 control rather than enabling anything;
  group 7's own `0xf20` bit 11 is harmless and equally inert.

With geometry, both ratio forms, a working buffer and the bucket-4 coefficients
all programmed and readback-verified, the arbitrary-ratio unit still produces no
output. Group 7 latches every write but nothing observable happens, so the
leading explanation is that the H713 does not implement the datapath behind the
register block.

So the remaining no-GPU option is still the fallback in [RESULT.md](RESULT.md):
power-of-two to 960x544, then the proc upscaler at `0x05180000` magnifying
1.333x. Lossier than a single-pass 1.5x would have been, but both halves are
measured.

## Method note

Getting here required fixing the address translation *twice*. The first was the
`.text` skew recorded in [ARBITRARY-RATIO.md](ARBITRARY-RATIO.md). The second:
the skew is **per-segment**, not per-file. In `libVE.so`, `.rodata` has
Addr == Off (skew 0) while `.text` has skew 0x1000 and `.data` skew 0x3000.
Applying the text skew to a `.rodata` table address produced ASCII strings where
a table should be, and I nearly read that as "the table is not there". The fix
is to build a vaddr->offset map from the LOAD program headers and use it for
every read:

```python
segs = [(va, va+filesz, off) for each LOAD]
def f(va): return off + (va - lo)   # for the segment containing va
```

The self-check that caught it: one of the three literals resolved to `0xe1b0`,
exactly `.data`'s start, which was obviously right — so the arithmetic was
correct and the *translation* was wrong.
