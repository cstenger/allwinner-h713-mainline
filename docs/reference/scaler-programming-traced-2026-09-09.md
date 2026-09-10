# The composition scaler, traced in display.bin

Static RE, no board time. Answers the question the failed 1080p scaling attempt
left open, and retires one hypothesis outright.

Firmware `local/mips-display/board-b-mips/display.bin`, base `0x8b100000`,
SHA-256 `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
**MIPS address = ARM physical + `0xB5000000`**, so composition at `0x05000000`
is `0xBA000000` in firmware space. Disassemble with `tools/mips/disasm.py`.

## Who programs it

A scan for `lui 0xba00` followed by a load/store found **238 composition-block
accesses**. Every scaler register is written by one function:
**`PanelWinNode::update` at `0x8b1a48cc`**.

## The register structure

Two channels, each with an 8-bit ratio pair and two ratio+height pairs:

| | channel A | channel B |
| --- | --- | --- |
| 8-bit ratio pair | `0x0f0` | `0x210` |
| ratio + height | `0x174` / `0x178` | `0x274` / `0x278` |
| ratio + height | `0x1b4` / `0x1b8` | `0x2b4` / `0x2b8` |
| source size | `0x224` — width in `[15:0]`, height in `[31:16]` | |

## Field widths — not what they look like

These are **bitfield inserts**, not whole-word writes:

```
0x174:  ins $a3, $t1, 0x10, 0xc    bits [27:16], TWELVE bits
        ins $a3, $a2, 0,    0x10   bits [15:0],  SIXTEEN bits
0x0f0:  ins $v0, $a1, 0, 8         bits  [7:0],  EIGHT bits
        ins $v0, $a0, 8, 8         bits [15:8],  EIGHT bits
```

So `0x174` is a 16-bit field plus a 12-bit field, and `0x0f0` is two 8-bit
fields. Anything writing whole words here is overwriting neighbours.

## The 1080 path is hardcoded in the firmware

```
0x8b1a4990  addiu $t0, $zero, 0x438    ; 1080  -> 0x1b8 low 16
0x8b1a49a0  addiu $t0, $zero, 0x21c    ;  540  -> 0x178 low 16
```

gated on a flag at `+0x50` in the node object. So `0x178`/`0x1b8` carry the
**source heights** (chroma and luma), and the firmware plainly supports a 1080
source.

**This retires the "the scaler is upscale-only" hypothesis.** That came from
having only ever observed ratios at or below unity (`0x40` unity, `0x2B` for an
852 source upscaled to a 1280 panel). The 16-bit ratio field and an explicit
1080 branch say downscale is available.

## Why the 1080p test went black

The attempt wrote `0x174` and `0x1b4` but **left `0x178`/`0x1b8` at their 720p
values** (360 / 720) while every other word said 1080. Height mismatch, and the
firmware never programs one of these without the other.

It also vindicates two values previously flagged as guesses: `0x278 =
0x6002021C` (low half 540) and `0x2b8 = 0x60020438` (low half 1080) were
**correct** — they are channel B's copy of the same pair.

## The full update sequence

`PanelWinNode::update` (`0x8b1a48cc`..`0x8b1a4dc0`, 317 instructions) touches
**26 composition registers**, each guarded by a dirty-mask bit, in this order:

```
 1  0x050001b8   9  0x050002b8  17  0x05000858  25  0x05000840  <- COMMIT counter
 2  0x05000178  10  0x05000274  18  0x0500085c  26  0x05000040  <- FINAL, bit 25
 3  0x050001b8  11  0x05000278  19  0x05000860
 4  0x05000178  12  0x05000224  20  0x05000854
 5  0x050001b4  13  0x05000210  21  0x05000860
 6  0x05000174  14  0x05000804  22  0x05000138
 7  0x050000f0  15  0x05000808  23  0x0500082c
 8  0x050002b4  16  0x0500080c  24  0x05000844
```

### The final step, which no test of ours ever performed

After the counter, the function ends by toggling **bit 25 of `0x05000040`**,
selected by the dirty mask:

```
0x8b1a4d38  ext  $v0, $s1, 0x10, 1     ; dirty bit 16?
0x8b1a4d3c  beql $v0, $zero, ...
0x8b1a4d4c  ins  $v1, $zero, 0x19, 1   ;   -> CLEAR bit 25
0x8b1a4d50  sw   $v1, 0x40($v0)
0x8b1a4d58  beqz $s1, ...               ; dirty bit 15?
0x8b1a4d6c  ins  $v1, $a0, 0x19, 1     ;   -> SET bit 25
0x8b1a4d70  sw   $v1, 0x40($v0)
```

So the real apply is **counter bump, then `0x05000040` bit 25**. Every scaling
attempt stopped at the counter.

### Registers our tests never wrote at all

`0x05000808`, `0x05000854`, `0x05000860`, `0x05000138`, `0x0500082c`, and
`0x05000040`. `0x05000138` is notable: it is the node's own counter field
mirrored into a register.

### What is still unknown

**The ratio value itself.** There is no obvious division computing it: the only
two shift-by-6-then-divide sites in the image are timing math (`x960/÷n` and
`x100000/÷n`, with a divide-by-3 reciprocal nearby). Consistent with the
2026-08-31 finding that composition follows the client's VideoInfo coordinates,
the value most likely arrives **pre-computed** rather than being derived on the
MIPS. Tracing the CPU_COMM message that carries it is the next lead.

## HAZARD: the scale test wedges the display

Two runs, two wedges. Neither the script's restore, nor manually rewriting
composition, AFBD, gain, heights and the commit counter, recovered the panel —
**only a reboot does**. Assume any run that programs composition for a non-native
source will cost a reboot and a full bring-up.

That is consistent with the sequence above: the tests never performed the final
`0x05000040` step, so composition is left half-applied in a state the firmware
itself never produces.

Do not run `decd-scale-test.sh` casually.

## Node-object field map

`PanelWinNode::update` loads its values from the node at `$s0`:

| offset | goes to |
| --- | --- |
| `+0x90` | `0x1b4` bits [15:0] |
| `+0x94` | `0x1b4` bits [27:16] |
| `+0x98` | `0x1b8` low 16 (when `+0x4c` set) |
| `+0x9c` | `0x174` bits [15:0] |
| `+0xa0` | `0x174` bits [27:16] |
| `+0xa4` | `0x178` low 16 (when `+0x4c` set) |
| `+0xa8` | `0x0f0` bits [7:0] |
| `+0xac` | `0x0f0` bits [15:8] |
| `+0x44` / `+0x48` | `0x224` width / height |

Reproduce with `tools/video/decd-scale-test.sh` (`PHASE=scale`), which now
read-modify-writes the low 16 bits of `0x178`/`0x1b8`/`0x278`/`0x2b8` exactly as
the firmware's `ins rt, rs, 0, 0x10` does.
