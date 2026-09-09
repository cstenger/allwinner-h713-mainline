# Handoff — 2026-09-08: video plays on the panel

Companion to [the MIPS callback trace handoff](handoff-2026-09-08-mips-callback-trace.md)
(a separate session, same day) and successor to
[the composition-block handoff](handoff-2026-09-06-composition-block.md).

**Real Cedrus-decoded video renders correctly on the panel with the MIPS core
alive, and the source route now lives in the driver.**

Chain: Cedrus decode → zero-copy dma-buf → IOMMU translation → DECD fetch →
MIPS window layer → panel. 29.96 fps, `0x0306101c = 1` throughout.

Photographs: `local/lcd-photos/test_80` (static frame), `test_81` (the doubling
regression, since fixed). Commits `bdd1506`, `6fda761`, `8225282`, `5479f4e`.

**Session ran 2026-09-08 into 2026-09-09.** Three power cycles, all in the last
stretch and all from the hard-lock described below.

> **Read this first if you are rebuilding the DECD module.** The build tree that
> produced the working module was missing three patches that are *in the series*
> — `0071` (release fence lifetime), `0072` (refuse non-contiguous dma_buf
> import), `0073` (single-mapping DMA constraint). Rebuilding with them applied
> stopped the SoC hard-lock reproducing. See "The hard-lock, and the three
> missing patches".

## The three faults

| | wrong | right |
| --- | --- | --- |
| format byte `0x05600011` | `0` = RGB888 | **`3` = NV12** |
| plane-address publish | — | **`0x0560006c`** |
| source-config commit | — | **`0x05600014`**, and it **retires on vsync** |

The two latches do different jobs and are not interchangeable:

- **`0x05600014`** commits the **source configuration** — seven geometry words
  and the source enable.
- **`0x0560006c`** publishes the **plane addresses** of the two-plane YUV path.

Both were already documented in
`patches/kernel/0065-drm-h713-afbd-scan-out-nv12-directly.patch`, whose comment
names the exact trap: *"they set the format byte and kept feeding AFBD_SRC, so
the fetch stayed 4 bytes/pixel."*

### The commit retires on vsync — the thing nobody had written down

Every shell recipe that ever worked wrote registers through separate `devmem`
processes and then slept 100 ms — six vsyncs. Issued back to back from the
kernel the commit gets microseconds, **does not retire, and the hardware
silently ignores the configuration while every register still reads back
correct**.

Symptom: the frame renders **doubled side by side at half height** — a
2-bytes-per-pixel fetch, each display row consuming two source rows, so even
rows land left, odd rows right, and 720 rows end at display row 360 (`test_81`).

**The failure is invisible to a register dump.** Proving that required dumping
three whole regions and finding them byte-identical between a working run and a
broken one:

| region | span | result |
| --- | --- | --- |
| afbd | `0x05600000..0x1FF` | identical |
| top | `0x05700000..0xFF` | identical — **never compared before this session** |
| composition | `0x05000000..0x87c` | identical |

The only differing words, `+0x630..+0x648`, are already classified in
`reference/frame-composition-block-capture-2026-08-31.txt` as *"live or
per-frame telemetry"* — a symptom of the different picture, not a cause.

Poll the latch to zero with a budget **longer than 16.7 ms**. A 10 ms poll gives
up before the first frame boundary, logs `source commit did not retire`, and
reproduces the doubling exactly.

## What is in the driver now

`patches/kernel/0095` (in series) programs the seven geometry words, source
enable, format byte and config commit **from the submitted descriptor**:

```
decd 5600000.dec: DECD route: 1280x720 stride 1280 hw-format 3
```

- Staged in `frame_item_create()`, applied from the submit ioctl **after
  `dec_reg_enable()`** — `docs/ge2d-plane-open-re.md` records that the vendor
  never writes the format selector alone.
- Re-applied whenever the source enable bits are clear. Caching on geometry
  alone silently skips it after anything disables the source between streams.
- `item->format_shadow` was hardcoded to `0` (= RGB888), which is why every
  trace reported format 0 while the panel was fed NV12: the byte was only ever
  traced, never programmed. It now comes from `fmt_attr_tbl` column 8.

**Deliberately not in the driver:** chroma gain `0x05140508` and plane selector
`0x051c006c`. They live in the display engine, are not mapped by this driver,
and are shared with the MIPS logo path. Routing the panel to video is a
display-ownership decision, not a decoder one.

## The harness

`tools/video/decd-all-preconditions.sh` drives three sources through one
verified sequence and **refuses to hold for a visual test unless every
precondition passes**. A refusal costs no operator attention.

```
MODE=static     file staged into the carveout      bypass + physical
MODE=carveout   Cedrus frame 0 copied there        bypass + physical
MODE=live       Cedrus, driver-owned ring          translation + IOVAs
DRIVER_ROUTE=1  AFBD block left entirely to the driver
```

It checks core, IOMMU, selector, gain, seven geometry words, format byte, all
eight ring slots (or, in live mode, that each is driver-written and each Y/C pair
is separated by exactly the luma-plane size, with the ring advancing), all
seventeen composition registers, that the frame bytes are present at the fetch
address, and that the source process is still alive.

It caught, before any of them reached the panel: a `0x7C` vs `0x0000007C` width
mismatch; a spent cumulative `ring_writes_max`; a false pass validating the
previous run's leftover addresses; a cleared source enable; and a racy Y/C read
that returned a negative delta.

## Corrections to the record

- **"Composition is the cause" (2026-09-06) — withdrawn.** On a normal boot all
  seventeen registers are already at 1280x720; the 852x480 state was
  self-inflicted by that session's own source-coordinate client run. Composition
  *does* own the displayed footprint.
- **"Translation is the fault" — withdrawn and disproven.** It came from
  `decd-static-via-iova.sh`, which carried the missing `0x05600014` commit and
  so never tested translation. `MODE=live` renders correctly through IOVAs.
- **`f410ebf`'s inference retired**: zero IOMMU faults does **not** prove the
  IOVAs are mapped — it is equally consistent with silent zeroes. The conclusion
  it supported happens to be true; the reasoning was invalid.
- **Stock playback is not evidence for our path.** Its `0x05600010 = 0x03000013`
  (format 0) was cited as proof format 0 was correct, but stock composites video
  into an RGB surface. A matching register is evidence only when both sides are
  doing the same thing.
- **The 60 Hz hard-lock claim was made, retracted, and then explained.** First
  declared non-reproducing on four clean runs; then it locked twice in two
  attempts on a fresh boot; then rebuilding with the three missing patches
  stopped it reproducing, including under the exact fresh-boot condition. The
  intermediate claim was premature — four samples on one boot were never
  evidence about a hazard that had shaped experiment design since 2026-09-04.
  See the dedicated section below.

## The hard-lock, and the three missing patches

**Symptom:** the whole SoC wedges during live Cedrus playback with the MIPS
alive. No SSH, no serial, no console; only a power cycle recovers.

**Cause, very likely:** the build tree that produces the DECD module branches
from a point that predates three patches which are in the series:

| patch | state in the tree we were building from |
| --- | --- |
| `0071-misc-decd-fix-release-fence-lifetime` | **was ABSENT** |
| `0072-misc-decd-refuse-a-non-contiguous-dma-buf-import` | **was ABSENT** |
| `0073-misc-decd-declare-the-single-mapping-dma-constraint` | **was ABSENT** |
| `0094` (`ring_writes_max`), `0095` (driver route) | present |

`0071` exists because `frame_item_release()` did `kfree(item->fence)` while
`FRAME_SUBMIT` had handed userspace a `sync_file` holding a reference to that
same `dma_fence`. So **every frame retirement freed a fence userspace might
still hold**. Live playback retires ~30 frames/second; static single-frame tests
retire almost none — which matches "static stable, live locks" exactly.

**Evidence after applying all three and rebuilding:**

```
uptime 47 s   300 frames, 29.94 fps, core alive     <- the locks were at ~57 s
uptime 88 s   preconditions pass, core alive
uptime 95 s   preconditions pass, core alive
+ six further clean live runs on a warm board
```

Nine clean live runs, three inside the first 100 s of uptime, against **two
locks in two attempts in that same window** immediately before. Two independent
improvements came with it: standalone `decd-play` previously reported *"release
fence has not signalled in 2000 ms with 4 held"* and now completes, and the
`decd-client` segfault disappeared.

**What is NOT established: the mechanism.** A dangling `dma_fence` producing a
*silent* whole-SoC wedge — no oops, no serial output — is not an obvious failure
mode; a use-after-free normally leaves a trace. `0072`/`0073` constrain DMA
imports and feel closer to a bus-level hang. Which of the three actually matters
is unknown, and this is absence-of-failure evidence. Do not treat it as closed.

**Practical consequence:** build the module from a tree with 0071/0072/0073
applied. They apply cleanly on top of the 0094/0095 tree. The module currently
on the board is `/root/sunxi-decd-fenced.ko`.

## Board state

Core alive (`0x0306101c = 1`), test FIT
`h713-kernel-decd-iommu-0076v3.fit` with
`initcall_blacklist=h713_afbd_platform_driver_init`,
**`/root/sunxi-decd-fenced.ko`** loaded (`auto_route=1`, `ring_writes_max=1`) —
this is the build WITH 0071/0072/0073; `sunxi-decd-route.ko` is the older build
without them and should not be used,
`hy310-cpu-comm-next.ko` loaded, logo path restored, IOMMU state preserved
across harness runs. `display_cfg.xml` on the FAT still has elog enabled —
**leave it**.

Bring-up from a cold boot:

```sh
python3 tools/serial/reboot-to-uboot.py /dev/ttyUSB0 45
python3 tools/serial/console.py --port /dev/ttyUSB0 --wait 3 'h713_disp init 0x34'
python3 tools/serial/boot_kernel.py --load /root/fits/h713-kernel-decd-iommu-0076v3.fit \
    --extra initcall_blacklist=h713_afbd_platform_driver_init --secs 30
```

Then on the board:

```sh
rmmod sunxi_decd; insmod /root/sunxi-decd-fenced.ko ring_writes_max=1
insmod /root/hy310-cpu-comm-next.ko
DRIVER_ROUTE=1 MODE=live DWELL=30 sh /root/decd-all-preconditions.sh
```

One `h713_disp init` per boot; never re-release a quiesced core with direct MMIO.

## Open work

- ~~No vsync-correct flipping~~ — **measured 2026-09-08, and it is already
  correct.** See "Flipping is already vsync-correct" below.
- **The DECD driver leaks `sunxi_scanout_dmabuf` exports — STILL OPEN.** A fix
  (`0096`) works but **breaks live playback** and is out of series; see below. `dec_release_file()` was a no-op, so whatever a
  client submitted last stayed pinned after it exited (a frame is released only
  when a *later* frame displaces it). Measured +2 references per `decd-client`
  run even on clean exit, 89 in one session; leaked references pin identity
  IOVAs and Cedrus then cannot allocate. After the fix: six client runs and
  three live runs with **zero** refcount growth.

  **The refcount model, which two attempts got wrong before it worked:**
  all four ring slots **alias one frame holding one reference** (put once, not
  four times — putting each slot is a use-after-free and segfaulted the client);
  `q->interlace_hold` is the literal `(void *)1` **armed flag**, never a
  pointer; the repeat path increments the refcount **once per vsync** and pushes
  one `release_fifo` entry each time, so **fifo depth is the outstanding
  reference count and is not bounded by the four slots** (eleven observed) — a
  fixed 8-entry array silently capped and the leak survived that "fix";
  `q->last_released` and the global `last_frame` are each separate holders.

  Recognising the symptom: GStreamer reports *"Not enough memory to allocate
  source buffers"* while `MemFree`, `CmaFree` and `buddyinfo` are all healthy.
  It is not memory pressure. Pre-existing leaked references are orphaned and
  still need a reboot to clear.

**Attempted fix regresses playback.** `patches/kernel/0096` drains held frames
on the last close and does fix the leak (zero refcount growth over six client
and three live runs). But the drain sets `q->slots[i] = NULL`, and
`dec_frame_queue_sync()` writes a **blank (zero) address for every NULL slot**
on each vsync — so the ring alternates between zeros and new frames. On the
panel: solid colours cycling black / pink-purple / black, with `0x05600070`
reading zero for the whole hold while preconditions had passed moments earlier.
"Last close" is not a sufficient guard: the drain fires while a player is still
running, and why `open_count` reaches zero mid-run was not diagnosed.

Next attempt should either find why `open_count` hits zero while a player runs
and gate on active streaming instead, or **drain without nulling the slots**, so
`dec_frame_queue_sync()` never sees a NULL slot to blank.
- **`decd-play` requests VideoInfo selector 0**, which the firmware resolver maps
  to hardware format 0 = RGB888. It only works because the driver never programs
  the format byte from that selector. Selector 6 resolves to format 3 and is the
  honest value — but **changing it was tried and reverted** (`fd9ec35`,
  reverted by `6284b2c`). It is verifiably correct and has **zero** effect on
  rendering, so it carries no benefit; it was backed out to stop carrying a
  pointless change while an unexplained hard-lock is in play. If it is
  revisited, note the failed hypothesis: selector 6 is the firmware resolver's
  input, so it *might* make the firmware act on the descriptor and conflict with
  the driver's route. That is plausible and wrong — the lock reproduced with
  selector 0, and was in any case the missing fence patch. The change itself was
  never shown to be harmful; it was dropped because it has no benefit and was
  muddying an unexplained failure. It could reasonably be re-landed now that the
  lock is understood.
- **`0x05600024 = 0x002C004F`** (crop origin) is still an undecoded constant.
- **Gain and selector still applied by shell**, by design. If the decoder should
  own them, that is a design decision about display ownership.
- Audio is not wired into this path; `mpv` playback remains the separate
  VA-API/DRM route.

## Flipping is already vsync-correct

The earlier "no vsync-correct flipping, tearing expected" line was an inherited
assumption, never a measurement. Both halves have now been measured and both
are correct, so there is nothing to fix.

**Atomicity** — `tools/display/latch-timing.c`. The plane-address publish at
`0x0560006c` retires with a **uniform 0..16.7 ms** distribution under randomised
write phase (n=60: min 775 us, median 10.3 ms, max 16.6 ms, flat histogram
across eighths of a frame, **0/60 under 50 us**). That is the signature of a
register latching on the frame boundary, so a ring rewrite cannot split a frame.
The config commit at `0x05600014` behaves the same way, which is consistent with
the vsync-retirement finding above.

> **Sampler trap, recorded because it nearly produced a wrong answer.** A fixed
> 3 ms inter-sample delay plus the ~13.7 ms wait sums to one frame period, which
> phase-locks the sampler to the panel: every write lands at the same point in
> the frame and the spread collapses to a constant 13.69 ms. That reads exactly
> like a fixed hardware latency. Randomising the delay is what exposes the true
> uniform spread.

**Cadence** — `tools/display/flip-cadence.c`, which timestamps every change of
the live Y address at `0x05600070`. During real playback:

```
flips=120, active span 3.97 s  =>  29.98 fps displayed   (source 29.97)
mean dwell 33.4 ms (2.00 vsyncs), worst 50.2 ms
  1 vsync :   2      2 vsyncs : 116      3 vsyncs : 1
```

116 of 119 frames held for exactly 2 vsyncs — correct 2:2 for 29.97 fps content
on a 60 Hz panel — and the displayed rate matches the source to 0.03%. The
single 1+3 pair is one late frame in four seconds.

> Report the rate over the **active span**, not the sample window. The clip is
> short; if playback ends mid-window, dividing by the window reports a fraction
> of the real rate next to a correct per-frame dwell, which looks like a
> contradiction and is purely an artefact. The first run of this tool printed
> "8.50 fps" beside a correct 33.3 ms dwell for exactly that reason.

Minor and not a defect: the vsync handler rewrites all four ring slots every
vsync even when the frame has not changed (`ring_writes_done` advances ~61/s
against 30 fps content). Redundant work, but the publish is idempotent and
atomic, so it costs bus traffic rather than correctness.

## 0071/0072/0073 — confirmed visually on both paths

**2026-09-09, from a cold-boot baseline, one change at a time.**

| step | module | result |
| --- | --- | --- |
| baseline | `81bad18a` (0094+0095) | static frame **correct** (operator-confirmed) |
| + 0071/0072/0073 | `67d9d788` | static frame **correct** |
| + 0071/0072/0073 | `67d9d788` | live playback **correct**, 300 frames @ 29.94 fps, logo restored |

So the three patches are good on both the static and playback paths, and every
attribution made during the preceding confused stretch — patch 0096, the
VideoInfo format selector, the rebuilt client binaries, and these three patches
— was **wrong**. The cause was board-state drift alone (next section).

**Caveat on the format selector.** `2ed6218` re-lands VideoInfo selector 6 in
`tools/video/decd-{play,client}.c`, but the visual confirmations above used the
**restored original binaries** (`decd-client.coord1080` = `256143c8`,
`decd-play` = `ab5f6814`), which request selector 0. **Selector 6 is therefore
committed but not visually verified.** Rebuild and re-confirm before relying on
it; it has no effect on rendering by analysis, so this is low risk but unproven.

## Board-state drift — cold boot before debugging a rendering regression

**2026-09-09.** Byte-identical software — module `81bad18a` (patch 0095) and
client `256143c8` — rendered correctly, then produced **solid black/pink** after
roughly an hour of uptime and a dozen module load/unload cycles (including one
broken build), with 28 leaked scanout references outstanding.

Everything verifiable still checked out: all seven geometry words, format byte 3,
all eight ring slots, all seventeen composition registers, frame bytes present at
`Y_PHYS`, bypass, selector. Vsync healthy at 61 IRQ/s. The config commit retired
with no warning. The harness passed every precondition.

**A cold boot restored it immediately**, with the same binaries and module,
first submit on the fresh boot.

Consequences:

- **Rendering can fail while every measurable precondition is correct.** The
  harness cannot catch this; only the panel can.
- **Cold boot before debugging a rendering regression** on a board that has been
  up a long time with many module cycles. Re-establish the baseline visually,
  then change one thing at a time with a look after each.
- What actually drifts is **unknown**. Candidates: leaked scanout references
  pinning IOVAs, MIPS firmware state, accumulated display-block state.

Cost of learning this the hard way: several hours attributing the failure in
turn to patch 0096, then the VideoInfo format selector, then rebuilt client
binaries, then 0071-0073 — every attribution wrong and reverted, because the
baseline had silently moved underneath all of them.

## Method notes

**When a register dump says two runs are identical and they visibly are not,
stop diffing values and instrument the transaction.** Four rounds of plausible
theories produced nothing; instrumenting the commit latch produced the answer in
one run, and the fix followed from arithmetic (10 ms poll against a 16.7 ms
frame boundary).

**"One more run, then stop" is the right rule for guessing, not for measuring.**
This session was one run from being abandoned. The distinction that matters is
whether the next step produces a *measurement* or another hypothesis.

**Read the project's own record before spending an operator look.** The two
latches, the vendor's accompanying calls, and the classification of
`+0x630..+0x648` were all already written down. Three of the day's operator
looks were spent on hypotheses that a register read — or a `grep` — could have
ranked for free beforehand.

**A `grep` that silently drops half the data is worse than no grep.** `^056000`
excluded every address from `0x05600100` up, so two sessions of "full block"
diffs compared only half the block, and the OSD-channel differences were all in
the half never examined.
