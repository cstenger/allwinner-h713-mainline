# VE scale-down probe — the fixratio register triple is NOT wired on H713

> ## ⚠ REFUTED THE SAME DAY — THE PROBE WAS AT THE WRONG BASE
>
> **The scale-down works.** This sweep programmed the **top-level** VE at
> `0x40`/`0x44`/`0x48`. The registers are in the **H.264 engine block** at
> **`0x240`/`0x244`/`0x248`**. Move the writes there and the hardware produces
> real scaled frames: [../ve-scaledown-2026-09-11/RESULT.md](../ve-scaledown-2026-09-11/RESULT.md)
> and [the handoff](../../handoff-2026-09-12-ve-scaledown.md).
>
> **Why sixteen clean nulls were not evidence.** The control register at the
> top-level base is real and writable, so it read back correctly — but the
> *address* registers there read back **zero**, and a scaler with nowhere to
> write produces nothing. The harness now aborts if the luma address reads zero,
> and the rule generalises: **a null is only evidence once the stimulus is shown
> to have reached the hardware.**
>
> The document's own closing caution — do not declare the VE scale-down dead on
> one register set — was correct, and is the reason the right base was found.
> Everything below is kept for that.

2026-09-11. Kernel patch `0097-EXPERIMENT-media-cedrus-probe-the-ve-scale-down-secondary-output`
built, deployed as a module, and swept. Headless throughout — no display, no
MIPS, no operator.

## What was built

A harness, not an implementation. `cedrus_sd_setup()` runs per job from
`cedrus_device_run()`, allocates a coherent secondary buffer, poisons it with
`0xa5`, points `VE+0x44`/`0x48` at it, and writes a raw module-parameter value to
`VE+0x40`. The buffer is dumpable at `/sys/kernel/debug/cedrus_sd_buf`.

Inert by default: with `sd_w=0` not one register write changes.

The poison matters. A scaler that never runs leaves `0xa5` intact, which
separates "wrote nothing" from "wrote black" — a flat fill is ambiguous on this
hardware.

## The sweep

`sd_w=1280 sd_h=720`, 1080p decode, 8 frames per point:

| `sd_ctrl` | `sd_fmt` | non-poison bytes |
| --- | --- | --- |
| `0`, `0x1`–`0x7`, `0xf`, `0x100`, `0x101`, `0x10f`, `0x8000000f` | 0 and 1 | **0** |
| `0xFFFFFFFF` | 1 | **0** |

**Nothing was ever written to the secondary buffer**, in 25 configurations.

## But the harness is sound, which is what makes the negative worth anything

Both gates that have burned this project were checked explicitly:

1. **The decode really ran.** `ffmpeg -loglevel error` produced no output, and
   the poison dump returned a full 1382400 bytes — so the buffer, the debugfs
   path and the read are all working.
2. **The register writes really land.** Writing `sd_ctrl=0x55` gave
   `VE+0x40 = 0x15` — *not* the `0x0F` default, and not `0x55` either. The value
   is derived from what I wrote, so `cedrus_write()` is reaching the hardware.

## The finding: VE+0x40 is a 5-bit register on this SoC

Writing `0xFFFFFFFF` reads back **`0x0000001F`**. So `VE+0x40` implements
**bits [4:0] only**.

The vendor's `H264ConfigureScaleRotateRegister` composes bits `[2:0]` (mode)
*plus two 4-bit fields around `[11:8]`*. **Those upper fields do not exist on the
H713.** And `VE+0x44`/`0x48` never hold a written value — they read `0x00000000`
even with all bits set in `0x40`.

That is consistent with the vendor libraries' own capability checks:
`this hardware not support fixratio scale` and `interlaced video cannot be
scaled in current platform`. The H713 appears to be a part where the *fixratio*
scale-down path is not wired.

## What this does NOT close

**I tested one of the two scalers.** `H264ComputeScaleRatio` feeds the fixratio
path — the `0x40`/`0x44`/`0x48` triple — and that is what this sweep exercised.

The **new scaler** (`H264ConfigNewScaler`) uses a different register set:
`VE+0x20` (bit 9 cleared with `bic r1, r1, #0x200`), plus `0xcc`, `0xe4`, `0xe8`,
`0xec`, `0xf8`, `0xfc`, and a 256-byte coefficient table. **`VE+0x20` was never
touched in this sweep**, and it is plausible that `0x44`/`0x48` do not latch
until the scaler is enabled there.

So the honest position is: the fixratio triple is not wired, and the new-scaler
path is untested. Declaring the VE scale-down dead on this evidence would repeat
the pattern this project has fallen into repeatedly — testing one register of a
set and reading the null as final.

## Next

1. Extend the harness with `sd_ctrl20` and the `0xcc`/`0xe4`/`0xf8`/`0xfc` set,
   clear `VE+0x20` bit 9 as `H264ConfigNewScaler` does, and re-sweep. Same
   headless loop, no new risk.
2. Disassemble `H264ConfigNewScaler` past `+0xdc10` for the coefficient upload
   and the size/phase register semantics — the 256-byte table has to go
   somewhere, and that write is the one instruction sequence that would name the
   remaining registers.
3. Only then is a negative meaningful.

The board is left with the harness loaded and inert (`sd_w=0`), and normal 1080p
decode verified clean afterwards.
