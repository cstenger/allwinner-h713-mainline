# A two-axis scaler at 0x05180000 — found, decoded, and confirmed against hardware

> ## WHAT HAPPENED NEXT (2026-09-11 / 09-12)
>
> The field map below is correct and every register it names checked out on
> hardware. Two things it left open are now settled:
>
> - **It is an UPSCALER.** `ratio_h` clamps at unity; below unity it magnifies by
>   `1/ratio`, above unity it does nothing. The proposed 1/2 liveness test would
>   not have shrunk anything. Measured:
>   [proc-scaler-upscale-only-2026-09-11/RESULT.md](proc-scaler-upscale-only-2026-09-11/RESULT.md).
> - **`0x34` is the input window, and it matters more than anything else here.**
>   Leaving it at the raster's {1280,720} while commanding magnification clips
>   the output into a hard-edged rectangle. Setting it to the true input size is
>   what made the block usable:
>   [ve-scaledown-2026-09-11/UPSCALE-GEOMETRY-CONFIRMED.md](ve-scaledown-2026-09-11/UPSCALE-GEOMETRY-CONFIRMED.md).
>
> It is now **stage 2 of the surviving 1080p-on-720p route** — see
> [the 2026-09-12 handoff](../handoff-2026-09-12-ve-scaledown.md).

Static RE plus two register reads. **No board time beyond a `devmem` loop, no
reboot.**

This is the first block in this project with **separate horizontal and vertical
ratio registers**. Composition (`0x05000000`) has no scaler at all; the panel
down-scaler (`0x051c0120`) is vertical-only. This one is neither.

## The registers

Written by one function, `0x8b1a66d0`, called from `ProcWinNode::WriteReg`
(`0x8b1a6bac`). `$a0` is the `ProcWinNode`, `$v0` is `0xba180000` = ARM
`0x05180000`.

```
0x8b1a6730  lw  $a1, 0xc($a0)       ; ratio_h   <- ProcWinNode::CalcScaleRatio
0x8b1a6734  lw  $t0, 0x10($a0)      ; ratio_v
0x8b1a6758  ins $v1, $a1, 0, 0x16   ; 0x05180008[21:0] = ratio_h
0x8b1a6764  ins $v1, $t0, 0, 0x16   ; 0x0518003c[21:0] = ratio_v
```

Both 22-bit, both 16.16 fixed point with unity `0x10000` — the same encoding
`CalcScalingRatio_2` and the panel down-scaler use.

| register | field | meaning |
| --- | --- | --- |
| `0x05180000` | `[31:16]` | constant `0x0F00` |
| | `[15:0]` | **H phase** = `(unity + ratio_h) >> 2` |
| `0x05180004` | `[15:0]` | constant `0x0F00` |
| `0x05180008` | `[21:0]` | **H ratio** |
| | `[30:28]` | H integer phase (`node+0x14`) |
| | `[26:24]` | V integer phase (`node+0x18`) |
| `0x05180014` | `[27]` | **1 = both axes at unity → no scaling** |
| `0x05180020` | `[31:24]` | format/mode byte, from `(node->0xbc)->0xc` |
| `0x0518002c` | `[15:0]` / `[31:16]` | size / `node->0x30 + 4` |
| `0x05180030` | `[15:0]`, `[19:18]=0` | size |
| `0x05180034` | `{[31:16], [15:0]}` | size pair |
| `0x05180038` | `[15:0]` | **V phase** = `(unity + ratio_v) >> 1` |
| `0x0518003c` | `[21:0]` | **V ratio** |
| `0x05180040` | `[31] = 1`, `[15:0]` | enable-ish + size |
| `0x05180044` | `[15:0]` | offset |
| `0x05180050` | `[15:0]` / `[31:16]` | size pair |

## It matches hardware, field for field, before any experiment

Two independent captures: `linux-mips-alive-decd-4sample-2026-08-31.txt`
(MIPS alive, taken for an unrelated reason and never read), and our own
**cold-booted board today with the MIPS parked**. Both read identically, on all
four instances:

```
05180000 0x0F008000     0x0F00 const ✓   phase 0x8000
05180004 0x00100F00     0x0F00 const ✓
05180008 0x43010000     ratio_h = 0x010000 = UNITY ✓   int phases 4 and 3
05180014 0x08000000     bit 27 = 1  -> "no scaling" ✓
05180020 0x02000000
0518002c 0x00350500     1280,  53
05180030 0x000102D0      720
05180034 0x050002D0     1280, 720
05180038 0x00100000     V phase 0x0000
0518003c 0x00010000     ratio_v = 0x010000 = UNITY ✓
05180040 0xC0000500     bit 31 = 1 ✓   1280
05180044 0x00000031      49
05180050 0x001B02D0      720,  27
0518005c 0x00010438     1080  (not written by this function)
```

The phase check is the one that removes all doubt. The code computes the H phase
as `(unity + ratio_h) >> 2`; at unity that is `(0x10000 + 0x10000) >> 2 =
0x8000`, and the register reads **exactly `0x8000`**. That is a derived value
with no other plausible source.

Geometry is our panel's: 1280 and 720 throughout. And `49` at `0x05180044` is the
same `49` that appears as the video window's x origin in the 09-05 WCE log
(`m_video_win_2: [49, 22, 852, 480]`).

**Four instances at `0x100` stride**, all populated and identical — matching the
firmware's stage-name table, which lists `proc-vs_upscaler` and
`proc-vde_upscaler` alongside `proc-vs_dmuxin` / `proc-vs_out`.

## Direction semantics

`ProcWinNode::CalcScaleRatio` (`0x8b1a5f98`) produces
`ratio = unity × min(in,out) / max(in,out)` — **always ≤ unity** — plus a
direction byte per axis. `ProcWinNode::ReCalcInOutWin` (`0x8b1a6190`) consumes
the byte to pick which window is derived from which:

```
flag != 0 (upscale)    in_size  = ceil(out_size * ratio / unity)     in <= out
flag == 0 (downscale)  in_size  = ceil(out_size * unity / ratio)     in >= out
```

The direction never reaches the hardware as a bit. It is implied by the
**geometry**: the block is told an input size and an output size, and the ratio
is `unity × min/max` either way. For `1920 → 1280` that is
`1280 × 65536 / 1920 = 0xAAAA`, with the input registers carrying 1920 and the
output registers 1280.

## Why the block survey missed this for months

`tools/mips/block-survey.py` counts **`lui` sites**, and `0x8b1a66d0` reaches
the whole block through **one** `lui` and 48 displacements. So the survey
reported:

```
0xba18  0x05180000      1   ** not characterised **
```

One site, bottom of the table, easy to skip. Counting *accesses* instead of
`lui`s gives 13 distinct registers, all written. The same undercount hid real
size in two other blocks: `0x050c0000` reported 22 sites but has **83**
registers, and `0x05140000` reported 16 but has **72**.

> **A scan that ranks by proxy will bury the thing you are looking for.**
> `block-survey.py` was built to make a "none" answer trustworthy, and it is
> sound for that. It was then read as a ranking of importance, which it is not.

## What is NOT established

**Whether this block is on our path.** That is the question that already
consumed `0x05000000` and `0x051c0120`, and nothing here answers it:

- The 08-31 capture spans DECD idle vs DECD submitting a 1280x720 frame, and
  **zero registers differ**. That is *not* evidence either way — a 1280x720
  frame on a 1280x720 panel needs no scaling, so an unchanged unity scaler is
  what both hypotheses predict. It does not discriminate.
- Our driver does not map `0x05180000`. It is reachable with `devmem` today,
  so testing needs no kernel change.

## The write set, if we test it — and the trap to avoid

`0x05180014[27]` is currently **1**, computed by the firmware as "ratio_h ==
unity **and** ratio_h == ratio_v". It is written by the driver, so it is an
input, not a status: **a bypass**.

Writing a ratio while bit 27 stays set would repeat, for the third time, the
exact error this project has now made twice — `0x051c0138` alone with
`0x0124[26:25]` left at bypass, and `0x05000174` alone. The minimum coherent set
is:

```
0x05180014  [27]    = 0             LEAVE BYPASS
0x05180008  [21:0]  = ratio_h
0x05180000  [15:0]  = (unity + ratio_h) >> 2      H phase
0x0518003c  [21:0]  = ratio_v
0x05180038  [15:0]  = (unity + ratio_v) >> 1      V phase
            plus the input/output size registers, which carry the direction
```

### Input vs output — settled

`ProcWinNode::DbgDump` (`0x8b1a5d00`) prints each member with its offsets, the
same trick that cracked `GetPsuPfuWin`:

```
m_in_win     +0x3c x, +0x40 w, +0x44 y, +0x48 h
m_out_win    +0x4c x, +0x50 w, +0x54 y, +0x58 h
m_meter_win  +0x5c .. +0x68
```

Feeding that through `0x8b1a66d0`:

| register | source | meaning |
| --- | --- | --- |
| `0x05180034` | `{in_win.w, in_win.h}` | **INPUT size** |
| `0x0518002c[15:0]` | `out_win.w` | **OUTPUT width** |
| `0x05180030[15:0]` | `out_win.h` | **OUTPUT height** |
| `0x05180040[15:0]` | `out_win.w` | output width again |
| `0x05180044[15:0]` | `node->0x2c` | 49 in the capture |
| `0x0518002c[31:16]` | `node->0x30 + 4` | 53 in the capture |

The capture reads `0x05180034 = 0x050002D0` (in 1280x720) and
`0x0518002c[15:0] = 0x500`, `0x05180030[15:0] = 0x2D0` (out 1280x720) — in and
out equal, ratios at unity, bypass bit set. Entirely self-consistent.

### The test this makes possible

A liveness test needs no 1080p plumbing — shrink the raster we already scan out,
with an exact power-of-two ratio so the arithmetic cannot be argued with:

```
in  = 1280x720   (unchanged)   0x05180034 = 0x050002D0
out =  640x360                 0x0518002c[15:0] = 0x280
                               0x05180030[15:0] = 0x168
                               0x05180040[15:0] = 0x280
ratio_h = ratio_v = 0x8000     exactly 1/2
  0x05180008[21:0] = 0x8000
  0x0518003c[21:0] = 0x8000
  0x05180000[15:0] = (0x10000 + 0x8000) >> 2 = 0x6000     H phase
  0x05180038[15:0] = (0x10000 + 0x8000) >> 1 = 0xC000     V phase
  0x05180014[27]   = 0                                    LEAVE BYPASS
```

Expect the image to shrink to a quarter of its area. Four instances exist and we
do not know which carries our raster, so the test should sweep them one at a
time rather than write all four at once.

**Not run.** Needs an operator watching, and it writes an enable on live display
hardware.
