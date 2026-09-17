# The H.265 scale-down path is a separate scaler block at VE + 0xf00

**Update 2026-09-17:** [The shared-scaler handoff](../handoff-2026-09-17-shared-scaler.md) supersedes
the H.264 routing, power-of-two quantization, and rotation recommendations
below. Patch 0120 uses this polyphase block for both codecs and removes rotation.

**Source: H713's OWN vendor blob**, not H6-CedarC —
`local/h713-lab/ve-extract/libs/libawh265.so` (ARM32 Thumb, Android 30,
`.symtab` stripped but **every function is exported via `.dynsym`**).
No hardware, no booting the vendor stack.

This supersedes the working assumption behind patches 0097/0099-era H.265 work:
that the H.265 secondary output is the H.264 SDROT recipe at different offsets.
**It is not, and that approach cannot work by construction.**

## Why our port times out

`HevcJudgeScaleMode` @ `0x19ea1` sets a mode field to **2** whenever a real
downscale is requested:

```
r7 = src_w, ip = src_h      ; r5 = req_w, r0 = req_h
if (src_w <= req_w && src_h <= req_h) skip    ; nothing to do
if (req_w == 0 || req_h == 0)          skip
if (mode != 0)                         skip    ; already decided
mode = 2
```

`HevcSetOutputConfigReg` @ `0x1a5f5` then branches on it:

```
0x1a882  ldr r6,[sl,#4] ; ldr r0,[r6,#8]      ; r0 = scale mode
0x1a888  cmp r0, #2
0x1a88a  bne.w #0x1aa76                       ; -> simple scale_precision path
         ...                                  ; mode 2 falls through here
```

The `reg50.scale_precision` path at `0x1aa76` — the power-of-two shift pair
that mainline's dead defines describe and that our driver implements — is the
**`mode != 2`** path. For an actual scale-down the vendor never takes it.

Mode 2 instead does `veOps->getGroupRegAddr(self, 7)` and programs a different
register block. We set `write_sc_rt_pic` (CTRL bit 9) and leave that block
unconfigured, so the engine waits on it forever: `frame processing timed out`.

## Group 7 = "VE/Top1 Level" = VE + 0xf00

From `libVE.so` (`/lib/libVE.so` in `vendor.img`), the group table — 10 entries
of 28 bytes, `{int id; char name[20]; int offset;}`:

| idx | id | offset | name |
| --- | --- | --- | --- |
| 0 | 0 | `0x000` | VE/Top Level |
| 1 | 1 | `0x100` | DEC/Mpeg 1/2/4 |
| 2 | 2 | `0x200` | DEC/H264 |
| 3 | 3 | `0x300` | DEC/VC-1 |
| 4 | 4 | `0x400` | DEC/RV |
| 5 | 5 | `0x500` | DEC/H265 |
| 6 | 6 | `0xe00` | DEC/JPEG |
| 7 | 2 | `0x200` | DEC/AVS |
| 8 | 5 | `0x500` | DEC/AVS2 |
| 9 | **7** | **`0xf00`** | **VE/Top1 Level** |

H6-CedarC's `VE_REGISTER_GROUP` enum stops at 6 (JPEG) and has no `0xf00`
entry at all — which is why reading that source could never have found this.

## What the block is

A **4-tap / 32-phase polyphase scaler with loadable coefficients**, not a shift
divider. Offsets are relative to VE + 0xf00. Every field is written with
read-modify-write `bfi`, so the block carries live bits — never blind-store it.

| offset | field | meaning |
| --- | --- | --- |
| `+0x10` | `[29:16]`, `[13:0]` | **14-bit** output dims — `[13:0]` pairs with the horizontal ratio, `[29:16]` with the vertical |
| `+0x14` | `[15:0]`, `[31:16]` | **step**: `(src << 12)/dst - 1`, horizontal in the low half, vertical in the high half |
| `+0x18` | `[13:0]`, `[29:16]` | **inverse ratio**: `(dst << 12)/src - 1`, same axis order |
| `+0xe4` | `[31:2]` | a buffer address, written as `(addr >> 10) << 2` — i.e. `addr >> 8` with the low 2 bits cleared, the same `>>8` convention as `reg54`/`reg58` |
| `+0xf8` | `[11:2]` | coefficient FIFO index — the blob writes the constant `0x340` |
| `+0xfc` | word | coefficient FIFO data port, written **64 times** (see below) |

Both ratios are computed with round-to-nearest, e.g. horizontal step:

```
r2 = ((src << 12) + dst/2) / dst - 1
```

For 1280 -> 640 that is `(1280<<12)/640 - 1 = 0x1FFF`. A float copy of each
ratio is computed alongside (`vdiv.f32 s16/s18`) purely to pick the filter set.

### Coefficient upload

```
H265ScaleCopyCoef(v_ratio_float, buf)          ; 128 bytes -> buf
H265ScaleCopyCoef(h_ratio_float, buf + 0x80)   ; 128 bytes -> buf+0x80
[+0xf8] = 0x340 at [11:2]
for (i = 0; i < 32; i++) [+0xfc] = buf[i];          /* vertical   */
for (i = 0; i < 32; i++) [+0xfc] = buf[0x20 + i];   /* horizontal */
```

`H265ScaleCopyCoef` @ `0x1df79` picks one of **15 sets** by downscale ratio and
`memcpy`s 0x80 bytes. Table base is `.rodata` **`0x9030`**, set *i* at
`0x9030 + i*0x80`; `0x9030 + 15*0x80 = 0x97b0` is exactly the end of `.rodata`.

| idx | ratio | idx | ratio | idx | ratio |
| --- | --- | --- | --- | --- | --- |
| 0 | `< 1.125` | 5 | `< 1.75` | 10 | `< 2.75` |
| 1 | `< 1.25` | 6 | `< 1.875` | 11 | `< 3.0` |
| 2 | `< 1.375` | 7 | `< 2.0` | 12 | `< 4.0` |
| 3 | `< 1.5` | 8 | `< 2.25` | 13 | `< 5.0` |
| 4 | `< 1.625` | 9 | `< 2.5` | 14 | `>= 5.0` |

A NULL destination returns -1; a ratio below 1.125 yields set 0.

Each set is 32 phases x one word, and **each word is 4 signed bytes summing to
exactly 128** — unity gain in Q7. Set 0 phase 0 is `(0, 127, 1, 0)`, effectively
a passthrough; set 14 phase 0 is `(35, 58, 35, 0)`. All 480 phases across all
15 sets check out, which independently confirms the base address and layout.

**We no longer use the vendor's table — see "Our own coefficients" below.**
The extracted copy was only ever a scoring baseline and has been deleted.

**Consequence: H713 CAN downscale H.265, at arbitrary ratios — better than the
power-of-two-only H.264 SDROT — but only through this block.**

## HARDWARE-CONFIRMED MAP (2026-09-16, read + write-readback on the board)

The block is **live, mapped and writable from our driver**. A
write-`0xffffffff` / read-back / restore sweep of all 64 words returned these
15 implemented registers. Every register read **0 before the probe** — in a
plain decode, in a scaled decode, and while the engine was wedged — so the
reset state really is all-zero and nothing pre-initialises it.

| offset | writable mask | blob writes it? | reading |
| --- | --- | --- | --- |
| `+0x00` | `0000001f` | **no** | 5-bit control — mode/enable |
| `+0x04` | `00000001` | **no** | single flag — start/bypass |
| `+0x0c` | `3fff3fff` | **no** | two 14-bit dims — input size |
| `+0x10` | `3fff3fff` | yes | two 14-bit dims — output size |
| `+0x14` | `ffffffff` | yes | step, `(src<<12)/dst - 1`, H low / V high |
| `+0x18` | `3fff3fff` | yes | inverse, `(dst<<12)/src - 1` |
| `+0x20` | `ffffffff` | **no** | ? |
| `+0x24` | `ffffffff` | **no** | ? |
| `+0xe4` | `fffffffc` | yes | address `>>8`, 4-byte aligned |
| `+0xe8` | `fffffffc` | **no** | address |
| `+0xec` | `fffffffc` | **no** | address |
| `+0xf0` | `fffffffc` | **no** | address |
| `+0xf4` | `fffffffc` | **no** | address |
| `+0xf8` | `00000ffc` | yes | coefficient FIFO index (`0x340`) |
| `+0xfc` | `ffffffff` | yes | coefficient FIFO data |

**The masks independently confirm every field width recovered from the
disassembly** — `+0x10`/`+0x18` came back exactly `3fff3fff` (the two 14-bit
`bfi` fields), `+0xe4` exactly `fffffffc` (the `[31:2]` address), `+0xf8`
exactly `00000ffc` (the `[11:2]` index). That is five independent confirmations
that the RE is right, from hardware rather than from reading the same binary
twice.

**`+0x00` (5 bits) and `+0x04` (1 bit) are the strongest candidates for the
missing enable/trigger**, and `HevcSetOutputConfigReg` does not touch either —
consistent with them being set once in the VE-open path rather than per
picture. This is an inference from the mask widths plus the blob's silence, not
something observed being written; it needs confirming against whatever sets up
the VE (likely in `libVE.so`/`libcdc_base.so`, not the codec lib).

There are **five** address registers (`+0xe4`..`+0xf4`), of which the blob
writes only the first. A plausible split is input luma/chroma, output
luma/chroma and a line buffer, but that is a guess.

Probing caused no IOMMU faults, no Oops and no hang; the board stayed healthy
across the whole sweep.

## FIRST WORKING RUN (2026-09-16): it decodes, at the right scale

Programming `+0x10`, `+0x14`, `+0x18`, `+0xe4` and the coefficient upload is
**enough to make an H.265 scaled decode complete**. Thirty frames, zero ffmpeg
errors, **no timeout and no IOMMU fault**, and a full capture buffer produced.
Every previous attempt timed out. WIP sources:
`local/h713-lab/ve-extract/derived/*.scaler-wip`.

The staging is worth recording because each step was diagnostic:

1. Configure the block but leave `+0xe4` at 0 -> the decode still fails, but the
   symptom **changes** from a bare timeout to
   `sun50i-iommu: Page fault for 0x0 (master 0, dir rd)`. The block is now
   *fetching*, which proves the configuration took.
2. Point `+0xe4` at a mapped buffer -> **fault and timeout both disappear**, and
   a real picture appears in the capture buffer.

Geometry is **correct**, and checked rather than assumed:

- the picture lands in the top-left `640x360` of the 1280-stride canvas; the
  region to the right is ~0 and below is exactly 0, as it should be;
- a scale sweep against software references at 640x360, 648x368 ... 704x424
  ranks **640x360 best**, so the scale factor really is 2x, not merely close;
- per-block offset search finds `dx = dy = 0` across the frame, so there is no
  drift;
- horizontal gradient energy 1.46 vs the reference's 1.49 — the polyphase
  filter is doing real filtering and is not blurring.

## IT IS CORRECT NOW — the field order was backwards

**The bug was the H/V field assignment.** In all three geometry registers the
**HIGH half is horizontal/width and the LOW half is vertical/height** — the
opposite of what the disassembly appeared to say. Corrected:

| register | `[31:16]` / `[29:16]` | `[15:0]` / `[13:0]` |
| --- | --- | --- |
| `+0x0c` in size | width | height |
| `+0x10` out size | width | height |
| `+0x14` step | horizontal `(src_w<<12)/out_w - 1` | vertical |
| `+0x18` inverse | horizontal `(out_w<<12)/src_w - 1` | vertical |

Results, luma PSNR against a software scale of the same frame:

| case | PSNR | uniformity |
| --- | --- | --- |
| 1280x720 -> 640x360 (2x/2x) | **41.87 dB** | top 42.10 / bottom 41.65 |
| 1280x720 -> 640x180 (2x/4x) | **36.55 dB** | top 36.25 / bottom 36.88 |

**The banding is gone** — that was the wrong-field-order signature, not a
sequencing problem. For calibration, the hardware-filter emulation scores
41.89 dB against bicubic, so at 41.87 dB the hardware is as close to the
reference as a correct scaler can be.

**A symmetric ratio cannot find this bug.** With 2x on both axes the step and
inverse values are identical, so only `+0x10` (640 vs 360) differs, and a
partial fix looks like success. The 2x/4x asymmetric case is what pins every
field down — fixing `+0x10`/`+0x14` but leaving `+0x18` swapped still gave a
correct-looking symmetric result and **5.38 dB** asymmetric. Always validate a
scaler on an asymmetric ratio.

Coefficient bank order (vertical first vs horizontal first) is worth only
~0.2 dB even on the asymmetric case; the vendor's order (vertical first) is
kept because it is what the blob does, not because it measurably wins.

Working implementation:
`local/h713-lab/ve-extract/derived/*.scaler-working`.

## Main10 works too

**`h07-640x480-main10.h265` scaled 640x480 -> 320x240: luma 39.34 dB**
(top 38.88 / bottom 39.86), **chroma U 36.10 dB, V 31.15 dB**. Means match the
reference to a tenth of a level. Three things were needed:

**1. The reconstruction buffer was allocated too small at 10 bits — a real
pre-existing bug.** `cedrus_update_recon_format()` calls
`cedrus_prepare_format()` directly and never adds `extra_cap_size`, so the
recon buffer got room for the 8-bit planes only and the engine wrote its 2-bit
plane past the end. This only bites when the scaler is on, because that is the
only time the reconstruction lives in its own buffer.

**2. The first-output 2-bit registers describe the RECONSTRUCTION when scaling.**
`cedrus_h265_setup()` computed them from `dst_fmt`; with the scaler on that is
the *scaled* picture, so both the offset and the 2-bit stride were wrong. They
must come from `recon_fmt`.

**3. The secondary output needs its own 2-bit plane**, programmed in the same
place as the rest of the secondary config:

```c
VE_DEC_H265_OFFSET_ADDR_SECOND_OUT = dst_fmt.sizeimage - 2bit_size(w, h);
VE_DEC_H265_10BIT_CONFIGURE |= SECOND_2BIT_STRIDE(ALIGN(w / 4, 32))
                             | SECOND_2BIT_ENABLE
                             | SECOND_OUT_FMT(8BIT_PLUS_2BIT);
```

Mainline already carries every one of these defines — `OFFSET_ADDR_SECOND_OUT`,
`SECOND_2BIT_STRIDE` `[21:11]`, `SECOND_2BIT_ENABLE` BIT(22), `SECOND_OUT_FMT`
`[24:23]`, and the `8BIT_PLUS_2BIT / P010 / 10BIT_4x4_TILED` enum — as **dead
defines that nothing ever wrote**, and they match the vendor's
`regHEVC_10BIT_CONFIGURE` struct bit for bit.

Checking **chroma** is what rules out a bad 2-bit offset: a wrong
`OFFSET_ADDR_SECOND_OUT` lands the 2-bit plane inside the chroma plane, which
luma-only PSNR cannot see.

### Regression sweep

All seven HEVC vectors pass **scaled and unscaled**, 30 frames each, zero
timeouts and zero faults: h01 main, h02 720p, h03 no-WPP, h04 scaling lists,
h05 custom scaling lists, h06 lossless, h07 Main10. H.264 scaling is
unaffected.

### MEASUREMENT TRAP — `-pix_fmt gray` corrupts the reference

An earlier pass reported 18.2 dB using `ffmpeg -pix_fmt gray` references. That
number was measured wrong: **`gray` applies a limited->full range expansion**,
so every comparison was against a rescaled reference.

**Always validate the yardstick with an UNSCALED control.** An unscaled
hardware HEVC decode must be bit-exact against the software decode:

| reference | unscaled control | verdict |
| --- | --- | --- |
| `-pix_fmt gray` | **28.7 dB** | pipeline broken, all numbers junk |
| `-pix_fmt yuv420p`, take the luma plane raw | **99.0 dB** | bit-exact, trustworthy |

Extract luma by taking the first `W*H` bytes of a `yuv420p` frame; never let
ffmpeg convert to `gray`. The control also rules out frame-ordering doubts:
dump capture #1 with `CEDRUS_DUMP_AT=1` and compare against software frame 0,
where decode order and display order agree.

### Proven irrelevant (each verified byte-identical output)

- **The power-of-two shifter.** The vendor's mode 2 leaves
  `reg50.scale_precision` at zero and lets this block do all the scaling;
  setting it to 1,1 alongside the scaler changes **nothing at all**.
- **`+0x0c` input size.** Writing the source dimensions changes nothing.
- **`+0xe4` is NOT the image source.** Pointed at a freshly allocated, zeroed
  1 MiB scratch buffer the output is still a real picture, so the pixels come
  from the decode pipeline on the fly. `+0xe4` behaves like a line/scratch
  buffer: it must be valid (or the block faults reading address 0) but its
  contents do not feed the image.
- **The other four address registers `+0xe8`..`+0xf4` are UNUSED.** Each was
  pointed at its own 512K region poisoned with `0xa5` and the dirty-byte count
  read back after decoding. Result:
  `dirty bytes (e4 e8 ec f0 f4) = 7680 0 0 0 0` — only `+0xe4` is ever written,
  and the output is byte-identical with the other four programmed. So the
  banding is **not** a missing-buffer problem.

  **`+0xe4` takes exactly 7680 bytes = 6 source lines of 1280** — the working
  set of a 4-tap vertical filter plus margin. It is sized and used correctly.

## The coefficient FIFO, probed

- **`+0xf8` does not visibly auto-increment.** Read back after 64 writes to the
  data port it still holds exactly what we wrote (`0x0d00` = `0x340 << 2`).
- **`+0xfc` is a latch, not a window onto coefficient RAM.** Reading it returns
  the *last written word* (`c0de003f`, our k=63 pattern) at index `0x340` and at
  index `0` alike. Coefficient RAM cannot be verified by read-back.
- **The hardware DOES auto-increment internally.** Rewriting `+0xf8` before each
  word — plausible given the two facts above — makes the picture dramatically
  worse (**5.35 dB**, versus 19.03 dB for index-once). So the blob's sequence
  (set the index once, then stream 64 words) is right, and our implementation
  already matched it.

That 5.35 dB is a useful **sensitivity handle**: getting the coefficients wrong
costs ~14 dB. At 19 dB ours are landing roughly where they should.

## The reference is NOT the problem

The obvious remaining excuse was that we compare a vendor 4-tap filter against
ffmpeg's bicubic. Emulating the hardware's own filter in numpy — 32 phases,
4 signed taps, `/128`, phase = bits `[11:7]` of the Q12 position, using the
coefficient set the driver actually selects — gives:

| comparison | PSNR |
| --- | --- |
| hardware vs its own filter emulated | **19.05 dB** |
| hardware vs ffmpeg bicubic | 19.03 dB |
| **emulation vs bicubic** | **41.89 dB** |

The two independent references agree with each other at 41.9 dB; the hardware
disagrees with both at ~19 dB. **The hardware output genuinely differs from any
correct 2x downscale of the source** — this is not a filter-kernel artefact and
not a yardstick artefact.

## What is still unknown

- The **enable/trigger** for the 0xf00 block. Nothing in this function obviously
  starts it; either `write_sc_rt_pic` is sufficient once the block is
  configured, or there is a bit elsewhere in group 7 that this path does not
  touch because it was set at init.
- What `[sb+0x44]` (the `+0xe4` address) actually points at — a line buffer or
  an intermediate surface. It is NOT the output buffer: that is still
  `reg54`/`reg58` from the DPB entry.
- Whether `+0xf8 = 0x340` is a fixed FIFO reset index or encodes a
  target/phase count.
- Whether the block is shared with any other user (the JPEG group sits at
  `0xe00`, immediately below).

**Addressing is NOT a blocker:** the DT window is `reg = <0x01c0e000 0x1000>`
and `/proc/iomem` confirms `01c0e000-01c0efff`, so `0xf00`-`0xfff` is already
inside the mapped range. `cedrus_read()`/`cedrus_write()` reach it with no DT
change. Reading the block to dump its reset state is therefore safe and is the
obvious first hardware step.

## Two corrections to earlier notes

1. **`DDR_CONSISTENCY_EN` (CTRL bit 31) IS set on H713.** H6-CedarC gates it on
   `nDecIpVersion == 0x31010`; H713's blob tests `0x31010 || 0x33110`, and
   H713 reads **`0x33110`** (live, from VE top `0xe0`; `0xf0` reads 0, `0xe4` =
   `0x12011`). The note saying it should be clear was derived from the wrong
   source. Setting it alone does not fix the hang — both states were tested.
2. **There is no `VECORE_MODESEL_REG` access in this version.** H6-CedarC
   read-modify-writes bit `0x00200000` between the `0xe8` and `0xec` writes;
   H713's blob goes straight from `0xe8` to `0xec`. Leaving MODESEL alone is
   correct.

Everything else we program — `0xe8`/`0xec`/`0xc4`/`0xc8`/`0xcc`, `reg50` field
layout, `reg54`/`reg58` as `addr >> 8`, `reg80` low-8 chroma bytes — matches
the blob exactly. That was verified independently on hardware: a register dump
taken just before the trigger is bit-identical between a working H.264 scale
and a hanging H.265 scale.

## Method notes

- `.gnu_debugdata` here is a **header skeleton with no symtab** — not the usual
  MiniDebugInfo. Don't count on it; `.dynsym` is what carries the names.
- Local `objcopy`/`objdump` cannot read ARM ("Unable to recognise the
  architecture"), same as for aarch64. Use pyelftools + capstone.
- `.text` vaddr is file offset **+ 0x1000** here (per-segment skew, again).
- Register-name strings like `regHEVC_ExtraCtrl_reg50` live in **`.dynstr`**,
  not `.rodata` — they are exported `.bss` shadow-variable symbols, so
  `readelf --dyn-syms` maps every register to an address directly.
- Do not name a scratch disassembler `dis.py`; it shadows the stdlib `dis`
  module that `inspect` imports, and pyelftools fails with a confusing
  circular-import error.

## Our own coefficients — the licensing blocker is gone

`tools/video/gen-scaler-coef.py` generates an equivalent table from standard
kernels, so nothing proprietary needs to ship. Ours is measurably **better**
than the vendor's on hardware:

| case | ours | vendor |
| --- | --- | --- |
| 1280x720 -> 640x360 | **42.42 dB** | 41.87 |
| 1280x720 -> 640x180 | **36.88 dB** | 36.55 |
| Main10 640x480 -> 320x240 | **40.04 dB** | 39.34 |

It loses only below ratio 1.25, where the vendor's near-delta is sharper and
where a downscaler barely matters. Only 2 of 480 words coincide with theirs —
what two independent cubic designs look like, not a copy.

### How it was designed, and the two things that mattered

**A bit-accurate software model came first.** Fitting the arithmetic against
known-good hardware output gave **67.8 dB**, which is sub-LSB, so coefficients
could be designed and scored offline instead of guessed on the board. The model:
step is the true ratio (the register holds step-1), taps at `[ip-1..ip+2]`,
phase `(pos>>7)&31`, separable with a **full-precision intermediate**, final
`>>14` truncated, edges clamped.

**The design target has to be the metric you report.** A first attempt scored
against Lanczos-3 with full anti-aliasing and lost 1.3 dB on hardware: that
reference blurs harder than ffmpeg's bicubic, so the optimiser chose kernels
that were too wide. Scoring against ffmpeg's actual output, in full 2D, at each
bucket's real operating ratios, fixed it.

**At exactly 2x only phase 0 is used.** `step = 0x2000`, so `(pos>>7)&31` is 0
for every output pixel. A bucket optimised only at its midpoint gets its most
common case wrong, which is why each set is scored at its lower bound too.

Quantisation is largest-remainder with a **stable** tie-break; without that,
regeneration differed by +/-1 in 9 of 480 words across numpy versions. The
difference was immeasurable on hardware, but a generator that cannot reproduce
its own output is not a provenance record.

## The coefficient banks: FIRST is horizontal, SECOND is vertical

The 64-word upload is two 32-word banks, and the mapping is the opposite of
what the blob's `CopyCoef(v_ratio, buf)` / `CopyCoef(h_ratio, buf + 0x80)`
ordering suggests -- the same inversion already found in the geometry
registers, and settled the same way, on hardware.

Load a near-delta into the first bank and a heavy blur into the second, then
measure gradient energy per axis against the reference:

| upload order | horizontal | vertical |
| --- | --- | --- |
| delta, blur | **1.04x** (sharp/aliased) | 0.89x (blurred) |
| blur, delta | 0.91x (blurred) | **1.06x** (sharp/aliased) |

A clean mirror image: **the first bank drives horizontal, the second vertical.**

**A symmetric ratio cannot see this.** Both banks then hold the same set, so
2x/2x and 4x/4x are identical either way; only a mixed ratio exposes it. With
the wrong order, 1280x720 -> 640x180 applies the 4x kernel across and the 2x
kernel down and scores 35.08 dB. Corrected it scores **47.85 dB**.

That is also why an earlier order test looked like it proved the opposite:
run with bucket-averaged coefficients the two banks were nearly the same
filter, so swapping them moved the result by 0.2 dB and read as "order does not
matter". The test only becomes discriminating once the two banks differ
sharply. A null result from a test that cannot resolve the difference is not
evidence.

### Two process notes from this round

`install-kernel-module.sh` prints "loaded" even when the `scp` that precedes it
has failed, and the board's rootfs had filled to 100%, so several builds were
silently never installed -- one "impossible" measurement was simply a stale
module. **Verify the board's module md5 against the one just built**, every
time; the results above were all re-measured that way. 232M came back from
`journalctl --vacuum-size=40M`.

## Arbitrary ratios work, and that retires the composite route's reason to exist

`cedrus_compose_shift()` quantises every compose request to a power of two,
because that is all the H.264 SDROT shifter can express. The VE+0xf00 scaler
has no such limit, and forcing a non-power-of-two output through it works:

| case | PSNR | ratio | coef sets | phases exercised |
| --- | --- | --- | --- | --- |
| 1280x720 -> 960x540 | **44.06 dB** | 1.333 | 2 | 11 of 32 |
| 1280x720 -> 854x480 | **43.11 dB** | 1.499/1.500 | 3 and 4 | **32 of 32** |

No timeouts, no faults. The 1.5x case is the important one: it drives the whole
32-phase bank across two different coefficient sets -- machinery that had never
executed before, since at a power-of-two ratio only phase 0 is live -- and the
bucket-averaged sets, which until now were validated only against the software
model, hold up at 43 dB on silicon.

**Why this matters beyond the API.** The display path currently has the VE
produce 960x544 and the display proc upscale it to 1280x720, because 1920->1280
is 1.5x and the quantiser cannot express it. That second stage is patches 0098,
0103, 0106, 0108 and 0111, and the grey-streak / phase-window / route-window
class of bugs that cost most of this project's bench time. If the VE performs
1.5x directly, the display-side scaler leaves the video path entirely.

Caveats before acting on it:

- **The quantiser must stay for H.264.** Its SDROT really is power-of-two only,
  so this becomes a per-codec fork in `cedrus_compose_shift()`, not a
  replacement.
- Only two arbitrary ratios have been measured. Minimum and maximum ratio, and
  any output alignment requirement, are still inferred from field widths rather
  than probed.
- The exact-ratio phase-0 solutions do not help here -- non-power-of-two ratios
  use all 32 phases, so they get the bucket-averaged sets. 43-44 dB is good but
  it is below the 45-55 dB the power-of-two cases now reach.
- The API shape is still open: hantro uses `S_FMT` + `ENUM_FRAMESIZES` rather
  than `COMPOSE`, and `enum_framesizes` is unimplemented here. Worth settling
  before the selection logic is rewritten, not after.
