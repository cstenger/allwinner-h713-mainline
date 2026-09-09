# Review request — H713 no-GPU video path, 2026-09-08

Self-contained brief for an outside reviewer. No repo access assumed. Everything
below is measured on hardware unless labelled as inference.

**Short version.** Decoded video now plays correctly on the panel with no GPU
and the display co-processor alive. Two problems that were open when this brief
was first written are now closed: a dma_buf reference leak (fixed, section 6)
and an SoC hard-lock (stopped reproducing after three missing patches were
applied, section 4/5). **The one thing we genuinely want outside eyes on is
whether the hard-lock fix is a real mechanism or a coincidence** — see
section 7, question 1.

---

## 1. The system

Allwinner **H713** SoC in a consumer projector, being brought up on mainline
Linux 6.18.38 (aarch64). Relevant blocks:

- **Cedrus / VE** (`1c0e000.video-codec`) — the video decoder. Mainline driver,
  H.264 and 8-bit HEVC bit-exact, production-hardened. Not in question here.
- **DECD** (`5600000.dec`) — an Allwinner "AFBD" display fetch engine. Reads a
  frame from DRAM and hands it to the display pipeline. Out-of-tree driver
  (`drivers/misc/sunxi_decd`) reconstructed from IDA decompilation of the
  vendor's `decd.ko`. Two MMIO regions: `afbd` at `0x05600000` (1 KiB) and
  `top` at `0x05700000` (256 B).
- **A MIPS co-processor** running vendor firmware `display.bin`, which owns the
  display *composition* block at `0x05000000` and the panel window layer. It is
  a black box we drive via a CPU_COMM mailbox and a debug shell. MIPS address =
  ARM physical + `0xB5000000`.
- **IOMMU** (`sun50i-iommu` at `0x02010000`). Master 2 is DECD.
  `0x02010030` is a per-master bypass register: bit N set = master N bypassed.
  `0x7C` = master 2 bypassed (physical addressing), `0x78` = master 2
  translating (IOVAs).
- Panel is 1280x720 @ ~60 Hz. Test content is 1280x720 NV12 at 29.97 fps.

**Goal:** decoded video on the panel without the GPU, with the MIPS firmware
alive (it owns the panel, so parking it is not a general solution).

---

## 2. What works

**Real Cedrus-decoded video renders correctly on the panel with the MIPS alive.**
Chain: Cedrus decode → zero-copy dma-buf → IOMMU translation → DECD fetch →
MIPS window layer → panel. Confirmed visually by the operator; 29.96 fps.

Three register facts had to be right, and all three were wrong for a long time:

| | wrong value | correct value |
| --- | --- | --- |
| format byte `0x05600011` | `0` = RGB888 | **`3`** = linear 8-bit NV12 |
| plane-address publish | — | **`0x0560006c`** |
| source-config commit | — | **`0x05600014`** |

**The two latches do different jobs and are not interchangeable.**
`0x05600014` commits the source *configuration* (seven geometry words + source
enable). `0x0560006c` publishes the *plane addresses* of the two-plane YUV path.

**Both latches retire on vsync.** Measured with randomised write phase: uniform
0..16.7 ms retirement, never under 50 µs, flat histogram across eighths of a
frame. This is why the whole thing was hard — shell recipes always slept 100 ms
after a commit and never noticed; kernel code issuing writes back-to-back gets
microseconds, the commit does not retire, **and the hardware silently ignores
the configuration while every register still reads back correct**.

The symptom of an unretired commit is a frame rendered **doubled side by side at
half height** (a 2-bytes-per-pixel fetch: each display row consumes two source
rows, so 720 rows end at display row 360).

**Flipping is already vsync-correct.** Because the publish latches on the frame
boundary, a ring rewrite cannot split a frame — no tearing is structurally
possible. Cadence measured during playback: 116 of 119 frames held exactly 2
vsyncs, displayed rate 29.98 fps against a 29.97 fps source.

Also established: **solid green = "fetching nothing"**, not a colour bug
(Y=U=V=0 through BT.601 clamps R and B to 0 and gives G≈135). Treat it as an
uncommitted or unpublished register.

---

## 3. Where the register state is

A working configuration, for reference:

```
0x05600010 = 0x03000313   source ctrl: enable bits 1:0 = 3, format byte = 3
0x05600020 = 0x02CF04FF   crop, minus one (1279 x 719)
0x05600024 = 0x002C004F   crop origin -- UNDECODED CONSTANT
0x05600030 = 0x02D00500   picture size 1280 x 720
0x05600040 = 0x00000500   luma pitch 1280
0x05600044 = 0x00000500   chroma pitch 1280
0x05600048 = 0x02D00500   1280 x 720
0x0560004c = 0x01680500   chroma 1280 x 360
0x05600070/74/78/7c       Y ring, four slots
0x05600084/88/8c/90       C ring, four slots  (C - Y = 0xE1000 = 1280*720)
0x05600098               VideoInfo descriptor pointer
0x0560006c               plane-address publish latch (consume-on-write)
0x05600014               source-config commit latch (consume-on-write)
```

Display-engine registers, owned by the MIPS/logo path, still set from shell:
`0x05140508 = 0x144C0000` (chroma gain) and `0x051c006c = 0x39000000` (plane
selector; `0x29000000` is the OSD/logo path).

---

## 4. RESOLVED (mechanism unproven) — the build tree was missing three patches

> **UPDATE — acted on, and it looks like the answer.** The three patches were
> applied to the build tree and the module rebuilt. Results below in this
> section. The hard-lock did not reproduce in six consecutive live runs.

The build tree that produced the running DECD module branches from a point that
predates three patches which *are* in the patch series:

| patch | state in the tree we build from |
| --- | --- |
| `0071-misc-decd-fix-release-fence-lifetime` | **ABSENT** |
| `0072-misc-decd-refuse-a-non-contiguous-dma-buf-import` | **ABSENT** |
| `0073-misc-decd-declare-the-single-mapping-dma-constraint` | **ABSENT** |
| `0094` (`ring_writes_max` test knob) | present |
| `0095` (driver route, added today) | present |

0071 exists because `frame_item_release()` does:

```c
dec_fence_signal(item->fence);
kfree(item->fence);            /* still present in our tree */
```

`FRAME_SUBMIT` hands userspace a `sync_file` wrapping that `dma_fence`, and
`sync_file_create()` holds a reference until the fd closes. So **every frame
retirement frees a fence userspace may still hold**. 0071 replaces the `kfree`
with `dma_fence_put()`.

Live playback retires ~30 frames/second. Static single-frame tests retire
almost nothing. That asymmetry matches the observed failure pattern below.

### Result of applying 0071/0072/0073

All three applied cleanly to the tree, keeping 0094 and 0095. Measured after
rebuilding and loading:

- **The hard-lock did not reproduce**: six consecutive live playback runs, core
  alive after every one, one of them operator-confirmed as playing correctly.
  Immediately before the fix, on a fresh boot, it was **two locks in two
  attempts**.
- **Fence retirement now works.** Standalone `decd-play` previously reported
  *"frame 0's release fence has not signalled in 2000 ms with 4 held"*; it now
  completes (`PLAY_COMPLETE frames=60, 29.83 fps`).
- **The client segfault is gone** — three consecutive `decd-client` runs exit 0.
- **The dma_buf leak is unchanged** at +2 per client run, as expected: these
  patches address fence lifetime and DMA constraints, not the frame-retirement
  refcount.

**The discriminating test has now been run.** Both original locks were on a
*fresh boot* (uptime ~57 s), so the warm-board runs above did not reproduce the
failing condition. After a reboot, with the patched module, live playback was
started at **uptime 47 s** and repeated twice more:

```
uptime 47 s   300 frames, 29.94 fps, core alive
uptime 88 s   preconditions pass, core alive
uptime 95 s   preconditions pass, core alive
```

Nine clean live runs in total, three of them inside the first 100 seconds of
uptime, against **two locks in two attempts** immediately before the fix, in the
same window. The failing condition has been reproduced and it no longer fails.

Remaining honest caveat: this is still absence-of-failure evidence, and the
mechanism is not proven. A dangling `dma_fence` producing a silent whole-SoC
wedge (no oops, no serial) is not an obvious failure mode, and that is one of
the questions below.

---

## 5. THE ONE REAL QUESTION — SoC hard-lock: fixed in practice, unexplained in principle

**Symptom:** the whole SoC wedges. No SSH, no serial, no console. Only a power
cycle recovers.

**When:** live Cedrus playback with the MIPS alive.

**Very likely resolved by section 4** — the missing `0071` fence fix. After
rebuilding with it, nine clean live runs including three inside the first 100
seconds of uptime, which is the window both locks occurred in. Retained here
because the *mechanism* is unproven; see the questions below.

**The confusing part at the time:** four consecutive clean live runs on a board
with ~6 hours uptime, then **two locks in two attempts** after a fresh boot.
That is now explicable if the trigger is fence-retirement traffic rather than
uptime, but it was not understood then.

Ruled out:
- **Not the VideoInfo format selector.** The second lock happened with the old
  value (`0`) forced.
- **Not obviously the 60 Hz ring rewrite**, which was the standing historical
  hypothesis. Thousands of ring writes ran clean in the good runs.

Not ruled out:
- The missing 0071 fence fix (section 4).
- Something about fresh-boot vs long-uptime state.
- Interaction between our driver programming the source and the MIPS firmware
  doing the same.

Historical context: "real Cedrus traffic + live display MIPS hard-locks the
SoC" has been a standing hazard since 2026-09-04, and experiment design has
been shaped around it. Earlier today it was declared non-reproducing on the
strength of four clean runs; **that claim has been retracted**.

---

## 6. FIXED — dma_buf reference leak

Included because the refcount model below may be relevant to section 5, and
because two attempts failed before it worked.

**Was:** `dec_release_file()` was a no-op, and a frame is released only when a
**later frame displaces it**, so whatever a client submitted last stayed pinned
after it exited or was killed. Measured **+2 references per `decd-client` run
even on clean exit**, 89 accumulated in one session. Leaked references pin
identity IOVAs; Cedrus then fails to allocate:

```
sun50i-iommu: iova 0x6c800000 already mapped to 0x6c800000 cannot remap to ...
cedrus 1c0e000.video-codec: dma alloc of size 1384448 failed
```

Userspace sees *"Not enough memory to allocate source buffers"* while `MemFree`,
`CmaFree` and `buddyinfo` are all healthy — **not** memory pressure. Neither
`STOP_VIDEO_STREAM` nor `rmmod` reclaimed them; only a reboot did.

**Now:** `patches/kernel/0096` drains on the last close. Six client runs and
three live playback runs with **zero** refcount growth, no oops, display paths
unaffected.

**The refcount model, which two attempts got wrong:**

- `dec_frame_queue_resume()` assigns **one frame to all four slots** and nets a
  single reference (`refcount_inc`, then `video_frame_put` on the progressive
  path). The slots **alias**. Putting each slot separately is a use-after-free
  on the second put — that segfaulted the client.
- `q->interlace_hold` is overwritten with the literal `(void *)1` as an **armed
  flag**, not a pointer, so it must never be put.
- The repeat path increments the refcount **once per vsync** and pushes one
  `release_fifo` entry each time, all aliasing the same object. **Fifo depth is
  the outstanding reference count and is not bounded by the four slots** —
  eleven observed. An attempt that collected into a fixed 8-entry array silently
  capped at 7, so the leak survived a "fix" that logged success.
- `q->last_released` and the global `last_frame` are each separate holders.

The tell that broke it open: `DECD drain: slots=1 fifo=7 misc=1` while
`frame_item_release` never fired — eight puts, zero retirements.

## 7. What we would like reviewed

Most of the original list is now closed. The one that matters:

**1. Is a dangling `dma_fence` a credible mechanism for a silent whole-SoC
wedge?** Rebuilding with 0071/0072/0073 stopped the lock reproducing — nine
clean live runs, three inside the first 100 s of uptime, against 2-for-2 failure
in that same window immediately before. But a use-after-free normally produces
an oops, not a silent lock of the entire chip with **no serial output at all**.

   - Which of the three would you expect to matter, and why? `0072`/`0073`
     constrain DMA imports (refuse non-contiguous, declare a single-mapping
     constraint), which intuitively feels closer to a bus-level hang than the
     fence does.
   - Is there a plausible path from "freed `dma_fence` still referenced by a
     `sync_file`" to a hardware hang rather than a kernel oops?
   - This is absence-of-failure evidence. What would make it evidence of a
     *mechanism*?

**2. Instrumentation that survives a total wedge.** We narrate to `/dev/kmsg`,
which reaches the UART live, and the lock leaves nothing. What is worth trying —
a hardware watchdog with a scratch register, SoC-level bus error/timeout
registers polled from a second core, JTAG?

**3. Sanity check on the vsync-latch conclusion** (section 2). We infer "latches
on the frame boundary" from a uniform 0–16.7 ms retirement under randomised
write phase, never under 50 µs. Is there a better test? Note a trap we hit: a
*fixed* inter-sample delay phase-locks the sampler to the panel and collapses
the distribution to a constant that looks exactly like a fixed hardware latency.

**4. Anything in section 2 that looks wrong.** The two-latch split
(`0x05600014` = source config, `0x0560006c` = plane addresses, both vsync-
latched) is reverse-engineered from behaviour, not documentation.

## 8. Method notes that may help interpret the record

- **A fixed inter-sample delay phase-locks a sampler to the panel.** A 3 ms
  sleep plus a ~13.7 ms wait sums to one frame period, so every write lands at
  the same phase and the measured spread collapses to a constant that looks
  exactly like a fixed hardware latency. Randomising the delay exposed the truth.
- **Register dumps cannot see latch ordering.** Three whole regions (`afbd`,
  `top`, and the composition page `0x05000000..0x87c`) were byte-identical
  between a working run and a broken one. The difference was purely *when* the
  commit retired.
- **Two causal claims were made and withdrawn today**: "composition is the
  cause" (it owns the displayed footprint only) and "IOMMU translation is the
  fault" (it works; the test that implicated it carried a missing commit).
- Repeated failures were caused by ad-hoc shell scripts diverging from the
  verified sequence, so there is now a harness
  (`tools/video/decd-all-preconditions.sh`) that checks ~40 preconditions and
  refuses to run a visual test unless all pass.

## 9. Current board state

MIPS core alive (`0x0306101c = 1`), DECD module built with
**0071/0072/0073 + 0094 + 0095 + 0096** loaded, `auto_route=1`,
`ring_writes_max=1`, static and live preconditions passing, no refcount growth,
logo path restored, zero oops.

Note: build trees under `build/` vary. Many predate 0071/0072/0073 — check
before trusting a DECD result.
