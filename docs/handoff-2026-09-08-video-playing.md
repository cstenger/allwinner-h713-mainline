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

**No power cycles.** The board ran the whole session on one boot.

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
- ~~**The 60 Hz hard-lock did not reproduce.**~~ **RETRACTED — it does.** Four
  live runs were clean on a board with ~6 h uptime, then **two locks in two
  attempts on a fresh boot**, both requiring a power cycle. The second lock
  happened with `DECD_FMT=0`, i.e. the old value forced, so it is not the
  selector. What distinguishes the clean runs from the locking ones is **not
  known**. Treat live Cedrus playback with the MIPS alive as able to lock the
  SoC, and do not design experiments on the assumption that it is safe.

## Board state

Core alive (`0x0306101c = 1`), test FIT
`h713-kernel-decd-iommu-0076v3.fit` with
`initcall_blacklist=h713_afbd_platform_driver_init`,
`/root/sunxi-decd-route.ko` loaded (`auto_route=1`, `ring_writes_max=1`),
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
rmmod sunxi_decd; insmod /root/sunxi-decd-route.ko ring_writes_max=1
insmod /root/hy310-cpu-comm-next.ko
DRIVER_ROUTE=1 MODE=live DWELL=30 sh /root/decd-all-preconditions.sh
```

One `h713_disp init` per boot; never re-release a quiesced core with direct MMIO.

## Open work

- ~~No vsync-correct flipping~~ — **measured 2026-09-08, and it is already
  correct.** See "Flipping is already vsync-correct" below.
- **The DECD driver leaks `sunxi_scanout_dmabuf` exports.** One session
  accumulated **89** references. Once leaked they pin identity IOVAs and Cedrus
  allocation starts failing:
  `sun50i-iommu: iova 0x6c800000 already mapped to 0x6c800000 cannot remap` and
  `cedrus: dma alloc of size 1384448 failed`. The module cannot be unloaded to
  clear them (refcount != 0), so **only a reboot recovers**. Symptom to
  recognise: GStreamer reports *"Not enough memory to allocate source buffers"*
  while `MemFree` and `CmaFree` are both healthy and `buddyinfo` shows plenty of
  order-10 blocks — it is not memory pressure.

  **Mechanism, established 2026-09-08.** A submitted frame holds a `dma_buf`
  reference for its image and VideoInfo buffers, and is released only when a
  **later frame displaces it**. Whatever was submitted last is never displaced,
  so it stays pinned. `dec_release_file()` is a **no-op**, so a client exiting
  or being killed reclaims nothing, and `dec_frame_manager_free()` does not
  help: it drains `fmgr->ready_list` and the interlace pair but never the
  queue's four ring slots, which is exactly where displayed frames sit.
  Measured: **+2 references per `decd-client show` even on clean exit**, +1 per
  `decd-play` run. `STOP_VIDEO_STREAM` does not reclaim them, and neither does
  `rmmod sunxi_decd` — the references are orphaned, so **only a reboot
  recovers**.

  **A fix was attempted and reverted.** Draining `slots[4]` plus the interlace
  and shutdown holds from `dec_release_file()` on last close, with the source
  disabled and the ring blanked first, was implemented and tested. It failed in
  two ways and neither is superficial:

  1. **It did not fix the leak.** The drain reported "released 4 held frame(s)"
     and the refcount still climbed +2 per run (7 → 9 → 11 → 13). So
     `video_frame_put()` on a slot does not drop the underlying `dma_buf`
     references — something else in the frame/item refcount model holds them,
     and that model needs to be understood before drain points are added.
  2. **It crashed userspace.** `frame_item_release()` signals *and* `kfree`s the
     fence; calling it while the client still holds the `sync_file` fd
     reintroduces exactly the use-after-free that patch 0071 exists to fix.
     `decd-client` segfaulted.

  So a correct fix must first answer: who holds the `dma_buf` reference after
  `video_frame_put()`, and what is the fence's lifetime relative to the frame's.
  Do not add a drain until both are known.
- **`decd-play` requests VideoInfo selector 0**, which the firmware resolver maps
  to hardware format 0 = RGB888. It only works because the driver never programs
  the format byte from that selector. Selector 6 resolves to format 3 and is the
  honest value — but **changing it was tried and reverted** (`fd9ec35`,
  reverted by `6284b2c`). It is verifiably correct and has **zero** effect on
  rendering, so it carries no benefit; it was backed out to stop carrying a
  pointless change while an unexplained hard-lock is in play. If it is
  revisited, note the failed hypothesis: selector 6 is the firmware resolver's
  input, so it *might* make the firmware act on the descriptor and conflict with
  the driver's route. That is plausible and wrong — the lock reproduces with
  selector 0.
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
