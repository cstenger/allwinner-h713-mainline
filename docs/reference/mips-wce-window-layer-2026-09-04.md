# The MIPS window layer, recovered from RTTI — 2026-09-04

Static analysis of `display.bin`, no board time. This is step 1 of
[mips-window-layer-plan.md](../mips-window-layer-plan.md), and it moves that
plan's target: the entry point it names is settled and closed, and a cheaper
lever turned up in a register window our driver already maps.

Everything below is read out of the firmware image unless it says otherwise.
The one hardware cross-check is called out where it is used.

## Method, and why it worked this time

`display.bin` is **C++ with RTTI left in**. Every part of the display pipeline
is a class with a typeinfo record and a vtable, and the source filenames are in
`.rodata` (`./PanelWinNode.cpp`, `./WCETop.cpp`, `./window_manager.cpp`). Once
one vtable is located, the slot index is stable across the whole hierarchy, so
recovering one class reads all of them.

Two tools were written for this and are worth reusing:

- [`tools/mips/vtables.py`](../../tools/mips/vtables.py) — anchors on the
  Itanium-ABI name strings (`9NRWinNode`, `12PanelWinNode`), walks back to the
  typeinfo and forward to the vtable, and prints the class hierarchy with slots.
- [`tools/mips/cfg.py`](../../tools/mips/cfg.py) — recursive-descent CFG walk.
  Needed because this firmware uses **out-of-line basic-block placement**: a
  function's blocks are not a contiguous range, and other functions sit between
  them. Address-range reasoning mis-attributes code here, and did.

## Correction: `0x8b1a4810` is not a function, and it is not PanelWinNode's

[status.md](../status.md) and the plan both describe "`0x8b1a4810..0x8b1a4dbc`
(364 instructions)" as one routine programming both AFBD and the scaler, filling
the scaler "from a **PanelWinNode** window descriptor". That range spans two
different functions and names the wrong class. The stack prologues settle it —
there are exactly two in the region, with different frame sizes:

```
0x8b1a4538  addiu $sp,$sp,-0x60      F starts
0x8b1a480c  addiu $sp,$sp, 0x60      F's epilogue (delay slot of jr $ra)
0x8b1a48cc  addiu $sp,$sp,-0x38      G starts
0x8b1a4dbc  addiu $sp,$sp, 0x38      G's epilogue
```

`0x8b1a4810` sits in **F's out-of-line cold blocks**, which occupy
`0x8b1a4810..0x8b1a48cc` — past F's own `jr $ra`. Reading forward from there
walks off the end of one function and into another.

And `0x8b1a4810` itself is worse than an arbitrary starting point: a scan of
every branch and jump in the image finds **no instruction anywhere that targets
it**. It is one dead `sw $v0, 0x10($s1)` the compiler left behind. The real cold
blocks begin at `0x8b1a4814`.

Counting `lui` immediates per function separates the two cleanly:

| function | `lui` blocks touched | role |
| --- | --- | --- |
| **F** `0x8b1a4538` (+ cold `0x8b1a4810`) | `0xba60` × 8 — AFBD only | programs the AFBD fetch, ends on the commit pair |
| **G** `0x8b1a48cc` (+ cold `0x8b1a4dc0`) | `0xba00` × 15 — scaler only | programs the scaler, then **calls F** |

F's last act is the frame commit our own driver already writes every atomic
update:

```
0x05600014 bit 0 = 1        commit latch
0x0560006c bit 0 = 1        dirty
```

**G has no `jal` caller anywhere in the image.** It is reached through a vtable,
and that is what opened the rest of this file up: `0x8b1a48cc` is stored at
`0x8b207a60`, which is **slot 4 of the vtable for `NRWinNode`** — not
PanelWinNode. The scaler at `0x05000000` belongs to the *noise-reduction /
source* node, and the register list the plan recovered is correct; only the
owning class was wrong.

## The WCE — Window Composition Engine

Recovered from RTTI. All five node classes derive from `TIWinNode : TINode`,
and **slot 4 is the per-node "program your hardware" virtual**:

| class | source file | log tag | slot 4 | hardware it writes |
| --- | --- | --- | --- | --- |
| `CapWinNode` | `./CapWinNode.cpp` | `wce_cap` | `0x8b1a092c` | none in range — capture side |
| `DETNWinNode` | `./DETNWinNode.cpp` | `wce_detn` | `0x8b1a1a64` | scaler `0x05000000`, `0x050c0000` |
| `NRWinNode` | `./NRWinNode.cpp` | `wce_nr` | `0x8b1a48cc` | **scaler `0x05000000`**, then AFBD via F |
| `PanelWinNode` | `./PanelWinNode.cpp` | `wce_panel` | `0x8b1a5a38` | **LVDS `0x051c0000`** |
| `ProcWinNode` | `./ProcWinNode.cpp` | `wce_proc` | `0x8b1a6a08` | route `0x05140000` |

Member names, straight out of the debug-dump format strings:

```
CapWinNode    in_win  crop_win  picture_win  out_win  m_scale_ratio_h  m_scale_ratio_v
DETNWinNode   m_out_win  m_detn_win  m_video_win  m_picture_win  m_motion_win[0..3]
NRWinNode     m_in_win  m_out_win  m_crop_win  m_read_fetch_win
PanelWinNode  m_video_win  m_video_win_2  m_program_win  m_crtc_panel_win
              m_21_9_scaler_win  m_border_overlay_win
ProcWinNode   m_in_win  m_out_win  m_meter_win
```

Above the nodes sit three singletons:

| class | source file | notable members |
| --- | --- | --- |
| `TWCETop : IWceTop` | `./WCETop.cpp` | `SetWindow`, `CalcWinSize`, `AdjustWinCfgForPixelAlign`, `CalcCaptureActiveWin`, **`IsEnablePanelDownScaler`** |
| `TWindowManager : IWinMgr` | `./window_manager.cpp` | `UpdateWce`, `SetAspectRatio`, `SetOverScanRatio`, `DbgDumpWindowConfig`, `WinMgrCallback0/1` |
| `TWCEDataBase : IWceConfig` | `./WCEConfig.cpp` | `GetWinCfg`, `GetMotionWinCfg`, `GetAplDclWinInfo` |

`TWindowManager`'s vtable is at `0x8b208920` (so an object's vptr is
`0x8b208928`). Slots named by matching each function against the trace string it
passes to the logger at `0x8b150948`:

| slot | vptr offset | address | name |
| --- | --- | --- | --- |
| 4 | `+0x10` | `0x8b1aafcc` | `SetOverScanRatio(value)` |
| 6 | `+0x18` | `0x8b1ab034` | takes a 4-edge rect; called with `{0,1000}`×4 |
| 8 | `+0x20` | `0x8b1ab2b4` | `SetAspectRatio` |
| 9 | `+0x24` | `0x8b1ab384` | active-window query — what CPU_COMM `Wce_GetActiveWindow` calls |
| 14 | `+0x38` | `0x8b1ab444` | `DbgDumpWindowConfig` |
| 15 | `+0x3c` | `0x8b1ab43c` | `DumpAllNodeWinInfo` |

**The singleton pointer is at MIPS `0x8bac4bf0`** (`0x8b1ac5f8` is a two-line
getter). Under the measured `+0x40000000` MIPS→system window that is ARM
**`0x4bac4bf0`** — readable with `md.l` while the core is alive, with no shell
and no RPC.

## `win` — a window-manager debug command, in the firmware already

The firmware's UART/monitor shell has a top-level `win` command. Registration,
in the shell's command table:

```
0x8b20deec  flags   0x00002000
0x8b20def0  name    "win"
0x8b20def4  handler 0x8b19fe00
0x8b20def8  help    "for window debug only"
```

`0x8b19fe00` `strcmp`s `argv[1]` against a 12-byte-stride subcommand table at
`0x8b206e80` and tail-calls `handler(argc-1, argv+1)`:

| subcommand | handler | help string | what it does |
| --- | --- | --- | --- |
| `win os <0..100>` | `0x8b1ac654` | `set overscan` | `strtol` base 10, clamped to ≤100; builds a `{0,1000}`×4 rect, calls mgr slot 6 with it, then **slot 4 (`SetOverScanRatio`) with the parsed value** |
| `win rn <0..2>` | `0x8b1ac788` | `set refresh node` | |
| `win wi` | `0x8b1ac62c` | `get all win size info` | tail-calls mgr slot 15, `DumpAllNodeWinInfo` |
| `win wm` | `0x8b1ac604` | `get win mgr info` | tail-calls mgr slot 14, `DbgDumpWindowConfig` |

Usage string: `Usage: win[option] command`. Separately, the shell has
`win_on` / `win_off` — "enable/disable window manager" — at `0x8b110948` /
`0x8b110960`.

**Why this matters.** `win wi` prints the live geometry of every window node —
exactly the descriptor content the plan proposes to reconstruct by
disassembly — and `win os` is a **live scaling knob** that needs no descriptor
work at all. [mips-display-recovery.md](../mips-display-recovery.md) already
established that the monitor shell is registered and driveable from the ARM
through an uncached SysView ring at `0x4bd01000`, with the ring never yet
driven. That remaining work is static, and it is now worth doing.

**Not verified:** whether the `0x2000` flag word gates `win` behind a privilege
level. The entry immediately before it is `{"VS", …, "default user"}`, which
looks like a user-level marker, so this should be checked before planning
around it.

## The panel down-scaler is at `0x051c0124`–`0x051c0138`

This is the find that changes the plan's cost.

`PanelWinNode::WriteDownScalerRatio` (`0x8b1a58c0`, traced with the string at
`0x8b207c50`) writes the **LVDS block at `0x051c0000`**, not the scaler at
`0x05000000`. Signature, from the disassembly:

```
WriteDownScalerRatio(self, win_a, win_b, ratio)
    s1 = ratio & 0x3fffff                       /* 22 bits */
    if (self[8] == <global 0x8b206dac>)   -> ENABLE path
    else                                  -> BYPASS path
```

The enable path (`0x8b1a59cc`..`0x8b1a5a20`):

```
0x051c0124  bits [26:25] = 3            enable  (ins $v1,$a0,0x19,2 with a0=3)
0x051c0128  bits [15:0]  = win_a[0x04]  u16
0x051c012c  bits [15:0]  = win_a[0x0c]  u16
0x051c0130  bits [31:16] = win_a[0x04]
0x051c0130  bits [15:0]  = win_a[0x0c]
0x051c0138  bits [21:0]  = ratio
```

The bypass path (`0x8b1a58e8`..) clears `0x051c0124[26:25]`, sets
`0x051c0120[26:24] = 2`, and reprograms `0x0128`/`0x012c`/`0x0130`/`0x0134`
from the *other* window, with `0x0128` taking `win_b[0x04] - 6`.

A window struct is `{x, w, y, h}` as u32 — the `lhu` at `+0x04` and `+0x0c`
picks up `w` and `h`.

### The stock capture confirms the decode, register for register

[`stock-osd-lvds-coupled-2026-08-31.txt`](stock-osd-lvds-coupled-2026-08-31.txt)
sampled this block on stock Android at idle, before any of this was understood:

| register | stock value | what the disassembly predicts |
| --- | --- | --- |
| `0x051c0124` | `0x06000000` | bits [26:25] = `0b11` — **enabled**, exactly the `ins …,3,0x19,2` |
| `0x051c0128` | `0x00000500` | `w` = 1280 |
| `0x051c012c` | `0x000002D0` | `h` = 720 |
| `0x051c0130` | `0x050002D0` | `(w << 16) | h` |
| `0x051c0138` | `0x08010000` | bits [21:0] = `0x010000` — **unity in 16.16** |

Five registers, five matches, from a capture taken for an unrelated reason.
Stock runs this block **enabled at unity** on an idle 1280x720 panel.

### Two things follow, and they are worth separating

**Measured:** these registers exist, stock enables them, and the field layout is
now known from both sides.

**Inference:** that writing a non-unity value into `0x051c0138[21:0]` scales the
picture. Nothing has been seen to change size — that is still the plan's
unproven item 1. What is new is that the test is now cheap.

### Why this is cheaper than the `0x05000000` route

`0x05000000` is the **NRWinNode** scaler — the source stage, in a part of the
pipeline our driver does not own, and every write to it has been inert. The
`0x051c0000` block is the **PanelWinNode** stage, the output side, and our KMS
driver already writes `0x051c006c` there — the plane selector, whose effect on
our path was established causally in
[`lvds-006c-stock-causal-2026-08-31.md`](lvds-006c-stock-causal-2026-08-31.md).
So this block is demonstrably in our path with the MIPS parked, which is the
exact property `0x05000000` lacks.

**One line stands between us and the test.** `patches/kernel/0078` maps

```
reg = <0x05600000 0x400>, <0x05140000 0x1000>, <0x051c0000 0x100>;
```

`0x100` stops 0x24 bytes short of `0x051c0124`. No `h713_disp dump` block covers
it either (`lvds-phy` `0x051c0000`+0x20, `lvds-phy-mid` `0x051c0020`+0xa0,
`lvds-phy2` `0x051c00b0`+0x40), which is why we have a stock reading of these
registers and never one of our own.

## When stock turns the panel down-scaler on

`TWCETop::IsEnablePanelDownScaler` (`0x8b1a7df4`):

```
query config -> v
if (v != 0x1001000b):
        if (cfg[4] != 0x10010013) -> third path
        trace "No need to enable panel down scaler"; return 0
if (cfg[4] >= 0x438)              /* 1080 */
        return 0
mode = sig[4]
if (mode == 0x00020016)                              -> enable
else if ((mode - 0x0002006a) < 7 &&
         ((0x49 >> (mode - 0x0002006a)) & 1))        -> enable   /* offsets 0,3,6 */
else    return 0
trace "Need to enable panel down scaler"; return 1
```

`cfg[4]` is compared against **1080** and gates the whole thing, so the
down-scaler is a *panel-shorter-than-1080* feature, enabled for a small set of
1080-class input modes. That is precisely the 1080p→720p case this work is
after, and it is the vendor's own designed path rather than something inferred
from a ratio-shaped register.

The enums `0x1001000b`, `0x10010013`, `0x00020016`, `0x0002006a` are not decoded.

## What this does *not* change

- **CPU_COMM `Wce_SetWindow` is still closed.** `0x8b109d54` has a real body —
  it masks three caller pointers to 28 bits, ORs `0xa0000000` to make them
  uncached MIPS addresses, and calls `0x8b14cd18` — but
  [cpu-comm-call-table.md](cpu-comm-call-table.md) already established that
  `0x8b14cd18` stores its arguments into three globals and calls a stub at
  `0x8b1099c8`. Re-derived here independently; the earlier conclusion stands.
  `Wce_GetActiveWindow` remains the one real live query (mgr slot 9).
- **`ge2d_dev.ko`'s `svp_ioctl` → `tgd_put_plane_info` is not the window-layer
  entry point.** [ge2d-plane-open-re.md](../ge2d-plane-open-re.md) disassembled
  it end to end on 2026-08-26: it is the RGB OSD flip, RGB-only, writing AFBD
  channel registers directly, and it never signals the MIPS. Step 1 of the plan
  as written would re-derive a closed result.
- **The hard lock.** Live MIPS plus real Cedrus/DECD traffic still locks the
  SoC. Nothing here touches that.

## Open, in the order that looks cheapest

1. **Read `0x051c0120`–`0x051c0140` on our board**, MIPS parked, our path
   scanning out 720p. Pure read, no risk. Tells us whether the block is enabled
   and at what ratio on a U-Boot-initialised pipeline.
2. **Write a non-unity ratio to `0x051c0138[21:0]`** with an operator watching.
   Needs the DT `lvds` window widened from `0x100`; that is the only code change.
3. **Drive the monitor-shell SysView ring** and issue `win wi` / `win wm`. Gives
   the live window geometry for free and makes `win os` available as a second,
   independent scaling lever.
4. Decode the config enums in `IsEnablePanelDownScaler`, and find who calls
   `WriteDownScalerRatio`'s caller — i.e. what sets `self[8]` to the value that
   selects the enable path.
