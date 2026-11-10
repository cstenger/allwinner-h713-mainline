# Runtime IOMMU on master 2: the flip ordering is the whole trick (2026-09-01)

**Result: moving decoded video renders on the panel through segmented IOVAs, at
27 fps, with zero IOMMU faults.** This closes the corruption investigation that
ran from 2026-08-26. It also retracts two conclusions that were recorded as
final.

Everything below is from one bench session, six runs, on a RAM-loaded
`6.18.38` kernel. Every artifact was SHA-256-verified against the recorded ones
before use.

## The rule

> Perform the master-2 `IOMMU_BYPASS 0x7c -> 0x78` transition while the DECD
> **video source is disabled** — that is, with only the inherited U-Boot logo
> route live. Once the flip is spent, enabling the video route and running
> visible playback is clean.

Operationally: run the player **directly** first (no wrapper, no
`apply_visible_route`), which spends the flip against the logo route; then run
the visible wrapper as a second session in the same boot. Patch 0075 guards the
flip with `dec->iommu_runtime_enabled` in `struct dec_device`, which persists
across processes until module unload or reboot, so the second run never flips.

## Why: the video source scans from address zero

Read on a fresh boot, modules loaded, before any submit:

```text
0x05600010  0x03000010   source DISABLED (the visible route sets 0x03000013)
0x05600020  0x043F077F   inherited 1920x1088 fallback geometry
0x05600040  0x00000780   stride 1920
0x05600070  0x00000000   source base = ZERO
0x051c006c  0x29000000   selector: logo
```

The instant `apply_visible_route` enables that source, it raster-scans **from
physical address 0** across roughly the first 2 MB. Under bypass those reads go
nowhere and harm nothing — which is exactly why the DECD route always worked on
a bypass boot. The moment translation turns on, they are L1-invalid.

Every fault observed landed inside that window, and nowhere else:

| run | configuration | fault VA |
| --- | --- | --- |
| 1 | segmented, moving, old wrapper | `0x29000` |
| 2 | segmented, moving, reordered wrapper | `0x26000` |
| 3 | segmented, frozen frame 60 | `0x81000` |
| 4 | contiguous (0074), frozen frame 60 | `0x16000` |

Page-aligned, different every run — a raster walk caught at whatever offset it
had reached. None is near the identity-mapped logo carveout (`0x6c100000`) or
DECD metadata (`0x4d941000`), whose mappings work correctly, and none is near
the frame IOVA (`0xfe000000`).

The fault always fired within microseconds of the bypass write and **before the
frame was enqueued** — `frame_item_create()` maps, then
`sun50i_iommu_set_master_translation(true)` flushes and clears the bypass bit,
then the frame is enqueued. In run 3 the IOMMU IRQ and the flip carried
timestamps 27 µs apart; in runs 1 and 2 they landed in the same printk batch.
So the frame's IOVA was never the faulting address.

### Fault register decode

```text
0x02010130  INT_ERR_ADDR_L1    the faulting VA
0x02010180  L1PG_INT     = 0x4 master 2
0x02010118  INT_ERR_ADDR(2)= 0   per-master register stays zero
0x02010184  L2PG_INT     = 0x0   no L2 fault
```

`L1PG_INT` means **L1-invalid** — no page-directory entry at all for that
megabyte, which is what "nothing in low memory is mapped" looks like.

## The two-step reproduction

Segmented FIT (`2b1581e6…`), modules loaded by path in the order
`sunxi-scanout-dmabuf`, `sunxi-decd`, `sunxi-cedrus`, all three hashes verified.

**Step 1 — nonvisible, spends the flip.** Player run directly, no wrapper:

```sh
DECD_FREEZE=1 DECD_FREEZE_AT=60 DECD_DUMP=/tmp/step1.bin \
  /root/freeze-at/decd-play-freeze-at /root/leota-720p.h264 300
```

Result: `bypass 0x7c -> 0x78`, **no page fault**, `L1PG_INT` never latched, dump
bit-exact, and the operator confirmed the logo stayed up untouched for the whole
12 seconds. `0x05600070` afterwards held `0xFDC00000` — an IOVA.

**Step 2 — visible frozen still, no flip occurs.**

```sh
ARMED=yes ALLOW_STOPPED_MIPS=yes DECD_FREEZE=1 DECD_FREEZE_AT=60 \
  DECD_DUMP=/tmp/step2.bin PLAYER=/root/freeze-at/decd-play-freeze-at \
  /root/decd-visible-sequence-fence.sh --play /root/leota-720p.h264 300
```

Result: **the frame rendered correctly and the logo returned.** Zero faults for
the boot. `pages=338 contiguous=NO breaks=1 longest-run=692KiB absent=0` — a
genuinely fragmented buffer, real measurement.

**Step 3 — moving playback, the goal.**

```sh
ARMED=yes ALLOW_STOPPED_MIPS=yes DECD_DUMP=/tmp/step3.bin \
  PLAYER=/root/freeze-at/decd-play-freeze-at \
  /root/decd-visible-sequence-fence.sh --play /root/leota-720p.h264 300
```

```text
PHYS pages=338 contiguous=NO breaks=56 longest-run=8(32KiB) absent=0
PLAY_COMPLETE frames=300 elapsed=11060ms rate=27.13fps
RETIRE_STATS fence-retired=299 unsignalled-at-exit=1 peak-held=4 cap=4 stalls=0
```

Operator: moving video rendered as expected, logo restored. Zero faults.

**`breaks=56 longest-run=32KiB` is the decisive number.** That is the most
fragmented buffer of the entire session — worse than the 31-break / 64 KiB case
that produced green corruption on a bypass kernel — and it played perfectly.

## The procedure became a driver behaviour the same day

Patch 0076 makes the ordering the driver's responsibility: park source 0 across
the transition, flip, then re-enable once the ring holds a real address. It took
three attempts, and the two failures are worth keeping because each one moved
the fault somewhere diagnostic.

| version | unpark point | result |
| --- | --- | --- |
| v1 | immediately after the flip | fault at **`0x00000000`**, 17 ms after a clean flip |
| v2 | after the enqueue, gated on the Y ring | **no fault**, but timed out and left the source parked |
| v3 | after `dec_reg_enable()`, gated on the ring | **no fault, correct picture** |

**v1** proved parking works: the fault address moved from a mid-scan value to
precisely zero, because the source was re-enabled while its base was still 0 and
simply restarted the scan from the beginning.

**v2** looked like a timing problem and was not. It polled up to 200 ms for the
ring and gave up — then a post-run read found all four Y slots holding
`0xFDC00000`. The poll was in the wrong *place*: `dec_reg_enable()` at the end of
`dec_frame_submit()` is what kicks the block into consuming the queue, and it
runs after the enqueue. No timeout would have helped. Its safety gate — warn and
leave the source parked rather than restore blind — turned what would have been
a second wedged boot into a warning line.

**v3** unparks after the kick and reports `video source unparked onto
0xfe000000 after 75 us`. The ring arms on the *first* poll iteration, confirming
v2's diagnosis exactly.

Validated as the **first DECD session of a boot**, no operator procedure:

- frozen frame 60: zero faults, operator-confirmed still, logo restored;
- moving playback: zero faults, 300 frames at 27.12 fps, 299 fence retirements,
  zero stalls, operator-confirmed animation, logo restored.

### And the wrapper should not have been showing garbage

The diagnostic wrapper enabled the video source at a fixed `sleep 0.2`, long
before any frame existed — so on a `--freeze-at` run the panel showed nearly two
seconds of the source scanning low memory. Under bypass that is merely ugly; it
is the *same* scan that faults under translation. `decd-visible-sequence.sh` now
waits for the Y ring to arm before applying the route.

With that fix the moving run needed **no park at all**: the source was already
disabled when the flip happened, so 0076 had nothing to do. That is the better
arrangement, and it makes 0076 the safety net rather than the mechanism. Both
belong in place — userspace should not enable a source with no frame behind it,
and the driver should not assume userspace got that right.

## A positive control has to be re-established after every wedge

Two runs in this session were watched against a panel whose state was unknown,
because after a fault-and-reboot nobody confirmed the logo had actually come
back. U-Boot prints `boot logo published and committed` on a black boot too, so
the log is not the control. "Source left parked" and "panel died an hour ago"
produce an identical black screen.

Confirm the logo is visible **after** booting and loading modules, immediately
before arming any visible test. It costs one question and it is the difference
between a result and an anecdote.

## What this retracts

- **"The IOMMU route is CLOSED — do not re-run it" is wrong.** The route works.
- **"One master-2 page fault wedges AFBD for the rest of the boot" is the wrong
  rule.** The fault does wedge it, but the fault is *avoidable*: flip with the
  source disabled and there is none. Do not budget one fault per boot; design
  for zero.
- **Patch 0074's contiguous Cedrus pool is not required.** Fragmented capture
  buffers display correctly through a single IOVA.
- **The banding is not a surface-reuse race.** No banding appeared in moving
  playback. It was the segmented-buffer corruption all along. Patch 0071 (the
  release-fence UAF) remains a correct and independent fix.

## Why the earlier session's results looked different

The preceding session's results were **real and are now reproduced**. Its
sequence happened to run a nonvisible test first, which spent the flip against
the logo route. The handoff recorded the results but not that precondition, so
following it literally — visible test first — could only fail. Its
"visible frozen run had no faults" is true because the flip had already been
spent in the previous run, not because the flip is inherently fault-free.

## Measurement traps found the same day

- **`absent=N` invalidates the PHYS contiguity line.** On a 0074 contiguous-pool
  build the probe printed `contiguous=yes breaks=0` from **zero** resolved pages
  (`absent=338`): reserved `no-map` memory has no `struct page` for pagemap to
  report. Any contiguity number from a 0074 build proves nothing. Segmented
  builds report `absent=0` and are real.
- **`DECD_FREEZE_AT` alone does nothing.** `decd-play.c` gates the discard on
  `freeze &&`, so a freeze run needs **both** `DECD_FREEZE=1` and
  `DECD_FREEZE_AT=N`, or you silently get a moving run instead of the control.
- **`irq_count()` sums the GIC hwirq number.** The `/proc/interrupts` line
  `330: 0 0 0 0 GICv2 142 Level decd` yields 142, so "DECD IRQ: 142 -> 741"
  really means 0 -> 599. The delta is correct; the absolute numbers are not.
- **Verify the FIT hash, not only the modules.** The two runtime FITs differ
  only by build timestamp in `uname -v` (`11:48:56` contiguous vs `11:52:01`
  segmented).

## Frame 60 is a real picture

`DECD_FREEZE_AT=60` submits decoded frame 60, SHA-256
`70bddcf8d5c05caf4c6abd0d29399b7467f47caea470c80f7d3998831379cfec`, which a host
`ffmpeg -f rawvideo -pix_fmt nv12` decode reproduces byte for byte. It is a
**brightly lit face on a black background**: Y mean 27, min 13, max 139, chroma
essentially neutral. Dark, but with an unmistakable subject — a near-black panel
is not a plausible rendering of it.

Frame 0 is the all-black one,
`3b3d249c8078333d4145f11b6af004dfe28514fdd5ea90491b5d98fb48331ab8`. Do not
confuse the two when judging a still.

## Method note

Four visible runs were spent chasing a race between the wrapper's route rewrite
and the first submit. The race did not exist. What settled it was re-running a
**known-good control** and discovering it no longer passed — which proved the
problem was in the setup, not in the theory being tested. Two free measurements
then finished the job: a host decode of frame 60 (is the target picture even
distinguishable from black?) and a single register read (`0x05600070 = 0`).

Both were available from the start. Re-run a known-good control before
diagnosing a new failure, and take the free measurement before the expensive
observation.
