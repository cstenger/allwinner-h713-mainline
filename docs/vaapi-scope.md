# Hardware decode for stock players — VA-API scope

Written 2026-08-16. Answers one question with numbers rather than estimates:
**what would it take for `mpv` (and anything else using ffmpeg) to decode on the
VE instead of the CPU, without patching mpv, ffmpeg or GStreamer?**

The short version: the chain is real, the H.264 half is nearly free, the HEVC
half is a rewrite, and 10-bit is blocked in the kernel rather than in userspace.

---

# RESULT — H.264 decodes on the VE through stock ffmpeg, 2026-08-16

**Done, and validated bit-exact on hardware.** `libva-v4l2-request` (PR #38 plus
[three patches](../patches/libva-v4l2-request/)) drives cedrus from unmodified
ffmpeg. All five vectors of the M1 ladder — 320x240 baseline through 1920x1080
high — decode **bit-exact** against the host-generated references, and the VE's
interrupt count rises by exactly one per frame, so the hardware is doing it.

| | |
| --- | --- |
| `vainfo` | loads `__vaDriverInit_1_22`, advertises 5 H.264 profiles, `VAEntrypointVLD` |
| bit-exactness | 5 of 5 vectors, `tools/video/va-decode-test.sh` |
| decode cost | **1.233 s wall / 0.637 s CPU** for 60 frames of 1080p (software: 2.72 s CPU) |
| what blocked it | *not* the codec — the shim created the bitstream queue with zero buffers, because ffmpeg no longer preallocates a VA surface pool. See patch 0003. |

**The one number to carry into the display work:** copying decoded frames back
to system memory with `hwdownload` costs *more than the decode* (1.8 s extra for
186 MB of 1080p) because V4L2 MMAP buffers are uncached. Decode-to-file pays
that; a display path that maps the surface as a dma-buf does not.

## The display path — plays on the panel, and crashes the kernel intermittently

Step 6 was attempted the same session. It gets **all the way to video on the
panel**: `mpv` hardware-decodes on the VE and renders through EGL-on-GBM against
our KMS driver, and a 1200-frame 720p25 clip has played to completion.

The two things worth knowing before picking this up:

**1. It must be `--hwdec=vaapi-copy`, not `--hwdec=vaapi`.** Plain `vaapi`
fails with `Could not create a VA display`, and the reason is structural rather
than a misconfiguration: mpv's `vo=gpu` DRM path asks for a **render node on the
KMS device** (`drm_params_v2.render_fd`) and our display-only driver has none —
`renderD128` belongs to panfrost on `card0`. `--vaapi-device` is accepted and
*ignored* on this path. Our shim ignores the DRM fd entirely, so any node would
do; mpv just will not offer one. Patching mpv is out of scope by standing
constraint, so `vaapi-copy` — which builds its own VA display and honours
`--vaapi-device` — is the working invocation:

```
LIBVA_DRIVER_NAME=v4l2_request mpv --hwdec=vaapi-copy \
  --vaapi-device=/dev/dri/renderD128 \
  --vo=gpu --gpu-context=drm --drm-device=/dev/dri/card1 clip.mp4
```

That costs the copy-out measured above. Zero-copy would need either a render
node on `card1` or the `drmprime-overlay` path (mpv reports `Failed to find
drmprime plane with idx=-2` today).

**2. It panics intermittently — and it is memory corruption, not a codec bug.**
Two of four runs of the same 48-second clip took the board down. Captured on
serial:

```
Unable to handle kernel NULL pointer dereference at virtual address 0000000000000010
CPU: 3  Comm: kworker/u16:1
Workqueue:  0x0 (pan_js)             <- panfrost job scheduler, work fn is NULL
pc : stmmac_hw_setup+0x844/0xbd4     <- nonsense; this board has no Ethernet
Call trace: dequeue_entities / dequeue_task_fair / __schedule / worker_thread
...
cedrus 1c0e000.video-codec: frame processing timed out!
rcu: INFO: rcu_sched detected stalls on CPUs/tasks: 0-...! 1-...! 3-...!
```

A workqueue whose work function is `0x0` and a PC that resolves to an unrelated
built-in symbol are both signatures of **corrupted kernel memory**, not of a
driver returning an error. It surfaces in panfrost's job scheduler because that
is what runs constantly during playback, which does not mean panfrost is the
culprit. In play: `sun50i_h713_afbd`, `sunxi_cedrus`, `sunxi_scanout_dmabuf`,
`panfrost`.

**The controls say it is the combination, not either half:**

| run | result |
| --- | --- |
| hardware decode, `--vo=null`, 48 s / 1200 frames | **stable** (VE IRQ count exactly 1200) |
| software decode, on the panel, 48 s | **stable**, played to completion |
| hardware decode **on the panel**, 48 s | **2 of 4 runs panicked** |

### The KASAN kernel — built, and how to run it

Make the crash legible rather than guessing at it. The debug kernel exists:

```
KERNEL_CONFIG=kasan build/build.sh kernel     # -> build/out/h713-kernel-kasan.fit
```

`patches/kernel/board/kasan.config` turns on generic KASAN (outline, plus
`KASAN_VMALLOC` because module text and DRM/GEM allocations live there) and
builds cedrus, the AFBD KMS driver, panfrost and scanout-dmabuf **in** rather
than as modules — KASAN only instruments what is compiled in its tree, so as
modules the four suspects would be the only unchecked code. It also sets
`CONFIG_LOCALVERSION="-kasan"`, which is not cosmetic: `uname -r` becomes
`6.18.38-kasan`, so `/lib/modules/6.18.38-kasan` does not exist, udev loads
nothing, and the production kernel's modules cannot be loaded into a KASAN
kernel by accident. (They must not be: KASAN changes core struct layouts, so a
stale `.ko` reads wrong offsets and corrupts memory itself.) `MAGIC_SYSRQ` is on
there too, with serial-BREAK support.

Getting it onto the board **does not go over WiFi** — see the gotcha above; that
link cannot carry a file. One YMODEM transfer at the U-Boot prompt, made
permanent so later boots are instant:

```
python3 tools/serial/load_fit.py build/out/h713-kernel-kasan.fit --port /dev/ttyUSB0 --addr 0x50000000
```

~17 minutes at 10.8 KB/s. Then, at the prompt:

```
fatwrite mmc 1:2 0x50000000 h713-kernel-kasan.fit ${filesize}
h713_disp auto 0x34 logo
bootm 0x50000000
```

and on any later boot, `fatload mmc 1:2 0x50000000 h713-kernel-kasan.fit; bootm
0x50000000`. The production `h713-kernel.fit` is never touched, so the way back
from a bad debug kernel is an ordinary boot.

Two things change when this kernel boots, and both will trip you up:

- **The DRM card numbers swap.** Built-in drivers probe in a different order
  than modules, so on the KASAN kernel `card0` is `sun50i-h713-afbd` and `card1`
  is panfrost — the reverse of the production kernel. mpv wants
  `--drm-device=/dev/dri/card0` here. `renderD128` is panfrost either way.
- **Usable RAM drops to 780 MB** from ~1 GiB; that is the shadow, and it is the
  cheapest confirmation that KASAN is really on, alongside
  `KernelAddressSanitizer initialized (generic)` in dmesg.

### Result of the first KASAN reproduction attempt — the crash did not fire

Decode is still bit-exact under KASAN (`v04` → `a991db21…`), so the kernel is
sound. But **the crash did not reproduce**, across **~24 minutes of continuous
looping 720p playback on the panel — 42,773 frames by the VE's interrupt
count — with zero crashes and zero KASAN reports** (three runs: 240 s, 300 s
and a 900 s soak). The pre-KASAN kernel failed 3 of 4 runs, usually inside 48
seconds.

That kernel changed two things at once, unavoidably — KASAN only instruments
what is compiled in its tree, so covering the four suspect drivers meant
building them in. So the control was run: **the same four drivers built in,
without KASAN** (`patches/kernel/board/builtin-drivers.config`).

### The control settles it — KASAN was hiding the bug

**It crashed at T+198 s**, on the same playback. So built-in versus module is
*not* the variable; KASAN's presence is. And note KASAN produced no report
either — it did not miss a detection, the racing access appears not to have
happened at all, which points at its 2–3x slowdown moving the window rather
than at coverage.

The control's trace is also far better than the original, because with these
drivers built in there are no module offsets to confuse the symbolizer. Where
the first capture said `Workqueue: 0x0 (pan_js)` and a PC in an unrelated
built-in, this says exactly what is happening:

```
Unable to handle kernel NULL pointer dereference at virtual address 0000000000000000
CPU: 3  Comm: kworker/u16:2  Not tainted 6.18.38-builtin
Workqueue: pan_js drm_sched_run_job_work
pc : pwq_tryinc_nr_active+0xfc/0x204
lr : __queue_work+0x520/0x648
Call trace:
 pwq_tryinc_nr_active+0xfc/0x204 (P)
 __queue_work+0x520/0x648
 queue_work_on+0x3c/0xa0
 drm_sched_run_job_work+0x4d8/0x504
 process_scheduled_works+0x170/0x300
 worker_thread+0x2fc/0x45c
```

The DRM GPU scheduler queues its run-job work, and the workqueue core
dereferences NULL doing it — so the workqueue the scheduler is submitting to is
NULL or freed underneath it. That is a **lifetime/teardown race in
drm_sched + panfrost**, provoked by the VE-decode-plus-display combination, and
it is not a VA-API bug: nothing in the shim, cedrus or the AFBD driver appears
in that path.

Decoded further against the `vmlinux` that produced it, so the next session does
not have to. The `Code:` bytes in the Oops match `pwq_tryinc_nr_active+0xfc`
exactly:

```
b5d4: 88e87d6c   casa w8, w12, [x11]      <- raw_spin_lock(&nna->lock)
b5d8: 350006e8   cbnz w8, <slowpath>
b5dc: f9400128   ldr  x8, [x9]            <- FAULTS, x9 = 0
b5e0: eb09011f   cmp  x8, x9
```

`ldr` then `cmp` against the same register is `list_empty()`, so the faulting
line is the `if (list_empty(&pwq->pending_node))` immediately after
`raw_spin_lock(&nna->lock)` in `pwq_tryinc_nr_active()`. Two things follow.
That branch is only reachable for a **`WQ_UNBOUND`** workqueue (`wq_node_nr_active()`
returns NULL otherwise and the function takes the early `!nna` exit), which fits:
`drm_sched_init()` gives each scheduler its own `alloc_ordered_workqueue()`, and
ordered implies unbound. And `+0x4d8/0x504` in `drm_sched_run_job_work` is the
**final** `drm_sched_run_job_queue(sched)`, the requeue at the very end of the
function — not the early no-job path.

So the shape to look for is: the scheduler requeues its own run-job work at the
tail of that function while something concurrently tears the workqueue (or its
`pool_workqueue`) down. `drm_sched_run_job_queue()` only checks
`READ_ONCE(sched->pause_submit)` before `queue_work()`, which is not
synchronised against a teardown running on another CPU. panfrost's reset path
(`panfrost_job_timedout` → `drm_sched_stop`/`drm_sched_start`, `panfrost_job.c`)
is the obvious thing to audit against it — and note the `cedrus: frame
processing timed out!` in the very first capture, which would be exactly the
kind of event that triggers a reset. `kworker … exited with irqs disabled` is why the board then
hard-locks rather than merely oopsing — sysrq gets no response afterwards, so
recovery is the power switch.

### Upstream has not fixed it — checked 2026-08-17

- **The race is still there in current master.** `drm_sched_run_job_queue()` was
  refactored to `if (!drm_sched_is_stopped(sched)) queue_work(...)`, but
  `drm_sched_is_stopped()` is literally `return READ_ONCE(sched->pause_submit);`
  — a rename, not a fix. Queueing is still an unsynchronised check-then-act
  against a teardown that may be running on another CPU.
- **The one panfrost fix that looks relevant is already in our tree.**
  `796a9f55a8d1` ("drm/sched: Use struct for drm_sched_init() params", which
  carried the panfrost `timeout_wq` regression fix) — our `panfrost_job.c` sets
  `args.timeout_wq = pfdev->reset.wq`, so we are not hitting that.
- `panfrost_job.c` has no post-6.18 commits touching reset or scheduler
  lifetime. The newest adjacent work is Philipp Stanner's Feb 2026
  "drm/sched: Remove racy hack from drm_sched_fini()", which targets the
  entity-teardown `FIXME` still present in our `drm_sched_fini()` — a real race,
  but not the one in our trace.

### A better hypothesis than the drm_sched race — rogue VE DMA

Before spending another kernel cycle on drm_sched, weigh the competing
explanation, because it fits *all* the evidence and the scheduler race fits only
some of it. **The VE has no IOMMU** — deliberately, and documented at length in
patch 0024:

> `NO iommus PROPERTY -- deliberate, 2026-08-09.` `iommus = <&iommu 0>` here
> crashed the kernel on the first decode: **rogue VE DMA corrupted the printk
> ringbuffer**, faulting in `_prb_read_valid()` … the iommu node is inert, so
> the DMA layer handed cedrus IOVAs expecting translation, nothing translated
> them, and the VE wrote them as raw physical addresses.

So this board already has a precedent for the VE writing outside its buffers and
corrupting whatever kernel memory happened to be there. And crucially, **KASAN
cannot see device DMA** — it instruments CPU accesses only. That explains the
otherwise-odd result that KASAN was not merely quiet but produced *no report at
all*, while the crash vanished.

It also explains the control matrix better than a scheduler race does:

| | VE DMA active | display/GPU active | result |
|---|---|---|---|
| `--vo=null` | yes | no | stable — a stray write lands in idle memory |
| software decode on panel | **no** | yes | stable — nothing writes out of bounds |
| hardware decode on panel | yes | yes | **crashes** — panfrost's structures are the neighbour |

What I checked and did *not* find: cedrus's own geometry is internally
consistent, `cedrus_video.c` sizing the NV12 buffer with `ALIGN(width,16)` /
`ALIGN(height,16)` and `cedrus_hw.c` programming the same 16-alignment into
`VE_PRIMARY_FB_LINE_STRIDE_*`. So there is no obvious under-allocation to point
at — the hypothesis needs the H713's VE3 to want more than mainline cedrus
assumes, which is unproven.

### Both experiments run, 2026-08-17 — it is memory corruption, and drm_sched is a victim

Run on the control kernel with `oops=panic` added to the command line, which
turns each crash into a 5-second self-reboot and takes the human out of the
loop entirely (`panic=5` was already there). Highly recommended for this work.

| run | clip | `cma=` | outcome |
| --- | --- | --- | --- |
| (first) | 1280x720 | 128M | fatal Oops T+198 s — `pwq_tryinc_nr_active`, workqueue internals |
| **A** | 1280x720 | 128M | fatal Oops T+457 s — `rb_erase` ← `timerqueue_del` ← `__hrtimer_run_queues`, faulting on `0x3fd945c0` |
| **B** | 1280x**736** | 128M | fatal Oops T+113 s — `dma_fence_add_callback` ← `drm_sched_run_job_work` |
| **C** | 1280x720 | **256M** | no fatal Oops in 480 s; **530 ×** `WARNING … enqueue_dl_entity` (deadline scheduler), then rebooted after the window |

**Four different corrupted structures across four runs** — a workqueue's
`pool_workqueue`, the hrtimer red-black tree, a dma_fence, and the deadline
scheduler's runqueue. Three of those have nothing whatever to do with video or
graphics. **A code race faults in the same place; random corruption does not.**
So the drm_sched teardown race is not the bug — `drm_sched_run_job_work` is
simply the hottest code during playback and therefore the most likely thing to
trip over whatever got scribbled on. That also retires the earlier reading of
the first trace.

Note the faulting address in run A: `0x3fd945c0` is not a kernel virtual
address, it is a **physical-looking address inside the 1 GiB of DRAM** — a
pointer field holding something that looks like a DMA address.

**Experiment 2 (height alignment): refuted.** A 32-aligned 1280x736 clip did not
merely fail to help, it crashed *sooner* (113 s vs 457 s). The
16-versus-32-row-overrun mechanism is not what is happening. Good — that
hypothesis was cheap to kill and would have been expensive to chase.

**Experiment 1 (CMA size): the symptom moved.** At `cma=256M` the same clip
produced no fatal fault in the observed window, but a storm of corruption
warnings against a *different* structure. **drm_sched cannot care how big the
CMA pool is; a stray write must.** Layout-dependence is the signature.

Taken with KASAN's silence — no crash *and* no report, from a kernel where all
four suspect drivers were instrumented — the remaining explanation is a write
that the CPU never issues: **DMA from a device**, which KASAN cannot see, into
memory it does not own. The VE has no IOMMU and this board has a documented
precedent for exactly that (patch 0024, quoted above).

### VA-API is ruled out — it reproduces with no VA-API at all (2026-08-17)

| run | decode | scanout buffers | result |
| --- | --- | --- | --- |
| A/B/C | VA-API shim → cedrus | mpv KMS/GBM, **from CMA** | crashes, 113–457 s |
| **D** | **GStreamer** `v4l2slh264dec` → cedrus | `gles-play`, **reserved carveout** `0x6c100000` | **clean** — 480 s, ~28,437 frames |
| **E** | **GStreamer** `v4l2slh264dec` → cedrus (to `fakesink`, no display) + mpv **software** decode to the panel | mpv KMS/GBM, **from CMA** | **crashes** — `stack-protector: Kernel stack is corrupted in: internal_add_timer` |
| **I** | **none at all** — the VE is never opened, `ve=0` interrupts from boot to panic | mpv KMS/GBM, **from CMA** | **crashes** — `kernel stack overflow` at ~940 s. Cedrus is not necessary; see Experiment I below |

Run E is the one that settles it. There is **no VA-API in it anywhere** — the
hardware decode is GStreamer's, going nowhere but `fakesink`, and the picture on
the panel is *software*-decoded. It still corrupts the kernel, this time
tripping the stack protector: a fifth distinct victim, after a
`pool_workqueue`, the hrtimer rbtree, a `dma_fence` and the deadline scheduler.

So the earlier claim in this document that the crash "is not a VA-API bug" was
right, but for the wrong reason and on the wrong evidence — it now rests on a
direct experiment rather than on reading a call trace. **mpv, ffmpeg and the
libva-v4l2-request shim are all exonerated.** The necessary and sufficient
ingredients are:

> ⚠ **The first half of this is now refuted — see "Experiment I" below. Cedrus
> is NOT necessary.** What survives is the second half, the CMA-backed scanout.
>
> ~~cedrus decoding into CMA buffers, concurrently with~~ a KMS/GBM scanout
> buffer that is allocated from CMA.

Run D is the control that shows the second half matters: the *same* hardware
decode, with scanout coming from the reserved carveout instead of CMA, is clean
over 28,000 frames. Which is also why every earlier "decode alone is fine"
result held — with `--vo=null` nothing else was claiming CMA.

### The guard says it is not an overrun (2026-08-17)

`patches/kernel/0039-media-cedrus-add-runtime-dma-guard.patch` pads every cedrus
capture buffer, poisons the padding, and checks it once the VE has completed the
frame — the only way to witness a write that no MMU mediates. Off by default;
arm it with `sunxi_cedrus.dma_guard=65536` on the kernel command line.

First, the IOMMU claim this rests on, verified on the running board rather than
taken from a comment: `/sys/class/iommu/` and `/sys/kernel/iommu_groups/` are
both **empty**, the DT node `iommu@30f0000` has `status = "disabled"`, and the
`video-codec` node carries **no `iommus` property**. Nothing translates VE DMA.
(That proves no IOMMU is *active*, not that the silicon lacks the block — patch
0024 records every register at `0x030f0000` reading zero on this hardware, which
is why it is disabled.)

Results, both informative and both negative for the obvious theory:

- **Decode-only with the guard armed: zero reports**, output still bit-exact
  (`a991db21…`). The VE does not write past the frame it is given.
- **The full crashing workload with the guard armed: 13,391 frames over 450 s,
  no crash and zero reports** — where that exact workload died three times
  before, at 113 s, 198 s and 457 s. The 64 KiB of padding *changed the CMA
  layout*, exactly as `cma=256M` did, and the crash went away without the guard
  ever being touched.

**So it is not a bounded overrun past the capture buffer.** There is a stronger
argument for that conclusion than the guard alone: the victims — a kernel
stack, the hrtimer rbtree, a `pool_workqueue`, a `dma_fence`, the deadline
runqueue — are **slab and stack allocations, which are unmovable and therefore
never placed in CMA**. A write running off the end of a CMA buffer lands in
neighbouring *CMA* pages, which host only movable allocations. To corrupt a
kernel stack, the write has to go somewhere else entirely — a stale or wrong
address, not an off-by-a-bit.

### The concrete candidate: cedrus frees DMA buffers without halting the VE

`cedrus_stop_streaming()` does not reset the engine. For the OUTPUT queue it
calls `ctx->current_codec->stop(ctx)` — which for H.264 **frees
`pic_info_buf` and `neighbor_info_buf`** (`dma_alloc_attrs` with
`DMA_ATTR_NO_KERNEL_MAPPING`) — then `pm_runtime_put()`, then returns the
buffers. Nothing anywhere in that path asserts the VE's reset or waits for it to
go idle. The driver's *only* `reset_control_reset()` is in the watchdog timeout
handler, and `cedrus: frame processing timed out!` appeared in the very first
crash capture.

If the VE is still executing when those pages are freed, it keeps writing into
memory the allocator has since handed to slab or a kernel stack. That mechanism
predicts everything observed: arbitrary victims rather than one, layout
dependence, invisibility to KASAN, and the fact that it takes a second engine
competing for CMA to make the freed pages get reused quickly enough to matter.

### ⚠ RETRACTED — the A/B below was underpowered, and a one-hour soak refutes it

**Read this before the section that follows.** On 2026-08-17 the full
configuration — IOMMU translating both VE ports *and* `stop_reset=Y`, i.e. both
mitigations on — was soaked, and it **crashed after 390 seconds**:

```
Internal error: Oops - Undefined instruction: 0000000002000000 [#1]  SMP
CPU: 3  PID: 3266  Comm: kworker/u16:2
Workqueue:  0x0 (pan_js)          <- work function NULL, as in the very first crash
pc : __schedule+0x284/0x794
Call trace: __schedule / schedule / worker_thread / kthread
```

So kernel memory is still being corrupted, with the same signature this
investigation started from. **`cedrus_stop_streaming()` not halting the engine
is therefore not established as the root cause.** The A/B that appeared to
establish it was one run per arm, and crash latency across this whole
investigation has ranged 113 s to 848 s — a single clean 450 s arm was never
strong enough to carry the conclusion, and I should have said so at the time
rather than after the counterexample.

What survives from that experiment: the *fix-off* arm did crash, and the
IOMMU-on/fix-off arm degraded a kernel panic to an mpv segfault. Both remain
consistent with cedrus contributing. What is now false is "root cause found".

**The control this investigation never ran with adequate exposure** is the one
that would settle it: the display path active for ten-plus minutes with **no
hardware decode at all**. The only such run was 48 seconds. Every long run that
crashed had cedrus decoding in it, but so did nearly every long run, so that
correlation is much weaker than it looked. The display block (`dec@5600000`,
IOMMU master 2) is in **bypass** in our DT, exactly as the vendor has it, so it
can still write anywhere — and `sunxi-scanout-dmabuf` hands physical addresses
to display hardware by design.

### Experiment I — that control ran, and it crashes with the VE at zero (2026-08-17)

**Cedrus is not necessary for the corruption.** The display path alone panicked
the kernel after ~940 seconds with the video engine never once interrupted.

Trace and full heartbeat series:
[`docs/reference/expI-display-only-no-ve-crashes.log`](reference/expI-display-only-no-ve-crashes.log).
Harness: [`tools/video/soak-display-only.sh`](../tools/video/soak-display-only.sh)
and [`tools/serial/soak-capture.py`](../tools/serial/soak-capture.py).

Same kernel as every crashing run (`6.18.38-builtin`), same `cma=128M`, no
IOMMU (verified on the board: `/sys/class/iommu/` empty, zero iommu groups),
`oops=panic`. Workload was `mpv --hwdec=no --vo=gpu --gpu-context=drm` looping
720p to the panel — run E's display half with the GStreamer/cedrus half
subtracted. Thirty-two consecutive 30-second heartbeats, every one of them:

```
SOAK t=931s ve=0 ve_delta=0 gpu=418868 gpu_rate=452/s cma=112544kB deaths=0
[ 1008.405674] Insufficient stack space to handle exception!
[ 1008.405716] CPU: 2 UID: 0 PID: 41 Comm: kworker/u16:1  6.18.38-builtin
[ 1008.405737] Workqueue:  0x0 (pan_js)
[ 1008.405862] Kernel panic - not syncing: kernel stack overflow
```

`ve=0` is a **positive** witness, not an assumption: cedrus is built into this
kernel and cannot be removed, so the `1c0e000.video-codec` interrupt count
staying at zero from boot to panic is direct evidence that no frame ever
reached the engine. `deaths=0` says mpv ran continuously, so the display path
was driven for the whole 940 s rather than quietly idling.

**On the strength of one run.** The retraction above is about an underpowered
*clean* arm, and that caution does not transfer here. This claim is a
refutation of a necessity — "cedrus must be decoding" — and a single
counterexample is logically sufficient to kill one. What one crash does *not*
establish is any positive claim about rate or cause.

`Workqueue: 0x0 (pan_js)` is the same NULL work function as the very first
crash and as the retracted soak, so this is the same bug, not a new one.

**A sharper forensic clue than "random victim".** The panic is a stack
overflow, and the reason is a truncated pointer:

```
sp        : 0000000081350040
Task stack: [0xffff800081350000..0xffff800081354000]
```

The stack pointer should be `ffff8000_81350040`. Its **upper 32 bits have been
zeroed** — the low half is intact and correct. That is the signature of a
32-bit write landing on the high word of a 64-bit pointer, which also fits a
`work_struct` function pointer reading as `0x0`. Previous crashes were recorded
as "a different victim every time"; this one additionally says *what shape* the
write is.

**What that narrows to.** The obvious suspect for a stray 32-bit write
clobbering a `work_struct` would be DECD — patch 0034 fixed exactly that bug,
`jiffies_hist[jpos + 2]` running off a `u32[100]` into the adjacent
`struct work_struct`. **It is not DECD here.** On `-builtin` there is no module
tree at all, DECD is a module, and its `"decd"` interrupt is absent from the
run's `/proc/interrupts` baseline. The live display path was only: the AFBD KMS
driver (0037), panfrost, and `sunxi-scanout-dmabuf` (0036).

Combined with run D — GPU rendering *and* hardware decode, scanout from the
reserved carveout, clean over 480 s — the discriminating variable across every
run in this document is now **where the scanout buffer lives**, not what feeds
it.

#### A second ve=0 failure, weaker but consistent

The first attempt at this control (same file, appended) lost mpv to a signal at
~250 s with `ve=0`, leaving the kernel up. It is weaker evidence because the
signal was not recoverable, and *why* is worth carrying forward:
**`/proc/sys/debug/exception-trace` is 0 on this rootfs**, so the kernel prints
nothing for a userspace fault. An empty `dmesg` after a mysterious process
death is therefore not evidence of anything. The harness now sets it to 1,
records mpv's exit status through `wait()`, and restarts mpv so a single death
no longer ends an hour-long run.

### The A/B that suggested halting the VE stops the corruption (superseded)

`patches/kernel/0040-media-cedrus-halt-ve-before-freeing-dma-buffers.patch`
pulses the engine's reset in `cedrus_stop_streaming()` before `codec->stop()`
frees anything, while the device is still powered. It is behind
`sunxi_cedrus.stop_reset` (default on, **writable at runtime**), which is what
makes the test worth trusting: both arms ran in the **same boot**, with the same
CMA layout and the same workload, so nothing but the reset differs.

Critically, `dma_guard` was left at **0** for this — the padding from patch 0039
masks the crash by itself, and would have invalidated the whole comparison.

| arm | `stop_reset` | result |
| --- | --- | --- |
| **A** | `Y` | 450 s, **13,338 frames, clean** |
| **B** | `0`, flipped via sysfs, same boot | **crash** — NULL deref, `Workqueue: 0x0 (pan_js)`, `pc : dequeue_entities` (the CFS scheduler — a sixth distinct victim) |

So the mechanism is established: **cedrus frees DMA buffers that the VE may
still be writing into, and the page allocator hands those pages to slab or a
kernel stack.** Everything observed follows from that — arbitrary victims rather
than one repeatable site, layout dependence, KASAN blindness (the writer is a
device, and this SoC has no usable IOMMU), and the need for a second CMA
consumer to make the freed pages get reused quickly enough to matter.

**How much this proves, honestly.** One clean 450-second arm against one crash
is not a long baseline, and crash latency has ranged from 113 s to 848 s. What
makes it convincing is the within-boot flip plus the prior record: five earlier
reproductions, four of them inside 457 s. The confirmation still owed is a long
soak with `stop_reset=Y` — an hour, not eight minutes.

**Before this ships as a fix**, the caveat in the patch has to be closed: a
reset is device-wide, so it must not fire while a second m2m context is mid-job.
Either check that no job is running, or perform the reset from the m2m job
context. Upstream cedrus has the same hole on every SoC it supports; it is
merely harmless where an IOMMU contains the engine.

### And the vendor does contain it — checked against board B's binaries

Patch 0024 already documents the vendor's `mmu_aw: iommu@2010000`
(`allwinner,sunxi-iommu`, `#iommu-cells = <2>`, SPI 71, `clocks = <&ccu 0x30>`),
that mainline's `iommu@30f0000` is the H6 base and simply wrong here, and that
`ve@1c0e000` attaches as master 0. Re-derived from `local/stock-boot/sunxi.fex`
and confirmed. Two things that comment does **not** say, and both matter now:

- **The display block is behind the IOMMU too.** `dec@5600000` — the same
  address our AFBD KMS driver binds — is `iommus = <&mmu_aw 2 0>`. So is
  `ge2d@5240000` (master 2), `demux` and `audbrg` (master 6), `ve1` (1),
  `av1@1c0d000` (5). **Both engines in our crashing combination are translated
  in the vendor stack and untranslated in ours.**
- **The vendor kernel genuinely drives it**, rather than merely declaring it in
  DT. `strings` on `boot_a-board-b.img` gives 159 IOMMU symbols including
  `sunxi iommu init tlb failed`, `sunxi iommu: irq = %d`, `sunxi iommu int
  error!!!`, `Attached IOMMU controller to %s device.`, plus
  `arm_iommu_attach_device` and the build path
  `H713_SDK_V1.3_Branch/longan/kernel/linux-5.4/drivers/iommu/`.

That reframes patch 0024's conclusion. "The honest state is no IOMMU, which is
also the safer one" was the right call at the time — being handed IOVAs that
nothing translates is worse than dma-direct. But it is now clear what running
untranslated costs: cedrus's post-free writes reach arbitrary kernel memory, and
this investigation spent a session chasing six different victims that an IOMMU
would have reported as one fault naming the offending master.

So porting the vendor IOMMU stops being a nice-to-have. It is the containment
mechanism for this entire class of bug, and the reason the vendor never had to
notice that `stop_streaming` does not halt the engine. The work it needs is
already scoped in patch 0024: a driver for `allwinner,sunxi-iommu` (the cell
count and register layout both differ from mainline's `sun50i-iommu`, and
register compatibility with the H6 block is untested), and the CCU gate checked
before probing because an ungated block hangs this interconnect.

**Where to point the next session:**

- It is **kernel-side**, in cedrus and/or the AFBD KMS/scanout path — not in
  any userspace video component.
- The question to answer is which side writes out of bounds: does the VE
  overrun its capture buffer into a neighbouring CMA allocation, or does the
  KMS/scanout path overrun its own? Guard/poison pages either side of both
  allocations answer it directly, and they see what KASAN cannot — KASAN
  instruments CPU accesses, and neither of these writes comes from the CPU.
- `CONFIG_DMA_API_DEBUG` is the other cheap instrument.
- Also worth a look while in there: **`kmssink` cannot drive our KMS driver at
  all.** It fails negotiation, and with `videoconvert` in the pipeline it
  produces `GStreamer-CRITICAL … range start is not smaller than end for
  'GstIntRange'` — our driver is advertising a degenerate size range in its
  plane/mode caps. Unrelated to the corruption, but it blocked the cleanest
  version of this experiment and is a real bug.

**Next steps, in order of cost:**

1. `CONFIG_DEBUG_OBJECTS` + `DEBUG_OBJECTS_WORK` — targets exactly this (a work
   item used after free or never initialised) at a fraction of KASAN's overhead,
   so it is far less likely to perturb the window shut the way KASAN did.
2. Read `drm_sched_run_job_work()` against panfrost's scheduler teardown in
   6.18 with the question "who can free `submit_wq` while a job work is still
   queued?", and check whether upstream has already fixed it.
3. Only then reach for KASAN again, and if so with those drivers back as
   *instrumented modules* in `/lib/modules/6.18.38-kasan`, plus
   `CONFIG_PSTORE`/ramoops so a report survives the lockup — nothing reaches the
   journal, because journald cannot flush during a panic.

Note that `CONFIG_MAGIC_SYSRQ` (in both debug fragments, with
`tools/serial/sysrq.py` to drive it over a UART BREAK) did **not** rescue this
particular wedge: with every CPU spinning interrupts-disabled, nothing runs the
handler. It is still worth having for the softer hangs.

**Still open:** the crash above, zero-copy display, HEVC in the shim, and 10-bit.

---

## The display IS translatable — and the soak that should have settled it hit a different bug (2026-08-21)

The primary experiment finally ran: `iommus = <&iommu 2 1>` on the AFBD node
(patch 0052), on a kernel otherwise **bit-identical to production** — the
`dispiommu` fragment changes no config symbol, so `uname -r` stays `6.18.38`,
`/lib/modules/6.18.38` loads unchanged, WiFi and BT come up, and the DRM card
numbering stays `card0` panfrost / `card1` AFBD. That last part is what made the
run observable over ssh instead of over a 115200-baud console, and it is worth
keeping for every future display experiment.

**Four things are now established, and they hold regardless of the soak.**

1. **A second master can share this IOMMU.** The worry was real — sun50i-iommu
   installs one page table at a time (`iommu->domain`), and its `attach_dev`
   detaches whatever was there — but `.device_group` is
   `generic_single_device_group`, which caches **one** group on the
   `iommu_device` and hands it to every master behind it. So the display joins
   cedrus's group rather than displacing it:
   ```
   [0.800646] platform 1c0e000.video-codec: Adding to iommu group 0
   [0.806856] platform 5600000.display:   Adding to iommu group 0
   ```
   Read the helper's name as "singleton group", not "single-device group".
2. **Master 2 really is translated**, and the proof is a fault:
   ```
   [0.812726] sun50i-iommu 2010000.iommu: Page fault for 0x000000006c3d5000 (master 2, dir rd)
   ```
   That is the panel still fetching U-Boot's physical carveout in the window
   between the IOMMU attaching the device and the KMS driver programming an
   IOVA. It is a *positive control*: the master faults, so it is not bypassing.
3. **The handover works, and it is the reason a null result would mean
   something.** There is exactly **one** such fault, not a storm — the block
   stops re-fetching after the IOMMU resets its port — and after AFBD probes at
   6.39 s (`adopting 1280x720, stride 5120, source 6c100000`) there are none at
   all. A translated master that fetches successfully is by definition fetching
   *mapped* IOVAs, so the scanout is genuinely going through the page table. No
   register read is needed to establish that, and it is better evidence than one
   would be.
4. **Decode is unaffected by the shared domain:** the full VA1 ladder is 5/5
   bit-exact with the display attached, and `ve` interrupts still rise one per
   frame.

Patch 0051 (rate-limit the fault print) was written for the storm that did not
materialise. Keep it anyway: `sun50i_iommu_report_fault()` runs in hard IRQ with
`iommu_lock` held and called `dev_err()` once per faulting transaction, which is
a console-bound hang waiting for a master that faults per-frame.

### The soak is INVALID — the display stopped being exercised at 30 s

`mmu_delta` stayed at 0 for the whole run and the board never corrupted, but
**none of that counts**, because the display stopped being exercised after
roughly half a minute:

```
SOAK t=30s  ve=0 gpu=11253 gpu_rate=375/s mmu_delta=0
SOAK t=60s  ve=0 gpu=11253 gpu_rate=0/s   mmu_delta=0
...          gpu frozen at 11253 for the next nine minutes, deaths=0
```

`gpu` frozen with mpv still alive is exactly the false-survival the harness
header warns about. What actually happened is on the console at the same
instant:

```
[159.550902] sunxi-mmc 4022000.mmc: send stop command failed
[159.556572] panfrost 1800000.gpu: unexpectedly high interrupt latency
```

`mmc@4022000` is the **eMMC**, i.e. the rootfs. From there the filesystem was
gone: journald went unkillable (`Processes still around after SIGKILL` — D
state), a `dd` hung, and every shell command that touched a path hung while
`/proc` kept answering normally. mpv froze because it could not read the next
block of the clip.

At the time this was read as a storage bug unrelated to the corruption. The
production control below makes that unlikely: it is more probably **the same
stray write, landing in the mmc path instead of a task_struct**. A different
victim every run is this bug's signature, so a wedged eMMC needs no separate
explanation.

**Do not read the clean `mmu_delta=0` as evidence.** Thirty seconds of exposure
against a bug whose crash latency ranges 113–848 s is the same mistake the
retraction earlier in this document is about.

### What to run next, and why it is a control rather than a fix

The two candidate explanations are not distinguishable from this run:

- **pre-existing** — concurrent display + GPU + WiFi + eMMC load wedges the
  eMMC on any kernel. Note the eMMC still carries the 4x clock-accounting error
  that patch 0048 fixed **only for mmc1**: `max-frequency = <200000000>` on a
  controller whose driver doubles the rate and whose CCU carries a fictional /2
  post-divider. `d957eea` records that the measurement was attempted and does
  not settle it.
- **caused by this patch** — and there is a mechanism, which is why it cannot
  just be waved off. This kernel reports `iommu: DMA domain TLB invalidation
  policy: strict mode`, and sun50i-iommu's flush path spins with `iommu_lock`
  held and interrupts disabled. Adding a second, actively-allocating master
  lengthens those IRQ-off windows, and *both* symptoms landing in the same
  6 ms — a GPU complaining about interrupt latency and an eMMC missing a command
  completion — is what that would look like.

So the next run is the **production kernel, same clip, same mpv invocation, no
display IOMMU**. If the eMMC wedges there too it is pre-existing and becomes the
blocker for all display work; if production runs clean, patch 0052 caused it and
`iommu.strict=0` (a cmdline knob, no rebuild) is the first thing to try.

### That control ran, and it panicked in forty seconds (2026-08-21)

Neither branch above. The production kernel — panel up, same clip on the same
eMMC, same bootargs, same mpv invocation, **no display IOMMU** — reproduced the
corruption almost immediately:

```
SOAK MPV-DIED #1 by t=30s rc=139 SIGSEGV
[141.125261] Kernel panic - not syncing: kernel stack overflow
```

**Two conclusions, and the first retires a worry rather than a hypothesis.**

1. **Patch 0052 did not cause the wedge.** The bug is present without it. The
   eMMC wedge in the dispiommu run is best read as the *same stray write*
   landing in a different victim — the signature of this bug has always been a
   different victim every run, and an mmc structure is as good a target as a
   `pool_workqueue`. It does not need a separate explanation, and the
   `iommu.strict=0` idea can be shelved.
2. **The reproduction is fast.** Forty seconds of display exposure, against a
   documented range of 113–848 s. If that holds it changes how this bug can be
   worked: controls become minutes rather than hours. Treat it as one sample
   until a second run agrees.

### The best trace yet — the victim is a task_struct

`docs/reference/expJ-production-control-stack-overflow.log`. The registers pin
down what the earlier runs could only describe:

```
Workqueue:  0x0 (pan_js)
pc : el1h_64_sync+0x0/0x70
lr : process_scheduled_works+0x214/0x300
sp : 0000000081320040
x29: ffff800081323d90
```

`x29` is intact and sits in the task's 16 KiB stack
(`0xffff800081320000..0xffff800081324000`). `sp` holds **the same low 32 bits
with the top half zeroed** — `0x0000000081320040` where
`0xffff800081320040` belongs. It is not a stack that overflowed by recursing;
it is a stack pointer that came back wrong.

That points at one structure. `cpu_switch_to()` restores `fp` and `sp` from
`task->thread.cpu_context`, where they are adjacent:

```c
struct cpu_context { unsigned long x19..x28, fp, sp, pc; };
```

`fp` (+80) survived, `sp` (+88) lost its high word, and `pc` (+96) is
consistent with `lr` pointing into `process_scheduled_works` — exactly where
this kworker would have been switched out. So the write was **four bytes of
zero at `cpu_context.sp + 4`**, inside a slab-allocated `task_struct`, and the
task died on the *next* context switch into it rather than at the moment of the
write.

This is the same "upper 32 bits zeroed, low half intact" shape recorded earlier,
now with a named victim and a named mechanism. It also explains why the faulting
site is different every time: the corruption is silent until something *uses*
the field.

And note `MPV-DIED ... SIGSEGV` **before** the panic. Userspace was hit too, so
whatever writes is not confined to kernel allocations.

### Panfrost is the remaining unisolated variable

The GPU has been live in every run on record — the crashing ones *and* run D,
which was clean — so it has never been in the "changed" column of any
comparison. It is also the one candidate that neither of this project's
detectors can see: KASAN does not instrument device DMA, and panfrost maps the
scanout dma-buf into its **own** MMU, so the sun50i IOMMU cannot fault on it no
matter how long patch 0052 soaks.

`VO=drm` is the control that removes it. mpv renders on the CPU into the same
CMA dumb buffers and page-flips them, so the scanout path is unchanged:

```
SOAK start ... vo=drm
SOAK t=30s ve=0 gpu=0 gpu_rate=0/s afbd_rate=57/s mmu_delta=0
```

`gpu=0` is positive proof the GPU never ran — panfrost is loaded and could
fire — and `afbd_rate=57/s` proves the panel is being driven at very nearly
60 Hz throughout. That is the pairing the earlier runs lacked: a null result
that is *known* to have been exposed.

### It ran clean for forty minutes, and the GPU arm crashed twice more

```
SOAK DONE vo=drm t=2406s deaths=0 ve_delta=0 gpu_delta=0 afbd_delta=143646 mmu_delta=0
```

**143,646 scanout commits, zero GPU interrupts, zero mpv deaths, zero faults,
no reboot.** Cross-checked against the console: the serial capture matched no
stop pattern at all, and `panfrost-job` read **0** in `/proc/interrupts`
afterwards while `h713-afbd` read **144,430**. Log:
`docs/reference/expL-vodrm-no-gpu-clean-40min.log`.

The GPU arm was then re-run and crashed again in ~60–90 s
(`docs/reference/expK-gpu-arm-rerun-ccu-pointer.log`), so the fast latency is
n=2, not a fluke.

**This closes a 2x2 that supersedes "where the scanout buffer lives".**

| GPU renders | scanout buffer | result |
| --- | --- | --- |
| yes | reserved carveout | clean, 480 s (run D) |
| yes | **CMA** | **crash — ~40 s, then ~60–90 s** |
| **no** | CMA | clean, 2406 s / 143,646 commits |

Neither ingredient is sufficient alone. The corruption needs **panfrost
rendering into a CMA-backed scanout buffer**. That is a much sharper statement
than the earlier "the discriminating variable is where the scanout buffer
lives, not what feeds it" — *what feeds it* turns out to matter just as much,
and the earlier phrasing should be read as superseded.

Two caveats kept deliberately: `VO=drm` removes several things at once — job
execution, panfrost's MMU mappings, GBM allocation, and the dma-buf
export/import between `card1` and `card0` — so this indicts that *set*, not
panfrost's DMA specifically. And the clean arm is 2406 s against a crash
latency whose full recorded range is 113–848 s, so it is ~2.8x the longest
crash on record rather than 60x the fastest.

### The second trace: two CPUs, kernel and userspace, in the same microsecond

`expK` is the most informative crash yet, because two independent faults land
together:

```
CPU 3  sugov:0        pc : ccu_helper_wait_for_lock+0x54/0xbc
                      x20: faef800080111000        <- should be ffff8000_...
CPU 0  av:h264:df1    DABT (lower EL) ... level 1 translation fault
                      in libavcodec.so.61.19.101[15a79c,...]   (WnR=1, a write)
```

`x20` is `common->base + reg` inside the **clock driver** — a fresh victim,
neither of the earlier ones. And at the same instant a *userspace* libavcodec
thread faulted writing to an unmapped address. One bad pointer does not do
that. A single event scribbled over memory belonging to the kernel **and** to a
user process at once, which is what a device writing a block to the wrong
physical address looks like.

**The corrupted values look like pixel data.** The high half of the CCU pointer
went `ffff` → `faef`; in `expJ` the high word of `cpu_context.sp` went
`ffff8000` → `00000000`. Black, and a colour. A GPU writing a frame of a video
into recycled memory would produce exactly that distribution — mostly zeros
with occasional non-zero words — and it explains why every victim is a
different structure: one stray render pass covers a great many of them.

Migration metering (`mig_delta`, `pgmigrate_success`) is now in the harness on
the hypothesis that CMA page migration moves a page out from under a live GPU
mapping. First data point is `mig_delta=10` over 30 s on the GPU arm — real but
small, and there is no clean-arm comparison yet because the counter was added
after that run. **Not evidence of anything yet**; it is instrumentation for the
next pass.

### Where this leaves the investigation

The suspect list is finally short, and for the first time it excludes the
display itself:

- **cedrus** — exonerated (crashes with `ve=0`).
- **VA-API / mpv / ffmpeg / the shim** — exonerated (reproduces with none of them).
- **AFBD / the KMS scanout** — now effectively exonerated too: it ran 143,646
  commits at full rate for 40 minutes with nothing else touching the buffers.
  It is also read-only by construction — the driver programs `AFBD_SRC` and a
  stride, and a scanout engine that reads a recycled page shows garbage, it
  does not corrupt.
- **panfrost, or the dma-buf import path it requires** — the remaining suspect.

### Reading the import path — what it ruled out, and the one fact that matters

The chain was read end to end: `panfrost_gem_prime_import_sg_table()` →
`drm_gem_shmem_prime_import_sg_table()` → `panfrost_gem_open()` →
`panfrost_mmu_map()` → `mmu_map_sg()`, plus the teardown side. **No smoking gun
in it**, and it kills two hypotheses including one of mine.

Confirmed empirically first, from `/sys/kernel/debug/dma_buf/bufinfo` during
playback — the split-render path is real and is exactly what was assumed:

```
size 03723264  exp_name drm   Attached Devices: 1800000.gpu     (x4, 14,893,056 B total)
panfrost gems:  3723264  ... 0x3  "GEM PRIME buffer"   (imported|exported)
                134217728 resident 2097152                       <- growable tiler heap
```

Four ~3.55 MiB dumb buffers allocated on `card1` (AFBD → CMA), exported, and
imported **only** by panfrost.

- **Mapping lifetime is properly refcounted.** `panfrost_gem_mapping` is a kref;
  release runs `panfrost_mmu_unmap()`, removes the `drm_mm` node, then drops the
  GEM reference, and `panfrost_gem_free_object()` `WARN_ON_ONCE`s if any mapping
  survives. No leak path found.
- **Imported pages cannot be freed under the GPU.** The importer holds a dma_buf
  reference, which holds the exporter's GEM object, which holds the CMA
  allocation.
- **The CMA-migration hypothesis is DEAD.** Two independent reasons. An
  allocated CMA buffer is out of the buddy allocator and is not a migration
  candidate. And panfrost's own heap pages — the only movable-looking memory it
  maps — come from `drm_gem_shmem_create()`, which does
  `mapping_set_gfp_mask(..., GFP_HIGHUSER | ...)` **without `__GFP_MOVABLE`**,
  with a comment saying in as many words that MOVABLE "conflicts with CMA...
  if you're going to pin these pages". The `mig_delta` counter stays as
  background noise; it is not evidence and should not be cited as such.
- **`get_pgsize()` cannot over-map.** It returns 2 MiB only when the address is
  2 MiB-aligned *and* `size >= SZ_2M`, and `*count` is an integer division of
  `size`, so a mapping never runs past its sg entry.

**The fact that matters: neither crash log contains a single panfrost MMU
fault.** No `Unhandled Page fault in AS%d`, no MMU messages at all, in `expJ` or
`expK`. The GPU never touched an unmapped VA. So this is **not** "the GPU
escapes its page tables" — it is writing through mappings the driver installed,
which means either those mappings point somewhere they should not, or the page
tables themselves were already corrupted by the first event in a chain.

Two real defects found on the way, both worth reporting upstream, neither
matching our symptom:

1. **A failed GPU mapping is silent.** `mmu_map_sg()` discards
   `ops->map_pages()`'s return, and `panfrost_mmu_map()` returns 0
   unconditionally. Worse, on failure `mapped = max(mapped, pgsize)` fabricates
   forward progress, so `iova`/`paddr` advance as though the map succeeded and
   the region is left with a hole. Would surface as MMU faults, which we do not
   have.
2. **`panfrost_mmu_map()` hardcodes `IOMMU_CACHE` for every BO, including
   imports.** Our AFBD buffers come from `drm_gem_dma`, i.e. `dma_alloc_wc` —
   *write-combine, non-cached*. So the same physical pages are mapped
   non-cacheable by the display and CPU and cacheable by the GPU. On ARM,
   mismatched memory attributes for one physical address are architecturally
   unpredictable. This is a genuine bug in our configuration; its expected
   symptom is torn or stale pixels rather than corruption of unrelated memory,
   so it does not obviously explain the crash — but it is wrong regardless.

### Patch 0053 was written and tested — it does NOT fix the corruption

The cacheability mismatch is real, and both ends of it were verified rather than
assumed. `drm_gem_dma_create()` takes the `else` branch to `dma_alloc_wc()`
(our AFBD driver never sets `map_noncoherent`), so the scanout pages are Normal
Non-cacheable. Neither `gpu@1800000` nor `display@5600000` declares
`dma-coherent`, so `pfdev->coherent` is false. Our Mali is a **G31** and
Allwinner does not set `GPU_QUIRK_FORCE_AARCH64_PGTABLE`, so panfrost uses
`ARM_MALI_LPAE`, where `IOMMU_CACHE` selects `ARM_LPAE_MAIR_ATTR_IDX_CACHE` →
`ARM_MALI_LPAE_MEMATTR_WRITE_ALLOC`. Cacheable on one side, non-cacheable on the
other, same physical pages.

Patch 0053 drops `IOMMU_CACHE` for imported BOs. **The GPU arm still panicked,
at 75 s** — squarely inside the 40–90 s baseline.
`docs/reference/expM-0053-noncached-imports-still-crashes.log`.

So the mismatch was a real bug and is now fixed, but it is not the corruption.
The patch is worth keeping on its own terms — aliasing one physical address with
mismatched cacheability is architecturally undefined on ARM regardless of
whether it is what is killing this board — but it buys no stability here.

A mechanism worth recording, because it was considered and does *not* hold: a
cacheable GPU mapping could leave dirty L2 lines that get written back after the
buffer is freed and its pages recycled, which would look exactly like our
symptom. It is guarded. `panfrost_mmu_unmap()` calls `panfrost_mmu_flush_range()`,
whose `AS_COMMAND_FLUSH_PT` (0x04) is documented in `panfrost_regs.h` as "flush
all L2 caches then issue a flush region command", and `panfrost_mmu_disable()`
issues a full `AS_COMMAND_FLUSH_MEM` when an address space is released.

### What the crash site is now telling us

The last two crashes are the **same site**, which is new — every earlier run had
a different victim:

```
CPU 1  Comm: sugov:0    pc : ccu_helper_wait_for_lock+0x54/0xbc
   ccu_pll_notifier_cb  <- clk_change_rate <- clk_set_rate
   <- dev_pm_opp_set_rate <- __cpufreq_driver_target <- sugov_work
```

That is the **CPU DVFS path**: schedutil changes frequency, the sunxi-ng PLL
notifier polls a lock bit through `common->base`, and the dereference faults.
In `expK` that pointer had its high half corrupted (`faef8000…`); in `expM` it is
a well-formed vmalloc-range address that takes a **level 3 translation fault**,
i.e. plausibly a corruption that happened to land back inside the vmalloc range
at an unmapped page.

Do not over-read the repetition. GPU load drives constant frequency changes, so
this path runs hot and dereferences a long-lived pointer — a busy target rather
than necessarily a meaningful one. But `ccu_common` is long-lived driver data,
not a recycled allocation, which makes it a slightly different class of victim
from the `task_struct` and `pool_workqueue` seen earlier.

Still **zero panfrost MMU faults** in this run, as in every other.

### ⚠ The carveout experiment ran, and it REFUTES the 2x2 above

Patch 0054 gives the AFBD driver a 64 MiB `no-map` `shared-dma-pool` at
0x70000000 as its scanout source, with mpv and panfrost otherwise untouched.
**It crashed at ~31 s**, in `pwq_dec_nr_in_flight` — a `pool_workqueue`, which
is the very first victim this investigation ever saw.
`docs/reference/expN-carveout-scanout-still-crashes.log`.

The arm was valid, and this was **proven rather than inferred**, because a
silent fallback to CMA would have looked exactly like a clean result
(`docs/reference/expN-carveout-buffers-proof.txt`):

```
CmaFree_before=130688kB / CmaFree: 130688 kB     <- flat; the CMA arm dropped to ~112,544
dma_addr=0x0000000071000000  size=3723264        <- all three scanout FBs
dma_addr=0x0000000070c00000  size=3723264           inside the 0x70000000 pool,
dma_addr=0x0000000070800000  size=3723264           on 4 MiB slot boundaries
panfrost-job: 3785                               <- the GPU really was rendering
```

There is also no silent-fallback path to worry about by construction: once
`of_reserved_mem_device_init()` succeeds, `dma_alloc_wc()` on that device goes
through `dma_alloc_from_dev_coherent()`, which fails with ENOMEM rather than
reaching for CMA.

**So "the corruption needs panfrost rendering into a CMA-backed scanout buffer"
is wrong, and the table that concluded it is superseded.** The CMA half does not
survive. Corrected:

| renderer | scanout | result |
| --- | --- | --- |
| mesa/GBM via panfrost (`mpv --vo=gpu`) | CMA | crash, 40–90 s |
| mesa/GBM via panfrost (`mpv --vo=gpu`) | **carveout** | **crash, ~31 s** |
| CPU (`mpv --vo=drm`) | CMA | clean, 2406 s |
| `gles-play` (minimal GLES) | carveout | clean, 480 s |

Where the scanout buffer lives is **not** the variable — that idea has now been
tested directly and failed. What survives every run is narrower and simpler:
**panfrost doing real rendering work**. The two clean arms are the two where the
GPU either never ran at all, or ran a trivial program.

That also demotes run D. It was read as "GPU + carveout is clean", but it used
`gles-play`, which does far less GPU work than mesa driving a full GL
compositing path with a growable tiler heap. Its 480 s may be low stress rather
than a protective memory configuration, and it should no longer be cited as
evidence that the carveout protects anything.

### What is still standing

- **panfrost doing substantial rendering is necessary.** `--vo=drm` ran 2406 s
  with 143,646 scanout commits and `gpu_delta=0`.
- **cedrus, VA-API, mpv/ffmpeg, the shim, AFBD/KMS scanout, and the scanout
  memory source are all excluded.**
- **The GPU never faults.** Zero panfrost MMU faults across every crash.
- **The import path reads clean**, and `IOMMU_CACHE` on imports (a real bug,
  fixed by 0053) was not it.

The next thing to separate is the one difference left between the crashing and
clean GPU arms: mesa/GBM importing a `card1` dumb buffer into panfrost, versus
`gles-play` rendering into a `sunxi-scanout-dmabuf` export. Both use panfrost;
only one crashes. Either the import/export pairing matters, or — the duller and
now more likely reading — it is simply the *amount* of GPU work, in which case
the question becomes what panfrost does under load that corrupts memory without
ever raising an MMU fault.

### A hypothesis this investigation has been mis-reading: DVFS, not DMA

Worth stating plainly because it reframes everything above, and because the
evidence for it has been sitting in the traces being explained away.

**The last two crashes are inside the CPU DVFS path**, not merely near it:

```
ccu_helper_wait_for_lock  <- ccu_pll_notifier_cb <- clk_change_rate
<- clk_set_rate <- dev_pm_opp_set_rate <- __cpufreq_driver_target <- sugov_work
```

That was dismissed as "schedutil runs hot under GPU load, so it is a busy
target". That reasoning is only sound if the corruption is independent of what
the CPU is doing. If instead the **frequency/voltage transition itself** is the
corrupting event, then faulting inside the transition code is not coincidence,
it is the signature.

The whole investigation has assumed a *device writing to memory it should not*.
Every result is at least as consistent with **marginal DVFS** — a voltage or
PLL transition that is not stable under a heavy load, producing bit flips:

| observation | DMA-write reading | DVFS reading |
| --- | --- | --- |
| different victim every run | stray target address | flips land anywhere |
| KASAN blind | device DMA is not instrumented | not a CPU store at all |
| no IOMMU fault, ever | the write bypasses that master | nothing is translated |
| **no panfrost MMU fault, ever** | awkward — needs a valid mapping | expected |
| kernel + userspace faulting together | one wide DMA burst | expected |
| `ffff` → `faef` in a pointer | pixel data | **three bit flips (XOR 0x0510)** |
| `ffff8000` → `00000000` | black pixels | a flipped/zeroed half |
| needs heavy GPU load | GPU is the writer | GPU load drives thermals, the Mali rail, and constant CPU OPP changes |
| scanout memory source irrelevant | awkward — refuted 0054 | expected |
| `--vo=drm` clean over 2406 s | no GPU DMA | **the weak point: CPU rendering is also heavy load** |

The last row is the honest objection: software rendering pegs the CPU, which
should exercise CPU DVFS hard, and it ran 40 minutes clean. But it never
touches the **Mali rail** (`mali-supply`) or panfrost's devfreq, and it draws
far less total power, so it stresses a different transition and a different
thermal envelope.

`ffff` → `faef` deserves emphasis. As pixel data it is arbitrary. As
corruption it is `XOR 0x0510` — bits 4, 8 and 10 of a 16-bit field, with the
rest of the 64-bit pointer intact. A DMA burst overwriting a word would not
usually leave 13 of 16 bits correct.

**The test is cheap and needs no rebuild.** Pin both rails and re-run the mpv
GPU arm:

```bash
echo performance > /sys/devices/system/cpu/cpufreq/policy0/scaling_governor
echo performance > /sys/class/devfreq/1800000.gpu/governor
```

If the crash goes away with frequencies pinned, this is a power/clock
integrity problem and not a memory-corruption bug at all, and the whole
`cedrus / IOMMU / panfrost / CMA` line of enquiry has been chasing a symptom.
If it still crashes on schedule, DVFS is excluded properly rather than by
assumption, which it never has been. Note the earlier "DVFS was ruled out"
in the roadmap refers to the **SDIO wedge**, a different bug, and does not
transfer.

### It ran, and it is the first thing that has ever changed the outcome

**20 minutes clean on the arm that dies in 40–90 s.**

```
SOAK DONE vo=gpu t=1205s deaths=0 ve_delta=0 gpu_delta=587576 afbd_delta=71742
```

587,576 GPU interrupts and 71,742 scanout commits, `deaths=0` throughout, zero
crash patterns on the serial capture, board still up afterwards with no reboot.
`docs/reference/expP-cpu-pinned-20min-clean.log`. Against a baseline of n=3
crashes at 40 s, ~60–90 s and 75 s, this is the **first intervention in the
entire investigation to move the crash latency at all.**

**But it is confounded, and the `khz=` meter is what caught it.** The
`performance` governor did *not* hold 1416 MHz: thermal throttling pulled the
CPU to 1200–1296 MHz within about two minutes and held it there at 78 °C. So
the run changed two things at once — far fewer frequency transitions **and**
never reaching the top OPP. Had the heartbeat only recorded the governor name,
this would have been written up as "pinning fixes it", which is not what
happened.

### The vendor bins its CPU per die, and we do not

Read out of the stock DTB (`local/h713-lab/analysis/board-a-stock-20260622/`).
The vendor's table is not a plain `operating-points-v2`:

```
cpu-opp-table {
	compatible = "allwinner,sun50i-operating-points";
	nvmem-cells = <&speed>;   nvmem-cell-names = "speed";
```

An efuse selects a **speed bin**, and every OPP carries a voltage *per bin*
(`opp-microvolt-0x00010042`, `-0x0002001f`, …). A bin whose entry reads
`microvolt = 0` does not get that OPP **at all**. There are two ladders:

| bin family | top OPP the vendor allows |
| --- | --- |
| `…0042` / `…0043` | **1320 MHz @ 1100 mV** — 1392, 1416 and 1512 all unsupported |
| `…001f` / `…002f` / `…0040` | 1416 MHz @ **1060 mV**, 1512 MHz @ 1100 mV |

Ours is one fixed table applied to every die, with no efuse read;
`CONFIG_ARM_SUN50I_CPUFREQ_NVMEM` is not even enabled, though mainline carries
that driver for h6/a100/h616/h618/h700.

| freq | ours | vendor |
| --- | --- | --- |
| 792 | 900 mV | 900 mV ✓ |
| 1008 | 940 | 940 ✓ |
| 1104 | 960 | 960 ✓ |
| 1200 | 1000 | 1000 ✓ |
| 1296 | 1060 | 1060 as `default`; **unsupported** for `…0042/0043` |
| **1416** | **1100 mV** | **in neither ladder** — fast bins use 1060 mV, slow bins do not run it |

The low half of our table is vendor-exact, so it was derived properly. The top
entry is the outlier: 1416 MHz at 1100 mV is a point the vendor never programs
on any bin.

**And the efuse suggests this die is a slow bin.** SID word 0 reads
`0x03400042` — low half `0x0042`. Treat that as *suggestive, not proven*: it is
a pattern match against the vendor's key suffix, the high half (`0x0340`) does
not correspond to any vendor key prefix, and the real extraction lives in the
vendor cpufreq driver, which has not been disassembled. But if it holds, we have
been running a 1320 MHz-max die at 1416 MHz.

That would explain the whole shape of this bug without any rogue DMA: an
out-of-spec top OPP under sustained GPU + display load produces bit flips, which
land anywhere, which is why the victim is different every run, why KASAN and
both IOMMUs see nothing, why kernel and userspace fault together, and why
`ffff` → `faef` is three flipped bits rather than an overwrite.

### VALIDATED — 45 minutes clean on the built kernel (2026-08-22)

The fix is patch 0055: drop the 1416 MHz OPP. On a kernel actually carrying
it — `scaling_available_frequencies` ending at 1296000 with no sysfs override —
the GPU display arm ran:

```
SOAK DONE vo=gpu t=2707s deaths=0 gpu_delta=1316959 afbd_delta=161473 mmu_delta=0
=== SURVIVED after 2820 s (47.0 min) ===
```

Zero crash patterns on the console, 90 heartbeats with no gaps, no mpv deaths,
board up 52 minutes without a reboot, VA-API decode still 5/5 bit-exact.
`docs/reference/expS-0055-validation-45min-clean.log`.

**Both validity gates hold**, which is what makes it evidence rather than a
quiet run: `khz` shows 1104/1200/1296 and **never 1416**, so frequency
transitions were happening and the ceiling was genuinely in force; and
`afbd_rate` held 59/s throughout, so the panel was driven for the entire run.
2707 s is **3.2x the longest crash latency ever recorded** for this bug (848 s)
and roughly 30–65x what this exact configuration used to die at.

---

### It is the OPP, not the transitions

`schedutil` with `scaling_max_freq=1200000` — frequency changes **on**, top two
OPPs gone — ran **20 minutes clean**:

```
SOAK DONE vo=gpu t=1205s deaths=0 gpu_delta=577790 afbd_delta=71716
```

`docs/reference/expQ-cap1200-schedutil-20min-clean.log`, zero crash patterns on
serial. So the corruption is **not** caused by DVFS transitions — they ran
throughout. It is caused by reaching the top of our OPP table.

| arm | governor | ceiling | result |
| --- | --- | --- | --- |
| baseline | schedutil | 1416 | **crash, 40–90 s (n=3)** |
| pinned | performance | 1416 (thermally held ≈1200) | clean, 1205 s |
| capped | schedutil | **1200** | clean, 1205 s |

### The vendor cpufreq driver, disassembled

The vendor kernel is an **uncompressed 32-bit ARM image** (`boot_a-unpack/kernel`,
load base `0xC0008000`, found by counting literal-pool hits on known strings).
Its `sun50i_cpufreq_nvmem` probe is at `0xc074f808`; the efuse helper decodes as:

```asm
c074f89c:  bl   nvmem_cell_read(cell, &len)
c074f8bc:  cmp  r1, #4               ; len > 4 -> "Invalid nvmem cell length"
c074f8d8:  cmp  r3, r1               ; for (i = 0; i < len; i++)
c074f8dc:  ldrbne ip, [r5, r3]       ;   b = buf[i]
c074f8e0:  lslne  r0, r3, #3         ;   shift = i * 8
c074f8e8:  orrne  r2, r2, ip, lsl r0 ;   value |= b << shift
c074f8f0:  str  r2, [r7]             ; *out = value
```

**No shift, no mask, no combining with anything else** — the raw little-endian
cell value becomes the key, formatted `"0x%8.8x"` and installed as the OPP prop
name, so the core looks up `opp-microvolt-<key>`.

The `speed` cell is `vf-table@00`, `reg = <0x00 0x02>` — **2 bytes at SID offset
0**. This board's SID begins `42 00`, so our key is `0x00000042`.

**And that exposes a contradiction worth stating plainly: none of the 17 keys in
the vendor's CPU table can ever match a 2-byte cell.** Every one —
`0x00010042`, `0x000a0042`, `0x0002001f`, … — exceeds `0xFFFF`. So on this DTB
the per-bin voltages are unreachable for *any* die, and every die falls back to
the plain `opp-microvolt`, i.e. the `default` column.

That correction matters, because an earlier reading of this table ("slow bins
top out at 1320 MHz") was based on the bin columns and is **not** the operative
ladder. The operative one is:

| freq | vendor `default` | ours |
| --- | --- | --- |
| 1200 | 1000 mV | 1000 mV ✓ |
| 1296 | 1060 mV | 1060 mV ✓ |
| 1392 | 1100 mV | *(absent from our table)* |
| **1416** | **`<0x00>` — no voltage** | **1100 mV** |

So the durable statement is narrower and still damning: **1416 MHz carries a
nonzero voltage only under keys that can never be selected. Under the vendor's
actual working configuration it is never used at any voltage.** We ship it as
our top OPP, at 1100 mV, on every die.

Caveats kept: this is **board A**'s DTB; no board-B DTB has been extracted (only
the 51 GB raw images), and a different `vf-table` length there would change the
analysis. And the 1200 cap removed 1296 *and* 1416 together, while 1296 at
1060 mV matches the vendor exactly — so 1416 is implicated but not yet isolated.
The 1296-ceiling arm that separates them is running.

Two harness changes went in for this:

- **`VO=drm`** runs the same CMA-backed KMS scanout and page flips with mpv
  rendering on the CPU, so **panfrost never runs**. That control has never been
  run, and panfrost has been live in every run on record — clean and crashing
  alike — so it has never been isolated. It also maps the scanout dma-buf into
  its **own** MMU, which the sun50i IOMMU cannot see or fault on; if a stale one
  of those is the stray writer, no amount of soaking patch 0052 will ever show
  it. On this arm `gpu=` flat is positive proof the GPU never ran, exactly as
  `ve=0` was for cedrus.
- **`afbd_rate=`** meters scanout commits, so exposure stays measurable on an
  arm where the GPU is deliberately absent and `gpu_rate` cannot be the meter.
  Had it been there for this run, the collapse would have been obvious at t=60s
  rather than at t=600s.

### Operational lessons from the wedge

- **Do not probe a running soak.** A `/dev/mem` read of the AFBD registers hung
  in D state and cost a process; a `/root/*` glob typed at the serial console
  hung **the console shell itself**, which was the last interactive path in.
  Both were mine, and both were avoidable — the question they were asked to
  answer (is the scanout translated?) was already answered by the fault log.
- **There is no software reset from a wedged rootfs on this board.**
  `reboot`/`systemctl` are external binaries on the dead filesystem;
  `CONFIG_MAGIC_SYSRQ` is **off in the production config** (it is only in the
  debug fragments); and `exec 3>/dev/watchdog0` does not reset the board,
  almost certainly because systemd already holds and pets it. That leaves a
  physical power cycle. **Worth fixing before the next long run:** put
  `CONFIG_MAGIC_SYSRQ=y` in the shipping defconfig, or set
  `RuntimeWatchdogSec=0` so the watchdog can be claimed by hand.
- **Keep soak clips on tmpfs.** `/tmp` is a 467 MB tmpfs and the clip is 15 MB.
  Playing from `/var/tmp` puts the eMMC in the path of every display soak, which
  is how a storage bug got to masquerade as a display result.

---

# HANDOFF — start here, 2026-08-16

**The decision already made:** do not patch mpv, ffmpeg or GStreamer. Adapt our
own code to fit them. That is what makes libva-v4l2-request the route — it is a
VA-API *driver*, so stock players use it unmodified.

**The goal for the next session:** ~~get `libva-v4l2-request` decoding H.264 on
the VE, validated to bit-exactness with no display involved~~ — **done, see
RESULT above.** What remains is the display path, and it is deliberately the
next thing rather than something to have done at the same time: with decode
proven bit-exact on its own, a playback failure now has only one place to hide.

## Board state as of this handoff

| | |
| --- | --- |
| Kernel | `6.18.38`, built from the current series, **persisted** to the FAT (`fatwrite mmc 1:2 h713-kernel.fit`) and booting from it via `bootcmd` |
| Rootfs | **reflashed 2026-08-16** with `--profile dev`, which now also carries `vainfo` and `gdb`; `/` is 4.5 G with ~3.1 G free |
| KMS | `sun50i-h713-afbd` autoloads at boot, but **did not probe on this boot** — the panel needs the U-Boot incantation below, which decode work skips. `/dev/dri` therefore has only `card0`/`renderD128` (panfrost) |
| VA-API | driver installed at `/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so`, source + build tree in `/root/libva-v4l2-request` |
| `/root` | `video-test/` (the five M1 vectors, `reference-md5.txt`, `m1-decode-test.sh`, `va-decode-test.sh`), `libva-v4l2-request/`, `h713-va-bringup.tar.gz` |
| Missing for this work | nothing |

The vectors and the patched source were put there by injecting a tarball into
`rootfs.ext4` with `debugfs -w -R "write ..."` before `img2simg` — no root
needed, and it beats pushing 2.4 MB over a serial console after every flash.

**The panel needs `h713_disp auto 0x34 logo` at the U-Boot prompt before `boot`,
every single time.** Without it the KMS driver correctly refuses to probe. For
decode-only work you can skip it — nothing about VA-API needs the display.

## Operational gotchas this session cost time on

- **Serial writes must be paced.** Long command lines sent in one burst come
  back with doubled characters (`ddrivers`, `afbbd`) and the *shell runs the
  corrupted line*. `tools/serial/console.py` writes one character at a time and
  is the tool to use. This looks like a display artifact and is not.
- **`modprobe` is a silent no-op if a stale build is already loaded.** udev
  autoloads the module at boot, so after copying a new `.ko` you must `rmmod
  sun50i_h713_afbd` first or you will test the old one and misread the result.
- **Fastboot needs a cold power cycle.** Linux leaves musb in a state U-Boot's
  warm-reset path does not reinitialise, so `reboot bootloader` lands at a
  prompt with `No USB controllers found`. Flashing the rootfs therefore needs a
  human to pull power and press a key during the boot delay.
- **A FIT transfer over serial is ~12 minutes** at 10.8 KB/s. Budget for it.
- **mpv needs `--drm-device=/dev/dri/card1`** — panfrost holds minor 0 as a
  render-only node.
- **WiFi gets you a shell, and it cannot carry a file.**
  `tools/wifi/sta-connect.sh` turns the boot hotspot into a station on a real
  network; ssh then answers in 3.6 ms. But **two of two** sustained transfers
  wedged the board hard — no ssh, no serial, tty echo alive and the shell dead,
  recoverable only by pulling power. The second attempt showed the mechanism: a
  10.8 MB `scp` sat at **zero bytes for six minutes** with the board still
  responsive, then the console printed `cmd timed-out` (the aic8800 firmware
  command/confirm crash path already documented for this chip) and it went down.
  Use it for a shell and log reading; use the serial console or a baked rootfs
  for anything file-sized. This kernel also has no `CONFIG_MAGIC_SYSRQ`, so
  there is no software way back — which is why the KASAN fragment enables it.
- **The board's clock can be months behind**, which makes `meson setup` abort
  with `Clock skew detected` on files newer than "now". `date -u -s` from the
  host, then `hwclock -w`.
- **`/tmp` is a 467 MB tmpfs.** One 1080p vector decodes to 186 MB of raw NV12,
  so a ladder run fills it and ffmpeg's ENOSPC leaves a *truncated file with a
  valid md5* — which scores as a MISMATCH and reads as a decode bug. Write raw
  output to `/var/tmp`.

## The plan, in order

Steps 1–5 are **done** (2026-08-16); they are kept here because they are how you
reproduce the result, not as work outstanding.

1. ~~Rebuild and reflash the rootfs~~ — done. `tools/rootfs/build.sh --ssh-key
   KEY --kernel-tree build/linux-6.18.38-<hash> --profile dev --image-size 4G`,
   then `run fastboot_mode` at the U-Boot prompt and `fastboot flash UDISK
   rootfs.simg`. The 1.4 GB sparse image uploads in 45 chunks / **6 min**.
2. ~~Clone and fix the driver~~ — done, and the fixes are now a tracked series
   in [`patches/libva-v4l2-request/`](../patches/libva-v4l2-request/) on the
   pinned PR #38 head. There were **three**, not two: the missing `#include`,
   the vestigial `hevc-ctrls.h`, and the one that actually blocked decoding
   (patch 0003, the empty bitstream queue).
3. ~~Build on the board~~ — done, ~40 s. Build **on the board** and nowhere
   else: the driver's entry point is `__vaDriverInit_<major>_<minor>` taken from
   the libva version at build time, so a host build against libva 1.24 produces
   a `.so` the board's 1.22 loader will never call.
4. ~~`vainfo`~~ — passes; five H.264 profiles, `VAEntrypointVLD`, nothing else
   advertised.
5. ~~Decode to a file and check it byte-for-byte~~ — **5 of 5 bit-exact**, via
   `tools/video/va-decode-test.sh`.
6. **The display path** — attempted, and it plays; see the section above for the
   `--hwdec=vaapi-copy` requirement and the intermittent kernel panic that is
   now the open problem. Note `card1` only exists if the panel was brought up
   first with `h713_disp auto 0x34 logo` at the U-Boot prompt; on a decode-only
   boot there is no KMS device at all. To get back to that prompt without a
   human at the power switch, `tools/serial/reboot-to-uboot.py` reboots and
   types through the autoboot delay.

## What to expect to go wrong

The prediction below was written before step 5 ran. It was right that the
runtime was the risk and wrong about where: the failure was not in the codec
mapping at all, but in buffer allocation — the shim assumed a VA-API client
contract (a preallocated surface pool) that ffmpeg no longer follows. Worth
remembering as a pattern: *the error message named the codec, and the codec was
fine.* `strace` found it in one run; reading h264.c would not have.

> The compile is measured and safe; the *runtime* is not. PR #38 is unmerged
> third-party work whose own commit message says "POC", developed against H3/A64
> VEs rather than this one. Our cedrus is proven bit-exact through GStreamer, so
> the kernel half is sound — what is unproven is whether this shim drives it
> correctly. If step 5 produces frames that are *close but not identical*,
> suspect the reference-list or DPB mapping before suspecting the hardware.

That last sentence never got tested: the frames were identical on the first run
that reached the decoder. The DPB and reference-list mapping in PR #38 is
correct for H.264 on this VE across all five vectors — and the ladder is built
to exercise exactly that, since `v03` and `v04` are `bframes=2:cabac=1:ref=3`,
so reference list construction and reordering are under test rather than
assumed.

The display path in step 6 wants EGL-on-GBM against a KMS driver that only
scans out physically contiguous memory. GBM's split render/display arrangement
should handle it, but nobody has run it here.

**Fallback that needs none of this:** GStreamer already decodes H.264 *and*
HEVC on this hardware today. If the shim disappoints, a GStreamer sink wrapping
the proven `gles-play` path gets hardware-decoded video to the panel with no
third-party dependency at all.

---

## Why mpv cannot do it today

V4L2 has two decoder APIs and they are not interchangeable:

| | who parses the bitstream | who speaks it |
| --- | --- | --- |
| **Stateful M2M** | the kernel driver | ffmpeg's `h264_v4l2m2m`, i.e. mpv |
| **Stateless / Request API** | *userspace* | GStreamer's `v4l2codecs` |

cedrus is stateless, because the Allwinner VE has no bitstream-parsing firmware
and mainline will not put an H.264 parser in the kernel. Measured on the board:
`libavcodec.so.61` contains `v4l2m2m` symbols and **zero** `v4l2request`
symbols. So there is no configuration that connects mpv to this hardware — the
V4L2 Request hwaccels are an out-of-tree series that LibreELEC has shipped since
2018 and that is [still not merged upstream](https://ffmpeg.org/pipermail/ffmpeg-devel/2024-August/332034.html).

This is also why `gles-play` works: it drives GStreamer, which does implement the
stateless protocol.

## The chain that does work

```
cedrus → V4L2 stateless → libva-v4l2-request → libva → ffmpeg → mpv
```

Everything right of the shim is stock and unpatched. The shim is a *translator*,
not a decoder: by the time VA-API is called, ffmpeg has already parsed the
bitstream and hands over picture and slice parameters, which the shim converts
into Request-API controls. That is the whole job.

[bootlin/libva-v4l2-request](https://github.com/bootlin/libva-v4l2-request) is
that shim. mpv and ffmpeg on our image already have VA-API compiled in
(`mpv --hwdec=help` lists `vaapi (h264-vaapi)`), so only the driver `.so` is
missing.

---

## H.264: nearly free

Master is a red herring — last commit **2019-05-17**, using the pre-stabilization
`V4L2_CID_MPEG_VIDEO_H264_*` controls, and its structs differ from the 6.18 uAPI
exactly as you would expect from that break (12 fields moved out of
`slice_params`, `pred_weights` split into its own control, `v4l2_h264_reference`
introduced).

**But [PR #38](https://github.com/bootlin/libva-v4l2-request/pull/38) already did
that port.** It targets kernel 5.14, uses all eight
`V4L2_CID_STATELESS_H264_*` controls — precisely the set cedrus registers in
6.18 — and assumes slice-based decode, which is the only mode cedrus offers.

Built here against modern kernel headers to measure rather than guess:

| errors | cause | fix |
| --- | --- | --- |
| 5 × struct redefinition, 3 files | vestigial bundled `include/hevc-ctrls.h` colliding with now-upstream HEVC controls | don't compile `h265.c` |
| 1 × `implicit declaration of 'request_log'` | missing `#include` in `h264.c` | one line |

**Zero H.264 uAPI mismatches.** Two supporting checks also came back clean:
`vaExportSurfaceHandle` with `DRM_PRIME_2` is implemented, so decoded surfaces
export as dma-buf — the same path `gles-play` already proved on this hardware —
and the ARM detiling assembly is `#ifdef __arm__`-guarded at both definition and
call site, so aarch64 builds and negotiates linear NV12.

## HEVC: a rewrite, but the hardware earns it

PR #38 ported H.264 and left HEVC on the 2019 API. `h265.c` uses three old
controls; 6.18 and cedrus need **eight**.

| | H.264 (ported) | HEVC (not ported) |
| --- | --- | --- |
| controls | 8 of 8 present | **3 of 8** |
| `sps` | identical | 30 → 26 fields, 9 removed |
| `pps` | identical | 32 → 17, **20 removed** |
| `slice_params` | ported | 38 → 30, 16 removed; `data_bit_offset` → `data_byte_offset` |
| `decode_params` | ported | **entirely new**, 13 fields |
| `scaling_matrix` | identical | **entirely new** |
| `dpb_entry` | +2 fields | `rps`/`pic_order_cnt` → `flags`/`pic_order_cnt_val` |
| effort | one `#include` | ~400 lines of `h265.c` largely rewritten |

Two kinds of work hide in that table. Most is **mechanical**: every individual
boolean (`amp_enabled_flag`, `cabac_init_present_flag`, …) collapsed into a
single `flags` bitfield, so every assignment changes shape. The part needing
thought is the **reference picture set restructure** — per-slice `rps` became
per-frame `decode_params` carrying `poc_st_curr_before/after` and `poc_lt_curr`,
so the shim must map VA-API's `ReferenceFrames` plus
`RefPicSetStCurrBefore/After/LtCurr` into that shape. `entry_point_offsets`
(WPP/tiles) is a new control on top.

The saving grace: GStreamer's `v4l2slh265dec` is a working implementation of
those exact eight controls against this exact kernel. The semantics can be read
off rather than derived.

---

## HEVC decodes on this hardware — measured 2026-08-16

Worth establishing *before* costing a port, because if the VE could not decode
HEVC the whole question would be moot. It can, and with no driver changes:

| vector | result |
| --- | --- |
| `h01-640x480-main` (25 frames) | **bit-exact**, md5 `9ebd49ec…` = host software reference |
| `h02-1280x720-main` (25 frames) | **bit-exact**, md5 `c898a8f0…` = host software reference |
| throughput | **~550 fps** — 500 frames of 720p in 0.905 s including process startup |

Method is the M1 gate's: deterministic `testsrc2` source, Annex-B elementary
stream, decoded on the host to linear NV12 as ground truth, decoded on the
target through `filesrc ! h265parse ! v4l2slh265dec ! video/x-raw,format=NV12`,
md5 compared. Forcing NV12 is required for the same reason as H.264 — unforced
it negotiates the 32x32 tiled `ST12`, which is correct output that can never
match a linear reference. Vectors are generated by
`tools/video/make-test-streams.sh` (`h01`, `h02`).

`gst-inspect-1.0` registers `v4l2slh265dec`, and `/dev/video0` advertises `S265`
(HEVC Parsed Slice Data) alongside `S264`, `MG2S` and `VP8F`.

## HEVC port — Phase 0 done, the yardstick is re-established (2026-08-22)

Before touching `src/h265.c`, the instrument was rebuilt and re-verified, so a
later shim failure lands in one half rather than two.

**The vectors regenerate deterministically.** `h01` and `h02` rebuilt from
`make-test-streams.sh` reproduce the **exact reference md5s recorded on
2026-08-16** (`9ebd49ec…`, `c898a8f0…`), so today's runs are directly
comparable to the result that first established HEVC on this hardware.

**HEVC still decodes bit-exact on the VE, today**, through
`gst v4l2slh265dec`, with the video engine ticking **one interrupt per frame**
(75 for 75) — positive proof the hardware did the work rather than something
falling back to software. Gate: `tools/video/hevc-decode-test.sh`.

```
=== software control (the yardstick, not the subject) ===   3/3 PASS
=== gst v4l2slh265dec (the oracle: already known good) ===   3/3 PASS, ve+25 each
=== libva-v4l2-request through stock ffmpeg (the subject) === SKIPPED, no HEVC profile yet
```

### The finding that reshapes the port: entry point offsets are NOT optional

The plan had `V4L2_CID_STATELESS_HEVC_ENTRY_POINT_OFFSETS` as deferrable, on
the assumption our vectors used neither tiles nor WPP. **They use WPP.** x265
enables wavefront parallel processing by default and says so in its own tool
line (`frame threads / pool features : 5 / wpp(8 rows)`), so h01/h02 set
`entropy_coding_sync_enabled_flag` and every slice carries entry point offsets.

And cedrus genuinely consumes them: `cedrus_h265.c` copies them into a 4 KiB
entry-points buffer and programs it. So h01/h02 cannot decode through the shim
until that control is filled correctly — it moves from "defer" into the core of
the port.

**`h03-640x480-nowpp` was added for exactly this reason**: the same source with
`wpp=0`, no entry point offsets, bit-exact through GStreamer today. It is the
simplest stream that can possibly decode and therefore the right first
milestone, because it separates *"my control filling is wrong"* from *"I have
not implemented entry points yet"*.

### State of the code the port starts from

`src/h265.c` is still in the tree on the board (407 lines, three fill
functions), dropped from `meson.build` by our patch 0002 rather than deleted.
It sets **three** controls under the pre-stabilisation names
(`V4L2_CID_MPEG_VIDEO_HEVC_*`); the kernel wants `V4L2_CID_STATELESS_HEVC_*`.

cedrus registers all eight, but two need no work: `DECODE_MODE` already
defaults to `SLICE_BASED` and `START_CODE` to `START_CODE_NONE`, which is what
this hardware wants. So the port is **six** controls, not eight.

---

## HEVC DONE — all five vectors bit-exact through stock ffmpeg (2026-08-22)

```
h01-640x480-main            PASS (va) bit-exact, ve+25
h02-1280x720-main           PASS (va) bit-exact, ve+25
h03-640x480-nowpp           PASS (va) bit-exact, ve+25
h04-640x480-scaling         PASS (va) bit-exact, ve+25   H1: 10 pass, 0 fail
h05-640x480-scaling-custom  PASS (va) bit-exact, ve+25   VA1: 5 pass, 0 fail
```

(h04/h05 are the scaling-list vectors, added later the same day with the patch
that made them pass — see below. The first three were the state at the time of
the paragraph that follows.)

**The h03 stall was an uninitialised variable.** `context->h264_start_code`
decides whether the shim prepends an Annex-B start code to each slice, and it
is assigned **nowhere** — `h264_get_controls()`, which would set it, is defined
and never called. H.264 had been decoding bit-exact purely because the heap
happened to hold zero there.

cedrus accepts only `START_CODE_NONE`, for **both** codecs (`.max` and `.def`
are NONE for the H.264 control and the HEVC one alike). Setting the flag
explicitly to false fixes HEVC and makes H.264's luck deliberate.

### How it was found, and what that cost

Three hypotheses were tested and refuted from userspace before the kernel was
instrumented: an off-by-one in `data_byte_offset` (tested `+1` and `+3` — no
change), missing entry-point offsets (ffmpeg reports zero for WPP streams
anyway), and "x265 changed something else with `wpp=0`" (SPS, PPS and slice
headers all diff to zero). Each was cheap; none was the answer.

What ended it was `patches/kernel/0056`, dumping the controls cedrus receives
so the same stream could be run through GStreamer and the shim and diffed
directly. That produced three real bugs in one pass, and eliminated every
remaining difference as inert by checking it against what cedrus actually
consumes. **The lesson is to reach for the oracle's own values sooner** — the
one thing userspace could not show was what the working client sends.

The scaling-matrix idea was killed before a line was written, by checking that
`cedrus_h265_write_scaling_list()` is gated on
`V4L2_HEVC_SPS_FLAG_SCALING_LIST_ENABLED` and that our streams have it clear.
That reasoning was right about the *stall* and it also described, exactly, a
gap the gate was blind to — closed the same day, below.

### Scaling lists now pass, and the gate can finally see them (2026-08-22)

```
h04-640x480-scaling         PASS (va) bit-exact, ve+25
h05-640x480-scaling-custom  PASS (va) bit-exact, ve+25    H1: 10 pass, 0 fail
H.264 (unregressed)                                       VA1: 5 pass, 0 fail
```

The control was never set by either upstream tree —
`patches/libva-v4l2-request/0005` sets it. (That corrects "#44 dropped the
iqmatrix handling", above and in patch 0004: PR #38's own pre-#44 `h265.c`
mentions `iqmatrix` only in a declaration block it never reads, and sets three
controls, none of them a scaling matrix.) The gate could not have caught it,
because h01/h02/h03 all have
`scaling_list_enabled_flag = 0` and cedrus writes the scaling SRAM only when
that SPS flag is set. **A driver that fills nothing scores bit-exact on all
three.** Two vectors close the hole: `h04` (`--scaling-list default`: the SPS
enables lists and carries no data, so the HEVC defaults apply — non-flat from
8x8 up) and `h05` (explicit custom lists from
`tools/video/scaling-list-custom.txt`, non-flat at 4x4 as well, with DC
coefficients that differ from their own matrix, which is what `h04` alone is
blind to since every default DC is 16).

Both read `MISMATCH (va) ve+25` before the patch: 25 frames decoded on the
engine, to the wrong answer. Not a stall, not a rejected control — a completed
decode with the wrong quantisation. The oracle scored bit-exact on both
throughout, so **cedrus handles scaling lists correctly today**, custom DC
coefficients included; the entire gap was in userspace.

**A straight copy is correct, and that is not obvious.** HEVC codes scaling
lists in up-right diagonal scan order, so the natural assumption is that the
shim owes a permutation. It does not: `va_dec_hevc.h` says "Matrix entries are
in raster scan order which follows HEVC spec", the V4L2 control's kernel doc
says "expected in raster scan order" for every member, and ffmpeg's
`scaling_list_data()` (`libavcodec/hevc/ps.c`) already stores each coefficient
at its raster position, with `vaapi_hevc.c` copying the arrays across
unchanged. `h05` is the evidence rather than the reading: lists non-flat at
every size cannot come out bit-exact under a wrong permutation.

One version dependency worth recording: ffmpeg 6.1 and 7.1 both copy
`sl[size][matrix][j]` straight into the VA buffer. An older ffmpeg that
converted to diagonal order on the way out would silently produce wrong pixels
here, and there is no way for the shim to detect it.

### What remains, stated rather than hidden
- **Entry point offsets are not passed**, and do not need to be: ffmpeg reports
  `num_entry_point_offsets = 0` even for WPP streams, and h01/h02 are
  bit-exact regardless. Entry points parallelise WPP substreams; they are not
  required for correctness.
- **Two PPS flag bits are wrong** — `DEBLOCKING_FILTER_CONTROL_PRESENT` is set
  when the stream says 0 (#44 derives it because VA-API does not expose the
  field) and `UNIFORM_SPACING` is never set. Neither is referenced anywhere in
  cedrus, so both are inert here and were left alone rather than guessed at.
- **`h264_start_code = false` is right for cedrus and wrong in general.**
  Querying the per-codec `START_CODE` control is the correct form.
- ~~**A cedrus timeout wedges the VE for every client**~~ — **REFUTED
  2026-08-23 by direct test.** Ten consecutive watchdog timeouts, then the shim
  decodes bit-exact; the GStreamer oracle decodes bit-exact immediately after a
  timeout too. The engine self-recovers, and the "reboot between runs once
  anything has timed out" rule can be dropped. What DOES wedge it is **three or
  more concurrent decode clients**, which deadlock a client in
  `v4l2_m2m_cancel_job()` beyond the reach of SIGKILL — the observation that
  produced the original rule was almost certainly that, since a failing run
  leaves processes behind. See `docs/decode-production-readiness.md`.

---

## 10-bit does not work, and the blocker is in the kernel

`Main10` prerolls, reaches EOS in 40 ms having produced **zero frames**, and
forcing `P010_10LE` fails with `not-negotiated`.

The cause is not the H713. Our VE binds as `allwinner,sun50i-h6-video-engine`,
whose variant declares `CEDRUS_CAPABILITY_H265_10_DEC`, and the hardware
registers are there — `cedrus_regs.h` defines `VE_DEC_H265_SECOND_OUT_FMT_P010`
and `10BIT_4x4_TILED`, and `cedrus_h265.c` writes `VE_DEC_H265_10BIT_CONFIGURE`.
The kernel's uAPI even defines `V4L2_PIX_FMT_P010` and `NV15`.

But **`cedrus_video.c` exposes no 10-bit capture format at all** — its complete
list is `NV12`, `NV12_32L32`, `NV21`, `YUV420`, `YVU420` — and contains no
`bit_depth` handling. The capability bit only relaxes SPS *validation* in
`cedrus.c`; nothing downstream can express a 10-bit buffer, so nothing can
negotiate one.

So 10-bit HEVC needs a **cedrus patch** (add a 10-bit capture format gated on
`ctx->bit_depth`, wire the second-output-format registers), which is kernel work
in a staging driver — plausibly upstreamable, and independent of anything in
this document. Note also that the panel is 8-bit RGB after GPU conversion, so
10-bit buys source compatibility rather than visible quality.

---

## Scope, then

| item | effort | risk |
| --- | --- | --- |
| Build the shim for arm64, H.264 only | ~1 hour | low — measured, it's one `#include` and dropping `h265.c` |
| First decode, validated against the M1 ladder's references | a few hours | moderate — compiling is not decoding; PR #38 is unmerged WIP ("POC" in its own commit) developed against H3/A64-era VEs |
| mpv display path (`--hwdec=vaapi --vo=gpu --gpu-context=drm`) | unknown | **highest** — EGL-on-GBM against our KMS driver, never tried here, and the driver only scans out physically contiguous memory |
| HEVC in the shim | days | moderate — mechanical bulk plus the RPS restructure, with GStreamer as a reference |
| 10-bit HEVC | separate kernel work | unknown — no 10-bit format plumbed in mainline cedrus |

Recommended order: **decode-to-file first, display second.** Validate the shim
against the existing bit-exact references with no display involved, so a failure
lands in one half or the other rather than both.

And the standing alternative, which needs no shim at all: GStreamer already
decodes both H.264 and HEVC on this hardware today. What it lacks is only a sink
that reaches the panel without a CPU copy — see the GStreamer sink option in the
video-decode notes.
