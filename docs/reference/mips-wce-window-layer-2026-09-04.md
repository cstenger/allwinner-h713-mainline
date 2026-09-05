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

> ### ⚠ HAZARD, learned the hard way 2026-09-04: do NOT release the MIPS from Linux
>
> The ARM-side pump ([`tools/mips/mips-shell.py`](../../tools/mips/mips-shell.py))
> works and is validated in both directions, but **executing a command needs the
> core running, and releasing it from a booted Linux hard-locks the whole SoC.**
>
> The seven-write release sequence was replayed from Linux with `/dev/mem`
> (`0x02001600`, five writes to `0x0200160c`, the boot address at `0x03061030`).
> All seven writes went through and printed. The very next statement — a 2 s
> sleep and a read of `0x0306101c` — never returned. **Network dead, and serial
> dead too: no echo, no output, nothing.** Physical power cycle required.
>
> **This is a new failure mode, and it widens a hazard the project thought it
> understood.** The documented whole-SoC lock was *live MIPS + real Cedrus/DECD
> traffic*, with "static frames with MIPS alive are fine". There was no video
> here — no Cedrus, no DECD, an idle console. What was different from every
> earlier release is **where it was done from**: every previous release was from
> the U-Boot prompt, where nothing else owns the display. Here the KMS driver
> was bound, holding `0x05600000`/`0x05140000`/`0x051c0000` and the AFBD IRQ,
> when the window layer came up and took presentation.
>
> So the rule is not "MIPS + video locks the SoC". It is closer to **two owners
> of the display hardware locks the SoC**, and Cedrus traffic was one instance
> rather than the cause.
>
> #### The two-owner explanation was WRONG — tested and refuted
>
> The obvious fix was to remove the second owner: unbind `sun50i-h713-afbd`
> from `5600000.display`, then release. Tried it, with a serial capture running
> so a lock would still leave forensics
> ([`mips-release-lock-2026-09-04.txt`](mips-release-lock-2026-09-04.txt)).
>
> **The unbind was clean** — driver detached, `/dev/dri/card0` gone, IRQ 249
> freed, no oops, board fully responsive afterwards. **And it locked anyway, at
> the same instruction:**
>
> ```
> mips-shell: releasing the MIPS core -- if this is the last line, the SoC locked
> mips-shell:   0x02001600 <- 0x80000002  clock
> ...
> mips-shell:   0x03061030 <- 0x4b100000  boot address
> mips-shell:   0x0200160c <- 0x00070001  RELEASED     <- dies here, both times
> ```
>
> The narration is the payoff: `release_core()`'s "survived the release" line
> never appears, so **the lock is on the RELEASED write itself**, not on
> anything that follows it. Two runs, two different display-ownership states,
> identical failure. Whatever kills the SoC is in bringing the core out of
> reset while Linux is running — not in contention over the display registers.
>
> **One new clue, unexplained.** The unbind produced an IOMMU fault:
>
> ```
> Console: switching to colour dummy device 160x45
> sun50i-iommu 2010000.iommu: Page fault for 0x00000000ffc85000 (master 2, dir rd)
> ```
>
> Master 2 is `dec@5600000`. So detaching the driver does **not** stop the
> fetch engine — the hardware kept scanning and faulted the moment its
> translation went away. "Unbound" is not "quiesced", and any future attempt
> should stop the engine explicitly rather than assuming the driver teardown did.
>
> #### Release from U-Boot, then boot Linux — ALSO LOCKS, in early kernel boot
>
> The remaining no-flash idea: release the core at the U-Boot prompt (the
> placement that has always been safe), then boot Linux with the KMS driver
> prevented from ever registering, and pump from Linux where the mapping is
> uncached. No rebuild needed — `module_platform_driver()` gives the initcall
> symbol `h713_afbd_platform_driver_init`, so
> `initcall_blacklist=h713_afbd_platform_driver_init` in `bootargs` is enough.
> (`bootargs` is unset in the environment and comes from the FIT's DTB, but
> setting the env var overrides it: U-Boot's `fdt_chosen()` writes `bootargs`
> into the DTB whenever the variable exists.)
>
> **The release itself is confirmed clean at the U-Boot prompt** — a genuine
> positive worth keeping:
>
> ```
> md.l 0x0306101c 1   ->  0306101c: 00000000
> ... the seven writes ...
> md.l 0x0306101c 1   ->  0306101c: 00000001
> =>                      (prompt returns, further commands work)
> ```
>
> **Then Linux was booted and the SoC locked almost immediately.** With
> `earlycon` on the command line, serial produced:
>
> ```
> Starting kernel ...
> [    0.000000] Machine model: HY200 QZ713DF_A1 (Allwinner H713)
> ```
>
> and then nothing — no systemd, no login, no oops, no panic, and complete
> silence across a 45 s listen. That is inside `setup_arch`, long before any
> display code, and the KMS driver was blacklisted so it is definitively not
> ours.
>
> **So the failure is not about ownership of the display registers, and not
> about which side issues the release.** Three attempts, three orderings:
>
> | ordering | KMS driver | result |
> | --- | --- | --- |
> | release from Linux | bound | lock at the RELEASED write |
> | release from Linux | unbound | lock at the RELEASED write |
> | release from U-Boot, then boot Linux | never registered | lock in early kernel boot |
>
> **The generalisation: a live MIPS window layer and a booting/running Linux
> cannot coexist *in our stack*, by any ordering we can construct.**
>
> > **Do not read that as a hardware law — it is not.** Stock Android is Linux
> > booting under an already-released MIPS, and it works. So coexistence is
> > demonstrably possible on this silicon and the lock is a defect in **our**
> > kernel or DT, not a property of the SoC. Every "cannot" on this page is
> > scoped to our stack. The useful question is therefore *what does the vendor
> > kernel do differently in early boot*, not *whether it can be done*.
>
> #### The IOMMU lead is REFUTED — it never gets that far
>
> Tested 2026-09-04: released at the U-Boot prompt as before, then booted with
> `iommu.passthrough=1` **and** both drivers kept off the hardware entirely,
> `initcall_blacklist=h713_afbd_platform_driver_init,sun50i_iommu_driver_init`.
> Locked again.
>
> The last line on the console was:
>
> ```
> [    0.000000] psci: probing for conduit method from DT.
> ```
>
> **That is the refutation, and it does not depend on where exactly the hang
> is.** PSCI probing happens in early init, long before any platform driver is
> probed — so `sun50i_iommu_probe` had not run, and could not have run, at the
> moment the SoC died. The IOMMU cannot be the cause, and blacklisting it
> changed nothing because it was never reached.
>
> **A correction, because it nearly became a false finding.** This run looked
> like it "got much further" than the previous one, which stopped at
> `Machine model:`. It did not: the earlier attempt's console output was piped
> through a `grep` filter, and none of `reserved mem`, `cma`, `Zone ranges` or
> `psci` match any pattern in it. **The two boots may well have died at the same
> place.** Nothing here shows the failure point moved, and the tempting reading
> that the IOMMU knobs helped is unsupported. Capture boot output unfiltered.
>
> So the cause is in *very early* kernel init, before device drivers exist —
> which also rules out every driver-level explanation, not just the IOMMU one.
> What remains is unattractive to test: something the kernel does to memory,
> caches or the interconnect during `setup_arch`/`psci` init, or simply that the
> MIPS wedges the bus on its own a fixed time after release and the kernel is an
> innocent bystander. **Note that the release is followed by 20-30 s of operator
> typing before `bootcmd` runs, so the "time since release" confound has never
> been controlled** — a scripted release-then-immediate-boot would separate
> those two explanations, and is the only cheap experiment left here.
>
> #### Where that leaves the shell: no cheap route
>
> Both ways in are now blocked, for unrelated reasons:
>
> - **From Linux** — releasing the core locks the SoC, twice, independent of
>   display ownership.
> - **From U-Boot** — `md`/`mw` cannot reach the MIPS coherently (see the
>   docstring of [`tools/mips/mips-shell.py`](../../tools/mips/mips-shell.py)):
>   all DRAM is mapped MT_NORMAL cacheable, D-cache is on, `CONFIG_CMD_CACHE`
>   is unset, and U-Boot's own `h713_mips.c` calls `flush_cache()` /
>   `invalidate_dcache_range()` precisely because the ARM cache is not coherent
>   with the MIPS.
>
> The pump itself is finished and validated in both directions; it is the
> *core-alive* precondition that has no cheap path. Making U-Boot work means a
> bootloader flash (FEL boot is documented non-working here) to add cache
> maintenance or an in-U-Boot pump command. **Do not spend more power cycles
> re-attempting the Linux release.**

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

### Read on our board, 2026-09-04: identical to stock, register for register

`tools/display/panel-downscaler-probe.sh`, phases 1 and 2. Production kernel
6.18.38, MIPS parked (`0x0306101c = 0`), panel on the login prompt, no writes.

```
051c0120 0x42000000      051c0130 0x050002D0
051c0124 0x06000000      051c0134 0x00000000
051c0128 0x00000500      051c0138 0x08010000
051c012c 0x000002D0      051c013c 0x00000020
```

**All eight match the stock Android capture exactly**, including `0x0120` and
`0x013c`, which were not part of the predicted set. Nothing moved across a 3 s
resample, so this is configuration state, not a running counter.

So the U-Boot/MIPS bring-up leaves the panel down-scaler **enabled
(`0x0124[26:25] = 3`) at unity (`0x0138[21:0] = 0x010000`)**, on our pipeline,
with the MIPS parked. That is the best of the three outcomes this probe was
written to distinguish: the block is provisioned on our path rather than being
stock-only state, and the visible test is a genuine one-register change.

It does **not** show the block acts on our raster. At unity it cannot.

### The visible ratio test — NEGATIVE, 2026-09-04

Run with the operator watching, on the same boot. A 720p clip was playing and
**confirmed scanning out** — video plane 38 cycling four distinct framebuffer
ids, not merely mpv claiming its direct path.

```
0x051c0138: 0x08010000 -> 0x08018000    ratio 1.0 -> 1.5, readback confirmed
held 10 s
restored to 0x08010000, verified
```

**Operator: the video played normally.** No size change, no framing change, no
corruption, no flicker.

**What this closes.** Writing the ratio field alone, on the video path, does not
scale our raster. The register accepts the value and the picture is unaffected.

**What it does not close, stated precisely so it is not over-read later.** This
is one variant, not the space:

- It was run on the **video** path only (selector `0x051c006c = 0x39000000`).
  Our driver switches that selector between the RGB/OSD source and the DECD
  video source. If the down-scaler stage sits on the RGB side of that mux, or
  upstream of where we inject, it would be untouched by our video raster and
  produce exactly this null. **Now tested — see below.**
- The geometry registers were left describing 1280x720 → 1280x720. In the
  firmware, `WriteDownScalerRatio` writes the ratio and the width/height as one
  set. They come from the *same* window struct and the ratio is an independent
  field rather than derived from the geometry, so ratio-alone ought to have been
  meaningful — but it is not what the firmware ever emits.

Against that second point, one thing found while checking it **strengthens the
negative**: `PanelWinNode`'s slot 4 writes ~25 LVDS registers (`0x051c0000`,
`0x0004`, `0x0020`, `0x003c`, `0x0040`, `0x0050`, `0x00a0`–`0x00c4`, `0x0200`,
`0x0204`) and every one is a plain read-modify-write. **There is no commit latch
anywhere in this path**, so "the write was never latched" is not available as an
explanation the way it was for the AFBD-side experiments.

`0x051c0200`/`0x051c0204` are outside every window we have ever read.

### The RGB path — ALSO NEGATIVE. This route is closed.

The other side of the `0x051c006c` mux, run the same day so nothing else moved.
Gated differently, because the console issues no page flips: selector confirmed
at `0x29000000` (RGB/OSD) and the **TCON scan counter at `0x05880000` confirmed
advancing**, which proves the raster is being clocked out without needing a
flip. The console was filled with 40 lines of text first, so a rescale could not
be subtle.

The ratio was **pulsed**, not stepped — four cycles of 8 s at 1.5 and 3 s at
unity, 44 s total. The operator cannot see the script's output as it runs, and
the first RGB attempt was missed for exactly that reason; anything responding to
this field would have become a repeating, unmistakable pulse.

**Operator: no change at all — only the text the test itself printed. No size
change, no visual issues.** Restored and verified.

> **The panel down-scaler at `0x051c0124`–`0x051c0138` does not act on our
> raster, on either side of the mux. Do not re-run this register.**

The closure is stronger than a single null, and worth stating why:
**two independent paths**, a different liveness gate on each (cycling
framebuffer ids for video, an advancing scan counter for RGB), a repeating
pulse rather than one timed step, readback-confirmed writes, and — the part
that removes the usual escape hatch — **no commit latch exists anywhere in
`PanelWinNode`'s slot 4**, so "it was never latched" cannot be offered. That
excuse rescued several earlier AFBD experiments; it is not available here.

**What survives.** The block is real, provisioned by our own bring-up, and
byte-identical to stock. What it is *not* is reachable from where we inject.
That is the same shape of result as `0x05000000` and has the same explanation:
both stages belong to the MIPS window layer's pipeline, and our arrangement —
MIPS parked, injecting at AFBD, taking output at the LVDS selector — bypasses
the middle of that pipeline. Two scalers, two nulls, one cause.

### Two things follow, and they are worth separating

**Measured:** these registers exist, stock enables them, our own bring-up leaves
them identical to stock, and the field layout is now known from both sides.

**Refuted:** that writing a non-unity value into `0x051c0138[21:0]` scales our
picture. Tested on both paths, negative on both.

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

## The signalling mechanism — answered, and it closes the route

This is the question the plan's step D was written to answer: *what sets the
dirty mask that arrives in `s1` at `NRWinNode` slot 4, i.e. how does the ARM
tell the MIPS a window changed?* Static work, no board time.

**The answer is that nothing does. There is no ARM-side signal, because there is
no handshake — applying a window is an ordinary internal function call.**

### The apply dispatch

The five nodes are allocated in `TWCETop`'s constructor and stored at fixed
offsets, in pipeline order:

| offset | node | ctor | alloc |
| --- | --- | --- | --- |
| `+0x68` | `CapWinNode` | `0x8b1a04e0` | |
| `+0x6c` | `NRWinNode` | `0x8b1a31b8` | `0x194` |
| `+0x70` | `DETNWinNode` | `0x8b1a0e60` | `0x140` |
| `+0x74` | `ProcWinNode` | `0x8b1a5f68` | `0xc0` |
| `+0x78` | `PanelWinNode` | `0x8b1a50e4` | `0xa8` |

and applied by walking that table with a plain virtual call:

```
lw   $a0, 0x74($s0)        ; the node
lw   $v0, ($a0)            ; its vptr
lw   $v0, 0x10($v0)        ; slot 4 -- Apply
jalr $v0
lui  $a1, 0x40             ; <- the dirty mask, in the delay slot
```

Roughly seventy such sites cluster in `0x8b1a8000`–`0x8b1a9900`, repeatedly in
`Cap -> NR -> DETN -> Proc -> Panel` order.

### The mask is a compile-time literal

Harvested from every dispatch site, by node:

| node | masks passed |
| --- | --- |
| `Cap` | `0x1`, `0xffffffff` |
| `NR` | `0x4`, `0x20`, `0x40`, `0x44`, `0x80`, `0x100`, `0x1002`, `0x6a40`, `0x6e40`, `0x6ec0`, `0x7e46`, `0x10000`, `0x80004`, `0x80404`, `0x87e06`, `0xffffffff` |
| `DETN` | `0x20`, `0x1002`, `0x80000`, `0x260000` |
| `Proc` | `0x7e02`, `0x7e46`, `0x260000` |
| `Panel` | `0x400000` |

Every one is a `lui`/`ori` immediate. **There is no dirty word in memory** that
the ARM could set, and `0x4` — the bit that gates the whole scaler geometry
block — is simply what one particular internal caller passes.

`0xffffffff` is the full-refresh call, which is the interesting one: it would
re-apply every field a node currently holds. Reaching it still means executing
MIPS code.

### And the CPU_COMM `Wce` surface is decorative

The obvious hope was that one of the six `THal_Vp_Wce_*` entries reaches this
machinery. Checked, and the two scaling-shaped ones are the emptiest of all:

| CPU_COMM entry | implementation | what it does |
| --- | --- | --- |
| `Wce_EnablePixel2PixelMode` | `0x8b14cfd0` | 37 instructions, **calls only the logger**, twice |
| `Wce_DisablePixel2PixelMode` | `0x8b14d064` | 37 instructions, **calls only the logger**, twice |
| `Wce_SetWindow` | `0x8b14cd18` | writes three globals; worker `0x8b1099c8` is a stub |
| `Wce_SetMirrorMode` | `0x8b14cc64` | the one real mutator — a live `jalr` at `0x8b1099ac` via `0x8b109944`. Mirror, not scale. |
| `Wce_GetWindow` | `0x8b14cef0` | reads back those globals |
| `Wce_GetActiveWindow` | `0x8b14cf64` | genuine live query, mgr slot 9 |

**"Pixel to pixel" is exactly the name a 1:1/no-scaling toggle would have**, and
it is a pair of trace calls. Worth recording precisely so the next reader does
not spend a session on the name.

### What this means for the plan

Step D's premise — *populate the descriptor the MIPS reads, then signal it* —
describes a mechanism that does not exist. Window application is an internal
MIPS function call with a compile-time argument, so **driving the window layer
from the ARM requires executing MIPS code**: the debug shell, or patched
firmware. There is no third option, and no descriptor-plus-doorbell to build.

Combined with the shell being unreachable from both Linux and U-Boot, the whole
window-layer route now rests on a bootloader flash or a firmware patch.

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
