# The composition "scaler ratio" registers are line-buffer geometry

Static RE, no board time, no reboot spent. This answers "where does the ratio
value come from" with **there is no ratio**, and it retires the register set the
last three sessions have been trying to program.

Firmware `local/mips-display/board-b-mips/display.bin`, base `0x8b100000`,
SHA-256 `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
MIPS address = ARM physical + `0xB5000000`. Tools: `tools/mips/disasm.py`,
`tools/mips/cfg.py`.

## The finding

`0x05000174`, `0x050001b4`, `0x050000f0` and their channel-B counterparts
`0x05000274`, `0x050002b4`, `0x05000210` are **not scaler ratios**. They are the
AFBD fetch line-buffer descriptor: **row length, line-buffer level and line
count**, for the Y and C planes.

The values come out of a function whose own log line names all six:

```
0x8b1a2668   FrameBuffer::GetPsuPfuWin        ./FrameBuffer.cpp, tag "vnode"
0x8b2075e0   "Compression mode %d, Rowbyte, LineBufLevel & LineNumber:
              Y[0x%x, 0x%x, 0x%x], C[0x%x, 0x%x, 0x%x]"
```

Every branch of that function converges on one store sequence
(`0x8b1a2814`..`0x8b1a284c`) writing six caller-supplied pointers, and then
prints those same six registers in that order at `0x8b1a288c`. The stores and
the varargs match register for register:

| store | printf slot | quantity |
| --- | --- | --- |
| `$t0` | `0x1c($sp)` | Y Rowbyte |
| `$t3` | `0x20($sp)` | Y LineBufLevel |
| `$t4` | `0x24($sp)` | Y LineNumber |
| `$t2` | `0x28($sp)` | C Rowbyte |
| `$v0` | `0x2c($sp)` | C LineBufLevel |
| `$v1` | `0x30($sp)` | C LineNumber |

## How the six reach the hardware

`NRWinNode::CalcWindow` (`0x8b1a3704`) calls `GetPsuPfuWin` **three** times, each
time handing it pointers into its own node object:

```
0x8b1a3abc   &node+0x90 0x94 0x98 0x9c 0xa0 0xa4     <- channel A
0x8b1a3ae8   &node+0xb0 0xb4 0xb8 0xbc 0xc0 0xc4     <- channel B
0x8b1a3b0c   NULL, &node+0xa8, NULL, NULL, &node+0xac, NULL
```

The third call asks for **only the two LineBufLevels**. That is the whole of
`0x050000f0`.

`NRWinNode::WriteReg` (`0x8b1a48cc`) then does the bitfield inserts:

| node field | register field | quantity |
| --- | --- | --- |
| `+0x90` | `0x050001b4[15:0]` | Y Rowbyte |
| `+0x94` | `0x050001b4[27:16]` | Y LineBufLevel |
| `+0x98` | `0x050001b8[15:0]` | Y LineNumber |
| `+0x9c` | `0x05000174[15:0]` | C Rowbyte |
| `+0xa0` | `0x05000174[27:16]` | C LineBufLevel |
| `+0xa4` | `0x05000178[15:0]` | C LineNumber |
| `+0xa8` | `0x050000f0[7:0]` | Y LineBufLevel, 8-bit |
| `+0xac` | `0x050000f0[15:8]` | C LineBufLevel, 8-bit |

So **`0x1b4`/`0x1b8` are luma and `0x174`/`0x178` are chroma** — which is why
the hardcoded path at `0x8b1a4990` puts `1080` in `0x1b8` and `540` in `0x178`.
Those are line counts for a 1080-line source with 540 lines of 4:2:0 chroma,
not "a ratio's partner".

Channel B additionally clamps the level to the row length before writing:

```
0x8b1a4a24  sltu $a1, $a3, $a2      ; a3 = Rowbyte, a2 = LineBufLevel
0x8b1a4a28  movn $a2, $a3, $a1      ; -> min(Rowbyte, LineBufLevel)
```

which is a line-buffer clamp and makes no sense at all for a ratio.

`0x05000224` is `{[31:16] height, [15:0] width}` taken from the node's own
`+0x44`/`+0x48`.

## Nothing else in the firmware writes these registers

An image-wide scan for `lui 0xba00` + load/store at these eleven offsets returns
**48 accesses, all inside `NRWinNode::WriteReg`**, plus one unrelated site at
`0x8b153e7c` that touches only **bit 31** of the four LineNumber registers (an
enable toggle, not the count). There is no second writer, and no arithmetic
anywhere that produces a scale factor for them.

## The hardware captures agree — and explain the illusion

The reading that started this, from
[`scaler-engaged-2026-09-05.md`](scaler-engaged-2026-09-05.md):

```
0x05000174  0x00400040    "unity"        (a 1280-wide picture)
0x05000174  0x002B002B    "43/64 = 0.672, and 852/1280 = 0.666"
```

Under the correct decode both halves are Rowbyte and LineBufLevel, and
**Rowbyte is linear in the picture width**. Any two widths therefore produce a
value ratio equal to the width ratio — *whether or not anything scales*. That is
the entire content of the "0.672 ≈ 0.666" observation.

The arithmetic is consistent with compressed AFBD rows at ~0.8 byte/pixel and
`Rowbyte = ceil(row_bytes / 16)` (the `((x<<3)+0x7f)>>7` at `0x8b1a27cc`):

```
1280 px  ->  1024 bytes  ->  1024/16 = 64 = 0x40      exact
 852 px  ->   682 bytes  ->  ceil(682/16) = 43 = 0x2B  exact
```

Stated as consistency, not proof: pinning the exact branch needs the runtime
values of `fb+0x48`/`+0x50`/`+0x5c`/`+0x68`.

### The same log already showed the firmware *not* scaling

Four lines above the "scaler engaged" conclusion, in the same capture:

```
I/wce_nr     y_width:852, c_width:852, v_size:480
I/wce_panel  top_width:0, bottom_width:240, left_width:0, right_width:428
             m_video_win_2: [49, 22, 852, 480]
```

`1280 - 852 = 428`. `720 - 480 = 240`. Given an 852x480 picture on a 1280x720
panel the firmware **letterboxed it with border overlays** and left it at native
size. `PanelWinNode` has `WriteBorderOverlay1`/`WriteBorderOverlay2` for exactly
this. A scaler that was engaged would have had nothing to border.

> **`scaler-engaged-2026-09-05.md`'s headline is refuted.** The firmware did run
> its full window pipeline off our descriptor — that part stands and is still a
> real result. What it did *not* do is scale.

## Why the scale test wedges the panel

`PHASE=scale` writes `0x00600060` into `0x05000174`/`0x050001b4`, i.e. it sets
the fetch **row length and line-buffer level to 96** while the source, strides
and block counts describe something else. That mis-sizes the line buffers the
AFBD fetch runs out of. The wedge is not "composition left half-applied pending
a final apply" — it is a starved or overrun fetch, which is exactly the kind of
state a reboot is needed to clear.

**The missing `0x05000040` bit-25 step will not fix it**, because the values
being committed are wrong in kind.

## The one real ratio register, and why its negative does not hold

`PanelWinNode::WriteDownScalerRatio` (`0x8b1a58c0`) is the only place in the
firmware that programs a scale factor:

```
0x051c0138[21:0] = ratio      unity = 0x00010000   (16.16 fixed point)
```

Unity is confirmed twice on hardware — stock Android idle and our own board both
read `0x051c0138 = 0x08010000`.

**The branch is the opposite way round from how
[`mips-wce-window-layer-2026-09-04.md`](mips-wce-window-layer-2026-09-04.md)
records it**, and this matters:

```
0x8b1a58e0  beq $v1, $v0, 0x8b1a5998    ; ratio == unity -> the "bypass" branch
```

- **ratio == unity** → logs `"bypass"`, and sets `0x051c0124[26:25] = 3`.
- **ratio != unity** → **clears** `0x051c0124[26:25]`, sets `0x051c0120[26:24] = 2`,
  reprograms `0x0128`/`0x012c`/`0x0130`/`0x0134` from the window, and only then
  writes the ratio into `0x0138[21:0]`.

So `0x051c0124[26:25] = 3` is the **bypassed** state, not the enabled one. Stock
reads `0x051c0124 = 0x06000000` — bypassed at unity, which is what the log
string says it should be.

The 2026-09-04 visible test wrote `0x051c0138 = 0x08018000` **and nothing else**,
leaving `0x051c0124[26:25] = 3`. It exercised a bypassed stage. That negative —
on both sides of the `0x051c006c` mux — is **not sound**, and it is the same
error as the one this document is about: one register of a set written alone.

Re-running it correctly means writing what the firmware writes, in its order:

```
0x051c0124  [26:25] = 0        leave bypass
0x051c0120  [26:24] = 2
0x051c0128  [15:0]  = w - 6
0x051c012c  [15:0]  = h
0x051c0130  [31:16] = w, [15:0] = h
0x051c0134  [15:0]  = 0, [31:16] = w + x + 2
0x051c0138  [21:0]  = ratio
```

There is no commit latch in `PanelWinNode`'s slot 4, so these take effect as
written.

## Still open: the ratio's direction and its producer

The value lives in `PanelWinNode+8`. **No writer of that field has been found**
— it is not written anywhere in `0x8b1a4e00..0x8b1a5cc0`, and the `<<16`-then-
divide that would compute a 16.16 ratio does not appear in the WCE region at
all. Consistent with it arriving pre-computed, so the CPU_COMM lead from
2026-09-09 survives — it just points at `PanelWinNode+8`, not at composition.

Direction is **inferred, not proven**: the field is 22 bits with unity at bit 16,
leaving 6 integer bits above unity and only fractional room below. That fits
`ratio = src/dst` (downscale up to ~64x) far better than `dst/src`. For
1920→1280 that is `0x18000`; the `dst/src` reading would be `0xAAAB`. Try
`0x18000` first.

`TWCETop::IsEnablePanelDownScaler` (`0x8b1a7dxx`) gates the whole thing on the
configured output resolution and a `< 0x438` (1080) test, which is the shape you
would expect for "compose at 1080, squeeze to the panel".

## Corrections this lands

- `0x8b1a48cc` is **`NRWinNode::WriteReg`** — log tag `WriteReg`, file
  `./NRWinNode.cpp`, `NRWinNode` vtable slot 4. It is not `PanelWinNode::update`;
  [`scaler-programming-traced-2026-09-09.md`](scaler-programming-traced-2026-09-09.md)
  reintroduced a class name that was already corrected on 2026-09-04.
- "Two channels, each an 8-bit ratio pair plus two ratio+height pairs" → two
  channels of Y/C line-buffer geometry.
- "The scaler is upscale-only" was already retired; it is now moot.
- "`0x278 = 0x6002021C` and `0x2b8 = 0x60020438` were correct guesses" — the
  low halves are right and they are **line counts**, 540 and 1080.

## The habit that would have caught this

Both the 09-05 and 09-09 readings were built on register *values* and `ins`
masks without ever asking what the firmware **calls** the thing it is writing.
The answer was one `printf` away: the function that produces all six values
names all six in a format string.

Before deriving meaning from a bitfield, look for the log line that prints it.
