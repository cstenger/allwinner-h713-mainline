# The firmware's format mapping, recovered statically

Answers "why does the firmware program fmt 4 when stock plays at fmt 0", with
no bench time. Also unlocks static analysis of the firmware's display code
generally, which had not been possible before.

## Why every previous search of display.bin came up empty

The firmware contains **no reference to any display register address** in the
ARM's numbering — not as a `lui` immediate, not as a data word. `0x05600000`,
`0x05600010`, `0x0525c000`, `0x05200000` all return zero hits. That is not
because the firmware leaves the display alone; it is because the MIPS sees the
peripherals at a different address.

    MIPS address = ARM physical + 0xB5000000

Confirmed by correspondence across four blocks, and `0xb5000000` itself appears
as a constant 15 times:

    ARM 0x05600000  AFBD           ->  MIPS 0xba600000   (kseg1, uncached)
    ARM 0x051c0000  LVDS PHY       ->  MIPS 0xba1c0000
    ARM 0x05140000  display route  ->  MIPS 0xba140000
    ARM 0x05000000                 ->  MIPS 0xba000000

Anything searching this image for display accesses must use `0xba6…`, not
`0x056…`. `lui $rX, 0xba60` has 29 sites.

## The firmware does program the video source — statically confirmed

With the right base, the AFBD registers the firmware touches fall out directly.
It reads and writes `0x05600010` at 11 store sites, along with the geometry and
stride registers at `+0x20`…`+0x54`. The 2026-08-28 conclusion that the firmware
configures the video source was an inference from a register transition; it is
now visible in the code.

Two of those stores write the format field, both the same sequence:

    lbu  $a0, 0x30($sp)      ; format byte, a local
    lw   $v1, 0x10($v0)      ; 0x05600010
    ins  $v1, $a0, 8, 8      ; bits 15:8
    sw   $v1, 0x10($v0)

in the frame-programming function at `0x8b1a4538`. The byte at `sp+0x30` is
filled by `jal 0x8b1a31e8` with `$a2 = sp+0x30` and `$a1 = 0x5c($s0)`.

## The mapping table

`0x8b1a31e8` is a bounds-checked jump table: inputs `>= 0x10` take a default arm
that logs and writes 0; otherwise it dispatches through a 16-entry table at
**`0x8b2078a4`**, each arm storing a constant.

| input | AFBD fmt | note |
| --- | --- | --- |
| 0 | **0** | what stock plays at |
| 1 | 0 | default arm, logs an error first |
| 2 | 1 | |
| 3 | 0 | default arm |
| 4 | 2 | |
| 5 | 0 | default arm |
| 6 | 3 | |
| 7 | — | **no store**: leaves the caller's byte unmodified |
| 8 | 4 | |
| 9 | 5 | |
| 10 | 0 | default arm |
| 11 | **4** | what our client currently produces |
| 12 | 5 | |
| 13 | 0 | default arm |
| 14 | 7 | |
| 15 | 6 | |

**The result validates itself.** Input 11 maps to fmt 4, which is exactly what
was measured on hardware: the client sets 11, the firmware programs
`0x05600010 = 0x03000413`. A static reconstruction that reproduces a measured
value is worth more than one that merely looks plausible.

## What to do with it

Stock plays at fmt 0, and the only input that reaches fmt 0 without going
through the error-logging default is **0**. So the targeted change is to make
the client's format field 0 rather than 11.

That is testable on **our own stack** — no vendor boot: set the field, submit a
frame with the MIPS alive, and read `0x05600010`. If it reads `0x03000013`
instead of `0x03000413`, the mapping is confirmed end to end on hardware.

## CONFIRMED ON HARDWARE, both directions (2026-08-30)

Run with the MIPS alive (`preboot h713_disp init 0x34`), the DECD-exclusive
kernel, and one bounded submit per invocation. Control first, then the
experiment, in the same boot. Full logs in
[fmt-mapping-confirmed-2026-08-30.txt](fmt-mapping-confirmed-2026-08-30.txt).

| input sent | 0x05600010 after | fmt nibble | table predicted |
| --- | --- | --- | --- |
| 11 (the old value) | `0x03000413` | 4 | 4 |
| 0 (the change) | `0x03000013` | 0 | 0 |

`0x03000013` is exactly what stock plays at. Both directions match, so **the
caveat below is closed: VideoInfo `+0x40` is the resolver's input.** Running the
control first mattered -- it proves the apparatus reproduces the known
behaviour before the experiment is believed.

A second, independent sign the format is genuinely being interpreted rather
than merely stored: `0x0560004c`'s row count halves with it, `0x01E0` (480) at
fmt 4 to `0x00F0` (240) at fmt 0, which is the chroma-plane accounting changing
as the subsampling changes. Nothing else in the block differs between the two
runs.

Unexplained and worth its own look: after either submit, `0x05600030` and
`0x0560004c` carry `0x0354` = 852 in the low half and 480/240 in the high half,
i.e. 852x480 -- while `0x05600020` correctly reads `0x02CF04FF` = 1280x720
minus one and the stride is `0x500` = 1280. Stock's playback capture has
`0x0560004c = 0x02D00500`. So our source dimensions are right and some
downstream size is not.

Also settled: the first attempt at this test hard-locked the SoC during the
submit, which raised the possibility that fmt 0 itself caused it. It did not --
fmt 0 ran cleanly here. That lock was the known flakiness of this state.

## The original caveats

- The resolver's input is `0x5c($s0)`, a field of the firmware's frame object.
  That it is our VideoInfo format field rested on the 11 -> 4 correspondence.
  **Now closed by the hardware run above.**
- fmt is **necessary, not sufficient**. Forcing fmt 4 onto stock produced a
  tiled, half-height, colour-shifted picture rather than black, so fmt 0 alone
  will not make video appear. It removes one known-wrong input.

Entry 7 storing nothing is worth remembering: a client that sends 7 gets
whatever byte was last on that stack slot, which would look like an
intermittent, history-dependent format bug.
