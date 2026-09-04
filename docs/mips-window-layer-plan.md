# Plan — driving the MIPS window layer, for 1080p on the panel

Written 2026-09-04 for a fresh session. Everything below is measured unless it
says otherwise; the two things that are *not* proven are called out in
[What is not proven](#what-is-not-proven), and you should read that section
before spending a week on this.

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

## What is already established, and where it lives

Read these before touching anything. Most of a session was spent re-deriving
facts that were already written down.

| fact | where |
| --- | --- |
| Stock scales with the inline scaler at `0x05000000`, MIPS-driven — 45 `lui` sites, more than any other display block, writing the ratio and coordinate registers | [status.md](status.md) |
| The scaler is **inline, not a fetcher** — all 45 accesses are `lw`/`sw` read-modify-write to the same offset, no address is ever stored | [status.md](status.md) |
| The scaler's fields are **copied from a PanelWinNode window descriptor**, gated by dirty bits, by the routine at `0x8b1a4810` | [status.md](status.md) |
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

From disassembling `0x8b1a4810` (the routine that programs both AFBD and the
scaler). `s0` is the window object, `s1` the dirty mask.

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

### Step 1 — RE the ARM-side entry point (static, no board)

`ge2d_dev.ko`, board B, ARM 32-bit, **unstripped, 1111 symbols, relocations
intact**. SHA-256 `a79017e5d3bc9563135e463404d3bb38bf6f263d5b31fbe122768f2dca11583f`,
stashed at `local/h713-lab/extracted/ge2d_dev.ko` (gitignored; extraction recipe
in [ge2d-plane-open-re.md](ge2d-plane-open-re.md)). Disassemble with
`llvm-objdump -d --triple=armv7-none-linux-gnueabi`.

The runtime path is **`svp_ioctl` -> `tgd_put_plane_info`** (not
`tgd_init_planesetting`, which is probe-time only — that correction is already
in the doc and was itself a method error worth reading). Recover:

1. the ioctl number and the payload struct `tgd_put_plane_info` takes;
2. how that payload becomes the window object the firmware reads at `s0`
   (offsets above) — most likely a shared-memory descriptor, since CPU_COMM
   cannot carry frames;
3. **the signalling mechanism** — how ARM tells the MIPS a window changed, i.e.
   what sets the dirty mask that arrives in `s1`. This is the crux. Without it
   the descriptor is inert and you will reproduce 09-04's null.

Cross-check against the firmware side: `tgd_vblender_irq`, `tgd_flip_plane`,
`lvds_reset_fifo` are all in the same binary, and `0x8b1a4810`'s callers on the
MIPS side bound what the protocol can be.

### Step 2 — the minimal liveness experiment (one power cycle)

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

### Step 3 — only then, geometry and scaling

With a frame presenting, set a non-unity ratio in `+0x0174`/`+0x0274` through the
descriptor (not by poking the register — poking it directly was tested and did
nothing). That is the first real evidence the block scales.

### Step 4 — video

Only after step 3. This is where the hard lock lives; see below.

## Hurdles, in the order you will hit them

- **Live MIPS + real Cedrus/DECD traffic hard-locks the whole SoC.** No watchdog,
  SSH and serial both dead, physical power cycle required. Reproducible.
  ([reference/cedrus-decd-first-visible-playback-2026-08-31.md](reference/cedrus-decd-first-visible-playback-2026-08-31.md))
  Stock runs decode and MIPS display together fine, so this is *plausibly* our
  dual-ownership contention rather than a hardware law — but it is untested, and
  it is why step 4 comes last.
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

## What is not proven

1. **That this hardware scales at all.** It is an inference from the firmware
   writing ratio-shaped registers with 1080/540 and 720/360 coordinate pairs.
   Strong, but no frame has ever been seen to change size. If the descriptor
   path works and the ratio still does nothing, the payoff evaporates — so get
   to step 3 as early as the work allows.
2. **That live MIPS plus Cedrus traffic can coexist.** Stock does it; we locked
   the SoC trying. Whether that is contention or a hardware law is untested.

If step 2 cannot be made to work in a reasonable session, the honest fallback is
characterising the GPU path's artifacts — nobody has yet spent a session on
*why* `vo=gpu` drops 481 frames, and it is the only thing that puts 1080p on the
panel today.
