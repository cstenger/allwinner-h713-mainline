# Stock `decd.ko` register map

Recovered 2026-08-30 from `local/h713-lab/extracted/decd.ko` (unstripped) by
static analysis. No hardware time.

## How the bases resolve

`decd` uses `of_iomap`, so every access is base-relative and invisible to the
absolute-address extraction that works on `ge2d_dev.ko`. `dec_init` makes exactly
two `of_iomap` calls and derives a third base from the second:

```
of_iomap(node, 0) -> [r0+0x00]
of_iomap(node, 1) -> [r0+0x04]
                     [r0+0x08] = [r0+0x04] + 0x60
```

The third base is the `workaround` window, and hardware has independently placed
those registers at `0x0560006x` -- blue at `+5`, mux at `+8`, bypass at `+9`/`+c`,
`int_to_display` bit 4 at `+0`. That forces `[r0+0x04]` to be `0x05600000`, which
in turn makes `[r0+0x00]` the other window, `0x05700000`. It is corroborated by
`dec_reg_top_enable` working through `[r0+0x00]`.

| slot | physical | window |
| --- | --- | --- |
| `[r0+0x00]` | `0x05700000` | TVTOP |
| `[r0+0x04]` | `0x05600000` | AFBD |
| `[r0+0x08]` | `0x05600060` | workaround (AFBD + 0x60) |

**Stock's DT lists these in the opposite order to ours.** Stock has AFBD at reg
index 1; `sun50i-h713.dtsi` has it at index 0. Our port compensates --
`regs->afbd = of_iomap(node, 0)`, `regs->workaround = regs->afbd + 0x60` -- so
both combinations land on the same physical addresses. Self-consistent, not a
bug, but worth knowing before anyone "fixes" the reg order to match stock.

## The map

| function | registers |
| --- | --- |
| `dec_reg_top_enable` | `0x05700000`-`0x0570001c`, and `0x05600003` |
| `dec_reg_video_channel_attr_config` | `0x05600010`, `11`, `13`, `0x05600040`, `44`, `48`, `4c` |
| `dec_reg_enable` | `0x05600060`, `0x05600069`, `0x056000c4` |
| `dec_reg_int_to_display`(`_atomic`) | `0x05600060` |
| `dec_reg_set_filed_mode` / `_repeat` | `0x05600064` |
| `dec_reg_blue_en` | `0x05600065` |
| `dec_reg_mux_select` | `0x05600068` |
| `dec_reg_bypass_config` | `0x05600069`, `0x0560006c` |
| `dec_reg_set_dirty` | `0x0560006c` |
| `dec_reg_set_address` | `0x0560006c`, `0x05600094`-`0x0560009c`, + more |
| `dec_reg_get_y_address` | `0x05600070`, `0x05600074` |
| `dec_reg_get_c_address` | `0x05600084`, `0x05600088` |
| `dec_reg_frame_cnt` | `0x056000bc` |
| `dec_irq_query` | `0x056000c0`, `0x056000c4` |

## What is absent, which is the point

**`decd` never touches a composition or blending register.** Its entire surface
is TVTOP's top-enable plus AFBD source 0 -- fetch geometry, Y/C addresses,
format, interrupt, mux, bypass, dirty. It does not touch the channel controls at
`0x05600100` or `0x05600140`, it does not touch the mixer at `0x0525c000`, and it
does not touch the writeback engine (which is separately known to be disabled
during playback).

So on stock the ARM side never programs composition at all. Combined with the
established finding that the MIPS firmware programs the video source when a frame
is submitted, the division of labour is:

- **ARM/`decd`**: configure source 0's fetch and hand over frames.
- **MIPS firmware**: everything that gets that source composited onto the panel.

That is consistent with every fetch-side experiment coming back null while the
panel demonstrably scans out and responds to buffer writes: the missing step is
not a register the ARM side is supposed to write. It is firmware work we have not
reproduced.

`dec_reg_video_channel_attr_config` is the sharpest illustration. It is the only
ARM-side writer of the video source's format and geometry -- exactly the
registers the firmware was observed to program -- and it is dead code in stock
`decd.ko`, never called.

## Two blind spots this exposed

- `dec_reg_top_enable` writes `0xFFFFFFFF` to TVTOP `+0x08` through `+0x1c`. The
  original six-register TVTOP dump (`0x00`, `0x40`, `0x44`, `0x80`, `0x84`,
  `0x88`) misses all of it. The later 11-window block sweep reads `0x05700000`
  for `0x30` words and does cover it.
- The AFBD sweep window stops at `0x056001fc`, and `ge2d` references `0x05600200`
  and `0x05600224`. Both are writeback registers whose enable reads zero, so it
  is very likely immaterial -- but unmeasured.
