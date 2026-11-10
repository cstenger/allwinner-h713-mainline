# The selection is software, and the route is closed

2026-09-11, static RE plus a final headless sweep. Closes the arbitrary-ratio
line of enquiry opened in [ARBITRARY-RATIO.md](ARBITRARY-RATIO.md) and continued
in [BLOCK7-FOUND.md](BLOCK7-FOUND.md) and [COEF-UPLOAD.md](COEF-UPLOAD.md).

**Conclusion: the H713's VE implements the power-of-two scale-down and not the
arbitrary-ratio one.** Group 7's register file is present and writable; the
datapath behind it is not.

## The selection site

`H264ConfigNewScaler` and `H264ConfigureScaleRotateRegister` are called from
12 bytes apart, in the same `if`:

```
0x00e91c  ldrb.w r0, [r7, #0x2e2]   ; per-stream gate; 0 -> configure NEITHER
0x00e922  cbz    r0, #0xe940
0x00e924  ldr    r0, [r4, #0x40]    ; the scale MODE, from userspace
0x00e926  cmp    r0, #2
0x00e928  bne    #0xe936
0x00e92a  mov r0,r4 ; mov r1,sl ; mov r2,fp
0x00e930  blx    #0x17090           ; mode == 2 -> H264ConfigNewScaler
0x00e934  b      #0xe940
0x00e936  mov r0,r4 ; mov r1,sl ; mov r2,fp
0x00e93c  blx    #0x170a0           ; otherwise -> H264ConfigureScaleRotateRegister
```

So **`ctx+0x40 == 2` picks the arbitrary-ratio path** and anything else picks
fixratio. The mode comes from userspace — `ConfigExtraScaleInfo` validates that
it and the rotate mode are each `< 4`, then forwards to a plugin method at
`[obj+0x20]`.

There is **no hardware "use the new scaler" bit** anywhere in this sequence. The
two paths differ only in which registers the software chooses to program, and
they are mutually exclusive — `ConfigNewScaler` writes `0x244`/`0x248` but
never touches `VE_H264_SDROT_CTRL` at `0x240`.

### How it was found, and a method correction

I twice reported "no call sites" for these functions. Both were wrong, for two
different reasons, and both times the null was an artifact:

1. **Linear disassembly desynchronises.** Sweeping `.text` from its start and
   matching branch targets found *zero* callers even for
   `H264ComputeScaleRatio`, which obviously has some. Thumb is variable-length
   and `.text` contains inline literal pools, so a linear decode goes out of
   phase almost immediately and most real instructions are never seen. The fix
   is to decode the BL/BLX encoding at every 2-byte slot instead of trusting a
   sweep: 681 call sites appear where 0 did.
2. **Exported functions are called through the PLT, even from inside their own
   library.** `.rel.plt` carries `R_ARM_JUMP_SLOT` entries for
   `H264ConfigNewScaler` (GOT `0x185bc`) and
   `H264ConfigureScaleRotateRegister` (GOT `0x185c0`), so the call sites branch
   to PLT stubs at `0x17090`/`0x170a0`, not to `0xdb70`/`0xde78`. Resolving
   stub -> GOT slot -> symbol is what made the call graph visible.

The sanity check that exposed the first error: a scanner that reports zero
callers for a function that must have callers is broken, not informative.

## The final hardware sweep

`ConfigNewScaler` never writes `0x240`, so the possibility remained that the
new path needs an enable bit *there* that I had not tried — after moving to the
correct register I had only swept its low bits, because the earlier wide sweep
was done against the wrong address (top-level `VE+0x40`).

Swept every remaining bit of `VE_H264_SDROT_CTRL`, with the complete
arbitrary-ratio configuration loaded and verified (geometry, both ratio forms,
working buffer, bucket-4 coefficients):

```
0x1000 0x2000 0x4000 0x8000 0x10000 0x20000 0x40000 0x80000 0x100000 0x200000
0x400000 0x800000 0x1000000 0x2000000 0x4000000 0x8000000 0x10000000
0x20000000 0x40000000 0x80000000      -> all "nothing", 20/20 frames, no timeouts

control 0x500 -> 960x544 output as always
control 0x0   -> nothing
```

**Every bit of `SDROT_CTRL` is now characterised.** Only `[9:8]` and `[11:10]`
do anything, and they are the two power-of-two ratio fields. There is no enable
bit for a second scaler.

## Why this closes it

Four independent things now point the same way:

- The secondary output appears **only** when `SDROT_CTRL`'s power-of-two ratio
  fields are non-zero, and nothing else influences it.
- Group 7 (`VE+0xf00`) accepts and holds every write — geometry, ratios,
  inverse ratios, working buffer, 64 words of coefficients — and produces no
  observable effect.
- The selection is software-only, so there is no missing hardware enable to
  find; reproducing every register `ConfigNewScaler` writes *is* the whole
  configuration, and it was reproduced.
- `VE_VERSION` (`0x0f0`) reads `0x00000000`, `libVE.so` gates on `ic_version`
  with `You should know ic version!`, and `libawh265.so` carries
  `this hardware not support fixratio scale` — this vendor codebase handles
  per-SoC scaler capability differences explicitly.

A register file latching values is not proof the logic behind it exists. That
was the risk flagged when group 7 first accepted writes, and it is now the
conclusion rather than a caveat.

### What would still falsify it

One clean discriminator remains, and it needs no register work: boot the vendor
stack, play a 1080p file, and see whether the decoder emits a non-power-of-two
secondary output. If it does, the capability is there and I am missing a step;
if it falls back to 960x544 or letterboxes, the hardware agrees with this
conclusion. That is blocked on the vendor stack booting at all
(`docs/` vendor-stack notes: red->blue LED, zero UART as of 2026-08-26), so it
is a separate errand rather than a next step.

## Practical outcome

Unchanged from [RESULT.md](RESULT.md): the only measured no-GPU route to 1080p
on the 720p panel is

> **VE power-of-two to 960x544, then the proc upscaler at `0x05180000` with
> `ratio_h = 0xC000` for 1.333x -> 1280x725.**

Both halves are hardware-confirmed. It is lossier than a single-pass 1.5x
polyphase downscale would have been, and that is now a settled limitation of the
silicon rather than an open question.
