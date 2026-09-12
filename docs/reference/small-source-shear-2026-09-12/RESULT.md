# A source narrower than the panel SHEARS, and no register we can reach fixes it

2026-09-12, bench board, cold boot, operator watching. Follows the geometry fix
in commit 7742033, which is what first got a smaller framebuffer onto the glass.

## The result

**It is not tiling. It is a line-to-line shear**, and the mechanism is exact.

The consumer steps **1280 pixels per output line** whatever the source width, so
each successive line starts `(1280 - W)` pixels further into the buffer. When
`1280 / (1280 - W)` is a whole number the shear realigns and reads as clean
vertical tiles; when it is not, the picture shreds into an interlaced pattern.

| source | 1280 - W | predicted tiles | observed |
| --- | --- | --- | --- |
| 1280x544 | 0 | 1 | **1, clean and sharp** |
| 1024x544 | 256 | 5 | **5** |
| 960x544 | 320 | 4 | **4** |
| 896x544 | 384 | 3.33 (never realigns) | **shredded / interlaced** |

Four sizes, four matches, including the non-integer case predicting a
qualitatively different failure. The operator spotted the interlacing in the
grey ramp before the model did.

**Stride alignment is NOT the cause.** 1024 is 128- and 256-byte aligned and
still shears at 5 tiles; the earlier "960 is not 128-aligned" theory is dead.

## What the driver gets right

Everything it programs now follows the framebuffer, verified by register
readback during a live run at 960x544:

    0x05600020 SIZE_M1   0x021F03BF      0x05600040/44 strides  0x3C0
    0x05600024 BLOCK_M1  0x0021003B      0x05600048 luma  0x022003C0
    0x05600030 size      0x022003C0      0x0560004c chroma 0x011003C0

The proc upscaler is also correct and demonstrably working **horizontally**:
engaging it takes the tile count from 4 to 3, which is exactly the 1.333x it is
programmed for. Its registers read back with every live upper bit preserved.

**Vertical magnification does nothing.** `ratio_v = 0xC16C` latches and the
green bar -- the 176 unfetched lines below the 544 real ones -- is identical
whether the block is engaged or bypassed.

## What was eliminated, and how

A full mmap dump of **1088 registers** across every display block we know
(`afbd` 0x400, `comp` 0x300, `route` 0x600, `proc` 0x100, `lvds` 0x100,
`layer` 0x200), captured during a working 1280x544 run and a shearing 960x544
run, then diffed. Every register encoding 1280 in both runs was then poked live
to the real source width, with readback confirming the write and a verified
restore afterwards:

| poked | result |
| --- | --- |
| `route+14c`, `route+164` (1280) | no change |
| `route+518`, `route+528` ({1280,720}) | no change |
| `afbd+160` channel size | no change |
| `layer+080`, `layer+084` ({720,1280}) | no change |
| `comp+224` | no change |

`proc+040` = `0xC0000500` is the one candidate not yet poked; the block is
bypassed in the failing case, so it is unlikely but not excluded.

## The conclusion this points to

**The window width is MIPS-owned state, not a register we can reach.** This is
the same signature as 2026-09-04, when the composition ratio registers took
writes, read back correctly, and changed nothing, because the MIPS owns
presentation through its own window layer. Poking further is not the route.

The next move is desk work, no board time: find how the firmware reprograms a
window's width, via the VideoInfo descriptor it already consumes from us, or
via the window layer in `docs/mips-window-layer-plan.md`. Note the descriptor
demonstrably reaches the hardware -- before the geometry fix, `vi_follow=0` and
`vi_follow=1` produced visibly different failures (purple vs black).

## Method notes

- **A warm reboot leaves this display unable to render anything.** Every driver
  test needs a full power cycle. This cost most of a session before it was
  recognised, and it makes register-level bisection from userspace (patch 0100)
  worth far more than it looks.
- `busybox devmem` is one process per register and far too slow to sweep inside
  a 10 s window; `tools/display/blockdump.py` mmaps `/dev/mem` instead. Its
  bases MUST be page aligned -- an unaligned base fails the whole dump with
  `EINVAL` and produces an empty file that reads as "no suspects found".
- Prompt the operator BEFORE the observation window, never after.

## What the firmware's own source-configuration routine says

Static RE, no board time. `tools/mips/block-map.py` gives the registers; the
code is at **`0x8b1a3ea0`–`0x8b1a4408`** (MIPS address = ARM + `0xB5000000`).

**Field layouts, from the `ins` masks:**

    0x05600020  [12:0]  align16(width) - 1        [28:16] align16(height) - 1
    0x05600030  [12:0]  width, forced EVEN        [28:16] height
    0x05600048  [15:0]  luma width, align 4       [28:16] height (13 bits)
    0x0560004c  [15:0]  chroma width, align 4     [28:16] height
    0x05600040  [15:0]  luma stride, align 16     (upper half PRESERVED)
    0x05600044  [15:0]  chroma stride, align 16

Every one is a read-modify-write of a single field with `ins`. **Our driver
writes whole words.** For the sizes tested the discarded upper bits are zero, so
this is not the current fault -- but it is a latent one.

**THE STRUCTURAL FINDING: `0x020` AND `0x030` COME FROM DIFFERENT STRUCTURES.**

    lw  $a3, 4($a2)     -> width  feeding 0x020        (struct A)
    lw  $a2, 0xc($a2)   -> height feeding 0x020
    lw  $t0, 0xc($a1)   -> height feeding 0x030        (struct B)
    lw  $a1, 4($a1)     -> width  feeding 0x030

`$a1` and `$a2` are two distinct geometry descriptors -- the same picture-window
versus output-window split the `ProcWinNode` class exposes (`m_out_win`,
`m_video_win`, `m_picture_win`). Patch 0098 sets BOTH to the source size. That
is what first got a picture onto the glass, so it is closer than the inherited
panel values were, but conflating the two is the most likely reason the row
length is still 1280.

**Next session starts here:** identify which of `$a1`/`$a2` is the buffer and
which is the window, by finding the callers of this routine and typing the two
structures. Then decide what each of `0x020`/`0x030` should hold for a source
smaller than the panel. That is desk work; no board time and no operator.

Do NOT resume by poking registers. Nine were eliminated that way already.
