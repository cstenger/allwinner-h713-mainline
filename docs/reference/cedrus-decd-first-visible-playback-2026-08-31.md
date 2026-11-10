# Cedrus dma-bufs reach DECD scanout, and the picture is corrupt

> **SUPERSEDED 2026-09-01 — the corruption is fixed.** Moving decoded video now
> renders correctly at 27.13 fps with zero IOMMU faults. The cause was as
> diagnosed here (DECD scans linearly from one base, so a physically scattered
> Cedrus buffer is unreadable), and the fix is IOMMU translation on master 2 via
> patch 0075 — flipped **while the DECD video source is still disabled**.
> A buffer with 56 physical breaks and a 32 KiB longest run played perfectly.
> Patch 0074's contiguous pool is a valid control but not required, and the
> banding was never a surface-reuse race. This document is kept as the record of
> the diagnosis. Current truth:
> [iommu-runtime-flip-ordering-2026-09-01.md](iommu-runtime-flip-ordering-2026-09-01.md).

On 2026-08-31 the reconstructed Linux stack decoded H.264 with Cedrus and
submitted the decoder-owned NV12 dma-buf FDs directly to DECD.  The frames
became visible on the projector through the already-proven DECD YUV route.  No
CPU pixel copy and no Mali render occurred.

This is an important partial result, not correct playback.  The visible output
is dominated by horizontal bands, large flat zero-chroma (green) regions and
fine vertical striping, with only occasional recognizable fragments of the
intended picture.

> **Read the retirement sections below as history, not as diagnosis.** This
> document originally attributed the corruption to premature surface reuse. That
> hypothesis has since been **tested and refuted**: fence-driven retirement was
> implemented, 299 of 300 surfaces demonstrably retire on a signalled fence, and
> the panel is no better (`test_60`). The use-after-free it found was real and is
> fixed, but it was not the cause of what is on screen. The retirement argument
> is preserved because its reasoning looks compelling and should not be
> re-derived from scratch by the next reader.

## Artifacts

- player source: `tools/video/decd-play.c`
- guarded route/restore wrapper: `tools/video/decd-visible-sequence.sh`
- input: `local/video-test/leota-720p.h264`, 1280x720 NV12 output, 300 frames at
  30000/1001 fps
- input SHA-256:
  `3e98d05c4bd0598e8fa87b9f4d5aceaaae83cece9c99e9e02b79900a780ff06a`
- player source SHA-256 **as measured here** (the five-sample build):
  `af563407ccbf30296e93c61b29ec757805a5680366827fd552030c931c1096c1`
- target binary SHA-256 **as measured here**:
  `ab5f6814c8bdc77de65b52e2485e5d6d4a32727a385b73f89d199d88142ef0f2`

> `decd-play.c` has since been rewritten for fence-driven retirement and is now
> SHA-256 `f0069e6e71eedacf8097b746cfc282ca69116656b45f7cef11a7fa6e5fc9b6d5`.
> The two hashes above are the provenance of the *recordings* below — they are
> not the build to run next. Check which one is on the board before citing a
> result either way.
- wrapper SHA-256:
  `d2af5104dd8169536b1bed2caa1dcd42b0a5c95cac6973a5cf5d82d58447d6e7`

The two operator recordings are ignored by Git under `local/` but remain in
the working tree:

```
local/lcd-photos/test_58/IMG_0746.MOV
  sha256 58d64ab144dc60fb84838061c6343a38dcd7a0ecdd3f90c3558eb1e0caabf676
local/lcd-photos/test_59/IMG_0747.MOV
  sha256 4d6339190b51e0d9fe820d4b72543a4a6670c8482b3f5843fc5e893ce09da8a3
local/lcd-photos/test_60/IMG_0748.mov      <- fence-driven retirement, still corrupt
```

## Player contract

`decd-play` builds this target-side pipeline:

```
filesrc ! h264parse ! v4l2slh264dec ! video/x-raw,format=NV12 ! appsink
```

It deliberately rejects every silent fallback that would weaken the result:

- not exactly one `GstMemory`;
- not dma-buf backed;
- missing `GstVideoMeta`;
- not NV12 or not 1280x720;
- non-zero `GstMemory` offset;
- stride other than 1280 for both planes;
- chroma offset other than `1280 * 720 = 921600`;
- allocation smaller than the complete 1,382,400-byte NV12 image;
- missing DECD release-fence FD.

Only the 32 KiB VideoInfo allocation is exported from the fixed scanout
carveout at `0x6c8f0000`.  The Cedrus dma-buf FD itself is passed unchanged in
the stock 112-byte frame descriptor, format candidate 6.  The driver imports
that FD and derives C from Y plus one luma plane.  VideoInfo uses the previously
confirmed canonical 1920x1080 coordinate space and format selector zero.

The player does not touch shared route registers.  `decd-visible-sequence.sh`
owns the `ARMED=yes` gate, exclusive-owner DT checks, register snapshots,
active route and trap-based logo restoration.  Its `--play` mode can explicitly
run with the display MIPS parked only when `ALLOW_STOPPED_MIPS=yes` is also set.

## Nonvisual validation with the MIPS parked

The first full preflight completed:

```
decoded 1280x720 NV12: one dma-buf fd=13, stride=1280
chroma-offset=921600 size=1382400
VideoInfo: 1280x720, fps=29.970, format selector=0
PM_HINT on ok
PLAY_COMPLETE frames=300 elapsed=10017ms rate=29.95fps
DECD IRQ 142 -> 743
selector 0x29000000 -> 0x29000000
```

The inherited source control and geometry also stayed unchanged while the logo
remained selected.  A separate 90-frame trace completed at 29.95 fps and
observed many real Cedrus address pairs in the DECD ring.  Normal Y/C pairs
differed by exactly `0xE1000`, the 1280x720 luma-plane size.  Sampling Y and C
as separate MMIO reads occasionally caught a ring transition between the two
reads; those cross-pairs are observation races, not buffer layouts.

This proves zero-copy dma-buf import, DECD queueing and cadence independently of
the later visual corruption.

## Live-MIPS hard lock is reproducible with Cedrus traffic

A warm reboot to U-Boot retained the logo but left
`0x0306101c = 0`.  The first guarded visible attempt correctly refused without
changing the screen.  U-Boot was then run through the proven live sequence:

```
h713_disp init 0x34
md.l 0x0306101c 1        # 00000001
ext4load mmc 1:1a 0x50000000 /root/h713-kernel-decd-test.fit
bootm 0x50000000
```

Linux still read MIPS status one.  A nominally one-second, 30-frame nonvisual
Cedrus/DECD preflight printed its decoded layout, VideoInfo and `PM_HINT on`,
but never printed `PLAY_COMPLETE`.  Both SSH and serial became unresponsive;
the hardware watchdog did not recover the machine.  A physical power cycle was
required.

Therefore do not combine live display MIPS with real Cedrus+DECD playback.
Static carveout frames happened to survive that state in earlier tests, but
real decoder/IOMMU traffic reproduces the old whole-SoC lockup hazard.

The stable ordering is the normal U-Boot `auto` display path, which starts the
firmware, publishes the logo, then explicitly quiesces the MIPS.  At the prompt
`0x0306101c` reads zero.  Boot the DECD-exclusive FIT directly without another
`h713_disp init`.

## Visible results

With MIPS stopped, the Linux DECD IRQ handler owns the four-slot Y/C register
ring.  This is visible in `dec_sync_frame_to_hardware()` and does not require
firmware execution.

The first two-second run completed 60/60 submits at 29.74 fps; DECD IRQ advanced
142 to 263 and the wrapper restored the logo.  The operator reported a mixture
of good and bad frames.  An identical recorded repeat completed at 29.95 fps,
IRQ 7178 to 7304.  `test_58` shows horizontal green/grey/purple bands, with one
brief recognizable portion of the intended face.  Geometry covers the panel
and recognizable decoded content is present.

The initial player closed the returned fence and unreffed each `GstSample`
immediately after `FRAME_SUBMIT`.  That returns a V4L2 capture surface to Cedrus
while DECD may still be scanning it.  The banded result is the expected symptom
of decode and scanout sharing a surface without retirement synchronization.

An eight-sample retention ring was tried because DECD has four hardware slots.
It starved the Cedrus capture pool: the player stopped producing frames and
remained blocked, while the board, logo and SSH stayed healthy.  PID 794 was
terminated and the selector remained `0x29000000`.

A five-sample ring left enough capture surfaces.  Its nonvisual preflight
completed 90/90 frames in 3005 ms at 29.95 fps, IRQ 41311 to 41498.  The next
visible run completed 60/60 in 2006 ms at 29.91 fps, IRQ 48046 to 48173, and
restored the logo.  `test_59`, however, still shows severe horizontal
mixed-frame bands.  It contains more recognizable face regions than `test_58`,
but the mitigation is not a fix.

## The release fence: diagnosis, and the fix that is now written

**Status: the fence works, and it does NOT fix the picture.** The kernel change
is `patches/kernel/0071-misc-decd-fix-release-fence-lifetime.patch` and
`decd-play.c` now retires by fence: 299 of 300 surfaces released on a signalled
fence, zero stalls, measured on hardware. The visual run was then done and the
panel is **no better than `test_58`/`test_59`** (recording: `test_60`).

**Therefore premature surface reuse was not the cause of the corruption.** The
reasoning in this document that led from the bands to the fence lifetime was
sound about the *bug* — the use-after-free was real and is fixed — but wrong
about the *symptom*. Do not re-derive it. The fix is still worth keeping: it
removes a genuine UAF and it retires the retention heuristic (see the cap sweep),
but the picture problem is elsewhere and is now better bounded, because timing on
the consumer side has been eliminated by experiment rather than by argument.

The reconstructed kernel fence lifetime is unsafe:

```
frame_item_release()
    dec_fence_signal(item->fence);
    kfree(item->fence);
```

`dec_fence_fd_create()` wraps the same `dma_fence` in a `sync_file`, which owns
a fence reference until its FD is closed.  Directly freeing the object while
that reference exists is a use-after-free.  The current player closes the FD
immediately, which avoids exercising the dangling sync-file reference but also
throws away the authoritative retirement signal.

The correct kernel ownership is to signal and then drop the frame item's fence
reference with `dma_fence_put(&item->fence->base)`.  The fence object's existing
`.release` callback should be the only place that frees it.  Audit allocation
and error paths at the same time.

### The fence signals at the right moment, which is why this is worth fixing

Verified by reading patch `0013-misc-add-sunxi-decd.patch`, not on hardware.  It
matters because a fence that signals at submit time would be useless as a
retirement signal and the plan below would be wasted work.

`frame_item_create()` sets the item refcount to 1.  `dec_frame_submit()` then
does `refcount_inc()` per enqueue and calls `frame_item_release(item)` right
after creating the fence FD, so that call drops only the *submitter's*
reference; the queue still holds one.  The last reference is dropped from the
display side: `dec_frame_queue_enqueue()` installs the new item in all four
slots and defer-releases the previous `slots[3]`, `dec_frame_defer_release()`
parks one frame in `q->last_released` and pushes the one before it into
`q->release_fifo`, and `dec_vsync_process()` → `dec_frame_recycle()` drains that
into `release_work`, which runs `video_frame_put()` → `frame_item_release()`.

So the fence signals once the frame has been displaced from the display slots
and has cleared one further deferral plus a workqueue hop — conservatively late
rather than early, which is exactly the property a retirement signal needs.
Fixing the lifetime therefore yields a usable signal, not just a plugged
use-after-free.

Two things to check while making the change, both visible in the same code and
neither yet measured.  `dec_fence_alloc()` returns `NULL` on allocation failure
and the caller does not test it, so `dec_fence_fd_create()` would dereference
it.  And the fence is allocated only `if (dec->fence_ctx)`, so a player must
still handle a submit that returns no fence rather than assuming one.

### What patch 0071 changes

- `frame_item_release()` drops the item's reference with
  `dma_fence_put(&item->fence->base)`; `dec_fence_ops.release()` becomes the
  only thing that frees the fence.
- The fence context is reference-counted, one reference per live fence.  This
  matters only *because* of the first change: a fence can now outlive
  `dec_exit()`, and `ctx->lock` is that fence's lock
  (`dma_fence_init(&df->base, ..., &ctx->lock, ...)`).  A `sync_file` FD does not
  pin this module, so `rmmod` with an outstanding fence would otherwise free a
  live fence's spinlock — and this module is unloaded constantly during
  bring-up.
- `dec_frame_submit()` no longer passes a possibly-NULL `item->fence` to
  `dec_fence_fd_create()`, which dereferenced it; `dec_fence_fd_create()` also
  rejects NULL itself.

It applies cleanly at the end of the series (verified against 0013/0033/0034/
0035/0067) and the module builds with no warnings under `ARCH=arm64 LLVM=1`.

### What `decd-play` does now

The five-sample ring is gone.  Each submitted `GstSample` is held with its
fence FD in a submission-order queue; a non-blocking `poll()` sweep at the top
of every iteration retires from the head as fences signal, so the common case
never blocks decode.  A surface is unreffed and its FD closed only after the
fence signals.

The hold is capped (`DECD_MAX_PENDING`, default 4 — DECD's hardware ring depth)
and the cap must stay below the decoder's capture-pool size, because **the wait
is circular by construction**: DECD retires a frame only when a *later* frame
displaces it from the slots, so a held surface cannot be released without
submitting a new one.  That is the real shape of the eight-sample starvation —
not simple exhaustion, but every free capture buffer held pending a fence that
needs a free capture buffer to signal.  When the cap is reached the player
blocks on the oldest fence for a bounded 2 s and then **fails loudly** naming
the stalled frame, rather than degrading to surface reuse, which is the failure
mode that produced the bands in the first place.

Draining at EOS is bounded for the same reason: the last submissions have
nothing behind them to displace them, so their fences will not signal.  After
1 s the remainder is released unconditionally — the pipeline is stopping and
nothing will reuse those surfaces.

New output line, which is the evidence to read first on the next run:

```
RETIRE_STATS fence-retired=N unsignalled-at-exit=N peak-held=N cap=N stalls=N
```

`stalls=0` with `fence-retired` near the frame count means retirement kept up
without ever blocking the decoder.

### How to test it

1. Rebuild: the kernel FIT via `build/build.sh kernel` (0071 is in `series`, so
   the input digest changes and a fresh tree is built), plus the DECD-exclusive
   experiment patch as before; rebuild `decd-play` on the board with
   `tools/rootfs/verify-video-tooling.sh`.
2. Boot the DECD-exclusive FIT with the **display MIPS parked** — normal U-Boot
   `auto`, which publishes the logo then quiesces the MIPS
   (`0x0306101c = 0`), then `bootm` without another `h713_disp init`.
3. Nonvisual 300 frames first, and read `RETIRE_STATS` before anything else.
4. Only then a freshly announced two-second visual run, and inspect the
   recording against `test_58`/`test_59`.

### Measured on hardware

Board booted from RAM over YMODEM (nothing flashed): kernel
`h713-kernel-decd-fence.fit`, SHA-256
`fe5b6e503104adf07c20b637c5aae8eb8f85aabece202c2f4345719d36592cf0`, series +
0071 + the out-of-series 0068, `Linux 6.18.38 #1 SMP Mon Aug 31 21:57:06 PDT
2026`.  MIPS parked (`0x0306101c = 0`) throughout; no `h713_disp init`.

The board's `/lib/modules` predates this build and there is no
`CONFIG_MODVERSIONS`, so a stale `sunxi-decd.ko` would have loaded silently and
the run would have measured the *old* code.  Guarded by booting with
`modprobe.blacklist=sunxi_decd,sunxi_cedrus,sunxi_scanout_dmabuf` and
`insmod`-ing the three modules by explicit path, each SHA-256-verified against
the host build:

```
3368821d401a8e4521665f7fc322f58edfcd7a1b0b84aaa765ff2797a2168274  sunxi-decd.ko
fae727a5a1348016a766b29b1e9d73a63ba1a645b988b610519ec69d287e1d82  sunxi-cedrus.ko
280e5460577a4105d52c4c2d1b07a3ea012006f80bf8730ecec1a1bef0865f49  sunxi-scanout-dmabuf.ko
f0069e6e71eedacf8097b746cfc282ca69116656b45f7cef11a7fa6e5fc9b6d5  decd-play.c
```

300 nonvisual frames:

```
PLAY_COMPLETE frames=300 elapsed=11047ms rate=27.16fps
RETIRE_STATS fence-retired=299 unsignalled-at-exit=1 peak-held=4 cap=4 stalls=0
DECD IRQ 331: 7272 -> 7939        667 over 11.0 s = 60.4 Hz, the panel vsync
```

**299 of 300 surfaces were released on a signalled fence.** That is the result:
the returned fence is now a working retirement signal. `unsignalled-at-exit=1`
is the predicted tail — the last submission has nothing behind it to displace
it. `stalls=0` means retirement never blocked the decoder.

The four registers the visible route would touch were byte-identical before and
after (`0x05600010 = 0x03000010`, `0x05600140 = 0x03001901`,
`0x051c006c = 0x29000000`, `0x05140508 = 0x04000000`), confirming the nonvisual
path writes no shared display state.  `0x05600070` moved between two Cedrus CMA
addresses, so real decoder buffers went through the ring.

### The cap sweep, which retires the retention heuristic for good

| cap | elapsed | rate | peak-held | stalls |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 16089 ms | 18.65 fps | 2 | 298 |
| 4 | 11058 ms | 27.13 fps | 4 | 0 |
| 6 | 11056 ms | 27.13 fps | **4** | 0 |
| 8 | 11061 ms | 27.12 fps | **4** | 0 |

**`peak-held` saturates at 4 no matter how high the cap goes.** The hold
self-regulates to DECD's four-slot ring depth, because a fence signals as soon
as the hardware is actually finished. Two consequences:

- **`cap=8` no longer starves the capture pool.** The old build's
  eight-sample failure was a consequence of holding surfaces past the point
  hardware needed them; with fences it never reaches eight. The retention
  heuristic is not just replaced, it is unnecessary.
- **`cap=2` throttles** — 298 stalls, 18.65 fps — which is the same mechanism
  seen from the other side: hold fewer than the ring depth and the decoder waits
  on hardware. It confirms the circular-wait model rather than assuming it.

The cap is therefore a safety rail, not a tuning knob, and 4 is not a lucky
number — it is the hardware's.

**One honest gap: 27.16 fps against the 29.95 fps the five-sample build
reported**, about 1.0 s over 300 frames. The sweep rules out the hold depth
(cap 4/6/8 agree to within 5 ms). It is not attributed, and the old figure was
taken on a different kernel build, so the two are not strictly comparable. All
300 frames complete with zero stalls either way. Worth one measurement, not a
blocker.

### The visual run, and what it eliminated

Run with the route applied and latched (commit consumed, verified by the
wrapper), 60 frames:

```
PLAY_COMPLETE frames=60 elapsed=3043ms rate=19.71fps
RETIRE_STATS fence-retired=59 unsignalled-at-exit=1 peak-held=4 cap=4 stalls=0
DECD IRQ: 51215 -> 51404
restore state: ctrl=0x03000010 ready=0x00000000 gain=0x04000000 selector=0x29000000
```

Operator: no better than before. Recording `local/lcd-photos/test_60/IMG_0748.mov`,
SHA-256 `2bc832f5fcc9ed01c2255bf7f835a5b141a25fda5eb9a75817c931de89b4e1d7`.

**Eliminated: premature surface reuse.** 59 of 60 surfaces were released only
after DECD signalled it was done with them, and the picture is unchanged.

What the recording actually shows, as description rather than diagnosis:
horizontal bands of flat lime green (the zero-chroma colour this investigation
has seen before), a fine vertical stripe texture over much of the frame, a
lavender/magenta cast, and occasional recognizable fragments — one frame carries
a clear face. It is **not** two coherent pictures interleaved, which is what
frame mixing would look like, and that is consistent with retirement having been
the wrong hypothesis.

### Next: freeze one decoder buffer

The sharpest remaining question is not about timing at all. A static frame from
the **scanout carveout** displays perfectly, and a Cedrus buffer does not, so the
one variable never isolated is **where the buffer came from**.

`DECD_FREEZE=1` decodes exactly one frame, keeps the sample, and resubmits that
same dma-buf at ~30 fps. Nothing is decoding, nothing is recycled, the buffer is
complete and quiescent:

- still corrupt ⇒ timing is entirely out of the picture, and the fault is in how
  DECD *reads a decoder-produced buffer* — layout, contiguity, tiling, or the
  address it is given;
- clean and stable ⇒ the fault is timing after all, but on the producer side,
  and the fence is the wrong signal rather than a broken one.

Either answer is worth an observation, which is the property the earlier
experiments in this document lacked. Staged on the board:

```
/root/decd-play-fence                 built on-board from decd-play.c 6ddab920…
/root/decd-visible-sequence-fence.sh  sha256 32b99db469…
```

```
ARMED=yes ALLOW_STOPPED_MIPS=yes DECD_FREEZE=1 PLAYER=/root/decd-play-fence \
  /root/decd-visible-sequence-fence.sh --play /root/leota-720p.h264 90
```

### Freeze result: STEADY and corrupt — timing is eliminated

```
FREEZE: holding frame 0, resubmitting 89 times
PLAY_COMPLETE frames=90 elapsed=2985ms rate=30.15fps
RETIRE_STATS fence-retired=1 unsignalled-at-exit=0 peak-held=1 cap=4 stalls=0
DECD IRQ: 152802 -> 152987
```

The operator reports a **steady** corrupt image for the full ~3 s (photographed).
One complete, quiescent buffer at one fixed address, resubmitted 89 times, and
the panel does not change.

**This eliminates timing entirely** — not retirement (already eliminated), not
producer-side readiness, not frame mixing, and not a race inside the fetch,
because DECD reads the same wrong thing deterministically on every pass. The
fault is in **what DECD reads from a Cedrus buffer**: its content, its layout, or
the address DECD is given.

What the photograph shows, as description:

- the entire frame is **green — zero chroma everywhere**, despite the calibrated
  gain `0x144C0000` being applied and verified;
- the top ~55% is dense granular/blocky horizontal banding that looks like
  *data*, not picture;
- the bottom ~40% is flat featureless teal with no detail at all, and the
  transition between the two regions is sharp.

A partially-meaningful top and a flat bottom is the shape of a buffer whose
beginning holds something and whose remainder holds a constant — but that is an
impression from a projected photograph and must not be promoted to a finding.

### Next, and it costs zero operator observations

The question is now entirely about bytes, so stop spending visual runs on it.
Both of these are answerable at the console:

1. **Dump the decoded dma-buf from the CPU** — `mmap` the same buffer the player
   submits, write it to a file, and compare against a software decode of the same
   frame of `leota-720p.h264`. This answers "is the decoder's output actually
   correct linear NV12?" with a checksum instead of an opinion. Note that Cedrus
   natively emits **NV12_32L32 (32x32 tiled)** and only produces linear when the
   caps force `NV12`; blocky repeating texture is what tiled data looks like when
   scanned linearly, so this is a live hypothesis rather than a remote one.
2. **Copy those same bytes into the scanout carveout and display that.** It is a
   single-variable swap — identical content, different buffer provenance —
   against a carveout path already proven to display correctly. Corrupt ⇒ the
   decoded bytes are wrong. Clean ⇒ the bytes are fine and the fault is in how
   DECD reaches a Cedrus buffer (address, contiguity, or IOMMU domain).

Do (1) first: it needs no operator and no display state at all.

### Result: the decoder's bytes are BIT-EXACT. Tiling is refuted.

`DECD_DUMP=/root/board-f0.nv12` mmaps the *same dma-buf FD that is passed to
DECD*, brackets the read in `DMA_BUF_IOCTL_SYNC`, and writes all 1,382,400
bytes. Against the host software decode built with this project's existing
convention (`ffmpeg -i … -f rawvideo -pix_fmt nv12`):

```
board  3b3d249c8078333d4145f11b6af004dfe28514fdd5ea90491b5d98fb48331ab8
host   3b3d249c8078333d4145f11b6af004dfe28514fdd5ea90491b5d98fb48331ab8
```

**Identical.** The decoder's output buffer holds correct, linear, bit-exact
NV12. So:

- **the tiling hypothesis is refuted** — the buffer is genuinely linear, not
  NV12_32L32 mislabelled;
- **the content is not the problem**, and neither is the layout;
- the CPU can read the right pixels through the very FD DECD is handed.

Combined with the frozen-buffer result eliminating timing, this leaves exactly
one place for the fault: **how DECD reaches that memory.** Content, layout and
timing are all now excluded by measurement.

### The remaining candidate, and how to test it for free

The VE is attached to the real IOMMU (patch 0042). With an IOMMU in the path a
buffer can be a *contiguous IOVA over scattered physical pages*: Cedrus writes
through its translation and is correct, the CPU maps it page-by-page and is
correct, but DECD programs **one base address plus a stride** and walks physical
memory linearly. If DECD is on bypass (ours reads `0x7C`) or in a different
domain, it reads the first run correctly and then whatever else is resident —
which is the shape of the photograph: a partly-meaningful top, then unrelated
content and flat regions.

This is testable with no operator and no display state, from the player that
already maps the buffer:

1. walk `/proc/self/pagemap` over the CPU mapping and report whether the 338
   pages are **physically contiguous**;
2. compare page 0's physical address against the DMA address DECD actually
   programs into `0x05600070`.

Scattered ⇒ a single-base-plus-stride fetch cannot work by construction, and the
fix is a domain/mapping change rather than anything in the frame path. Contiguous
but with a different address ⇒ DECD is being handed an IOVA it cannot translate.
Patches 0069 (`decd attach to iommu master 2`) and 0070 (`identity-map the
adopted scanout for master 2`) already exist for exactly this area.

## ROOT CAUSE: the decoder's buffer is not physically contiguous

```
PHYS pages=338 first=0x46f7a000 contiguous=NO breaks=31 longest-run=16(64KiB) absent=0
0x05600070 = 0x46F7A000
```

Two facts, and together they are the whole answer:

1. Cedrus's buffer is **338 pages with 31 breaks**. The longest contiguous run
   is **16 pages — 64 KiB**.
2. The address DECD is programmed with is **exactly the first page**. So DECD is
   *not* being handed a wrong or untranslatable address. It starts in the right
   place.

`dec_dma_map()` keeps `sg_dma_address(sgt->sgl)` and discards the rest of the
scatterlist, and the hardware then scans linearly from that base. So DECD reads:

- the first **64 KiB** correctly — `65536 / 1280` = **51 of 720 luma lines**;
- then unrelated physical memory for the remaining ~93% of the frame;
- and chroma from `y + 0xE1000` = `0x4705B000`, which is 924 KiB past the start
  and therefore never in the buffer at all.

Every observation now has one mechanism:

| observation | explanation |
| --- | --- |
| bytes bit-exact via CPU | the CPU maps page-by-page; every page is correct |
| static **carveout** frames perfect | one segment spanning the whole buffer |
| corruption **steady** under freeze | physical layout is deterministic |
| whole frame **green** | chroma base is outside the buffer, reading mostly zeros |
| **banded** structure | mean run ≈ 10.6 pages ≈ 34 lines, so ~20 bands |
| bands *look like data* | the intervening physical pages hold other live allocations |

It also retrospectively explains an 08-28 stock-diff observation that was
recorded and never accounted for: **stock runs this block with the IOMMU
translating, not bypassed.** That was tested as a cause of the *black* screen and
correctly rejected — but it is exactly what lets stock's DECD scan a scattered
decoder buffer at all. The note was right; only its significance was missed.

### What to do about it

`patches/kernel/0072-misc-decd-refuse-a-non-contiguous-dma-buf-import.patch`
turns the silent corruption into a refusal that names the segment count and
sizes. It is a **guard, not a fix**: contiguous importers (the carveout, CMA) map
as a single segment and are unaffected.

The fix is to let DECD reach a scattered buffer, and the hardware already
supports it — **attach DECD to the IOMMU** so the import resolves to a
contiguous IOVA, which is what stock does. `patches/kernel/0069-EXPERIMENT-decd-attach-to-iommu-master-2.patch`
was written for this before there was evidence to justify it. There now is.

Note the failure mode this leaves if 0069 is applied naively: the VE and DECD
must agree on the domain, and the memory note that **the VE needs both master
ports (0 and 1) or it silently decodes corrupt** is a warning that this block's
IOMMU wiring has bitten before.

## The IOMMU run: what is already known, and what is actually new

0069 and 0070 have both been on hardware before, and re-reading those results
first changed the design of this run.

- **0069 alone is confounded.** Master 2 is the display's own fetch path, so
  translating it faults U-Boot's adopted scanout at attach
  (`Page fault for 0x6c332000 (master 2, rd)`) and the logo goes black. The
  black carried no information: a positive control showed a channel fetching a
  valid mapped buffer still rendered nothing, so **one fault wedges the AFBD
  fetch engine for the rest of the boot**.
- **0070 fixes that** with an `IOMMU_RESV_DIRECT` identity map for the
  `0x6c100000` carveout, plus a genuine `sun50i-iommu` bug fix (the driver
  cannot map before attach; `domain_alloc_paging()` now binds the instance).
  With it the board boots translating, zero faults, logo intact.
- On that boot DECD held a frame at IOVA `0xFFE00000` with C at `0xFFEE1000`,
  60 IRQ/s, zero faults. **Translation demonstrably works and DECD is happy
  behind it.**

So the IOMMU path itself is not the new thing. Two things are:

1. Those runs all used **carveout** frames, which are contiguous anyway. Whether
   a **scattered Cedrus buffer** resolves to a single contiguous IOVA for DECD
   has never been tested — and that is exactly the property the root cause
   turns on. Patch 0072 makes it self-verifying: if the import is still
   segmented it is refused by name, and if it is not, the guard is silent.
2. Those runs predate the 08-31 route. The 0070 boot ended black with
   `0x05600010 = 0x03000010` — source 0 never enabled — and concluded the video
   source was the open question. **It is no longer open**: the enable, geometry,
   chroma gain and plane-1 selector are all known and proven.

**Operational rule carried into the run: budget one page fault per boot and make
the risky step last.** The chroma read is safe by construction here — `y +
0xE1000` = 921600 sits inside the 1,382,400-byte mapping — unlike the earlier
fault where an OSD control ran one page past the buffer end.

Built as `h713-kernel-decd-iommu.fit`, SHA-256
`bb6c93564961f5025f78a1af5ad9a7bc01f48607338ed9cd7512c384ee2823fb`, series +
0071 + 0072 + out-of-series 0068/0069/0070. The DTB confirms
`iommus = <&iommu 2 1>` and both memory regions on `dec@5600000`.

### Result: the IOMMU makes the scattered buffer contiguous. Guard silent.

Boot is clean — `platform 5600000.dec: Adding to iommu group 0`, **the same
group as `1c0e000.video-codec`**, so DECD and the VE share a domain — with zero
page faults through boot, module load and the run.

```
PHYS pages=338 first=0x40dbc000 contiguous=NO breaks=2 longest-run=142(568KiB)
0x05600070 = 0xFDC00000     Y
0x05600084 = 0xFDCE1000     C, delta 0xE1000 = one 1280x720 luma plane
page faults / guard refusals = 0
```

The buffer is **still physically scattered**, but DECD is now programmed with an
**IOVA**, and **patch 0072 stayed silent**. That silence is the check: 0072
refuses any import with `nents != 1` or a short first segment, so the IOMMU has
mapped those scattered pages into a **single contiguous IOVA covering the whole
1,382,400-byte buffer**. Single-base-plus-stride now spans the entire frame
instead of 64 KiB of it.

The dumped frame is unchanged and still bit-exact
(`3b3d249c…`), so the buffer contents were never in question and are not now.

This is the mechanism fixed. It is **not yet a visual confirmation** — that
needs an operator, and the sharpest comparison available is a frozen frame
against the corrupt frozen frame photographed on the previous boot.

### Coalescing was luck until the device declared its constraint

The single-IOVA result above did **not** reproduce. Minutes later, on the same
boot, the same import came back as:

```
dma-buf import is not contiguous: 14 segment(s), first 20480 of 1384448 bytes
```

`dec` never called `dma_set_max_seg_size()`, so the DMA core applied its **64 KiB
default** and stopped coalescing there; whether the import collapsed to one
segment was down to how fragmented physical memory happened to be. Adding

```c
dma_set_max_seg_size(dev, UINT_MAX);
```

to `dec_init()` makes it deterministic: **five consecutive runs, zero guard
refusals**, IOVAs stepping cleanly (`0xFDC00000`, `0xFDA00000`, `0xFD800000`, …),
and throughput back to ~29.8 fps — the ~1 s deficit over 300 frames that could
not be attributed earlier was the fragmented mapping all along.

Without patch 0072 this would have been recorded as "the IOMMU fixes it" on the
strength of the first run. The guard is what caught it.

### And with a correct contiguous mapping, the panel goes BLACK

Frozen frame, route applied and latched, logo restored afterwards:

```
PLAY_COMPLETE frames=300 elapsed=10039ms rate=29.88fps
DECD IRQ: 61129 -> 61735          page faults: 0
```

**Operator: fully black.** The control that makes this admissible was run —
**the boot logo returns after restore**, and there were zero page faults, so the
AFBD fetch engine is healthy. This is not the wedged-engine trap that made the
0069 boot's black meaningless.

Black is a *change*, and an informative one. With a fragmented mapping DECD read
real DRAM and produced visible garbage; with a correct IOVA it produces nothing.
Reading an address that resolves to no memory returns zeros, and `Y=0, CbCr=0`
clamps to black. That is the signature of a fetch that is **not translating** —
it is taking `0xFDC00000` as a physical address, far outside this board's 1 GiB.

### The vendor master map, and a tested 0069/0070 negative

From `docs/iommu-port.md`, the stock DTB:

| device | master | vendor setting |
| --- | --- | --- |
| `ve@1c0e000` | 0 | `<&mmu_aw 0 1>` translated |
| `ve1@1c0e000` | 1 | `<&mmu_aw 1 1>` translated |
| `ge2d`, **`dec@5600000`** | **2** | **`<&mmu_aw 2 0>` — BYPASS** |
| `tvdisp@5000000` | 3 | `<&mmu_aw 3 1>` translated |
| `tvcap` / `av1` / `audbrg` | 4,5,6 | translated |

Live register on our 0069/0070 boot: `IOMMU_BYPASS (0x02010030) = 0x78`, so
masters 0–2 translate and 3–6 bypass. The vendor DT table describes its initial
state, not necessarily playback: the reverse engineering in 0069 found HWC's
`/dev/ge2d` ioctl `0x4681` calling `sunxi_enable_device_iommu(2, 1)` at playback
resume. Patch 0069 therefore attempts a real vendor operation, but performs it
as an early Linux device attachment rather than at the vendor's runtime boundary.

`tvdisp@5000000` — master 3, the composition block the firmware addresses most —
was the obvious candidate for a separate pixel-fetch port. **Tested and
refuted:** clearing bypass bit 3 (`0x78` → `0x70`) so master 3 translates, with a
10-second frozen frame, left the panel **black**, zero page faults, register
restored. Master 3 is not the pixel path.

### Where that leaves it

The narrow result is that the early-attach 0069/0070 configuration does not
work with this adopted-display route. It does **not** rule out IOMMU generally
or prove that stock uses physically contiguous decoder buffers. A faithful
future IOMMU test must start master 2 bypassed and reproduce the vendor's runtime
transition after mappings and Linux-owned display state are established.

The next experiment was defined to isolate provenance completely with no DT
change: copy a **decoded** frame into the scanout carveout and display it on a
bypass boot — same bytes, contiguous and physical. That experiment is now
complete and positive; see the 2026-09-01 continuation below. The remaining
bypass work is to make Cedrus allocate physically contiguous CAPTURE buffers,
with 0069/0070 excluded from that build.

## Current board and repository state

At handoff the board runs the DECD-exclusive 6.18.38 test FIT with the display
MIPS stopped, `/dev/decd` and `/dev/video0` present, and the boot logo restored.
The serial port is free.  `/root/decd-play` is the five-sample-retention build
whose binary hash is recorded above.  Persistent U-Boot `bootdelay` is `-1`, so
the next reboot stops at the prompt.  Do not run `h713_disp init 0x34` for the
next Cedrus test.

The normal production kernel has no `/dev/decd` because KMS owns the AFBD
window.  Returning to it requires a reboot and normal FIT boot; no persistent
boot setting needs repair.

## 2026-09-01 continuation: decoded-frame carveout control passes

The proposed provenance experiment is complete and positive. The first bypass
run copied decoded frame 0 into the carveout and displayed black for ten
seconds, with the logo restored afterwards. Host software decode then showed
that this was expected content rather than a route failure:

```
3b3d249c8078333d4145f11b6af004dfe28514fdd5ea90491b5d98fb48331ab8  frame-0 NV12
signalstats: YAVG=16.0002 UAVG=128 VAVG=128
```

Frame 0 of `leota-720p.h264` is effectively black and must not be used as the
visual positive control.

`tools/video/decd-play.c` gained `DECD_FREEZE_AT=N`: in freeze mode it discards
decoded frames `0..N-1` without submitting them, then freezes frame N. Source
SHA-256 is
`dd359d9c42329e953ec86a108a210037acf64d0b950e895b2e8f186b1f03525c`;
the matching target binary `/root/freeze-at/decd-play-freeze-at` is
`321c34009418589ae7c4205549e4a71af0d41b6788a5706500bf1995b9300dbd`.

A nonvisual dump first established the exact target content. Board-decoded frame
60 and the host software reference are byte-identical:

```
70bddcf8d5c05caf4c6abd0d29399b7467f47caea470c80f7d3998831379cfec  /root/leota-f60-board.nv12
70bddcf8d5c05caf4c6abd0d29399b7467f47caea470c80f7d3998831379cfec  host reference NV12
```

It is a visibly nonblack close-up face. An attempted replacement one-frame H.264
fixture was separately rejected because Cedrus did not decode it to its host
reference; it was never shown and carries no display evidence.

After the operator confirmed readiness, the decisive run was:

```
ARMED=yes ALLOW_STOPPED_MIPS=yes \
DECD_CARVEOUT=1 DECD_FREEZE=1 DECD_FREEZE_AT=60 \
PLAYER=/root/freeze-at/decd-play-freeze-at \
  /root/decd-visible-sequence-fence.sh --play /root/leota-720p.h264 300
```

It discarded 60 decoded frames without submission, copied the 1,382,400 bytes
of frame 60 to physical `0x6c500000`, and held that one buffer for 300
submissions:

```
FREEZE: holding decoded frame 60, resubmitting 299 times
PLAY_COMPLETE frames=300 elapsed=11966ms rate=25.07fps
RETIRE_STATS fence-retired=1 unsignalled-at-exit=0 peak-held=1 cap=4 stalls=0
DECD IRQ: 36337 -> 37059
restore state: ctrl=03000010 ready=0 gain=04000000 selector=29000000
```

Operator: **“I saw a frame of video; at first glance it looked correct.”** This
proves the same hardware-decoded NV12 bytes that fail from a segmented Cedrus
dma-buf display correctly from one physical run. The direct-path failure is
therefore physical-buffer provenance, not decoder content, NV12 layout, route,
geometry, colour state, selector state, or timing.

Patch 0074 now implements both a 64 MiB reusable VE `shared-dma-pool` and
`DMA_ATTR_FORCE_CONTIGUOUS` on Cedrus CAPTURE only. Because VE remains an IOMMU
client, the pool alone would be insufficient: the normal IOMMU DMA path may
still gather scattered physical pages behind a contiguous VE IOVA.

The normal series and the out-of-series 0068 test configuration built cleanly.
On a RAM-only hardware boot, Linux reserved the pool at `0x7c000000`, Cedrus
reported assignment to `video-codec-pool`, and patch 0072 accepted the direct
import. A nonvisible frame-60 freeze completed 90 submissions with the same
byte-exact `70bddcf8…` dump, and a 150-frame moving run completed with 149 fence
retirements, peak hold 4, and zero stalls. No 0072 refusal, warning, or IOMMU
fault appeared, and the logo selector stayed `0x29000000`. The pagemap PFNs
were unavailable (`absent=338`), so patch 0072's full-length one-segment check,
not the userspace `contiguous=yes` label, is the hard evidence.

All three final checks passed. Direct frame 60 held for 300 submissions and
looked good to the operator; a 300-frame moving clip completed at 27.09 fps
with 299 fence retirements, peak hold 4 and zero stalls, and the operator
noticed no issues. Both runs restored the logo. Three further consecutive
300-frame sessions completed at 27.09–27.12 fps with the same fence statistics,
no new kernel messages, and selector `0x29000000`. Patch 0074's bypass direct
path is hardware-proven.

This does not eliminate the vendor's likely runtime IOMMU method. Patches
0069/0070 tested an early Linux attachment and adopted-scanout identity map,
whereas vendor HWC starts master 2 bypassed and calls
`sunxi_enable_device_iommu(2, 1)` at playback resume. Preserve that as a separate
future branch and reproduce the timing/state transition faithfully.

Post-test board snapshot: RAM-loaded patch-0074 bypass kernel 6.18.38 (`Tue Sep
1 01:39:10 PDT 2026`), MIPS parked, serial free, no IOMMU page fault,
`IOMMU_BYPASS=0x7c`, and selector `0x29000000`. Every visible test restored the
logo route. Nothing was flashed; the test FIT and modules are only staged as
rootfs files.
