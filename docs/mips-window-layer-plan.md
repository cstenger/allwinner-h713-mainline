# Plan — driving the MIPS window layer, for 1080p on the panel

Written 2026-09-04 for a fresh session. Everything below is measured unless it
says otherwise; the two things that are *not* proven are called out in
[What is not proven](#what-is-not-proven), and you should read that section
before spending a week on this.

> ## ⚠ REVISED 2026-09-04, later — step 1 ran, and it moved the target
>
> Step 1 was done as desk work and is written up in
> [reference/mips-wce-window-layer-2026-09-04.md](reference/mips-wce-window-layer-2026-09-04.md).
> Three things changed:
>
> 1. **`display.bin` has RTTI**, so the whole window layer reads out by name:
>    five `*WinNode` classes, a `TWindowManager`, a `TWCETop`, and which
>    hardware block each node owns. It is not the black box this plan assumed.
> 2. **The scaler at `0x05000000` belongs to `NRWinNode`, not `PanelWinNode`**,
>    and the routine "at `0x8b1a4810`" is two functions read as one — see
>    [the descriptor section](#what-the-firmware-tells-us-about-the-descriptor).
> 3. **There is a second scaler, and it is in a window our driver already
>    maps.** `PanelWinNode::WriteDownScalerRatio` drives a panel down-scaler at
>    `0x051c0124`–`0x051c0138`, whose decode is confirmed register-for-register
>    against a stock capture. That makes the "does this hardware scale" question
>    answerable for one DT line and one write, instead of for a window-layer
>    port. **The step order below is rewritten around it.**
>
> The old step 1 — RE `svp_ioctl` → `tgd_put_plane_info` — is withdrawn. That
> path was disassembled end to end on 2026-08-26 and is the RGB OSD flip; it
> never signals the MIPS. See [Closed routes](#closed-routes-do-not-re-run-these).

## The goal, and why this route

Put 1080p on the 1280x720 panel using the SoC's own scaler, with no GPU.

The operator's stated priority is **specialized hardware over the GPU** — the
GPU path works today (`vo=gpu` on *stock* mpv, ~0.83x realtime, 481 dropped
frames, visible artifacts) but costs the no-GPU property that the DECD work was
built to win. Treat the GPU as the fallback, not the plan.

## The one-paragraph state of the world

Our display path has no scaler because **we own the fetcher, not the pipeline**.
The KMS driver maps three windows — `afbd` (`0x5600000`), `route` (`0x5140000`),
`lvds` (`0x51c0000`) — and nothing else. The scaler, mixer, vblender and TCON are
configured once at U-Boot/MIPS bring-up into a fixed 1280x720 single window and
never touched again. Stock does have scaling, in the inline scaler at
`0x05000000`, driven by the MIPS as part of its **window/composition layer**. The
MIPS owns presentation through that layer, not through the AFBD registers, so
the two arrangements cannot be mixed:

| | owner of presentation | scaler | who runs this |
| --- | --- | --- | --- |
| MIPS parked | ARM, via AFBD registers | bypassed, inert | **us** — 720p, no scaling |
| MIPS alive | MIPS, via window descriptors | in its path | **stock** — scaling available |

**The work is therefore to become stock's ARM side**: populate the window/plane
descriptors the MIPS reads, and signal it. There is no shortcut; the cheap ones
are all tested and closed (see [Closed routes](#closed-routes-do-not-re-run-these)).

> **Amended 2026-09-04.** That table is about **one** scaler, `0x05000000`, and
> it is `NRWinNode`'s — the source stage, which our path genuinely bypasses.
> There is a **second** one: `PanelWinNode` drives a panel down-scaler at
> `0x051c0124`–`0x051c0138`, in the LVDS window row 3 of that table says we map.
> Whether it is live with the MIPS parked is unmeasured — but unlike
> `0x05000000`, this block is *demonstrably* in our path, because our own plane
> selector at `0x051c006c` sits in it. Steps A and B below test it, and they are
> much cheaper than becoming stock's ARM side.

## What is already established, and where it lives

Read these before touching anything. Most of a session was spent re-deriving
facts that were already written down.

| fact | where |
| --- | --- |
| Stock scales with the inline scaler at `0x05000000`, MIPS-driven — 45 `lui` sites, more than any other display block, writing the ratio and coordinate registers | [status.md](status.md) |
| The scaler is **inline, not a fetcher** — all 45 accesses are `lw`/`sw` read-modify-write to the same offset, no address is ever stored | [status.md](status.md) |
| The scaler's fields are **copied from a window descriptor**, gated by dirty bits — the node is `NRWinNode`, not PanelWinNode, and the routine is `0x8b1a48cc` | [reference/mips-wce-window-layer-2026-09-04.md](reference/mips-wce-window-layer-2026-09-04.md) (corrects [status.md](status.md)) |
| The WCE class map: five `*WinNode` classes, which block each owns, the `TWindowManager` vtable, the `win` debug command | [reference/mips-wce-window-layer-2026-09-04.md](reference/mips-wce-window-layer-2026-09-04.md) |
| **A second scaler — the panel down-scaler at `0x051c0124`–`0x051c0138`**, decode confirmed against a stock capture | [reference/mips-wce-window-layer-2026-09-04.md](reference/mips-wce-window-layer-2026-09-04.md) |
| The MIPS owns presentation; releasing the core blanks an ARM-published image with **every** register identical | [status.md](status.md) |
| CPU_COMM frame routines are **stubs** (`SetImageBufferAddr` `0x8b10ada8`, `GetImageBufferAddr` `0x8b10adb0` = `jr ra; nop`) | [reference/cpu-comm-call-table.md](reference/cpu-comm-call-table.md) |
| `ge2d@5240000` is the **display controller, not a 2D engine** — killed 2026-08-25, revived and re-killed twice since | [handoff-2026-08-24-display.md](handoff-2026-08-24-display.md) "Hardware colour conversion", [kms-display.md](kms-display.md) |
| DECD register map, source geometry, the four-slot ring | [reference/decd-register-map.md](reference/decd-register-map.md) |
| The whole display bring-up, panel power, TCON, teardown | [mips-display-recovery.md](mips-display-recovery.md) |
| IOMMU masters (`dec`=2 bypass, `ge2d`=2, `tvdisp`=3 translated) | [iommu-port.md](iommu-port.md) |
| `ge2d_dev.ko` extraction recipe and symbol survey | [ge2d-plane-open-re.md](ge2d-plane-open-re.md) |
| 720p playback, the mpv patches, the retry-wedge hazard | [handoff-2026-09-03-video-playback.md](handoff-2026-09-03-video-playback.md) |
| What was attempted on 09-04 and which conclusions did not survive | [handoff-2026-09-04-video-scaling-and-display.md](handoff-2026-09-04-video-scaling-and-display.md) §6 |

**MIPS address = ARM physical + `0xB5000000`.** Every earlier search of the
firmware for display registers returned nothing because of this. AFBD is
`0xba600000`, the scaler `0xba000000`, GE2D `0xba240000`. Firmware VA to file
offset is `VA - 0x8b100000`.

## What the firmware tells us about the descriptor

> **Corrected 2026-09-04.** There is no single routine that programs both
> blocks. `0x8b1a4810` sits in the *out-of-line cold blocks* of a function that
> starts at `0x8b1a4538` and has already returned by then; reading forward from
> it crosses into a second function. `0x8b1a4810` is also **dead** — no branch
> or jump anywhere in the image targets it. The two functions are:
>
> - **`0x8b1a4538`** — AFBD only (`0xba60` × 8), ending on the commit pair
>   `0x05600014` bit 0 and `0x0560006c` bit 0 that our driver already writes.
> - **`0x8b1a48cc`** — the scaler only (`0xba00` × 15), which then *calls* the
>   AFBD one. It has no `jal` caller: it is **`NRWinNode` vtable slot 4**.
>
> The register list below is unaffected and was independently re-derived. Only
> the owning class changes, and it matters: the descriptor to populate is an
> `NRWinNode` (`m_in_win`, `m_out_win`, `m_crop_win`, `m_read_fetch_win`), not a
> PanelWinNode.

From disassembling `0x8b1a48cc`. `s0` is the window object, `s1` the dirty mask.

```
s0+0x4c, s0+0x50   branch selectors (0x50 == 0 takes the hardcoded fallback)
s0+0x90, s0+0x94   -> scaler +0x01b4  {[15:0], [27:16]}
s0+0x98            -> scaler +0x01b8  [15:0]   (luma height)
s0+0x9c, s0+0xa0   -> scaler +0x0174  {[15:0], [27:16]}   (the RATIO register)
s0+0xa4            -> scaler +0x0178  [15:0]   (chroma height)
s0+0xa8, s0+0xac   -> scaler +0x00f0  {[7:0], [15:8]}
s0+0x12c           -> scaler +0x0844  [15:0] as (value - 1)
s0+0x130           -> scaler +0x0844  [31:16] as round-up-even(value)
s0+0x134           -> scaler +0x0840  [15:0] as (value - 1)
s0+0x138           -> scaler +0x0840  [31:16] as (value + 1)
```

Dirty-mask bits seen: `0x0004` gates the whole geometry block, `0x0020`,
`0x2000` gates `+0x0844`, `0x4000` gates `+0x0840`, `0x8000` gates `+0x0040`
bit 25. Enable-shaped bits: `+0x0138` bit 27, `+0x0040` bit 25.

**Field widths come from the `ins` masks, and the obvious guess was wrong**:
`+0x0174` and `+0x01b4` are `{[27:16] 12-bit, [15:0] 16-bit}`, *not* two 16-bit
halves. `+0x00f0` is two 8-bit fields.

**Space A's 1080/540 are hardcoded constants**, written by the fallback branch
at `0x8b1a4988` when `s0+0x50 == 0`. The live values `0x60020438` and
`0x6002021C` are that default — the same class of inherited fallback as AFBD's
1920x1088, and **not** evidence of an active 1080p pipeline. Do not build on
them.

## The plan

**Do steps A and B before anything else.** They test the plan's load-bearing
unproven assumption — that this hardware scales at all — for one DT line and one
register write, on our existing path with the MIPS parked. If they come back
negative the whole window-layer port loses its payoff, and it is much better to
learn that in an afternoon than after it.

### Step A — read the panel down-scaler (no writes, no risk)

`PanelWinNode::WriteDownScalerRatio` programs a down-scaler in the **LVDS
window our KMS driver already maps**:

```
0x051c0124  bits [26:25] = 3            enable
0x051c0128  bits [15:0]  = width
0x051c012c  bits [15:0]  = height
0x051c0130  = (width << 16) | height
0x051c0138  bits [21:0]  = ratio, 16.16 fixed point
```

Stock Android at idle holds these enabled at unity — `0x06000000`, `0x500`,
`0x2D0`, `0x050002D0`, `0x08010000` — which matches the disassembly on all five.
**Nobody has ever read them on our board**: `patches/kernel/0078` maps
`<0x051c0000 0x100>`, 0x24 bytes short, and no `h713_disp dump` block reaches
them either.

So: read `0x051c0120`–`0x051c0140` with the MIPS parked and 720p scanning out.
Is the block enabled? At what ratio? That is a `devmem` loop and it discriminates
"U-Boot leaves this configured" from "this is stock-only state".

### Step B — write a non-unity ratio, with an operator watching

> **RAN 2026-09-04. Step A positive, step B NEGATIVE.**
>
> Step A: all eight registers read **byte-identical to stock**, with the MIPS
> parked — U-Boot leaves the down-scaler *enabled at unity* on our pipeline. So
> the block is provisioned on our path, not stock-only state, and no DT change
> was needed to read it (`busybox devmem` reaches it regardless).
>
> Step B: ratio `1.0 -> 1.5` at `0x051c0138`, held 10 s under a 720p playback
> confirmed scanning out (plane 38, four distinct fbs). **Operator: the video
> played normally.** Restored and verified.
>
> **Then the RGB path, also negative — so this register is closed.** Selector
> confirmed at `0x29000000`, TCON scan counter confirmed advancing, console
> filled with 40 lines of text, ratio **pulsed** four times (8 s scaled / 3 s
> unity) so the change could not be mistimed. **Operator: no change at all.**
>
> Two independent paths, a different liveness gate on each, readback-confirmed
> writes, and no escape hatch: `PanelWinNode`'s slot 4 is ~25 LVDS
> read-modify-writes with **no commit latch anywhere**, so "never latched"
> cannot be offered. **Do not re-run `0x051c0138`.**
>
> Same shape as `0x05000000`, and the same explanation: both stages belong to
> the MIPS window layer's pipeline, and our arrangement bypasses the middle of
> it. Two scalers, two nulls, one cause.
> Full record: [reference/mips-wce-window-layer-2026-09-04.md](reference/mips-wce-window-layer-2026-09-04.md).

Widen the DT `lvds` window from `0x100` to `0x200` — one line, no new node —
then set `0x051c0138[21:0]` away from `0x010000` while 720p is confirmed
scanning out (four distinct fbs cycling), and restore.

**This is the cheapest available test of "does this hardware scale."** Unlike
`0x05000000`, this block is demonstrably in our path with the MIPS parked: our
driver's plane selector at `0x051c006c` lives in it and its effect was
established causally
([reference/lvds-006c-stock-causal-2026-08-31.md](reference/lvds-006c-stock-causal-2026-08-31.md)).

Bound the risk the way the earlier ratio test did: one register, held for a
fixed dwell, restored and verified. If `0x0124`'s enable reads clear in step A,
set it as part of the same test rather than as a separate run — but change one
thing at a time across runs, not within one.

### Step C — the `win` debug command, for free geometry and a second lever

The firmware ships a top-level `win` shell command
([reference](reference/mips-wce-window-layer-2026-09-04.md)):

```
win wi          get all win size info    -> DumpAllNodeWinInfo
win wm          get win mgr info         -> DbgDumpWindowConfig
win os <0..100> set overscan             -> TWindowManager::SetOverScanRatio
win rn <0..2>   set refresh node
```

`win wi` prints the live geometry of every window node — the descriptor content
this plan proposes to reconstruct by disassembly — and `win os` is a second,
independent scaling lever needing no descriptor work.

Reaching it needs no wire and no firmware patch:
[mips-display-recovery.md](mips-display-recovery.md) established that
`shell_thread_monitor` is registered on an **uncached** SysView ring at
`0x4bd01000`, ARM-reachable, and confirmed that on hardware in 2026-08-07 — the
ring has simply never been driven. Writing that pump is static work. Check
first whether the `0x2000` flag on the `win` table entry gates it behind a
privilege level; that is not yet verified.

### Step D — RE the ARM-side entry point (static, no board)

Only if A–C say the payoff is real. **Do not start from `ge2d_dev.ko`** — its
`svp_ioctl` → `tgd_put_plane_info` was disassembled end to end on 2026-08-26 and
is the RGB OSD flip, RGB-only, writing AFBD channel registers directly and never
signalling the MIPS.

> **ANSWERED 2026-09-04, and it closes this step.** There is no signalling
> mechanism. The five nodes live at fixed offsets in `TWCETop`
> (`+0x68` Cap, `+0x6c` NR, `+0x70` DETN, `+0x74` Proc, `+0x78` Panel) and are
> applied by a plain virtual call, `node->vtable[+0x10](node, mask)`, with the
> **mask as a `lui` immediate in the delay slot** — a compile-time literal at
> ~70 internal call sites. There is no dirty word in memory for the ARM to set.
>
> The CPU_COMM `Wce` surface does not reach it either, and the two
> scaling-shaped entries are the emptiest: `Wce_EnablePixel2PixelMode` and
> `Wce_DisablePixel2PixelMode` are 37 instructions each that **call only the
> logger**. "Pixel to pixel" is exactly what a 1:1/no-scaling toggle would be
> called, and it does nothing — do not spend a session on the name.
>
> **So "populate the descriptor and signal it" describes something that does not
> exist.** Driving the window layer from the ARM means *executing MIPS code* —
> the debug shell or patched firmware — and both now need a bootloader flash.
> Full derivation:
> [reference/mips-wce-window-layer-2026-09-04.md](reference/mips-wce-window-layer-2026-09-04.md).

### Step E — the minimal liveness experiment (one power cycle)

Do **not** start with video. Get *any* image on the panel with the core running.

Cheapest known way into that state, with no reflash:

```
cold power cycle -> interrupt autoboot (preboot publishes the logo, quiesces the MIPS)
mw.l 0x02001600 0x80000002      # clock
mw.l 0x0200160c 0x00000000      # assert     mw.l 0x0200160c 0x00030001   # stage 3
mw.l 0x0200160c 0x00010000      # stage 1    mw.l 0x03061030 0x4b100000   # boot address
mw.l 0x0200160c 0x00030000      # stage 2    mw.l 0x0200160c 0x00070001   # RELEASED
```

`tools/display/mips-alive-scaler-test.py --cold --release-mips` does this. The
firmware is already resident at `0x4b100000` with its shared memory published,
so releasing the core is all that is needed. The panel goes lit-but-blank: the
window layer is live and has no content. **That blank panel is your test rig.**
Populate a descriptor, signal it, and see whether anything appears.

Success here is a picture — any picture — with `0x0306101c == 1`.

### Step F — only then, geometry and scaling through the descriptor

With a frame presenting, set a non-unity ratio in `+0x0174`/`+0x0274` through the
descriptor (not by poking the register — poking it directly was tested and did
nothing). That is the first real evidence the block scales.

### Step G — video

Only after step F. This is where the hard lock lives; see below.

## Hurdles, in the order you will hit them

- **Live MIPS + real Cedrus/DECD traffic hard-locks the whole SoC.** No watchdog,
  SSH and serial both dead, physical power cycle required. Reproducible.
  ([reference/cedrus-decd-first-visible-playback-2026-08-31.md](reference/cedrus-decd-first-visible-playback-2026-08-31.md))
  Stock runs decode and MIPS display together fine, so this is *plausibly* our
  dual-ownership contention rather than a hardware law — but it is untested, and
  it is why step G comes last.
- **`h713_disp init` renders nothing.** A black panel after it is expected, not a
  fault. On 09-04 this was misdiagnosed as the warm-reboot panel-power no-op and
  cost a power cycle. Check whether anything actually published an image before
  blaming the panel rail.
- **Every ARM-side render command quiesces the MIPS.** `auto <id> logo` (image,
  quiesced), `init` (no image, alive), `panel-test <id> vendor-logo` (image for
  15 s, quiesced). `quiesce` being an opt-in *mode* of `panel-test` does not mean
  other modes leave the core running — measured, it reads `0`. There is an
  unused `h713_disp logo-live <id>` in the U-Boot working tree (auto-logo without
  the quiesce) if you want it in one command.
- **`panel-test` renders are time-limited** (~15 s). Do not spend that window on
  60 s of register reads.
- **U-Boot prints "logo published" on a black boot too.** Confirm with your eyes
  before every visible test, and confirm *again* after any state change.
- **Self-clearing latches read back 0 on success** — `0x05600014`, `0x05600144`.
  Reading 0 is not a failed write. This has bitten the project twice.
- **A rejected plane commit is retried forever and every retry reprograms the
  plane.** 890,454 ERANGE commits faulted IOMMU master 2 and blacked the panel
  until a power cycle. Never run a display path without a bound on its retries.
- **Never enable the DECD video source with no frame behind it** — garbage under
  bypass, AFBD-wedging fault under translation. Flip IOMMU master 2 `0x7c`->`0x78`
  only while that source is disabled. ([memory: iommu-master2-flip-ordering])
- **`CONFIG_SUNXI_DECD=m` with no `CONFIG_MODVERSIONS`**: a stale `.ko` from
  `/lib/modules` loads silently against a new kernel and you measure the old
  code. Boot with `modprobe.blacklist=` and `insmod` by path with a SHA-256
  check. Blacklist rather than `rmmod`, which can clock-gate the live display.
- **Do not read `0x07091000`** (CPUS/ARISC). A plain read wedges the SoC.
- **Never hold PB5 low for long.** It is the light's supply enable *and* the fan.
- **FEL cannot be used for visible display tests.** In FEL the board is powered
  over USB and the panel and lamp rails do not come up. FEL is for recovery only.

## Method notes that actually saved time

- **Do the cheap byte-level measurement first.** Two visible runs were spent on
  hypotheses a checksum and a pagemap read could have ranked for free.
- **A `lui` scan of `display.bin` is complete.** No block address appears as an
  aligned data constant anywhere in the binary, so every MMIO address is formed
  from a `lui` immediate — which makes an *absence* in that scan conclusive.
  Use `0xba60` (AFBD) as a positive control.
- **This scaler has no observable state.** No counters, no status bits, and both
  ratios sit at unity. Register reads therefore cannot distinguish "not in our
  path" from "in our path, doing nothing" — two separate sessions drew the
  stronger conclusion and were wrong. Only a visible test decides.
- **Ask what a passing suite is blind to.** mpv's "Using direct DRM PRIME
  video-plane scanout" proves path *selection*, not display; `vo=drm` was black
  for weeks while every log said success. Gate on the plane holding a crtc, a
  non-zero fb, and an fb id that **changes** — and sample it several times,
  because mpv cycles only three framebuffers.
- **Operator-timed tests need their own turn.** Ask, wait for "ready", then run.

## Closed routes — do not re-run these

| route | verdict |
| --- | --- |
| GE2D as a scaler | **dead**, three times. It is the display controller. |
| CPU_COMM frame submit | **dead** — the routines are stubs. |
| Poking the scaler's ratio registers directly | **no effect**, MIPS parked or alive, operator watching both times. |
| Committing an ARM-programmed AFBD frame with the core alive | **ignored** — this is what proves the MIPS owns presentation. |
| Patch 0093 (dynamic AFBD geometry) | never seen on the panel; programs 4 of the 7 source-geometry words. Kept on disk, out of `series`. |
| DECD as a scaler | **dead** — one coordinate space, no ratio register in the whole 1 KiB window. |
| `svp_ioctl` → `tgd_put_plane_info` as the window-layer entry | **dead** — disassembled end to end 2026-08-26. RGB-only OSD flip, writes AFBD channel registers directly, never signals the MIPS. This was step 1 of the first draft of this plan. |
| CPU_COMM `Wce_SetWindow` | **dead** — real prologue, but its worker `0x8b1099c8` is `jr ra; addiu v0,zero,1`. It writes three globals that only `Wce_GetWindow` reads back. Re-verified 2026-09-04. |
| CPU_COMM `Wce_Enable/DisablePixel2PixelMode` | **dead** — 37 instructions each, and the only thing either calls is the logger. The name is exactly what a 1:1/no-scaling toggle would be called; it does nothing. |
| A descriptor-plus-doorbell handshake with the MIPS | **does not exist** — window apply is `node->vtable[+0x10](node, mask)` with the mask a `lui` immediate at ~70 internal call sites. Nothing external can set it. |
| Driving the MIPS debug shell from Linux | **blocked** — releasing the core from a booted Linux hard-locks the SoC, twice, and it is not display contention (unbinding the KMS driver first changed nothing). |
| Driving the MIPS debug shell from U-Boot | **blocked** — `md`/`mw` do no cache maintenance and all DRAM is mapped cacheable with no `dcache off`; the ARM cache is not coherent with the MIPS. |
| The panel down-scaler ratio at `0x051c0138` | **dead** — negative on the video path *and* the RGB path, 2026-09-04, operator watching both times, pulsed on the second. The block is enabled at unity and byte-identical to stock, and does not act on our raster from either side of the mux. No commit latch exists in this path, so "never latched" is not an available explanation. |

## What is not proven

1. **That this hardware scales at all.** Still the load-bearing unknown, and now
   with two negatives behind it: no frame has ever been seen to change size, on
   either scaler, on any path. The firmware evidence is strong —
   `TWCETop::IsEnablePanelDownScaler` gates on the panel being **shorter than
   1080**, and stock ships the panel down-scaler enabled at unity, which our own
   bring-up reproduces byte-for-byte — but it is still firmware reading, not a
   picture.

   **The cheap tests are now spent.** `0x05000000` and `0x051c0138` both accept
   writes and both do nothing to our raster, which is what the "we own the
   fetcher, not the pipeline" model predicts. Nothing short of driving the
   window layer will distinguish "the pipeline stage is bypassed" from "this
   silicon does not scale" — so anyone starting the port should know they are
   spending it on an assumption two experiments have failed to confirm and none
   has confirmed.
2. **That live MIPS plus Cedrus traffic can coexist.** Stock does it; we locked
   the SoC trying. Whether that is contention or a hardware law is untested.

If step E cannot be made to work in a reasonable session, the honest fallback is
characterising the GPU path's artifacts — nobody has yet spent a session on
*why* `vo=gpu` drops 481 frames, and it is the only thing that puts 1080p on the
panel today.
