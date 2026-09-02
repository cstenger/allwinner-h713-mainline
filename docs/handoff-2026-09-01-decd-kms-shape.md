# H713 handoff — 2026-09-01, late session

Two things happened. The runtime-IOMMU work **finished**: moving decoded video
renders on the panel with zero faults and no operator procedure. Then the
display architecture was settled. The first KMS/source-0 tests rendered
garbage, but they were incomplete queue submissions. Repeating Y, C and
VideoInfo across the complete four-slot ring made the known face render
correctly, and the Linux console restored exactly. The driver-owned shape is
now confirmed: one DRM driver, an RGB primary and a constrained fullscreen
NV12 plane implemented as an exclusive hardware mux.

---

## 1. KMS / video-plane experiment — false negative to confirmed handoff

The positive control passed immediately before the run: Chris confirmed that
the panel showed the Linux login prompt, proving KMS owned and drove the panel.
The staged command was then run once:

```sh
python3 tools/serial/console.py --wait 20 \
  'ARMED=yes /root/kmstest/kms-video-plane-test.sh 10'
```

The script programmed and read back the intended state:

```text
pre-test: ctrl=0x03000010 geom=0x043F077F/0x00420077 stride=0x00000780/0x00000780 ybase=0x00000000 gain=0x04000000 selector=0x29000000
WATCH THE PANEL: video plane for 10s, then the KMS route back
during test: ctrl=0x03000013 ybase=0x6C500000 selector=0x39000000
restoring the KMS route
restore state: ctrl=0x03000010 ready=0x00000000 gain=0x04000000 selector=0x29000000
```

Operator result: **the Linux login prompt was replaced by a garbage frame for
the test duration, then the prompt restored properly.** The known face did not
appear.

Post-test readback confirmed a clean restoration and no IOMMU transition:

```text
IOMMU_BYPASS  0x02010030 = 0x0000007C
video ctrl    0x05600010 = 0x03000010
video ready   0x05600014 = 0x00000000
video Y/C     0x05600070/84 = 0x00000000 / 0x00000000
KMS ctrl      0x05600140 = 0x03001901
KMS source    0x05600178 = 0x76D00000
chroma gain   0x05140508 = 0x04000000
selector      0x051C006C = 0x29000000
```

No new kernel warning or IOMMU fault appeared. The board remains on the same
RAM-loaded 0077 KMS kernel with the login prompt restored.

This resolves the staged experiment exactly as its outcome table predicted:

- KMS does **not** suppress source 0; changing the selector visibly displaced
  the console.
- The known DECD video-plane recipe does **not** render correctly alongside the
  live KMS RGB channel in this ownership/configuration.
- Therefore the simple “add DECD's register recipe as a second DRM plane” shape
  is **not confirmed**. The two channels fight or require additional shared
  state/commit sequencing that this complete standalone recipe does not supply.
- Restoration is reliable; the test did not wedge the display.

Do not rerun this unchanged test. Preserve it as the KMS-owned negative control
before choosing between fullscreen muxed planes, explicit channel handoff, or a
different DRM integration design.

### Explicit fullscreen handoff result — garbage from an incomplete ring

The first version of `tools/display/kms-video-handoff-test.sh`, SHA-256
`d8deb3954e55209f30d67d2ca9dd86dd6ee9ec119a0b3051deed9e6afe3ac304`,
was run once after an explicit operator **ready**. All commits were consumed:

```text
pre-test: video_ctrl=0x03000010 video_ready=0x00000000 kms_ctrl=0x03001901 kms_ready=0x00000000 kms_src=0x76D00000 selector=0x29000000
during test: video_ctrl=0x03000013 video_ready=0x00000000 kms_ctrl=0x83001900 kms_ready=0x00000000 ybase=0x6C500000 selector=0x39000000
restore state: video_ctrl=0x03000010 video_ready=0x00000000 kms_ctrl=0x03001901 kms_ready=0x00000000 kms_src=0x76D00000 selector=0x29000000
```

Operator: **garbage for the hold, a brief blue flash during restoration, then
the Linux prompt returned correctly.** Post-test registers exactly matched the
saved state, `IOMMU_BYPASS` remained `0x7c`, and no kernel warning or IOMMU
fault appeared.

This was not a repeat of the failed coexistence test. It committed the validated
disabled encoding `0x05600140 = 0x83001900` on KMS channel 1 before enabling
source 0, then performs the inverse exclusive transition during restoration.
Thus RGB and video fetch are never active together. It also verifies the frame
60 file's exact size and SHA-256 and rewrites it to `0x6c500000` with the mmap
writer before touching a display register.

The preflight on the live board matched every fail-closed expectation:

```text
frame size       1382400
frame SHA-256    70bddcf8d5c05caf4c6abd0d29399b7467f47caea470c80f7d3998831379cfec
selector         0x29000000
video ctrl/ready 0x03000010 / 0x00000000
KMS ctrl/ready   0x03001901 / 0x00000000
KMS source       0x76D00000
```

The result rules out concurrent RGB fetch as the explanation, but comparison
against the captured successful DECD state then found that this test was **not
a complete standalone source submission**. It populated only ring slot 0 and
left the dirty word and all VideoInfo addresses zero. A successful DECD static
submission had:

```text
0560006C  00000001                         ring dirty
05600070/74/78/7C  6C500000 in all slots  Y ring
05600084/88/8C/90  6C5E1000 in all slots  C ring
05600098/9C/A0/A4  4D941000 in all slots  VideoInfo ring
```

So source 0 could advance from the single valid address into uninitialised
slots. The earlier conclusion that garbage here necessarily meant a KMS
shared-state incompatibility is retracted; the queue shape was not equivalent.

The updated script preserves the first run as its default one-slot negative
control. `RING_ALL=yes` fills all four Y/C/VideoInfo slots, stages a valid final
VideoInfo page at reserved `0x4d941000`, and sets the dirty word before the
source commit. The board-verified inputs were:

```text
1b9c048ceb6f41af6e1f6fb56ab1202d80f1ed79292365e309884e707d4cdd74  kms-video-handoff-test.sh
3c225757336feee622d2c25c2d3e320a6282f16b99381f7601bc7377be0fff6b  f60.videoinfo
```

It was run once after another explicit operator **ready**:

```sh
ssh root@192.168.4.1 \
  'ARMED=yes RING_ALL=yes /root/kmstest/kms-video-handoff-test.sh 10'
```

All four Y slots read back `0x6c500000`, all commits were consumed, and the
dirty word had returned to zero by the active-state readback — the live service
accepted the queue. Operator result: **the face rendered correctly for the
hold, then the Linux login prompt returned correctly.**

Post-test state was exact: source control disabled, all Y/C/VideoInfo ring
registers and dirty zero, KMS control `0x03001901`, KMS source `0x76d00000`,
selector `0x29000000`, chroma gain `0x04000000`, and `IOMMU_BYPASS=0x7c`. No
kernel warning or IOMMU fault appeared.

This confirms the production architecture:

- the KMS driver may own AFBD while source 0 displays valid NV12;
- the RGB and video paths can be handed off exclusively and reversibly;
- a complete four-slot submission, not merely slot 0 plus source control, is
  required;
- the earlier two garbage results were test-shape negatives, not evidence that
  KMS and source 0 are fundamentally incompatible;
- a constrained fullscreen NV12 DRM overlay can retain the RGB framebuffer in
  software, stop its hardware fetch while video is selected, then restore it
  when the overlay is disabled.

Do not spend another operator observation on register-poke variants. The next
step is driver work: port this exact four-slot/VideoInfo/dirty transaction into
the KMS owner, initially accepting only fullscreen linear 1280x720 NV12.

### First DRM-plane implementation — built and staged, not yet booted

Out-of-series patch
`0078-EXPERIMENT-drm-h713-add-fullscreen-nv12-overlay.patch` now implements
that constrained plane in `sun50i-h713-afbd` without replacing the working
simple-pipe primary:

- one linear `DRM_FORMAT_NV12` overlay, exactly 1280x720 and fullscreen;
- exclusive RGB-off → source-0-on → selector-video handoff, and the exact
  inverse on disable;
- all four Y/C/VideoInfo queue slots plus the dirty latch;
- a coherent 4 KiB VideoInfo page whose embedded pointers use the display
  device's DMA address, so they can become IOVAs in the later IOMMU phase;
- contiguous PRIME imports only for this first hardware test. Fragmented
  Cedrus capture remains intentionally unsupported.

The patch applies after 0077. It passes strict `checkpatch`, the driver object
build, both DTB builds, a clean series-driven full kernel/module build and
`git diff --check`. `patches/kernel/series` was restored to end at 0073 after
the experimental build.

The resulting FIT and target-built atomic DRM client are staged but **neither
the FIT nor the client has been run**:

```text
e9df86f670260ee91e8be02cd1d11c3f6b532a8835ba4283e1582d58c9a5a3c0  /root/kmsnv12/h713-kernel-kms-nv12-0078.fit
47938e906c3dfbe42dcfade1fbac36624057ff90c1cf9cbbb878d6e5912d547f  /root/kmsnv12/kms-nv12-plane-test
280e5460577a4105d52c4c2d1b07a3ea012006f80bf8730ecec1a1bef0865f49  /root/kmsnv12/sunxi-scanout-dmabuf.ko
```

`kms-nv12-plane-test` imports the verified carveout frame as PRIME, creates a
two-plane NV12 framebuffer, enables the new plane through an atomic KMS commit,
then disables it and lets the driver restore RGB. It requires `ARMED=yes`.

### FIRST RUN — 2026-09-01 late. Client crashes; plane never displayed.

The 0078 kernel **was** booted (`#1 SMP Tue Sep  1 17:22:42 PDT 2026`) and the
driver binds correctly. Both planes register:

```text
plane[34]: plane-0    XR24, crtc-0, 1280x720   primary
plane[38]: video-0    crtc=(null)              new NV12 overlay, idle
```

Two client defects, in order.

**1. `msync` on a dma-buf mapping — fixed.** The first run died instantly with
`msync frame: Invalid argument`, before touching any display register. A dma-buf
mapping has no writeback path, so `msync(MS_SYNC)` returns EINVAL and the frame
is never flushed. Replaced with `DMA_BUF_IOCTL_SYNC` bracketing
(`SYNC_START|WRITE` before the read loop, `SYNC_END|WRITE` after), the same
idiom `decd-play.c` already uses. Rebuilt on the board; that specific failure is
gone.

**2. Kernel BUG on GEM_CLOSE — OPEN, this is the blocker.**

```text
kernel BUG at drivers/dma-buf/dma-buf.c:1589!
  dma_buf_vunmap_unlocked
  drm_gem_dma_free
  drm_gem_object_handle_put_unlocked
  drm_gem_handle_delete
  drm_gem_close_ioctl
```

Line 1589 is `BUG_ON(!iosys_map_is_equal(&dmabuf->vmap_ptr, map))` in
`dma_buf_vunmap`. `drm_gem_dma_free()` took the **imported** path
(`import_attach` set) and vunmapped a `dma_obj->vaddr` that does not match the
exporter's stored `vmap_ptr`.

**Operator saw NO change on the panel**, and every display register was still at
its idle RGB value afterwards (`0x05600010=0x03000010`,
`0x05600140=0x03001901`, `0x05600178=0x76D00000`, `0x051c006c=0x29000000`,
gain `0x04000000`), with `plane[38] crtc=(null)`. So the plane was **never
enabled** — the client failed before or during the atomic commit, jumped to its
cleanup path, and crashed there. Do not read the restored registers as evidence
that the handoff worked; nothing touched them.

The buffer path is the thing to look at. The client does not allocate a GEM
buffer: it wraps the carveout at `FRAME_PHYS` via `/dev/scanout-dmabuf`
(`SCANOUT_IOC_GET_FD`) and imports that dma-buf into the AFBD device with
`drmPrimeFDToHandle`. So the vmap contract between **`sunxi-scanout-dmabuf` as
exporter** and the AFBD driver's PRIME import is mismatched — either the
exporter's `.vmap` returns a pointer it does not record, or the importer is
using a `gem_prime_import_sg_table` variant that vmaps when the exporter cannot
support it. Check both before rerunning.

The kernel was left tainted `[D]=DIE` with a CPU that oopsed with IRQs disabled;
the board was rebooted and U-Boot republished the logo. **Do not trust any
measurement taken after that oops.**

## MOVING PLAYBACK WORKS AT PANEL RATE — 2026-09-01

`kms-nv12-plane-test` gained `MOVING=1`: it decodes with Cedrus and page-flips
the plane per frame, holding two surfaces (frame N is released only when N+2
arrives, since the hardware may still be scanning N until the flip retires).

```sh
ARMED=yes CEDRUS=1 MOVING=1 DECD_FREEZE_AT=0 \
  /root/kmsnv12/kms-nv12-plane-test /root/leota-720p.h264 10
```

```text
cedrus frame 0: dma-buf fd=11
FLIPS 299 in 5.01s = 59.71 fps
NV12 plane disabled; KMS RGB restored     rc=0
```

**59.71 fps against a 59.97 Hz panel — a flip every vsync.** It ended at 5 s
because it exhausted the 300-frame clip, not because it stalled. Operator: the
video moved as it should, **no tearing and no stuttering**, then the prompt
returned. No tearing means the flips are landing on vsync boundaries rather than
mid-scan — the failure a page-flip path can silently get wrong — so the plane's
commit path is correctly synchronised as well as fast enough.

**The 60 fps goal is already met; no optimisation is needed.** The two concerns
raised from code reading — `atomic_update` rewriting all per-stream registers
each commit, and the 50 ms sleeping `wait_ready` — do not bite: both fit inside
a 16.7 ms budget, consistent with DECD's measured 75 us ring-arm and 0.41 ms
submit. Do not spend time optimising them without a measurement showing a
problem.

**Operator saw it play ~2x too fast, and that is the test, not a defect.** The
appsink runs `sync=false` and the loop pulls as fast as the decoder delivers, so
a 29.97 fps clip presented every vsync plays at double speed. This measures the
ceiling; a real player pacing to PTS gets correct speed with 2x headroom. Same
distinction as `DECD_UNPACED` in decd-play.

**Not verified in that run:** 4 dmesg matches for `fault|BUG|Oops|WARN` were
left uninspected (the pattern also catches systemd noise). Confirm before
quoting the run as fault-free.

### FLIP TIMING MEASURED — drop-free, on every vsync

`kms-nv12-plane-test` now commits with `DRM_MODE_PAGE_FLIP_EVENT |
DRM_MODE_ATOMIC_NONBLOCK` and waits on the vblank event, so it measures when
each flip reached the screen rather than when the ioctl returned. The event wait
is bounded (200 ms poll) so a lost event cannot hang the test with the plane
still owning the panel.

```text
FLIPS 299 in 5.01s = 59.71 fps
FLIP_TIMING  n=298  mean=16.75ms  sd=0.03ms  min=16.51  max=16.99
FLIP_PERIODS 1x=298  2x=0  3x+=0  dropped=0 (0.00%)
```

**Every flip on its own vsync, zero drops, 30 us of jitter.** The operator's
"no tearing or stuttering" is now a measurement rather than an impression, and
page-flip events are confirmed working on a plane-only atomic commit, so the
driver's vblank wiring is sound.

The report deliberately prints the distribution and a per-period histogram, not
a mean: a 16.7 ms mean is equally consistent with every frame on its own vsync
and with half early, half doubled. Only `1x=298 2x=0` distinguishes them.

**Still open on measurement:** a PTS-paced run. This one was unpaced and played
~2x fast; whether pacing to timestamps holds 29.97 fps without dropping is
untested, and that is the actual playback case. Also unexamined:
`tools/display/tear-measure.py` and `edge-measure.py` from earlier display work.

### Measurement tooling — page-flip timing DONE above; remainder specified

The moving run proves the plane sustains panel rate. It does **not** establish
drop-free or tear-free presentation; "no tearing" is currently one operator
impression, which is worth having and is not a measurement.

**1. Page-flip event timestamps in `kms-nv12-plane-test` (do this first).**
The flip loop commits with flags `0` and no event, so it learns nothing about
when a flip actually landed. Commit with `DRM_MODE_PAGE_FLIP_EVENT |
DRM_MODE_ATOMIC_NONBLOCK`, then `drmHandleEvent()` with a
`page_flip_handler2` and record the vblank timestamp per flip. Report the
distribution of deltas, not just the mean:

  - a clean run is a tight cluster at ~16.68 ms (59.97 Hz);
  - any delta at or above 2 periods is a **dropped frame** — count them;
  - the spread is the **stutter** measure.

Fifteen lines or so, and it turns an impression into a number with no camera in
the loop. This is strictly better evidence than a recording for drops and
pacing.

**2. Check `tools/display/tear-measure.py` and `edge-measure.py` before writing
anything new.** They exist from earlier display work and the names suggest a
moving-edge methodology already built for exactly this question. If that tooling
is sound, use it rather than reinventing it.

**3. A PTS-paced run, which is the actual playback case.** The moving run was
deliberately unpaced to find the ceiling and therefore played ~2x fast. What is
untested is whether pacing to timestamps holds 29.97 fps without dropping —
exactly the gap that made `decd-play` report 27.1 fps against a 29.97 fps clip
while the hardware was nowhere near its limit.

**On recording the panel:** worth doing only as confirmation of a result already
obtained in software, never as the primary evidence. At 30/60 fps it is useless
(beat frequencies against 59.97 Hz). At 120 fps it is genuinely usable for
dropped frames, but for tearing it is confounded by rolling shutter — which
mimics tearing almost exactly — and possibly by temporal modulation in the light
engine, since this is a projector with a TI DLP controller in the path and it is
not established which stage drives the image. Settle that before trusting a
high-speed capture of this display. A recording's one unique value is catching
problems *downstream* of the DRM commit, which instrumentation cannot see.

### 1. Moving playback through the DRM plane — DONE, see above

Everything validated so far is a **static frame**. Page-flips, buffer rotation
and fence handling under the atomic API are untested. DECD did moving video, but
through a different submission path; do not assume it carries over.

Smallest useful test: extend `kms-nv12-plane-test`'s `CEDRUS=1` mode to keep
pulling samples and re-commit the plane per frame, holding each surface until
its flip completes. `decd-play`'s fence-driven retirement is the model — and the
lesson from it applies unchanged: a held surface is out of the decoder's CAPTURE
pool, so keep the hold shallower than the pool or the decoder starves.

### 2. Performance — two concrete targets, both visible in 0078 today

**`atomic_update` does the full setup on every commit.** It rewrites geometry,
both strides, the ring-mux word, all four Y/C/VideoInfo slots and the dirty
latch each time. For a page-flip only the Y/C addresses change. Everything else
is per-stream state, which is the same conclusion the DECD work reached
independently ("per-stream state, not a per-frame register dance"). Split the
first enable from subsequent flips.

**`h713_afbd_wait_ready()` uses the sleeping `readl_poll_timeout` with a 50 ms
timeout, called twice per enable.** At 60 fps the whole frame budget is 16.6 ms.
This has to become either a much tighter bound or vblank-driven before sustained
flipping is possible — and note it is a *sleeping* poll, so moving plane updates
into the vblank handler would make it a sleep-in-atomic bug. Design that
transition deliberately.

Reference points measured today: DECD's submit costs **0.41–0.47 ms/frame** and
is vsync-bound at ~60 fps, so the hardware is not the limit. The panel is
59.97 Hz.

### 3. Commit

Patches 0071–0073 are in series and validated. 0074 is dropped but retained.
0076 is validated; 0077–0080 are the KMS/IOMMU chain and out of series pending
the series-shape decision (KMS and DECD cannot both own AFBD). Nothing in this
session has been committed or flashed.

### 4. Audio

Untouched. `&codec`, `&i2s0/1/2`, `&spdif`, `&audio_bridge` and
`&dummy_cpudai` are all `status = "disabled"` in the board DTS, so it is a
greenfield bring-up rather than a repair.

### mpv TESTED — it ignores the plane. The gap is mpv, not the driver.

```sh
LIBVA_DRIVER_NAME=v4l2_request mpv --hwdec=vaapi --vo=drm \
  --drm-drmprime-video-plane=overlay --no-audio --frames=90 /root/leota-720p.h264
```

`rc=0`, no faults, display clean — and:

```text
VO: [drm] 1280x720 yuv420p          software format, not a hardware plane
vidctrl 0x03000010  sel 0x29000000  our NV12 plane never touched
```

No hwdec line at all. mpv fell back to software decode and `vo=drm`'s software
scaler, ignoring the overlay entirely.

**Why, and it is structural.** mpv 0.40.0 on this image has **no `drmprime`
hwdec** — only `vaapi`. `--drm-drmprime-video-plane` is only consulted on the
drmprime path, which needs frames in `AV_PIX_FMT_DRM_PRIME`; VA-API surfaces are
not that. And mpv's zero-copy VA-API display goes through `vo=gpu`, which wants a
render node on the KMS device that this display-only driver does not have
(`renderD128` belongs to panfrost). So neither of mpv's two zero-copy routes can
reach a DRM plane here.

The capability exists underneath — libva-v4l2-request surfaces *are* dmabufs and
`vaExportSurfaceHandle()` would yield the FDs. mpv simply has no path wiring
VA-API surfaces onto a plane.

Three ways forward, none needing kernel work:

1. **An ffmpeg/mpv build with the `v4l2request` hwaccel**, which outputs
   `AV_PIX_FMT_DRM_PRIME`, then `--hwdec=drmprime`. Most likely to work with the
   plane exactly as built, and keeps the "do not patch mpv" constraint.
2. **A GStreamer client** — `kmssink` already consumes dmabufs and drives KMS
   planes, and this project's own `decd-play` shows the decode half works.
3. Patch mpv to export VA-API surfaces as DRM PRIME. Excluded by the standing
   no-patching constraint, and the least attractive.

Option 1 is the one to try first, and it is a userspace build question. **The
driver side is done**: the plane exists, takes real fragmented Cedrus buffers
through the IOMMU, and renders them.

### CHAIN COMPLETE — a real Cedrus buffer renders on the DRM plane

**There was nothing to lift.** 0078's `atomic_check` never contained a
contiguity test; the restriction is the generic helper:

```c
/* drm_gem_dma_prime_import_sg_table() */
if (drm_prime_get_contiguous_size(sgt) < attach->dmabuf->size)
        return ERR_PTR(-EINVAL);
```

and `drm_prime_get_contiguous_size()` walks `sg_dma_address()` — **DMA
contiguity, not physical**. With the display IOMMU-attached by 0080, a
fragmented Cedrus buffer maps to one contiguous IOVA and the check passes on its
own. 0078's header described the helper's behaviour, not a gate it added.

`kms-nv12-plane-test` gained a `CEDRUS=1` mode that decodes with
`v4l2slh264dec`, holds the sample so the surface is not recycled, and hands the
decoder's own dma-buf FD to `drmPrimeFDToHandle`. Buffer provenance is the only
variable against the carveout run.

```sh
ARMED=yes CEDRUS=1 DECD_FREEZE_AT=60 \
  /root/kmsnv12/kms-nv12-plane-test /root/leota-720p.h264 10
```

```text
cedrus frame 60: dma-buf fd=21     a real decoder buffer
rc=0                                import succeeded, no -EINVAL
IOMMU faults: none.  L1PG_INT 0x00000000.
vidctrl 0x03000010  sel 0x29000000  clean restore
```

Operator: **the static face rendered, then the login prompt returned.**

So the full path works: hardware decoder → dma-buf → PRIME import → DRM NV12
plane → hardware YUV→RGB at scanout. No CPU copy, no GPU, no custom ABI, and the
decoder's physically scattered buffer handled by the IOMMU.

**What is left is mpv itself, and it is untested.** mpv's zero-copy output
previously failed with `Failed to find drmprime plane`; there is now a plane for
it to find. Whether mpv accepts it — fullscreen-only, NV12-only, exclusive mux,
no scaling — has not been tried. That is the next test, and it needs no new
kernel work.

### IOMMU LIFECYCLE PORTED — patch 0080, hardware-validated

The whole display path now runs through IOMMU translation, and the DECD
park/flip/unpark shape was **not** what was needed.

DECD imports buffers but never allocates them, so attaching it while bypassing
is harmless. The KMS driver allocates its own framebuffers: the moment the
device joins a paging domain, `drm_gem_dma` returns IOVAs, and under bypass the
hardware would scan an IOVA as a physical address — garbage from boot, before
any video frame exists. **There is no working bypassing phase, so there is no
runtime flip to port.** Translate from probe instead. 0078 already programs the
plane with source 0 disabled and enables it last, so nothing is in flight to
park either.

Three pieces, all in 0080: `.get_resv_regions` + the `domain_alloc_paging`
instance bind lifted from 0075 (absent in the KMS config); an identity map for
the adopted logo at `0x6c100000`; and
`of_reserved_mem_device_init_by_name(..., "framebuffer")` replacing the index-0
lookup, so listing the carveout in `memory-region` for its `iommu-addresses`
does not hijack dumb-buffer allocation.

Boot on `d463aa19adcc543194ed024918ed0206625714cfd6b83b386526416c51875da8`:

```text
platform 5600000.display: Adding to iommu group 0
BYPASS 0x02010030 = 0x00000078            master 2 translating from probe
framebuffers from the system CMA pool     by-name lookup correct
[drm] adopting 1280x720, source 6c100000  identity map held, no fault
KMS src 0x05600178 = 0xFFC00000           an IOVA, was 0x76D00000
```

Operator saw the logo through to the login prompt. **The console is being
scanned through the IOMMU.** Then the plane test:

```text
rc=0, no garbage frame, face rendered, prompt restored
IOMMU faults: none.  L1PG_INT 0x00000000 — never latched.
```

**Next:** 0078's contiguous-import restriction should now be liftable, because
PRIME imports resolve through the IOMMU and a fragmented Cedrus capture buffer
coalesces into one IOVA — the same mechanism that made DECD work. That is the
last known blocker between this and unmodified mpv on `--vo=drm`. Test it with a
real Cedrus buffer, not the carveout.

### RESOLVED — the NV12 DRM plane renders. 2026-09-01 late.

With patch **0079** added (`0077 + 0078 + 0079`, kernel
`#1 SMP Tue Sep  1 17:58:15 PDT 2026`, FIT
`6a4ea70e0c492ff2b72cb036c8eff3d5d6af41d0514a0392b1ddc2a3f2aef47d`) and the
client's `msync` replaced by dma-buf sync bracketing, the test passed on the
first attempt:

```text
rc=0
WATCH THE PANEL: /dev/dri/card0 plane 38 on CRTC 36 for 10s
NV12 plane disabled; KMS RGB restored
```

Operator: **the face appeared, correctly rendered, and the login prompt was
restored.** Zero kernel BUG/Oops/WARNING. `plane[38] crtc=(null)` afterwards and
every register back to idle RGB: `0x05600010=0x03000010`,
`0x05600140=0x03001901`, `0x05600178=0x76D00000`, `0x051c006c=0x29000000`,
gain `0x04000000`.

**This is the first driver-owned video plane on this hardware** — a real DRM
client, a real atomic commit, the driver performing the exclusive
RGB → video → RGB handoff itself, and clean teardown. The architecture is
confirmed end to end: one driver, RGB primary plus a fullscreen NV12 plane as an
exclusive hardware mux.

What remains before mpv can use it is unchanged and is listed under "Buffer
sharing" below: fragmented Cedrus imports, and porting the IOMMU lifecycle from
DECD into the KMS driver.

**ROOT CAUSE FOUND — it is one line in the driver.** `sun50i-h713-afbd.c:509`
uses `DRM_GEM_DMA_DRIVER_OPS_VMAP`, which sets
`gem_prime_import_sg_table = drm_gem_dma_prime_import_sg_table_vmap`. That
CPU-vmaps every PRIME import and stores the pointer in `dma_obj->vaddr`;
`drm_gem_dma_free` then vunmaps it on close, and `sunxi-scanout-dmabuf` does not
maintain a matching `vmap_ptr`, so the BUG fires.

**A scanout plane needs the DMA address, not a CPU mapping.** Change line 509 to
`DRM_GEM_DMA_DRIVER_OPS` (non-VMAP). `dumb_create` is unchanged, so fbcon on the
primary is unaffected — those buffers are allocated rather than imported and get
their `vaddr` from `drm_gem_dma_create`. This is the fix to try first; it is
smaller and more correct than reworking the client.

A dumb-buffer client (allocate on card0, write, `drmModeAddFB2` on that handle)
remains a good fallback if the import path still misbehaves, because it removes
the exporter/importer contract from the experiment and tests only the plane.

### Buffer sharing — what is and is not proven

| sharing | status |
| --- | --- |
| Cedrus → DECD | **proven**, zero-copy dma-buf FDs, 300 frames, bit-exact |
| carveout (`scanout-dmabuf`) → DRM plane | crashed; the vmap fix above |
| **Cedrus → DRM plane** | **untested, and it is the one that matters** |
| DECD + a DRM client at once | impossible and moot — 0068/0077 are mutually exclusive, and DECD is not a runtime component in the target design |

Cedrus → DRM plane is the mpv endgame and has two blockers beyond the vmap fix:

1. **0078 accepts contiguous PRIME imports only**, by its own statement, while
   real Cedrus capture buffers are fragmented — 56 physical breaks with a 32 KiB
   longest run in today's moving run.
2. **The IOMMU lifecycle lives in DECD, not in KMS.** Patch 0076's
   park → flip → unpark sits in `dec_frame_submit()`; the AFBD driver has none of
   it. Taking Cedrus buffers requires the same master-2 transition, the same
   "never enable source 0 without a frame address" rule, and the same
   unpark-after-`dec_reg_enable()` ordering. That ordering cost four wedged boots
   to establish — port it deliberately, do not re-derive it.

### Pre-test live state (retained for reproducibility)

### Live board state right now

- Booted from RAM: `/root/fits/h713-kernel-kms-video-plane.fit`,
  `#1 SMP Tue Sep  1 15:32:12 PDT 2026`, SHA-256
  `eb036d85e4c0214339cd1169ba243a93ccacd23e59f24451a61a430e2eeabb95`.
  Nothing flashed.
- That kernel carries out-of-series **0077**, which is the inverse of 0068:
  `display@5600000` **okay**, `dec@5600000` **disabled**. So the AFBD KMS driver
  owns the block and DECD is absent.
- KMS bound and **adopted** the U-Boot logo rather than resetting:
  `[drm] adopting 1280x720, stride 5120, source 6c100000`. `card0` is
  `sun50i-h713-afbd`, `card1` is panfrost.
- Frame 60 of the fixture is written into the adopted scanout carveout at
  physical `0x6c500000`, verified by reading it back through a separate mapping:
  SHA-256 `70bddcf8d5c05caf4c6abd0d29399b7467f47caea470c80f7d3998831379cfec`.
- The video plane is untouched by KMS and free:

```text
0x05600140  0x03001901   KMS channel control
0x05600178  0x76D00000   KMS scanning its own framebuffer
0x05600010  0x03000010   video plane DISABLED
0x05600070  0x00000000   video plane base zero
0x051c006c  0x29000000   selector on the KMS channel
```

### The positive control that was used

**Ask the operator what is on the panel before running anything.** It should be
a Linux console, not the U-Boot logo, because KMS bound and took over. If the
logo is showing, KMS is not driving the panel and the test is meaningless.

This is not optional ceremony. Two runs earlier today were watched against a
panel whose state was unknown, and U-Boot prints `boot logo published and
committed` on a black boot too, so the log is never the control.

### The command that was run

```sh
python3 tools/serial/console.py --wait 20 \
  'ARMED=yes /root/kmstest/kms-video-plane-test.sh 10'
```

It saves all nine registers it writes and restores them on exit, `SIGINT`,
`SIGTERM` and error. Then it programs the known-good video-plane state with the
plane addresses pointed at the carveout instead of a decoder buffer:

```text
0x05600020  0x02CF04FF   source size, 1280x720 minus one
0x05600024  0x002C004F   source block size
0x05600040  0x00000500   Y stride 1280
0x05600044  0x00000500   C stride 1280
0x05600070  0x6C500000   Y plane
0x05600084  0x6C5E1000   C plane (Y + 0xE1000)
0x05140508  0x144C0000   YUV chroma gain
0x05600010  0x03000013   source 0 enabled, format 0
0x05600014  1 -> 0       commit, consumed by hardware
0x051C006C  0x39000000   plane-1 downstream selector
```

### Original outcome table

| observation | conclusion |
| --- | --- |
| the face appears for 10 s, console returns | the video plane and a KMS-owned RGB channel coexist. The merged-driver design is confirmed and the remaining work is ordinary DRM plane work |
| console unchanged throughout | KMS is suppressing the plane — its bind-time behaviour or its atomic commits. A real constraint, found before any driver code |
| black or garbled | the two channels fight for the display. Also decisive; the script restores on exit |

The image is a **brightly lit face on a black background** (Y mean 27, max 139).
Dark, but unmistakable. A near-black panel is not a plausible rendering of it —
do not accept one as success. Frame 0 of the same clip *is* all black
(`3b3d249c…`); do not confuse them.

### Why this experiment and not "patch 0065 with the complete state"

0065 tried to make the KMS driver's **own RGB channel** interpret NV12. That
premise is dead: these registers belong to a *separate* video plane, which 0065
itself concluded correctly. It also never enabled the source, never sized it,
never set the chroma gain and never wrote the selector — five missing pieces,
not a tuning problem.

And the hardware question 0065 was reaching for is already answered: six runs
today lit the video plane and routed it via the selector while the logo channel
was live, then restored it. What is genuinely untested is doing that while **the
KMS driver owns the block**, which is exactly what is staged.

---

## 2. FINISHED TODAY — the runtime IOMMU route works

Full detail:
[`reference/iommu-runtime-flip-ordering-2026-09-01.md`](reference/iommu-runtime-flip-ordering-2026-09-01.md).
Operational handoff:
[`handoff-2026-09-01-iommu-runtime.md`](handoff-2026-09-01-iommu-runtime.md).

**Moving decoded video renders on the panel**: 300 frames, 27.12 fps, zero IOMMU
faults, no garbage, logo restored, driver-managed with no operator procedure.
The buffer that played had `breaks=56 longest-run=8(32KiB)` — *more* scattered
than the one that produced green corruption on a bypass kernel.

### The rule

Perform the master-2 `IOMMU_BYPASS 0x7c -> 0x78` transition while the DECD
**video source is disabled**. The source rests at base `0x00000000` with
inherited 1920x1088 geometry, so enabling it starts a raster scan through the
first ~2 MB of physical memory: harmless under bypass, L1-invalid the instant
translation arrives. Four runs that flipped with the source live faulted at
`0x29000`, `0x26000`, `0x81000`, `0x16000` — all inside that window.

**Patch 0076** makes this a driver behaviour: park source 0, flip, re-enable
after `dec_reg_enable()` gated on the Y ring holding a real address. Took three
attempts and the failures are instructive:

| version | unpark point | result |
| --- | --- | --- |
| v1 | right after the flip | fault at exactly `0x00000000` |
| v2 | after the enqueue, gated on the ring | no fault, timed out, source left parked |
| v3 | after `dec_reg_enable()`, gated on the ring | **no fault, correct picture** |

v2 is the useful one: it polled 200 ms and gave up, then a post-run read found
all four Y slots holding `0xFDC00000`. The poll was in the wrong **place**, not
too short — `dec_reg_enable()` at the end of `dec_frame_submit()` is what kicks
the block into consuming the queue. v3 reports `unparked onto 0xfe000000 after
75 us`: the ring arms on the first poll iteration.

### Retracted

- **"The IOMMU route is CLOSED — do not re-run it."** It works.
- **"One master-2 fault wedges AFBD for the boot, so budget one per boot."** The
  fault does wedge it, but it is avoidable. Design for zero.
- **Patch 0074's contiguous pool is required.** It is not, and it was **dropped
  from the series** — a permanent 64 MiB DRAM reservation buying nothing. Kept
  out of series as a fallback control for a bypass kernel.
- **The banding was a surface-reuse race.** It was not; none appeared in moving
  playback. Patch 0071 (release-fence UAF) stands as a correct independent fix.

---

## 3. PERFORMANCE — DECD is not slow, the fixture was

Measured with new `PHASE_MS` instrumentation in `decd-play`:

| per frame | paced (`sync=true`) | unpaced (`DECD_UNPACED=1`) |
| --- | --- | --- |
| rate | 27.10 fps | **49.32 fps** |
| `pull` (decode + PTS wait) | 32.87 ms | 0.15 ms |
| `submit` (DECD ioctl) | **0.47 ms** | **0.41 ms** |
| `reap` (wait for fences) | 0.05 ms | 16.20 ms |
| `other` (our validation) | ~3.5 ms | ~3.5 ms |
| stalls | 0 | 296 |

- **DECD costs 0.41–0.47 ms/frame.** Never the bottleneck.
- Every fps number this tool ever printed was measuring the fixture:
  `appsink sync=true` paces to the clip's 29.97 fps, and the freeze loop had a
  hardcoded 33 ms tick. That is why freeze runs measured *slower* (24.3–24.75)
  than moving ones despite doing no decoding.
- Unpaced, 80% of time is `reap` at 16.20 ms/frame ≈ 61.7 Hz against a 59.97 Hz
  panel. **DECD accepts a frame every vsync — it is 60 fps capable**, which is
  the best possible answer.
- The 29.95 → 27.1 "regression" is **not** the fence design (0.52 ms/frame
  total). It is ~3.5 ms/frame of fixed per-frame validation in the test player,
  identical in both runs. Not chased further because it vanishes when a real
  client drives a DRM plane instead of our validating harness.

---

## 4. THE SHAPE QUESTION — why the pending test matters

**DECD cannot help mpv as it stands.** It is a reconstructed vendor ioctl ABI on
`/dev/decd` — 112-byte descriptor, `FRAME_SUBMIT`, VideoInfo dma-buf, release
fences. Not V4L2, not DRM. Only our own `decd-play` can speak it.

The decode side is already standard and works: `libva-v4l2-request` drives
cedrus from **unmodified** mpv and ffmpeg. The gap is display-side, and
`vaapi-scope.md` names it exactly:

> mpv reports `Failed to find drmprime plane with idx=-2` today

`drmprime-overlay` is mpv's zero-copy no-GPU video output. It fails because
**there is no such plane**. That is why the working invocation is
`--hwdec=vaapi-copy` at 32 fps.

**A fact worth knowing: the current series has `display@5600000` disabled.** The
KMS driver is built `=y` but never binds — KMS was switched off to give DECD the
block, so there is no DRM target on the panel at all today. `kms-display.md`'s
working mpv-on-card1 predates that change.

So the shape is not DECD *versus* KMS. It is: **move what DECD taught us into
`sun50i-h713-afbd` as an NV12 plane.** Then unmodified mpv → VA-API decode on the
VE → dmabuf → DRM plane → hardware YUV→RGB at scanout, with no CPU copy, no GPU,
no custom player, and no DECD at runtime. DECD becomes the reference
implementation that recovered the register sequence.

Known costs, none of them investigated yet:

1. The KMS driver is a `drm_simple_display_pipe` — one CRTC, one primary plane,
   no overlays. A second plane means moving to a full atomic driver. This is the
   real engineering cost and it is larger than the register work.
2. DECD drives a four-slot Y/C ring off its own IRQ; a DRM plane does page-flips.
   Those must be reconciled, and 0071's fence work is relevant.
3. MIPS ownership is unsettled. Every DECD test parks the MIPS because real
   Cedrus traffic with it alive hard-locks the SoC. A production KMS driver has
   to answer this and nobody has designed it.
4. `0x051C006C` looks like a **mux**, not a blender — the video plane appears to
   replace the RGB channel rather than compose with it. Fine for fullscreen
   video, and consistent with stock, which wakes the GPU to composite video+UI
   into one buffer rather than blending in hardware. Not directly confirmed.

---

## 5. REPOSITORY STATE

Branch `h713-display-video-path`. **Nothing committed, nothing flashed.**

`patches/kernel/series` ends at **0073**. Verify this before building — a stale
backup re-added 0074 once during this session and had to be undone:

```text
0071-misc-decd-fix-release-fence-lifetime.patch
0072-misc-decd-refuse-a-non-contiguous-dma-buf-import.patch
0073-misc-decd-declare-the-single-mapping-dma-constraint.patch
```

Out of series, each with a header explaining why:

| patch | status |
| --- | --- |
| `0068-EXPERIMENT-decd-exclusive-owner-no-display-reset` | DECD owns AFBD; pairs with 0075/0076 |
| `0074-media-cedrus-allocate-capture-from-a-contiguous-pool` | **dropped**, fallback control only |
| `0075-EXPERIMENT-decd-enable-iommu-master-2-at-first-frame` | validated, needs 0076 |
| `0076-misc-decd-flip-the-iommu-with-the-video-source-parked` | **new, hardware-validated** |
| `0077-EXPERIMENT-enable-kms-alongside-the-video-plane` | hardware-validated KMS/source-0 owner state — inverse of 0068 |
| `0078-EXPERIMENT-drm-h713-add-fullscreen-nv12-overlay` | built and staged; first visible DRM-plane test pending |

**0068 and 0077 are mutually exclusive.** KMS and DECD share AFBD MMIO and SPI
110, so exactly one may be enabled.

### Building an experimental configuration

`build/build.sh kernel` is series-driven, so temporarily append the out-of-series
patches, build, then restore the series. The DECD+IOMMU configuration is:
series minus 0074, plus 0068, 0075, 0076 — with 0068 inserted after 0067.

### Tools changed

- `tools/video/decd-play.c` — `DECD_UNPACED=1` (removes PTS pacing and the freeze
  tick) and a `PHASE_MS` line attributing wall time. **Build it on the board.**
- `tools/video/decd-visible-sequence.sh` — now waits for the Y ring to arm before
  enabling the video source, instead of a fixed `sleep 0.2` that showed up to two
  seconds of garbage. `irq_count()` no longer sums the GIC hwirq number as a
  count (a clean boot read "142" instead of 0). The play-branch reorder made
  earlier in the session was **reverted**; the race it was written for does not
  exist.
- `tools/display/mem-write.c` — **new.** Writes a file into physical memory via
  mmap. Needed because `dd of=/dev/mem` fails with `EFAULT` on arm64 for no-map
  reserved regions; only mmap works.
- `tools/display/kms-video-plane-test.sh` — **new**, the pending experiment.
- `tools/display/kms-nv12-plane-test.c` — atomic DRM test for patch 0078; uses
  the contiguous carveout PRIME export and requires `ARMED=yes`.

### On the board

```text
/root/fits/h713-kernel-kms-video-plane.fit        eb036d85…  (booted now)
/root/fits/h713-kernel-decd-iommu-0076v3.fit      dbc679ce…  (DECD+0076, validated)
/root/iommu-0076v3/sunxi-decd.ko                  58d9ef3a…
/root/iommu-0076v3/sunxi-cedrus.ko                fae727a5…
/root/iommu-0076v3/sunxi-scanout-dmabuf.ko        280e5460…
/root/iommu-0076/decd-visible-sequence.sh         md5 f1781be1…  (updated wrapper)
/root/perf/decd-play                              instrumented player
/root/kmstest/{f60.nv12, mem-write, kms-video-plane-test.sh}
```

Networking works: the board is at **192.168.4.1** over its own AP, `scp`/`ssh` as
root. That is far faster than the 11-minute UART upload.

---

## 6. PROCEDURES AND TRAPS

- **Re-establish the positive control after every wedge.** Confirm the logo (or
  console) is visible *after* booting and loading modules, immediately before
  arming any visible test. U-Boot prints success on a black boot.
- **Never enable the video source with no frame behind it.** Garbage under
  bypass, AFBD-wedging fault under translation.
- **Verify the FIT hash, not just the modules.** `CONFIG_SUNXI_DECD=m` with no
  `CONFIG_MODVERSIONS` means a stale `.ko` loads silently against a new kernel.
  Boot with `modprobe.blacklist=sunxi_decd,sunxi_cedrus,sunxi_scanout_dmabuf` and
  `insmod` by path.
- **`absent=N` invalidates the `PHYS` line.** A 0074 build prints
  `contiguous=yes breaks=0` from *zero* resolved pages, because reserved no-map
  memory has no `struct page`. Only `absent=0` lines are real.
- **`DECD_FREEZE_AT` does nothing alone** — the discard is gated on `freeze &&`,
  so pass `DECD_FREEZE=1` too or you silently get a moving run.
- **`dd` cannot write `/dev/mem`** for no-map regions on arm64. Use `mem-write`.
- **Recovery from a master-2 fault:** reboot over serial; U-Boot republishes the
  logo and stops at `=>` with `bootdelay=-1`. Do not try to repair with another
  submission.
- **Do not run real Cedrus traffic with the display MIPS alive** — hard-locks the
  SoC, no watchdog. Park it; the Linux DECD IRQ owns the ring.
- **Do not unload `sunxi_decd` or invoke DECD PM-off after a test** — both can
  clock-gate hardware shared with the adopted logo path.

## 7. METHOD NOTES FROM THIS SESSION

- **Re-running a known-good control is what broke the deadlock.** Four visible
  runs went into diagnosing a race that did not exist. Re-running a recorded
  success, watching it fail, and finding the decoded output bit-exact proved the
  problem was in the setup rather than the theory.
- **Take the free measurement before the expensive observation.** A host decode
  of frame 60 (is the target even distinguishable from black?) and one register
  read (`0x05600070 = 0`) settled what four operator-watched runs had not.
- **Userspace completion is not proof of visible playback.** Every failed run
  printed `PLAY_COMPLETE frames=300` and restored plausible register values.
