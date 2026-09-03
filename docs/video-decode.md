# H713 video decode (VE / Cedrus → panel)

Started 2026-08-07, immediately after display bring-up completed. Operational
companion to [claude-display-handoff.md](claude-display-handoff.md), which is
what this work builds on.

Goal for this phase: **decoded video visible on the projector panel.**
**Reached 2026-09-01.**

---

## 2026-09-01 (later): moving decoded video on the panel, through the IOMMU

**300 frames of decoded H.264 rendered on the projector at 27.13 fps, zero
IOMMU faults, logo restored.** Operator-confirmed. This closes the corruption
investigation that began 2026-08-26.

The decisive measurement is the fragmentation of the buffer that played:
`pages=338 contiguous=NO breaks=56 longest-run=8(32KiB) absent=0`. That is
*more* scattered than the 31-break / 64 KiB buffer that produced green
corruption on a bypass kernel. Under translation it played perfectly, which
confirms root cause and fix end to end: DECD scans linearly from one base, and
translation is what makes a scattered buffer scannable.

**The whole difficulty was ordering, not addressing.** The master-2
`IOMMU_BYPASS 0x7c -> 0x78` transition must happen while the DECD **video source
is disabled** — only the inherited logo route live. The source rests at base
`0x00000000` with inherited 1920x1088 geometry, so enabling it starts a raster
scan through the first ~2 MB of physical memory: harmless under bypass, and
L1-invalid the instant translation arrives. Four visible runs faulted at
`0x29000`, `0x26000`, `0x81000` and `0x16000` — all inside that window, none
near the identity-mapped logo (`0x6c100000`) or the frame IOVA (`0xfe000000`).

Bench procedure: spend the flip with a **nonvisible** run first, then run the
visible test as a second session. Patch 0075 guards the flip with
`dec->iommu_runtime_enabled`, which persists until module unload or reboot.

Consequences for what is written below:

- **Patch 0074's contiguous pool is not required, and was dropped from the
  series on 2026-09-01.** Fragmented CAPTURE displays correctly through a single
  IOVA, so its 64 MiB permanent DRAM reservation bought nothing. The patch is
  kept out of series as a fallback control for a bypass kernel; the section
  below describing it is the record of that work.
- **The banding was never a surface-reuse race.** None appeared in moving
  playback. Patch 0071 stands as a correct independent fix.
- **"One master-2 fault wedges AFBD for the boot" is the wrong rule.** The fault
  does wedge it, but it is avoidable — design for zero faults, not one per boot.
- Any `contiguous=yes` reported by a 0074 build is **vacuous**: `absent=338`
  means pagemap resolved no pages at all, because reserved `no-map` memory has
  no `struct page`. Segmented builds report `absent=0` and are real.

**Patch 0076 makes that a driver behaviour and is hardware-validated.** It parks
source 0 across the transition and re-enables it after `dec_reg_enable()`, gated
on the Y ring holding a real address. Run as the *first* DECD session of a boot
with no operator procedure, both a frozen still and a 300-frame moving clip
rendered correctly with zero faults and restored the logo.

`decd-visible-sequence.sh` was fixed alongside: it enabled the video source at a
fixed `sleep 0.2`, long before any frame existed, so a `--freeze-at` run showed
up to two seconds of the source scanning low memory. It now waits for the ring to
arm. With that in place the moving run needed no park at all — the source was
already disabled at flip time — so the wrapper ordering is the mechanism and 0076
is the safety net. Keep both.

Full account, all six runs and the register evidence:
[reference/iommu-runtime-flip-ordering-2026-09-01.md](reference/iommu-runtime-flip-ordering-2026-09-01.md).
Operational handoff: [handoff-2026-09-01-iommu-runtime.md](handoff-2026-09-01-iommu-runtime.md).

---

## 2026-09-01: contiguous Cedrus CAPTURE hardware-proven

The route gap is closed and real decoder integration has begun.  A strict
target-side player now sends Cedrus-owned 1280x720 linear NV12 dma-buf FDs
directly through the reconstructed 112-byte DECD ABI, with no CPU pixel copy
and no Mali render.  A 300-frame nonvisual run completed at 29.95 fps and real
Y/C addresses cycled through DECD.  Two-second visible runs showed recognizable
moving decoded content and restored the logo.

Direct submission of segmented Cedrus buffers is not correct. Operator
recordings show horizontal bands that initially looked mixed from multiple
decoded pictures. Immediate sample return and deep retention were both tried,
but the fence and frozen-frame results below disprove reuse/timing; DECD is
instead scanning linearly beyond the buffer's first physical segment. Do not
use a live display MIPS for this test: one 30-frame real Cedrus preflight
hard-locked the SoC and required a power cycle. The Linux DECD IRQ owns the
address ring with MIPS parked.

**Fixed, and the fence works on hardware.** Patch 0071 fixes the
reconstructed release-fence lifetime — `frame_item_release()` signalled its
`dma_fence` and then `kfree()`d it while the returned `sync_file` still held a
reference — so the fence is finally usable as the retirement signal it already
was in timing terms.  `decd-play` now holds each sample until its fence signals,
with a bounded queue that fails loudly rather than reusing a surface DECD is
still scanning.  The eight-sample starvation also has a mechanism now: DECD
retires a frame only when a *later* frame displaces it, so a deep hold is a
circular wait, not simple exhaustion.

Measured: **299 of 300 surfaces retired on a signalled fence, zero stalls**, and
a cap sweep (2/4/6/8) shows `peak-held` saturating at **4** regardless — the hold
self-regulates to DECD's four-slot ring depth, so `cap=8` no longer starves the
capture pool at all. **But the picture did not improve** (`test_60`), so
premature surface reuse is eliminated as the cause. `DECD_FREEZE=1` then
resubmitted **one** complete, quiescent decoder buffer 89 times at a fixed
address: the image is **steady and corrupt**, which eliminates timing altogether
— not retirement, not producer readiness, not frame mixing, not a fetch race,
since DECD reads the same wrong thing deterministically. The fault is in what
DECD reads from a Cedrus buffer. Next steps are byte-level and cost no operator
time. That dump is done: the buffer read through the **same FD given to DECD**
is **bit-exact** against a host software decode (SHA-256
`3b3d249c…` both sides), so the NV12_32L32 tiling hypothesis is **refuted** and
the content and layout are correct. Content, layout and timing are now all
eliminated. The pagemap walk then found the cause: the decoder's buffer is
**338 pages with 31 breaks, longest contiguous run 64 KiB**, while
`dec_dma_map()` keeps only `sg_dma_address(sgt->sgl)` and the hardware scans
linearly from that single base. DECD starts correctly — `0x05600070` is exactly
the buffer's first page — then reads 51 of 720 luma lines and unrelated memory
for the rest, with chroma at `y + 0xE1000` landing outside the buffer entirely
(hence green). Carveout frames always worked because they are one segment.
Patch 0072 refuses a segmented import instead of corrupting silently, and 0073
declares the constraint (`dma_set_max_seg_size`) so the mapping is deterministic
rather than dependent on memory fragmentation.

**The bypass carveout control now passes with known-visible decoded content.**
The first attempt copied decoded frame 0 and appeared black, but host decode
showed that frame is itself black (`YAVG=16.0002`, `U=V=128`; NV12 SHA-256
`3b3d249c…`). `DECD_FREEZE_AT=60` was added so the diagnostic can discard
frames without submitting them and hold an exact later frame. The board's frame
60 dump is byte-for-byte the visibly nonblack host reference (SHA-256
`70bddcf8…`). On the bypass kernel, copying those bytes to physical
`0x6c500000` and resubmitting them 300 times produced an operator-confirmed
recognizable, apparently correct video still; the logo state returned after
restore. Therefore decoded content and all DECD route/layout programming are
good. **Physical-buffer provenance is the remaining direct-path fault.**

Patch 0074 implements the shortest path: a 64 MiB reusable
`shared-dma-pool` on the VE plus `DMA_ATTR_FORCE_CONTIGUOUS` on Cedrus's
CAPTURE queue only. The force attribute is necessary: with VE masters 0/1
behind the IOMMU, a pool alone can still be remapped from scattered physical
pages. The normal series and the out-of-series 0068 test configuration both
build cleanly.

The patch also passes its nonvisual hardware acceptance on a RAM-only boot.
Linux reserved the dedicated pool at `0x7c000000`, attached Cedrus to it, and
patch 0072 accepted a direct dma-buf import that it refused on the segmented
build. Frozen decoded frame 60 completed 90 submissions and its dump still
matched the host reference exactly (`70bddcf8…`). A separate 150-frame moving
run completed at 24.76 fps with 149 fence retirements, peak hold 4 and zero
stalls. The log contained no 0072 refusal, warning, or IOMMU fault; master 2
remained bypassed and the logo selector remained `0x29000000`. Userspace could
not read any pagemap PFNs on this image, so its `contiguous=yes` report is not
evidence; successful passage through 0072's full-length one-segment kernel
check is.

**Those final checks pass.** Direct frame 60 held for 300 submissions and the
operator reported, “It looked good”; the logo returned after the test. A
300-frame moving run then completed at 27.09 fps with 299 fence retirements,
peak hold 4 and zero stalls. The operator saw the short clip, noticed no issues,
and confirmed the logo returned. Three further consecutive 300-frame sessions
all completed at 27.09–27.12 fps with 299 fence retirements, peak hold 4 and
zero stalls. No new kernel message appeared, master 2 remained bypassed, and
the selector remained `0x29000000`. Patch 0074's bypass direct path is therefore
hardware-proven for a known-visible still, moving playback, repeated allocation
and teardown, fence retirement, and display-state restoration.

**The early-attachment 0069/0070 IOMMU route is closed; the runtime transition
it pointed at is not — and it works.** Attaching translated from probe
reliably coalesces the import but renders black with this adopted-display
configuration and no faults. The vendor DTB only describes the initial state:
master 2 starts in bypass (`<&mmu_aw 2 0>`), while reverse engineering shows HWC
calling `sunxi_enable_device_iommu(2, 1)` at the playback boundary. Patch 0075
models exactly that runtime transition, and **it is hardware-proven** — see the
2026-09-01 section at the top of this file. The one thing it needs that was not
obvious: the flip must land while the video source is still disabled.
Full account in [handoff-2026-08-31.md](handoff-2026-08-31.md) and
[reference/iommu-runtime-flip-ordering-2026-09-01.md](reference/iommu-runtime-flip-ordering-2026-09-01.md).

Complete measurements, artifact and recording hashes, current board state and
next steps:
[reference/cedrus-decd-first-visible-playback-2026-08-31.md](reference/cedrus-decd-first-visible-playback-2026-08-31.md).

---

## 2026-08-29: the premise is confirmed, and the stock diff is exhausted

Superseded by the 08-31 section above, which found the missing state and put a
frame on the panel. Kept because its eliminations still stand and are worth not
re-testing — but read its closing "the black is source 0's output not reaching
composition" as the working hypothesis of the time, not a conclusion: the actual
cause was inherited source geometry, a zero chroma gain and the plane-1
selector. Full account in [handoff-2026-08-29.md](handoff-2026-08-29.md).

**The no-GPU premise is measured, not inferred.** With stock Android playing
video and the player's transport controls auto-hidden, Mali runtime PM reads
`active +0 ms, suspended +15115 ms` over 15 seconds — the GPU is fully asleep
while video is on the panel. Measured with the controls *visible* it reads 100%
active, which is the player's UI, and a single sample would have supported the
opposite conclusion.

**Only AFBD is driven per frame.** Sweeping eleven register windows at idle twice
and during playback, the only video-driven registers are AFBD's Y bases
`0x05600070`-`7c` and C bases `0x05600084`-`90`, cycling as a ring. TVTOP, the
mixer, DE/OSD, LAYER, ROUTE, LVDS PHY, PLL, GE2D and the IOMMU show **zero**
registers differing between idle and playback. They are load-bearing but
configured once, so the per-frame surface is just AFBD's buffer slots.

**Overlays are a GPU composite on stock.** Video alone runs decoder → dma-buf →
AFBD source 0 → panel with the GPU asleep; video *with* UI wakes the GPU to
composite both into one buffer that AFBD scans out. There is no hardware
subtitle blending on this path.

**Every candidate difference has been forced onto working stock hardware and
none causes the black:**

| forced onto stock | result |
| --- | --- |
| bit 31 on `0x05600100`/`0x05600140`, committed | no effect |
| fmt 4 rather than stock's fmt 0, committed | tiled, half-height, colour-shifted |
| IOMMU master 2 bypassed | coloured static |
| mixer layer control, our value and zeroed, ±latch | no effect |

Since *every* way of breaking source 0 still puts something on the panel, the
black is source 0's output **not reaching composition** rather than a
misconfigured source. fmt 0 is still a real fix worth making — stock's value is
correct for NV12 and ours is not — but it is necessary, not sufficient.

**Two rules that change how to test here.** Writes to the AFBD block are **inert
until the per-register commit latch is pulsed** (control at `+0x00`, latch at
`+0x04`): an uncommitted write lands, reads back, holds indefinitely and does
nothing, so readback proves nothing. And the mixer, DE and TCON H/V totals are
**coupled** — changing two of three to match stock blanked the panel; the revert
restored it. Capture `0x05880020` on stock before revisiting that.

---

## 2026-08-26 correction: DECD is the vendor no-GPU display path

The older handoff below says DECD "has no job." That is now disproved by stock
Android: `hwcomposer.ares.so` calls `DECD_IOC_FRAME_SUBMIT` from
`DecoderDisplay::present()` for ordinary uncompressed video, passing an image
dma-buf plus a 32 KiB VideoInfo dma-buf. The missed ioctl is assembled as split
Thumb-2 `movw`/`movt` immediates, so the earlier byte search could not find it.

The photographed patch-0066 result remains useful, but only establishes that
the tested live OSD source fetched the NV12 bytes as packed 32-bit pixels. It
does not rule out DECD's distinct hardware YUV-to-RGB route. The corrected
112-byte ABI, metadata magic, and repeat-count offset are in patch 0067; the
mutually-exclusive, no-shared-reset test boot is patch 0068 (out of series).

That controlled boot was run on 2026-08-26. The request returned a real release
fence, the frame manager advanced, DECD/vsync ran at 59.7 Hz, the expected Y/C
and VideoInfo addresses reached its four-slot register file, and panfrost stayed
at zero interrupts. The panel still showed the U-Boot logo; hiding its serviced
packed-OSD channel showed black. Geometry correction did not expose DECD. So
the submission path works, but its output is not routed into the adopted
U-Boot display topology. Enabling DECD's stock internal blue generator while
the OSD was hidden also remained black for the entire observation. Because that
generator bypasses NV12 and VideoInfo, this isolates the failure to downstream
routing/plane topology rather than frame contents, format or metadata.

**The `/dev/ge2d` `0x4631` plan is withdrawn (2026-08-26, later).**
`tgd_put_plane_info()` was disassembled in full. It is the RGB OSD plane flip —
four colour formats, all RGB, no chroma plane, no DECD register anywhere in
`ge2d_dev.ko` — and it does what `sun50i-h713-afbd` already does every atomic
flip. Stock HWC pairs it with DECD because HWC has two layers to present, not
because it commits the video path.

What replaced it is better. The AFBD writeback engine in the same module
enumerates **three** sources with a uniform (enable, pixel format, size)
interface: `0x05600010` (bits 1:0 enable), `0x05600100` and `0x05600140`. Ids 1
and 2 are the OSD channels; **id 0 is the video source, and it is exactly the
register set DECD programs.** Patch 0066 wrote source 0's format byte and then
observed source 2's fetch, so it was never able to answer the YUV question.

**Tested 2026-08-26 and negative.** `tools/video/decd-enable-test.sh` set source
0's enable bits with DECD provably submitting at 60 Hz and valid Y/C in the
queue: all three values read back, and the panel did not change. Bits 1:0 are
writable and were never set, but setting them is not sufficient.

The finding that matters came from the test's own geometry check:
`dec_reg_video_channel_attr_config`, the only writer of the video source's
pixel-format selector, is **dead code in stock `decd.ko`** — no relocations
reference it and the module exports nothing. **So nothing on the ARM side
programs the video source's format**, and the component that does is almost
certainly the **MIPS firmware**, fed by DECD's VideoInfo dma-buf — which U-Boot
parks (`MIPS core quiesced`) on every boot we have tested. That predicts this
null and also explains why DECD's internal blue generator showed nothing.

Next work is CPU_COMM/VideoInfo, not AFBD registers. See
[ge2d-plane-open-re.md](ge2d-plane-open-re.md), "ioctl `0x4631` is the RGB OSD
flip". Historical conclusions below are retained as an audit trail, not as
current guidance.

### Where that went, 2026-08-28

Chased through, and the blocker moved. Full account in
[plane-brief-for-external-review.md](plane-brief-for-external-review.md) §0;
the short version:

- **ARM-side DECD submission is solid.** A diagnostic module that bypasses the
  reconstructed queue, programs all four hardware slots directly and masks the
  ARM DECD IRQ holds a frame indefinitely with the MIPS stopped. Nothing about
  the frame, format, stride, dma-buf or VideoInfo is the problem.
- **Routing is still absent, and it is downstream of fetch/format.** Source-0
  enable 1/2/3, mixer layer 0 (`0x0525c004: 0x1402 -> 0x1403`) and the fuller
  `0x1003` candidate were all negative, and so was the corrected internal-blue
  generator (`0x05600065[0]`) -- which bypasses Y, C, stride, dma-buf and
  VideoInfo entirely. Black in every combination.
- **Two candidate causes eliminated.** TVTOP's live route table already matches
  the authenticated firmware values exactly, so `dec_reg_top_enable()` is not a
  missing initialisation; and the stock-DT 200 MHz AFBD clock (we ran 100 MHz)
  makes no difference.
- **Releasing the MIPS under Linux is not the answer.** It reports running and
  then hard-locks the SoC -- Wi-Fi and serial with it. Shared ownership between
  the ARM reconstruction and the firmware is unsafe as currently built.
- **The real blocker is now CPU_COMM under project `0x34`.** Stock's startup is
  a handshake (`cpu_comm_dev` -> `mipsloader` loads image/config/TSE -> wait for
  CPU_COMM -> restart MIPS -> ~800 ms -> `THal_Vp_Init` -> HWC resumes SVP and
  DECD), and board B's vendor image has the `loadmips`/`libmips.so` /
  `display.mips.bootfinish` path to prove it. `THal_Vp_Init` now completes
  end to end under project `0x33` with its real ABI. Under `0x34` the firmware
  accepts the call and never schedules it. See
  [mips-display-recovery.md](mips-display-recovery.md), "Project 0x34 is not
  0x33 for RPC".

Also corrected in passing: `dec_reg_blue_en()` drives `workaround + 5` bit 0,
not `workaround + 16` bit 4 (patch 0013 was editing the low byte of a queued Y
address); the DECD frame descriptor is **112** bytes, not 128; the repeat count
lives at ioctl-wrapper `+0x10`, not `+0x18`; and the VideoInfo magic is
`0x61770000`, not `0x61766b40`. Patch 0067 carries these.

One more thing worth trusting: board A and board B ship a **byte-identical**
`hwcomposer.ares.so`, and their `decd.ko` / `ge2d_dev.ko` differ only in build
id -- the DECD enable, mux, blue, top-enable and IRQ routines normalise to the
same code. Use **board B** as ground truth for DT, module builds and boot-state
comparisons, but expect the video architecture to be shared.

---

# HANDOFF — state as of 2026-08-15

**Video decode is DONE.** Decoded H.264 reaches the panel through the GPU with
the CPU never touching a pixel, at the vsync ceiling, without tearing.

## What works, hardware-verified

| | |
| --- | --- |
| **ZERO-COPY PLAYBACK** | **59.71 fps** sustained over 2700 frames, 0 timeouts, operator-confirmed moving picture. VE decode -> dma-buf -> GPU convert -> scanout. `tools/video/gles-play.c` |
| **Tearing** | **none.** `db` 0.00% rows-with-no-bar vs a 16.94% positive control. `tools/video/gles-tear.c` |
| **H.264 decode** | **bit-exact** vs host software references, all five ladder vectors, re-verified on the current kernel. 311 fps standalone |
| **GPU** | Mali-G31 via mainline panfrost, GLES 3.1 on mesa 25.0.7 |
| **Presentation ceiling** | **58.93 fps** against a 59.7 Hz panel — the actual limit now |
| **CPU-conversion path** | still works, capped at 28.30 fps by the ~44 MB/s uncached read of the decoder's buffer. Superseded, kept as fallback |

## How to run it

```
reboot bootloader          # from Linux
h713_disp auto 0x34 logo   # REQUIRED every boot; plain autoboot does not do it
boot
```
then, on the target:
```
EGL_PLATFORM=surfaceless ./gles-play video-test/v04-1280x720-high.h264
```
`sunxi-scanout-dmabuf` auto-loads at boot. `gles-play` refuses to run if the
AFBD clock is gated rather than hanging the board on gated registers.

## Three claims in this file were wrong and are retracted

Read these before trusting anything historical here:

- **"Direct YUV scanout WORKS" (2026-08-12) — WITHDRAWN.** Did not reproduce;
  the same command produces the 4x-repeat greyscale it claimed to fix. It rested
  on a photo attributed to the wrong command, the second time that happened.
- **"The 28 fps ceiling is the cross-process handoff" (2026-08-10) — WRONG.**
  The handoff is nearly free; the cost is reading an uncached CMA buffer.
- **"The M1 md5 baseline has drifted" (2026-08-15) — WRONG, and mine.** A
  hand-typed pipeline missing `! video/x-raw,format=NV12 !`. The baseline was
  always intact.

## LOOSE ENDS — start here next session

In priority order. Item 1 is closed; item 2 is the remaining real debt, and the
rest are cheap.

1. **The rootfs can rebuild the video tooling — DONE 2026-08-15.** The video
   *runtime* now ships in the base package set, because this is a projector and a
   build that cannot play video is not a useful build of it; `--profile dev` adds
   the on-target compiler and headers. Details and the package rationale are in
   [rootfs.md](rootfs.md#video-runtime-and-the-dev-profile).

   Measured, not assumed. `tools/rootfs/verify-video-tooling.sh` chroots into a
   built image under qemu and compiles every tool with the image's own gcc:

   | image | result |
   | --- | --- |
   | the previous `build/out/rootfs.tar` (the debt) | **2/8** — `EGL/egl.h: No such file or directory`, and no `gstreamer-1.0.pc` at all. Only the two plain-gcc tools built |
   | `build.sh --profile dev` | **8/8** |

   Four things this turned up, three of them corrections to the note that used to
   be here:
   - `KHR/khrplatform.h` **does** ship in Debian — in `libgl-dev`, which
     `libgles-dev` depends on. Nothing needs to come from the Khronos registry.
   - `libglvnd-core-dev` is not needed; in trixie it ships only glvnd ABI
     headers.
   - **`gles-play.c`'s own documented build command had never linked.** It omits
     `gstreamer-video-1.0`, so `gst_video_info_from_caps`,
     `gst_buffer_get_video_meta` and `gst_video_meta_api_get_type` are undefined
     references. Whatever built the working binary on the board, it was not the
     command in the file. Fixed in the source header.
   - `sunxi_scanout_dmabuf` is a plain misc device with **no DT compatible and no
     module alias**, so udev could never have autoloaded it — the board must have
     been doing it by hand. Every image now carries
     `/etc/modules-load.d/h713-video.conf`.
2. **The display still needs U-Boot every boot.** `h713_disp auto 0x34 logo`
   before `boot`, or the panel stays dark and every tool refuses. Linux cannot
   bring the panel up itself. This is the largest remaining gap between "works on
   the bench" and "works as a product", and it is display work, not video work.
   The KMS driver added on 2026-08-15 does **not** close this: it adopts the
   display U-Boot brought up and deliberately never touches timing, the LVDS PHY
   or the display reset. See [kms-display.md](kms-display.md).
3. **The tearing floor run is flawed.** `gles-tear noflip` paints its static bar
   at the left edge, where keystone and lamp falloff make detection marginal, so
   it scored 16.42% when it should sit at or below `db`. Centre the bar and
   re-capture; one 17 s take. The result does not depend on it (`db` came in
   *below* the broken floor) but the floor is not usable evidence as it stands.
4. **Hypothesis worth one capture:** the CPU path's 23.03% floor used the same
   left-edge static bar and may have been inflated the same way.
5. **Decide what DECD is for — ANSWERED 2026-08-15, and the answer is "its
   registers".** DECD probes and works but has no job, while holding exactly the
   two resources a display driver needs: the AFBD window at `0x05600000` and the
   60 Hz vsync interrupt on SPI 110. Both now belong to the new KMS driver
   (patches 0037/0038) and `dec@5600000` is `status = "disabled"`. It is still
   built as a module and the node is one word from coming back.
   See [kms-display.md](kms-display.md).

## HEVC decodes too — 2026-08-16

The VE decodes H.265 as well as H.264, bit-exact, with no driver changes. Same
method as the M1 gate: deterministic `testsrc2` source, host software decode to
linear NV12 as ground truth, target decode through
`filesrc ! h265parse ! v4l2slh265dec ! video/x-raw,format=NV12`, md5 compared.

| vector | result |
| --- | --- |
| `h01-640x480-main`, 25 frames | **bit-exact** (`9ebd49ec…`) |
| `h02-1280x720-main`, 25 frames | **bit-exact** (`c898a8f0…`) |
| throughput | **~550 fps**, 500 frames of 720p in 0.905 s |

Forcing NV12 is required for the same reason as H.264: unforced it negotiates
the 32x32 tiled `ST12`, which is correct output that can never match a linear
reference. Vectors come from `tools/video/make-test-streams.sh`.

**10-bit does not work**, and the blocker is in the kernel, not this SoC:
mainline cedrus exposes no 10-bit capture format at all, so `Main10` reaches EOS
having decoded zero frames even though the capability bit and the hardware
registers are both present. Full analysis, and what it would take for stock mpv
to use the VE at all, in [vaapi-scope.md](vaapi-scope.md).

## NEXT PHASE — audio

The starting position, gathered but not yet acted on:

- **Stock DTB** (`local/stock-boot/sunxi.fex`, the authority — see the PPU
  lesson) carries `codec@2030000` compatible `allwinner,sunxi-internal-codec`
  with `pll_audio`/`pll_tvfe`/`codec_dac`/`codec_adc`/`codec_bus` clocks;
  `sndcodec@2030330` compatible `allwinner,sunxi-codec-machine`; `daudio2` pins
  on function `d_i2s2`; a `vs,trid-audio-bridge`; and a `sunxi,simple-audio-card`.
- **Third-party RE drivers exist** in
  `local/allwinner-h713-linux/drivers/audio/`: `snd-soc-sunxi-h713-codec.c`,
  `-cpudai.c`, `-machine.c`. **These are not vendor sources** — that tree is
  another project's mainline port ("HY300/HY310 Linux Porting Project",
  Copyright 2026), and the codec file says so in its own header: *"Reverse-
  engineered from stock vmlinux (sun50iw12) via IDA Pro"*. They name registers,
  which is useful, but they carry exactly the authority of an unverified
  decompilation — the same class of claim as
  [h713-inherited-claims-were-wrong]. The vendor's own Android stack is the
  authority; that tree is a peer, and its README still reports the same 4x1
  XRGB greyscale tiling this project diagnosed as a 4-bytes-per-pixel stride
  fault.
- **Mainline has `sun4i`/`sun8i` codec drivers** that may or may not fit; the
  H713 is sun50iw12 and the display work has repeatedly shown it is *not* H616.
- The roadmap entry is item 6, "Audio (I2S / codec / HDMI-in audio captured off
  the HDMI-RX) — depends on what's populated". **What is populated is the first
  question**: this is a projector with speakers, so a codec and amp should be
  there, but that is an assumption until someone looks at the board or gets a
  sound out of it.

**Method that worked all through video decode, and should carry over:** check
the stock DTB before mainline for anything H713-specific; build one instrument
per question; keep a positive control for every measurement; and confirm on
hardware before believing a claim, especially a convenient one.
## Board state right now

- **FAT `mmc 1:2` holds the DECD kernel** (persistent; `fatwrite` done). It has
  `dec@5600000` enabled and `CONFIG_SUNXI_DECD=m`.
- **`CONFIG_MODVERSIONS` is off**, so driver iteration needs only the ~63 KB
  `.ko` over serial (~1 min), not a 12-minute kernel transfer.
- `/root` on the target holds `h713-present`, `decd-client`, `sunxi-decd.ko`,
  `vedump.py`, the NV12 frames (`bars.nv12`, `one.nv12`, `frames30.nv12`) and
  `video-test/` with the H.264 ladder. Plus a lot of `*.log` scratch worth
  deleting. Both tools are current as of the 2026-08-14 simplification: the
  closed-investigation diagnostics (`yuvtry`, `flip-test`, `bar-noflip`,
  `vbprobe`, `leak-test`, `latency-probe`, `yuv-stream`) are gone — git has
  them if an old trail needs re-running — and every surviving command was
  re-verified on hardware after the rebuild.
- **The module is NOT auto-loaded**: `insmod /root/sunxi-decd.ko` after boot.
- **The display must be brought up in U-Boot before booting Linux**, every time:

```
reboot bootloader          # from Linux, lands at the U-Boot prompt
h713_disp auto 0x34 logo   # panel up; plain autoboot does NOT do this
boot
```

`h713-present` refuses to run if this was skipped (it checks the AFBD clock
gate) rather than hanging the board on gated registers.

## Direct YUV refuted, 2026-08-14

Photos in `local/lcd-photos/test_54/`, one camera position, cold boot, logo
reference shot first — the provenance discipline the `test_41` misattribution
forced on this project, applied to the claim that misattribution produced.

| phase | command | photo | result |
| --- | --- | --- | --- |
| 1 reference | logo from U-Boot | `IMG_0690` | logo, clean |
| 2 **control A** | `h713-present yuv2 bars.nv12 3 0` | `IMG_0691` | **4x repeat, greyscale** |
| 3 | DECD `FRAME_SUBMIT`, format untouched | `IMG_0693` | frame over logo (reproduces `test_53`) |
| 3b | + `h713-present fmt 3 1280` | `IMG_0694` | 4x repeat, greyscale |
| 4 | + `h713-present info 0` | `IMG_0695` | 4x repeat, greyscale |

**Control A is the finding.** It is the exact command the 2026-08-12 section
credits with working, run from a cold boot, and it produces the *same* 4x-repeat
greyscale that section says it fixed. Reference: `testsrc2` is 6 colour bars with
**one** diagonal; every failing photo shows ~16 stripes and **four** diagonals.

The arithmetic is the diagnosis, and it is the same one written down on
2026-08-09: 4 bytes/pixel over a 1280-*byte* stride packs four source rows into
each display row, and the greys are the Y plane landing in the RGB components.
The fetch never stopped being 4 bytes/pixel.

**The info page was not the cause.** `dec_frame_submit()`'s linear path sets the
info address to `y_phys + 4096` (`video_info_buffer_init()`), which on hardware
reads `info=6c101000` — 4 KB inside a Y plane that starts at `6c100000`. That is
a real bug, independently found in the research tree's RE notes, and it is worth
fixing. It is not what blocks YUV: `info 0` changed nothing.

### Why the format byte cannot work, from the vendor's own table

`LogoRegData.bin` DE blocks parsed with the record walker from
`h713_logo_walk()` (16-byte records, 4-byte resync). Every one of the 8 blocks
writes exactly this AFBD set and nothing else:

```
05600000 <- 80000020
05600140 <- 03001901   ctrl          05600164 <- 00000808
05600148 <- 008000ff                 05600168 <- 000003b2
0560014c <- 00000080                 0560016c <- 00000021
05600150 <- 02cf04ff   (h-1, w-1)    05600170 <- 00001400   stride
05600154 <- 002c004f                 05600174 <- 02d01400   (h, stride)
05600160 <- 02d00500   (h, w)        05600178 <- 6c100000   source
                                     05600144 <- 00000001   ready
```

| block | geometry | stride | bytes/pixel |
| --- | --- | --- | --- |
| 0 | 1920x1080 | 7680 | 4.0 |
| 1, 2, 5, 6 | 1280x720 | 5120 | 4.0 |
| 3 | 640x360 | 2560 | 4.0 |
| 4 | 864x480 | 3456 | 4.0 |
| 7 | 1024x608 | 4096 | 4.0 |

**Not one write to `0x05600010`–`0x13`, `0x40`, `0x44`, `0x70` or `0x84`.** The
registers this project has spent four sessions poking are not in the vendor's
scanout configuration.

### Which register holds the format — the candidates, narrowed

The vendor's own `sunxi_ge2d.h` gives the structure. AFBD channels are at
`0x05600100` (ch0) and `0x05600140` (ch1), **channel stride `0x40`**, so every
register in the table above is one channel's block at ch1. It also names two of
them outright, from `osd_interrupt_init()`:

```
#define GE2D_OSD_IRQ_CLEAR   0x168   /* WriteRegWord(90177896, -1) */
#define GE2D_OSD_IRQ_ENABLE  0x16C   /* WriteRegWord(90177900, 16) */
```

So `0x0560016c` is an **interrupt enable, not a format field**. That leaves four
registers in the channel block that could carry it:

| offset | reg | value | note |
| --- | --- | --- | --- |
| +0x00 | `0x05600140` | `03001901` | ctrl; bits [3:2] are `mirror_mode` per U-Boot |
| +0x08 | `0x05600148` | `008000ff` | |
| +0x0c | `0x0560014c` | `00000080` | |
| +0x24 | `0x05600164` | `00000808` | **best candidate** — two 8s reads like a per-component bit depth |

All four are constant across all 8 blocks while geometry and stride vary, which
is what a format field should do. **Sweep these before anything expensive:**
`load` puts pixels in place without touching a register, and `poke` changes one
field against an otherwise untouched vendor configuration. Success is the 4x
horizontal repeat collapsing to 1x.

## DECD's runtime suspend resets the display, 2026-08-14

`dec_disable()` calls `reset_control_assert(dec->rst_bus_disp)` on the **shared**
display reset, then drops `clk_bus_disp`. Measured: one `PM_HINT off` -> `on`
cycle took the AFBD window from `ctrl=03001901 stride=00001400 src=6c100000` to
all zeros, and the panel went black. U-Boot's programming does not survive it,
and `dec_enable()` cannot restore what it never wrote.

This is the Milestone 4 resource-ownership warning arriving early: U-Boot owns
these registers and DECD wants them. Consequences for anyone running this:

- `decd-client show` used to end with `PM_HINT off`, so **the panel blanked
  when the dwell expired** — including the 2026-08-12 run, which is why nobody
  could report what it showed. **Fixed 2026-08-14:** `show` now leaves the
  device enabled and says so; `decd-client pm off` still does the reset
  explicitly if wanted. Verified on hardware: the AFBD window survives a full
  `show` cycle intact.
- Any test that needs the display alive must take **one** `pm on` and never
  suspend. Recovery is `reboot bootloader` -> `h713_disp auto 0x34 logo` ->
  `boot`.

## The plane-0 hunt — live-poke campaign, all null, and the map it bought (2026-08-14)

One evening of operator-watched probes, every one register-verified as landing
and every one visually null except the calibrations. The value is the map.

### What was tried, in order

| probe | result |
| --- | --- |
| format sweep: `0x140/0x148/0x14c/0x164` bit variants, `0x000` bit 5 | null; writes verified sticking by pair-poke; `0x164` is 16-bit, holds reset default `0x808` in **both** channels |
| ch0 (`0x05600100`) enabled as a ch1 clone, ARGB source | null; status never leaves 0 |
| ch0 with the **vendor's own** ctrl `0x83000201` (from `ge2d_plane_afbd_writes[]`) + full `ge2d_plane_init()` write set + planar config | null; status never leaves 0 |
| the complete `dec_reg_video_channel_attr_config()` linear recipe incl. plane geometry `0x48/0x4c` | null — and `0x48/0x4c` were **already correct** (`(720,1280)/(360,1280)`, someone programs them every boot) |
| bypass byte `0x69` bit 0 cleared | null |
| mux `0x68` values 0/1/3 | null |
| ch1 ctrl "disabled" (`0x00010000` + ready) | **panel unaffected** — the disable does not latch |
| VBlender window geometry halved/moved | null; its `0x00` reads 0; MIPS-programmed geometry present (two windows `1280x720@(49,22)`) but pokes are not consumed |
| plane 0 DE-layer window (`0x05280040`) opened, cloned from plane 1 | null |
| OSD0 (`0x05248000`) cloned from **live** OSD1 incl. the plane-open bit `+0x1c[0]` | null |
| DE2 subs `0x05288000/0x0529c000` | both read all-zero — not in the live path |
| mixer ctrl `0x0525c038` bit sweep — including **removing** the live bit | null both ways; live value is `0x40`, not the `0x100` U-Boot writes, so something rewrites it post-boot |

Calibrations that DID show, proving the instrument: framebuffer content +
ch1 commit (the white-flash beacon), and the plane-1 layer X origin
`0x0528008c` (picture shifted ~400 px, the band fix's two-sided mover).

### The model this forces

The per-commit latch consumes **addresses, strides and origins** — that is why
flips, the 4x-repeat stride change, and the layer origin all work. It does not
consume **topology**: which planes exist, enables, routing. Removing the mixer's
only live bit and "disabling" ch1 both change nothing, so topology is latched
once at pipeline bring-up and never re-read. Every plane-0 resource accepts
writes that nothing consumes because plane 0 was not in the topology when U-Boot
brought the pipeline up.

Corollary: **no register poke can add a plane to a running pipeline.** The
plane-open ACTION is a bring-up-time sequence, and `tgd_is_plane_open()`
(OSD base `+0x1c` bit 0) is only its status readout — writing the bit does
nothing, confirmed live.

### Where the answer is

`local/h713-lab` holds board B's own `ge2d_dev.ko` — **unstripped, display
symbols intact** (SHA-256 `a79017e5d3bc...`, see mips-display-recovery.md).
The plane-open sequence is in there, statically recoverable: callers of
`ge2d_plane_init`, the tgd plane ioctls, and whatever orders VBlender/OSD0/ch0
enables against a pipeline restart. No more live pokes until that names a
candidate sequence.

## Gotchas that cost real time

- **The USB gadget only enumerates if Linux has not run since power-on.** Cold
  boot, interrupt at `=>`, then UMS/fastboot. Otherwise use YMODEM +
  `fatwrite ... ${filesize}`. See [flash.md](flash.md).
- **Score a bulk write by throughput, not exit status.** `dd` reported
  "4.3 GB, 1.0 GB/s" and exited 0 on a write that never reached the device.
- **A control must match the run in every respect except the variable under
  test.** "Nothing is running" is not the baseline for "something is running" —
  that error produced a phantom tearing defect and five wasted investigations.
- **The vendor is a strong prior, not a rule.** Copying its `reg` order would
  have pointed the driver at the wrong block.
- **`dec_frame_submit()` always returns 0**, even when disabled or when it drops
  the frame. The `fence_fd` is the only real feedback.
- **A register readback is not a picture.** `+0x11` accepts 3, retains 3 across a
  latch, and the panel does not change — because that register is not in the
  fetch path. Twice now a readback has been scored as a visual result. The panel
  is the instrument for a display claim; the register only says the write landed.
- **Re-run the control before believing an old success.** Two claims in this file
  were produced by attributing a photo to the wrong command. A control costs one
  boot and one photo.
- **Use the project's own instrument before writing an ad-hoc command.** The
  "M1 md5 drift" of 2026-08-15 was entirely a hand-typed pipeline missing
  `! video/x-raw,format=NV12 !`, which `m1-decode-test.sh` has always carried
  and whose comment predicts the exact wrong byte count. The script existed and
  I did not run it.
- **A control cannot validate a measurement it shares a defect with.** That same
  false drift survived a control — old kernel vs new kernel, byte-identical —
  because both runs used the same broken command. The control correctly showed
  "not caused by this change" and I over-read it as "the effect is real".
- **Operator watch windows need a panel-side beacon and an explicit go.** A
  probe launched while the operator reads the announcement is a probe nobody
  watched. Flash the panel white twice before the first trial, and never fire
  until the operator says go. A calibration trial must be UNMISSABLE (the
  400 px origin jump), not subtle (a 49 px window nudge that history recorded
  as a ~14 px wiggle).

## Next steps, in order — SUPERSEDED, kept for the trail

**All of the below is historical.** It was the plan while the GPU path was
still unknown; the GPU path then worked and made most of it moot. The live
plan is in LOOSE ENDS at the top of this file.

What actually happened to each item:

1. **Sweep the format registers** — done, all null. Closed by the
   topology-latch model.
2. **Capture the vendor configuring a video plane** — never needed. It was
   correctly costed as expensive (reaching the Android UI destroys the Debian
   rootfs) and the GPU path made it unnecessary.
3. **Decide whether DECD is the right block** — answered: it is not, for this
   purpose. Its registers are not in the scanout fetch path. Still carried; see
   loose end 5.
4. **Fix `video_info_buffer_init()`** — still unfixed and still wrong
   (`y_phys + 4096` lands inside the luma plane). Harmless while DECD is unused.
5. **Give DECD its own display reset** — moot unless DECD gets a job.
6. **The CPU-conversion path as fallback** — measured at 28.30 fps, below the
   30 fps content rate, and superseded by the GPU path at 59.71.
7. **`clock-frequency`** (we run 100 MHz, vendor asks 200) — never revisited;
   nothing depends on it now.

The original text follows.

## Next steps, in order (original, superseded)


1. ~~Sweep the four candidate format registers.~~ **DONE 2026-08-14 — all
   null**, and the whole live-poke approach is closed by the topology-latch
   model above. The next step is **static RE of board B's unstripped
   `ge2d_dev.ko`**: recover the plane-open sequence (callers of
   `ge2d_plane_init`, the tgd plane ioctls). Desk work, no panel time.
1b. **GPU path — UNBLOCKED 2026-08-15.** panfrost runs jobs (`PASS`, 1252
   Mpixel/s) after fixing the PPU base address and domain table from the stock
   DTB. The GLES video pass is now the live next step: import a cedrus CAPTURE
   dma-buf as an NV12 texture and render into the scanout region (wrapped by
   `DECD_IOC_MAP_LINEAR_BUFFER`), which removes all three M3 costs at once.
2. **Only if that dead-ends: capture the vendor configuring a video plane.**
   `LogoRegData.bin` is ARGB8888 only, so the answer is in the running Android
   stack. **This is expensive — do not treat it as a reboot.** Reaching the
   Android UI needs `boot_a` restored to the vendor image, `super` intact, and
   `UDISK` formatted f2fs, **which destroys the Debian rootfs** — they contend
   for the same partition and there is no free 4 GiB elsewhere — see
   [flash.md](flash.md), Methods 5 and 6. `run switch_vendor`
   alone gets the vendor *boot chain*, not the UI. It is also unproven that
   `/dev/mem` at `0x0560xxxx` is readable under stock Android's SELinux, so this
   can cost a rootfs rebuild and still yield nothing. If it is run anyway: a
   1280x720 H.264 clip diffs against DE blocks 1/2/5/6 with identical geometry,
   making the format the only variable; 1080p content diffs against block 0.
3. **Decide whether DECD is even the right block.** Its whole register window
   (`afbd + 0x60` onward) is disjoint from the scanout registers U-Boot drives.
   The research tree independently concluded `decd` drives AFBC-compressed video
   frames, and cedrus emits linear NV12 or Allwinner-tiled, never AFBC. Settle
   this before writing any more driver code against it.
4. **Fix `video_info_buffer_init()` regardless.** `y_phys + 4096` lands inside
   the luma plane. Confirmed on hardware (`info=6c101000`, `Y=6c100000`). It is
   not what blocks YUV, but it is wrong.
5. **Give DECD its own display reset, or none.** `dec_disable()` asserting the
   shared `rst_bus_disp` destroys U-Boot's display setup; see above.
6. ~~The CPU-conversion path is the fallback; measure whether conversion caps
   the frame rate first.~~ **MEASURED 2026-08-14 — it does not ship.** 28.3 fps
   sustained against 30 fps content, and the cap is the ~44 MB/s CPU read of the
   decoder's output buffer, not conversion (which is worth 3.7 ms/frame total).
   See the M3 result. **Try a cached V4L2 CAPTURE mapping before the plane RE**
   — if the buffer can be read at cache speed the existing architecture reaches
   real time with no display work at all.
7. Revisit `clock-frequency` (we run 100 MHz, vendor asks 200) once it works.

---

## Three blocks, and the naming trap

The existing docs use "DECD" and "Cedrus/VE3" interchangeably for "next: video
decode" ([status.md](status.md) says DECD, [roadmap.md](roadmap.md) says
Cedrus/VE3). They are different silicon and only one of them is a codec.

| block | node | what it is | state |
| --- | --- | --- | --- |
| **VE / Cedrus** | `video-codec@1c0e000` | the decoder — H.264/H.265/MPEG-2/VP8, V4L2 stateless M2M | binds, `/dev/video0` (2026-08-07) |
| **AV1** | `av1-decoder@1c0d000` | separate AV1 block | node exists, compatible `allwinner,sunxi-google-ve`, **no driver in our tree binds it** — inert |
| **DECD** | `dec@5600000` | **not a codec** — the AFBD frame-submission path that scans decoded frames out to the panel | patch 0013 present, `CONFIG_SUNXI_DECD` off, node `disabled` |

DECD owns the `0x05600xxx` AFBD window — the same registers
`h713_mips.c` already drives by hand (`0x05600140` ctrl, `0x05600170` stride,
`0x05600178` source). So the display bring-up did not merely leave DECD
"provisioned"; it left us already driving DECD's registers from U-Boot, which is
why the presentation plan below starts there rather than with the vendor driver.

**A research-tree claim to not repeat.**
`local/sun50iw12p1-research/docs/AV1_HARDWARE_DECODER_ANALYSIS.md` presents an
ioctl table as an AV1 decoder API ("MAJOR DISCOVERY"). It is not. That is
`decoder_display.h` — the DECD frame-submit interface — and
`DEC_FORMAT_YUV420P_10BIT_AV1` is a *pixel format the display path accepts*, not
a codec entry point. Same over-read pattern as the six load-bearing false claims
already caught in that tree; treat its video conclusions as unverified.

## Proven on hardware, 2026-08-07

| fact | evidence |
| --- | --- |
| Cedrus binds and registers a node | `cedrus 1c0e000.video-codec: Device registered as /dev/video0`; `/sys/class/video4linux/video0/name` = `cedrus` |
| the VE is behind the IOMMU | `platform 1c0e000.video-codec: Adding to iommu group 0` |
| the flashed kernel has the **4 MiB** scanout reservation | `OF: reserved mem: 0x6c100000..0x6c4fffff (4096 KiB) nomap non-reusable uboot-scanout@6c100000` — the 8 MiB version covering the `0x6c500000` back buffer is built but was never flashed |
| the target had **no** V4L2 userspace | no `v4l2-ctl`, `ffmpeg`, `gcc` or `python3` in the minimal rootfs |

**Binding is not decoding.** Cedrus binds on the strength of a DT compatible
(`allwinner,sun50i-h6-video-engine`) and its clock/reset handles; nothing in a
successful probe touches a codec register. Whether the H713's VE3 answers to the
H6 register map is the open question, and it is the same shape as the Crypto
Engine question that turned out negative after the driver had happily registered
every algorithm. Assume nothing from the probe line.

## Debian's ffmpeg cannot drive this decoder

Checked before building a rootfs around it. Debian 13 ships ffmpeg **7.1.5**,
whose `debian/rules` configures `--enable-libdrm` and **not**
`--enable-v4l2-request` (nor `--enable-libudev`, which the hwaccel needs). So
stock `ffmpeg -hwaccel v4l2request` is unavailable no matter what the version
number suggests.

**Consequence:** the off-the-shelf decode client is **GStreamer's
`v4l2slh264dec`** (gst-plugins-good's V4L2 stateless codec support, registered at
runtime when a compatible `/dev/videoN` exists). ffmpeg stays useful for stream
preparation, demuxing and software reference decodes. A custom ffmpeg build with
`--enable-v4l2-request` remains an option if GStreamer disappoints, but it is not
the starting point.

## The test-vector ladder

`tools/video/make-test-streams.sh` → `local/video-test/` (gitignored).

Each step adds exactly one coding feature, so a failure names the feature rather
than just failing. Annex-B elementary streams, because a container demuxer in the
decode path only adds a way to be wrong about something that is not the decoder.

| vector | size | profile | adds |
| --- | --- | --- | --- |
| `v01-320x240-baseline` | 320x240, 8 frames | Constrained Baseline | nothing — I+P, CAVLC, no B. If this fails the fault is fundamental |
| `v02-1280x720-baseline` | 1280x720, 60 | Constrained Baseline | panel-native size — separates "cannot decode" from "cannot decode at this size" (stride, buffer sizing, IOMMU mapping) |
| `v03-1280x720-main` | 1280x720, 60 | Main | B-frames + CABAC — reference-list construction and output reordering, which is what stateless userspace gets wrong first |
| `v04-1280x720-high` | 1280x720, 60 | High | 8x8 transform — what real-world files actually use |
| `v05-1920x1080-high` | 1920x1080, 60 | High | the real clip; integration test, no exact reference |

Every synthetic vector ships an NV12 **host software-decoded reference**
alongside it (`.nv12`), because "the decoder produced output" and "the decoder
produced the *right* output" are different claims. Source is `testsrc2`, which is
deterministic frame-for-frame, so the reference is a fixed artifact rather than
something that drifts between runs; and it moves, because a static scene never
exercises inter prediction.

## M1 RESULT — PASSED, 2026-08-09. The H713 decodes H.264 in hardware.

**Every vector in the ladder is bit-exact against its host software reference.**

| vector | | bytes |
| --- | --- | --- |
| `v01-320x240-baseline` | **PASS** | 921,600 |
| `v02-1280x720-baseline` | **PASS** | 82,944,000 |
| `v03-1280x720-main` (B-frames, CABAC) | **PASS** | 82,944,000 |
| `v04-1280x720-high` (8x8 transform) | **PASS** | 82,944,000 |
| `v05-1920x1080-high` (real clip) | **PASS** | 186,624,000 |

Mainline cedrus drives the H713 VE correctly, up to 1080p High profile, with no
driver changes at all. The pipeline is:

```
gst-launch-1.0 filesrc location=X.h264 ! h264parse ! v4l2slh264dec \
  ! video/x-raw,format=NV12 ! filesink location=out.nv12
```

### The entire fault was one device-tree property

`iommus = <&iommu 0>` on the `ve` node, pointing at an IOMMU that does not exist
at that address. Removing it fixed **both** symptoms at once — the kernel stopped
being corrupted *and* the decoder started working. No driver patch, no register
RE, no clock or IRQ change.

**Force the output caps.** Without `video/x-raw,format=NV12` the decoder
negotiates `NV12_32L32` — Allwinner's 32x32 tiled layout — and emits
`320x256` frames (122,880 bytes each, `ALIGN(240,32)=256`). That output is
correct but *tiled*, so it will never match a linear reference and looks like a
failure if scored naively. The 983,040-byte tiled result was the first evidence
the hardware was decoding at all.

### What this cost, and the lesson

The first diagnosis — "the inert IOMMU is the cause" — was **right**, and was
then talked out of on two grounds that both looked sound: that IOVAs allocate
top-down near 4 GiB and so should miss a 1 GiB DRAM at `0x40000000`, and that the
crash landed *after* clean pipeline teardown. Neither objection was silly; both
were wrong. The retraction cost more than the original error would have.

**The lesson is about what settles a question.** The IOMMU claim was testable
with a one-line DTS change from the moment it was made. Instead it was argued
about — refined, hedged, re-derived from register dumps and vendor DTBs — while
the deciding experiment went unrun. Worse, when the experiment was finally built
it was **bundled with a second change** (`power-domains`), which broke probe
before decode was reached and destroyed the run's ability to answer anything.

Rules earned here:

- **A one-line change that would settle it beats any amount of reasoning about
  whether it will.** Run it first, then theorise about the residue.
- **One variable per bench run.** The bundled build wasted a full
  build-plus-12-minute-transfer cycle and answered nothing.
- **A retraction needs evidence, not just a counter-argument.** "Here is why
  that mechanism seems implausible" is not the same as "here is a measurement
  showing it is not the cause."

## The diagnostic trail (kept — this is how it was found)

What follows is the failing state as it was investigated, retained because the
refutations are reusable and several are load-bearing for future work.

**The VE decoded nothing, and trying crashed the kernel.** Not "decoded
incorrectly" — zero frames out, on the easiest vector in the ladder.

| observation | evidence |
| --- | --- |
| the decoder advertises the right codecs | `--list-formats-out`: `MG2S` MPEG-2, **`S264` H.264**, `S265` HEVC, `VP8F`. Capture side offers `NV12`, `ST12` (32x32 tiled), `NV21`, `YU12`, `YV12` |
| GStreamer accepts the device | `v4l2slh264dec` + h265/mpeg2/vp8 all register from `libgstv4l2codecs.so` (gst-plugins-bad). `/dev/media0` exists, so the request API is present |
| format negotiation works | `Probed caps: ... format=(string)NV12, width=320, height=240` — `VIDIOC_ENUM_FMT` and `ENUM_FRAMESIZES` return sane values |
| **but nothing decodes** | pipeline goes PREROLLED -> PLAYING -> **EOS in 2.6-25 ms**, exits *cleanly* with no error, and the output file is **0 bytes** |
| **and the kernel dies** | recursive `Unable to handle kernel paging request`, then `Kernel panic - not syncing: kernel stack overflow`. Reproduced on 3 of 4 runs; `panic=5` reboots the board |

**The crash is memory corruption, not a decoder fault.** The faulting context is
`pc : _prb_read_valid+0x10` / `lr : desc_make_final+0x88`, `Comm: systemd-journal`
— the **printk ring buffer**. Something scribbled over kernel memory, and the
crash surfaced when journald next read the log. The infinite recursion follows
mechanically: printing the fault re-enters the ring buffer, which faults again.

**Timing matters and reframes it:** gst-launch reaches EOS, tears down, prints
`Freeing pipeline ...` and *exits* — the fault lands afterwards, at the shell
prompt. So this looks like a late DMA or a use-after-free at teardown, not a
fault while decoding.

### The control that makes this conclusive

```
gst-launch-1.0 filesrc location=v01-320x240-baseline.h264 ! h264parse \
  ! avdec_h264 ! videoconvert ! video/x-raw,format=NV12 ! filesink location=/root/sw.nv12
```

**921600 bytes, md5 `98a4dbc6e165766cbdfa4d8d4cc1238f` — bit-exact against the
host reference.** Software decode of the same file, on the same board, through
the same parse chain and the same NV12 convention, is perfect.

That single run validates the vector, `h264parse`, the pixel convention, and the
whole scoring method at once, and leaves the fault nowhere to hide but
`v4l2slh264dec` / cedrus / the H713 VE. **Run this control before believing any
future hardware-decode result.**

## The IOMMU is inert — and it WAS the cause (confirmed by removing it)

Read back on hardware with the driver bound and `iommu group 0` created:

```
0x030f0000 0x00000000   0x030f0010 0x00000000   0x030f0020 0x00000000  <- ENABLE
0x030f0030 0x00000000   <- TTB      0x030f0080/84/88 all 0x00000000
```

Every register reads zero, including `ENABLE` (+0x20) and `TTB` (+0x30), both of
which an attached domain writes. **Nothing is responding at that address.** The
DTS says so itself, in a comment directly above the node: *"Address 0x02010000 is
the H713 IOMMU MMIO base (unverified)"* — while the node uses `0x030f0000`, the
**H6** base. Its `resets = <&ccu 11>` is a bare index rather than a symbolic
`RST_*`, which is the same kind of transcription this project has been bitten by
twice already.

So cedrus was attached to an IOMMU that does not exist, and the DMA layer handed
it IOVAs believing they would be translated and bounded. **An inert IOMMU is
worse than no IOMMU**, because it removes bounds everything above it assumes are
enforced. Fixed regardless of whether it is this bug: `iommus` removed from the
`ve` node, node set `status = "disabled"`, both with the evidence in-tree.

**Confirmed on hardware.** Removing `iommus` from the `ve` node — with nothing
else changed — stopped the corruption and made the decoder work, all five vectors
bit-exact. The IOMMU was the fault.

Two objections were raised against this diagnosis before it was tested, and both
were wrong: that IOVAs allocate top-down near 4 GiB and so should miss a 1 GiB
DRAM at `0x40000000`, and that the crash landing after clean pipeline teardown
pointed at use-after-free rather than DMA. The IOVA argument presumably fails
because the addresses the VE actually emitted landed in DRAM anyway (aperture
base, or truncation) — but the point is that **neither objection was a
measurement**, and the one-line experiment that settled it was available the
whole time.

## Candidates, after a round of cheap live checks (2026-08-09)

All of these were checked on the running board with no flash cycle. Two of the
four are refuted, and **read the built artifact, not the DTS comment** — the
comments lie about this node twice.

**REFUTED — "the SRAM property is missing."** The DTS comment says *"Testing
without SRAM property first - may be optional on H713"*. The **built DTB has
`allwinner,sram = <0x1a 0x01>`**, and both `1a00000.sram` and `28000.sram` are
bound platform devices. The comment is stale relative to its own node.

**REFUTED — "a foreign interrupt drives cedrus into a freed context."**

```
327:   0  0  0  0   GICv2 107 Level   1c0e000.video-codec
```

hwirq 107 = SPI 75 + 32, so the IRQ is wired exactly as declared, is exclusively
cedrus's, and has fired **zero times**. The handler has never run, so it cannot
be completing work against freed state. *What survives* is the weaker form: a
count of 0 is equally consistent with "SPI 75 is simply not the VE's interrupt on
H713", and the DTS itself flags the divergence (*"IRQ: SPI 75 (H6 uses SPI 89)"*).
Zero is the expected reading either way, so this measurement cannot separate them.

**NARROWED — register-map divergence.** Full window dump with runtime PM forced
on (`echo on > .../power/control`, status `active`), via `tools/video/vedump.py`:

```
0000: c0000007 00000300 00000000 00000000
0010: 00000000 00000000 00000000 00010000
0030: 00000200 ...        0040: 0000000f ...
0080: 00001c55 000fffff 00008000 00000000
00e0: 00033110 00012011 00000000 00000000
00f0: 00000000   <- VE_VERSION
*
1000: c0000007 00000300 ...   <- identical to 0x000
# 12 non-zero rows of 512
```

Three facts:

- **The VE is present and reachable at the H6 base.** `0xC0000007` at `VE_MODE`
  is a plausible value, not a bus-error pattern.
- **The block aliases every 0x1000.** `0x1000` mirrors `0x000` exactly, so the
  decoded region is 4 KB while the DTS declares `reg = <0x01c0e000 0x2000>`.
  Only `0x000..0x0ff` decode while idle, which is expected — the H.264 engine
  bank at `0x200` appears only once `VE_MODE` selects it.
- **`VE_VERSION` (0xf0) is genuinely 0** on live, clocked, de-reset silicon.

**But it is NOT the fault, and an earlier revision of this page was wrong to
imply it.** `VE_VERSION` appears in mainline cedrus **only as a `#define` in
`cedrus_regs.h`** — `grep -rn VE_VERSION drivers/staging/media/sunxi/cedrus/`
returns the definition and its shift, and no reader. The driver never consults
it. So the zero is a real divergence signal about the silicon and a useful
fingerprint, and it explains nothing about the failure.

**Clock and reset management is correct** — worth recording, because it removes a
whole class of suspicion. CCU `0x0200169c` (gates in `[2:0]`, resets in
`[18:16]`) reads `0x00000000` when the VE is runtime-suspended and `0x00050005`
when active: BUS_VE and BUS_VE3 both gated on and out of reset, exactly as
patch 0022 intends.

**Do not read `0x01c0d000` (the AV1 block).** The same word shows AV1 gated
**off** with its reset **asserted** (bit 1 clear, bit 17 clear) — precisely the
condition the reset-before-gate rule says wedges the interconnect. Check
`0x0200169c` before probing anything in the VE family; the CCU is always clocked,
so that read is free.

**CLOSED — buffer sizing.** Not a bug. Cedrus sizes `NV12_32L32` correctly
(`ALIGN(width,32)`, `ALIGN(height,32)`, chroma `ALIGN(height,64)/2`), and the
hardware honours it: the tiled run produced exactly 122,880 bytes/frame for
320x240 (= `320 * ALIGN(240,32) * 3/2`). The 16-row alignment on the plain `NV12`
path is also fine — forcing `format=NV12` yields bit-exact 320x240 output. Both
paths are correct; `a01-320x256`/`a02-1280x736` were generated to test this and
were not needed.

**The zero IRQ count was the real tell, and it was misread.** With the IOMMU
attached the VE never raised SPI 75 — because it never successfully completed a
job, not because the IRQ number was wrong. Once the IOMMU was gone the same SPI
75 worked fine for 60-frame 1080p decodes. A zero interrupt count means "the
device never finished", which is a symptom, and it was briefly treated as
evidence about the interrupt *number*.

**Restore `power/control` to `auto` after any such probe.** Leaving the VE forced
on keeps it clocked indefinitely and changes the state every later test starts
from.

## DECD enabled — probes clean, display untouched (2026-08-12)

The vendor driver (patch 0013) is the only way to reach zero-copy, because
userspace can neither resolve a V4L2 buffer to a physical address nor program
display registers. Enabled and loaded on hardware:

```
decd 5600000.dec: tvtop link unavailable (-19); continuing unordered
decd 5600000.dec: reconstructed decd probed
```

| check | result |
| --- | --- |
| `/dev/decd` | created, char 243:0 |
| AFBD registers after load | `ctrl=03001901 stride=00001400 src=6c100000` — **identical to before** |
| panel | boot logo still displayed (operator-confirmed) |
| IRQ | `GICv2 142` = SPI 110, named `decd`, count 0 (requested then disabled, as probe intends) |

**Built as a module on purpose.** `dec_probe()` calls `pm_runtime_enable()` with
no `get`, so `dec_enable()` — which sets the AFBD clock rate, writes `0xffffffff`
into TVTOP `0x05700008..0x1c` via `dec_reg_top_enable()`, and calls
`dec_reg_mux_select(regs, 2)` — only runs on runtime resume. Loading is therefore
observable and reversible; none of that has fired yet.

### Where our DT deliberately differs from the vendor's

Checked against the stock DTB rather than assumed:

| property | vendor | ours | why |
| --- | --- | --- | --- |
| `reg` order | `0x5700000` then `0x5600000` | `0x5600000` then `0x5700000` | **Copying the vendor here would break it.** The driver does `afbd = of_iomap(node, 0)`. Every measurement says AFBD is at `0x05600000`: the flag bytes at `+0x10/11/13` match the vendor's linear branch, vblank at `+0xc0` ticks at 16.74 ms, and plane addresses at `+0x70/84` rendered colour bars |
| `clock-frequency` | 200 MHz | **100 MHz** | Three figures exist: vendor 200, U-Boot comments 600, `clk_summary` reports the live clock as 100. `dec_enable()` does `clk_set_rate()`; 100 makes it a no-op under a running panel. Raise once it works |
| `iommus` | `<&mmu_aw 2 0>` | absent | our IOMMU node is inert; attaching cedrus to it corrupted kernel memory |
| TVTOP | shipped and enabled | disabled | isolation — see patch 0033 |
| node children | `simple-bus` containing `mipsloader@3061000` | none | `of_platform_populate()` in probe would instantiate it; U-Boot already owns the MIPS side |

### Patch 0033: the TVTOP link, guarded at compile time

`sunxi_tvtop_client_register()` returns `-EPROBE_DEFER` without TVTOP, so DECD
would defer forever. Its whole body is a `device_link_add()` for ordering — no
hardware. **Merely ignoring the return value is not enough:** the symbol is an
`EXPORT_SYMBOL` owned by the tvtop module, so `depmod` records a dependency and
`modprobe sunxi-decd` pulls TVTOP in anyway. The guard has to be
`#if IS_ENABLED(CONFIG_SUNXI_TVTOP)` with a stub. Verified: `depends:` is empty
and no tvtop symbols remain in the `.ko`.

TVTOP is kept off because its probe owns `CLK_PANEL`, `CLK_DEINT`,
`CLK_SVP_DTL`, `CLK_BUS_DISP` and `RST_BUS_DISP` — the display resources U-Boot
programs and that the handoff depends on. A second owner of those clocks in the
same session that first enables DECD would confound any failure between them.

## Milestones

### M1 — the decoder decodes (the gate) — PASSED, see above

Flash the bring-up rootfs, then, in order: confirm `v4l2-ctl --list-formats-out`
advertises the stateless codecs; run `v4l2-compliance`; decode `v01` with
`v4l2slh264dec`; compare the output against the NV12 reference. Then climb the
ladder.

Scoring is per-vector and the ladder is the instrument: v01 failing and v03
failing mean completely different things.

**This is a gate, not a formality.** If VE3 diverges from the H6 register map,
it is found here for the cost of one boot, before anything is built on top.

### M2 — decoded video on the panel — DONE 2026-08-09

**Decoded H.264 plays on the projector panel, with correct colour and geometry,
at roughly real time.** Operator-confirmed on hardware. No kernel driver, no DRM:
plain userspace through `/dev/mem`.

The whole chain, with no intermediate file:

```
mkfifo /tmp/v.fifo
gst-launch-1.0 -q filesrc location=clip.h264 ! h264parse ! v4l2slh264dec \
  ! video/x-raw,format=NV12 ! filesink location=/tmp/v.fifo &
./h713-present nv12 /tmp/v.fifo
```

Confirmed in order, each before the next was believed:

| step | result |
| --- | --- |
| `/dev/mem` mmap of the `no-map` scanout under `STRICT_DEVMEM` | works — the reasoning in the header of `h713-present.c` holds |
| AFBD registers from userspace | `ctrl=03001901 stride=00001400 src=6c100000`, matching the handoff exactly |
| `fill` — solid colour, one commit | 342.8 MB/s, commit ok in 16367 us (one frame at 59.75 Hz) |
| `bar` — synthetic moving bar, double-buffered | **59.40 fps**, 0 timeouts, operator saw a red bar sweeping on blue |
| `nv12` — decoded video | 300 frames, 0 timeouts, **operator confirms the picture is correct** |

**The synthetic bar came first, deliberately.** It is decoder-independent, so a
decoder fault cannot masquerade as a display fault — the same discipline the
display bring-up used with `fb-anim`.

### Performance: the hardware was never the limit

| version | fps | read | convert | blit | commit-wait |
| --- | --- | --- | --- | --- | --- |
| first working | 11.95 | — | 84.0 | — | — |
| staging buffer + 4 threads | 19.65 | 31.71 | 10.99 | 4.12 | 4.06 |
| raw `read()` + bigger pipe | **28.33** | 14.83 | 8.68 | 3.82 | 7.96 |

Against a 30 fps clip. Both bottlenecks were bugs in the presenter, not silicon:

- **A `volatile` destination in the conversion loop.** Writing straight into the
  mmap'd framebuffer through a volatile pointer forbids vectorising or merging
  stores — one scalar store per pixel, 921,600 times, 84 ms/frame. Converting
  into an ordinary cached staging buffer and doing one bulk copy is **7.6x**
  faster, and the bulk copy also beats the per-pixel volatile fill (3.8 ms vs
  12 ms for the same bytes).
- **stdio's 4 KB buffer on a pipe.** `fread()` turned each 1.38 MB frame into
  ~337 blocking reads ping-ponging with the writer: 31.7 ms/frame. Raw `read()`
  in frame-sized gulps plus `F_SETPIPE_SZ` halved it.

**For scale, the actual hardware:** the VE decodes this clip at **268 fps**
(`gst-launch ... ! fakesink`, 300 frames in 1.117 s) with `ve-core` at 600 MHz —
the top rate in the vendor's OPP table. The panel commits at 59.7 Hz. Both have
enormous headroom; every limit hit so far was userspace glue.

### The 28 fps ceiling is the cross-process handoff, not decode or scanout

Measured 2026-08-10. **Fed from a page-cached file instead of a pipe, the same
code runs at the panel's refresh rate:**

```
from page-cached file:  58.93 fps   read 0.13  convert 7.48  blit 5.83  wait 3.53
live through the FIFO:  28.17 fps   read 11.87 convert 11.05 blit 3.80  wait 8.78
```

convert + blit + wait = **16.8 ms**, one frame period at 59.7 Hz. The
presentation path is **vsync-limited**, not compute-limited.

The live figure is not a limit of either end: the VE decodes this clip at
**268 fps** and presentation sustains **59 fps**. What costs ~19 ms/frame is
moving 1.4 MB between two processes and the contention that creates. Note that
*every* stage got faster without GStreamer alongside — conversion 11.05 -> 7.48,
commit-wait 8.78 -> 3.53 — so it is contention, not just the read.

**Two optimisations were tried and neither helped**, which is what located the
real cause:

- **A reader thread** (ring of 3, prefetching during convert/commit):
  28.33 -> 28.14 fps. It moved 2 ms out of `read` and straight into `convert`.
- **Conversion thread count**, swept 2/3/4: **28.35 / 28.16 / 28.17 fps.** As
  threads rise `convert` rises and `read` falls by the same amount, total pinned
  at ~35.3 ms. Stages trading time against a fixed ceiling is the signature of a
  shared resource, not of CPU shortage — and it is why more parallelism did
  nothing.

A memory-bandwidth explanation was proposed for that ceiling and **refuted** by
the page-cached run: if DRAM were the limit, removing the pipe could not have
doubled the frame rate while *also* making conversion faster.

**So do not micro-optimise the conversion.** NEON would attack 7.5 ms of a
16.8 ms budget that is already vsync-bound when fed properly. The win is
architectural: decode and present in **one process**, using V4L2 with dmabuf so
the decoder's own buffer is what gets presented, with no copy between them. That
is also the natural shape of whatever M4 becomes.

Remaining headroom, best first:

1. **Single-process V4L2 + dmabuf** — removes the handoff entirely. The measured
   headroom says this reaches vsync.
2. **Scan out YUV directly** — would kill convert *and* blit (13.3 ms), but see
   the negative result below: not available on this plane.
3. **NEON the conversion** — last, and only if something above changes the
   picture. Currently it optimises a stage that is not the constraint.

### Tearing: RESOLVED 2026-08-11 — double buffering works; the "defect" was a bad baseline

**Read this before the section below, which is kept as the trail and whose
conclusion is wrong.** The workload-matched control settles it:

| run | is the DISPLAYED buffer written? | rows with no bar |
| --- | --- | --- |
| idle panel, nothing running | no | 0.74% |
| **`bar-noflip`: full workload, scanout pinned to a buffer written once** | **no** | **23.03%** |
| double-buffered, no fixes | no | 30.46% |
| + post-flip vblank wait | no | 22.14% |
| + memory barrier | no | 16.91% |
| **single-buffered** | **yes** | **59.38%** |

`bar-noflip` does the identical per-frame work -- same two-phase fill, same
commit, 59.71 fps -- but fills `fb_back` while scanout stays pinned to an
`fb_front` written once. The displayed surface **cannot** be corrupted, and the
metric still reads **23.03%**. So ~23% is this instrument's floor *for a run
doing this workload*, not corruption.

Against that floor every double-buffered variant is at or below it, and only the
single-buffered control clearly exceeds it. **Double buffering works on the Linux
path.** M2's original claim was right; the retraction of it was wrong.

**The mistake, and it was made three times: a baseline that differed in more than
one variable.** The idle panel differs from a real run in motion *and* in whether
the fill/commit cycle runs at all. The motion confound was spotted and
controlled (`BAR_STEP=0`); the workload confound was not, so 0.74% was never the
right floor and every number built on it was misread. Five mechanisms were then
investigated against a phantom.

**What is real:**
- Single-buffered tearing: 59.38% vs a 23.03% floor. Genuine, and the reason
  double buffering exists.
- The metric is only trustworthy for large differences. 25 vs 30 vs 22 vs 17 are
  all inside the floor's variation, which also moves with camera framing
  (interior rows/frame ranged 1227-1758 across these recordings).
- The barrier in `flip_to()` and the vblank work are kept: both are *correct*
  independent of this, and the vblank register is what a DRM driver needs. But
  neither should be credited with fixing a defect that was not there.

**Rule earned:** a control must match the run in every respect except the one
variable under test. "Nothing is running" is not the baseline for "something is
running".

### The original investigation (conclusion WRONG, kept as the trail)

Previously this section said tearing was unmeasured and that double buffering was
"proven". **The proof was from the U-Boot path (test_37) and was carried across
without retesting.** Measured here, the Linux path corrupts a large fraction of
scanned rows.

| run | motion | fill+swap running | rows with no bar |
| --- | --- | --- | --- |
| `bar 1`, program exited | none | **no** | **0.74%** |
| `BAR_STEP=0 bar-vs` | **none** | yes | **30.46%** |
| `bar-vs` (vblank-locked) | yes | yes | 27.84% |
| `bar` + `EXTRA_VSYNC` | yes | yes | 31.30% |
| `bar` (as shipped at M2) | yes | yes | 25.65% |
| `bar-sb` single-buffered | yes | yes | 59.38% |
| `BAR_STEP=0 bar-vs` + `BAR_LATCH_WAIT` | none | yes | **22.14%** |

**The zero-motion control is the one that establishes it.** It differs from the
idle panel *only* in whether the fill/swap cycle runs — identical content every
frame, nothing to tear in the image itself — and it goes 0.74% -> 30.46%. So the
raster genuinely catches surfaces blued but not yet barred: **the displayed
buffer is being written.**

**Getting to a trustworthy number needed three controls, and two were missing at
first:**

- **Positive control** (`bar-sb`, single-buffered): without a run the metric is
  known to flag, a low reading cannot be told from an insensitive metric.
- **Negative control** (`bar 1`, idle): without it, 25.65% cannot be told from
  the metric's own detection floor.
- **Zero-motion control** (`BAR_STEP=0`): the idle control changed *two*
  variables at once — motion and activity. A moving red bar at ~955 px/s smears
  on an LCD and the metric needs `redness > 40` over a contiguous run, so motion
  alone could plausibly have produced the whole effect. It does not, but that
  was an assumption until measured.

**The two-phase fill is load-bearing for the metric.** `fill_bar()` must blue the
whole surface and then draw the bar. A single-pass bar-or-blue fill leaves every
row carrying a bar at some position, so the metric reads 0% whether or not the
panel tears — a meaningless pass. This was originally single-pass and was fixed
before any of these numbers were taken.

### Four mechanisms tested, none sufficient

Each manipulation was verified to have actually taken effect before its result
was credited — the failure mode this project already knows about.

| hypothesis | test | verified by | result |
| --- | --- | --- | --- |
| the flip register does not work | `flip-test`, two solid colours | panel alternates red/green; `src` reads back | **refuted** |
| buffer reused before scanout finished | `EXTRA_VSYNC=1` | frame rate 59.53 -> 29.82, a clean halving | **refuted**, 31.30% |
| swapping at an arbitrary scan phase | `bar-vs`: real vblank + dirty latch | 0 vblank misses, 59.49 fps | **refuted**, 27.84% |
| one-frame flip latency vs two buffers | `BAR_LATCH_WAIT=1` | frame rate 59.46 -> 29.88 | **partial**, 30.46 -> 22.14% |
| the flip lands late | `latency-probe` | panel: red -> green -> red | **refuted**, white never appears |

**`latency-probe` is the one measurement here that needs no metric and no camera
analysis** — it uses the fill as its own probe. Flip to the back buffer, then
immediately repaint the *front* buffer white: if white ever reaches the screen,
the front was still live when written, which is the corruption caught in the act.
It stayed green. Scope: `commit()` waits ~10 ms before the repaint, so this
proves the flip lands within ~10 ms rather than within one 16.74 ms frame — but
`bar-vs` has the same commit between its flip and its next fill, so by identical
reasoning its fills do target a buffer that is no longer live.

It also supersedes `flip-test` as evidence. That showed clean red/green
alternation but across **5-second dwells**, which only proves the flip works on a
long timescale and says nothing about a 16.74 ms frame.

**So the mechanism is still unknown**, and every straightforward explanation is
now eliminated by measurement rather than by argument. What remains untested is
whether the corruption involves our framebuffer writes at all — the DE or panel
may have internal line buffering that the "rows with no bar" metric is reading.
Distinguishing that needs per-buffer content signatures, not another fix attempt.

### What the vendor binaries gave up (and it is worth keeping)

Asked whether the deconstructed board-B binaries could help — they could, and
this is the durable result even though it did not fix the number:

- **The vendor swaps buffers inside the vsync IRQ**, not by polling:
  `dec_vsync_handler` -> `dec_frame_manager_handle_vsync` -> `sync_cb`
  (`dec_sync_frame_to_hardware`).
- **A real vblank register: `0x056000c0` bit 0**, from `dec_irq_query()`
  (`workaround + 96`, `workaround = afbd + 0x60`), acked by writing bit 0 back.
  **Measured: 20/20 events at 16.74 ms** against the panel's computed 16.75 ms
  period, 0.06%. This is a genuine vsync source and is exactly what a DRM driver
  would need.
- The vendor ANDs it with `+0xc4`, which reads **00** on our configuration — an
  interrupt-enable we never set. Transcribing the vendor condition literally gave
  300 vblank misses out of 300; poll `0xc0` alone.
- **Config changes are latched by the dirty bit at `0x0560006c`**, written after
  the address. `flip_to()` never did this.

**`AFBD_STATUS` bit 1 was assumed to be vsync since M2 and never checked.** It
correlates with the frame period — 59.4 fps, 16.75 ms totals — which is why it
went unquestioned. Correlating with the frame period is not the same as being the
frame boundary.

### Where to take it

**Not a fifth hypothesis.** The next step needs a different instrument: mark each
buffer with a distinct signature so a captured frame reports *which* buffer was
on screen and how stale it was, rather than inferring mechanism from an aggregate
percentage.

**And probably not in this tool at all.** `h713-present` is a `/dev/mem` poke;
correct buffer management belongs in the DRM driver where page-flip and vblank
are first-class, which is the M4 decision. The measured vblank register above is
the piece that work will need. A third buffer — the obvious fix if the latency
theory is right — needs a larger `uboot-scanout` reservation and therefore a
kernel change, so it is not a userspace tweak either.

**What this does not undermine:** the throughput results stand. 58.93 fps
vsync-limited presentation, 268 fps decode, bit-exact frames. Those were never
evidence about tearing, and tearing was never evidence against them.

### Direct YUV scanout — RETRACTED. Claimed 2026-08-12, refuted 2026-08-14.

**This section's conclusion is wrong and is kept as trail.** Control A on
2026-08-14 ran the very command below from a cold boot and got the 4x-repeat
greyscale this section says it fixed — see
[the refutation](#direct-yuv-refuted-2026-08-14).

The retraction it performs — of the 2026-08-09 "wrong plane for YUV" inference —
is itself withdrawn. That inference was reinstated by the vendor's register
table, which never programs any of the registers below.

**How this happened is worth more than the result.** The `test_41`
misattribution is described a few paragraphs down, in this same section, as the
reason a whole A/B was re-run from a cold boot. The claim written directly
beneath that warning was then accepted without the control it prescribes. A
register readback (`+0x10=03000310`) was treated as evidence the *picture* had
changed; it only ever showed the register had.

**The original text follows.**

**Confirmed on hardware:** an NV12 frame renders correctly on the panel with no
CPU colour conversion, using the vendor's plane-address path.

```
saved:  Y[0]=00000000  C[0]=00000000          <- both plane registers empty
set:    Y=6c100000  C=6c1e1000  flags=03000310  commit ok
```

`h713-present yuv2 <file.nv12> 3 0` — format code 3 (`fmt_attr_tbl` row index for
8-bit YUV420), plane strides 1280, and crucially:

| register | value | meaning |
| --- | --- | --- |
| `0x05600011` | `3` | format selector (table row index) |
| `0x05600040`/`44` | 1280 | plane strides |
| **`0x05600070`** | **Y address** | `dec_reg_set_address` idx 0, `base = afbd + 0x60`, `+16` |
| **`0x05600084`** | **C address** | same, `+36`; here Y + 1280*720 |
| `0x0560006c` | 1 | dirty latch |

**Why the earlier attempt failed, and it was not the hardware.** The 2026-08-09
attempts set the format byte and the strides but kept feeding the single packed
source at `0x05600178` — the **RGB data path**. A YUV format needs two plane
addresses. Our own register dump showed `0x05600070`/`0x05600084` reading zero,
which was noted at the time and dismissed as "a parallel mechanism we do not
use"; it is precisely what makes YUV work.

The conclusion recorded then — "the plane is an OSD/UI channel and Allwinner UI
channels are RGB-only" — was an **inference invented to explain a null I had
produced myself**. It was labelled as inference, which is something, but it was
still wrong, and it was committed as a reason to stop.

**Found by reading the vendor driver rather than by more experiments**, on the
operator's suggestion to establish the vendor's direction first.
`dec_sync_frame_to_hardware()` -> `dec_reg_set_address()` writes
`item->y_addr`/`item->c_addr` into those registers, and those come straight from
`DECD_IOC_FRAME_SUBMIT`'s `y_phys`/`c_phys`/`image_fd`.

### The vendor never reads the decoded frame on the CPU

This is the important architectural consequence, and it was measured
independently before the YUV result:

```
A  fakesink, never touches the buffer     0.255 s   sys 0.034
B  tmpfs file (real read + copy)          1.079 s   sys 0.901
C  FIFO                                   1.079 s   sys 0.882
   raw pipe bandwidth (dd, 419 MB)        423 MB/s
```

**B and C are identical**, and the pipe on its own runs at 423 MB/s — so the
handoff is nearly free and the cost is the **CPU reading the decoder's output
buffer** at roughly 48 MB/s. Cedrus CAPTURE buffers are CMA/dmabuf and are not
read through the cache.

**That invalidates the plan this section previously implied.** "Single-process
V4L2 + dmabuf to remove the handoff" was aimed at a cost that measurement shows
is small. Merging processes removes a nearly free copy and leaves the expensive
read exactly where it is. The vendor's design avoids the read entirely: decode
into a buffer, submit its physical addresses, let the display consume it.

**So the target pipeline is:** decode to a CMA/dmabuf buffer, write its Y/C
physical addresses to `0x05600070`/`0x05600084` with format 3 and the dirty
latch, commit. That removes the CPU read (~48 MB/s), the conversion (7.5 ms) and
the blit (3.8 ms) together.

> **TRIED IT — 2026-08-25. The registers are not in the scanout path.** Kernel
> patch 0065 implements exactly the above in `sun50i-h713-afbd`. `kmssink`
> negotiated NV12 (it had refused before) and every value landed in hardware:
> `0x05600011 = 3`, both strides 1280, `Y = 0x77100000`, `C = 0x771E1000` —
> `C - Y = 0xE1000`, precisely one 1280x720 luma plane. **The panel did not
> change**; it kept showing the console. Read back during the same run, the
> channel-1 block this driver scans out of was untouched: stride `0x1400`
> (5120 = 1280x4) and source `0x76D00000`, the fbcon framebuffer. The dirty
> latch read back 0.
>
> These registers are DECD's frame-submit file for a **separate video plane**,
> not a YUV mode of the AFBD channel. Configuring them programs a plane that is
> not in the active pipeline — which is the question the sequencing note below
> raised ("whether DECD can feed it at all given its registers are not in the
> scanout path") and it is now answered: not without opening the plane first,
> and the plane hunt established that plane-open cannot be poked into a running
> pipeline. The register semantics recovered from the vendor driver still look
> right; what is missing is the topology step. Patch 0065 is **out of series**
> with the full result attached, because on its own it only adds a format that
> negotiates and then shows nothing.

### The original attempts (conclusion WRONG, kept as the trail)

The prize was killing the CPU colour conversion (convert 8.7 ms + blit 3.8 ms =
12.5 ms/frame, most of the per-frame budget). **Three variants were tried on
hardware and all fail identically**, `h713-present yuvtry` with the `testsrc2`
colour-bar frame (photos in `local/lcd-photos/test_39/`, `test_40/`):

| attempt | result |
| --- | --- |
| format byte only | picture correct at the bottom, grey band ~1/3 down, black above |
| format + all three strides at 1280 | picture repeats **4x horizontally**, near-greyscale |
| format + strides + config latch | **identical** — no change at all, stable across 60 s |
| the same, re-run from a **clean boot** | **identical again** (`test_42` reference vs `test_43` test, same session, same camera position) |

**The last row exists because provenance matters.** A photo in `test_41` showed
correct colour bars and could not be attributed to a command — it was equally
consistent with `yuvtry` succeeding or with the ARGB restore that follows it.
Rather than publish a negative resting on that, the whole A/B was re-run from a
cold boot with the reference shot first. `test_41` was the restore. Four
attempts, one outcome.

**The 4x repeat is arithmetic, and it is the whole diagnosis.** 4 bytes/pixel
divided by 1 byte/pixel is 4: with the stride at 1280 *bytes*, one display row
consumes 320 ARGB pixels, so four source rows pack into each display row. **The
fetch is still 4 bytes/pixel — the format never changed.** The greys are the Y
plane being read as RGB components.

**And the write was not lost.** The readback prints `+0x10=03000310`, i.e. byte
`0x11` holds `3` after the write and after the latch. The register accepts the
value, retains it, and the fetch does not change. So this is not a shadowing or
sequencing problem, which is what the latch attempt was testing.

**Most likely explanation — inference, not proven.** The plane this path drives
is an **OSD/UI channel**, and on Allwinner display engines UI channels are
RGB-only; YUV formats belong to **VI (video input) channels**. If that holds
here, no value written to an AFBD format byte can produce YUV on this plane, and
the change needed is to route through a VI channel in the mixer — which means
owning the DE configuration that currently arrives wholesale from the vendor's
`LogoRegData` replay. That is M4-scale work, not a poke.

> **⚠ The block below over-claims — corrected later the same day.** What patch
> 0066 established is that the live channel fetched **linear packed 32-bit under
> the tested recipe**. It does NOT identify the cause, and so does not prove this
> inference: an incomplete recipe, or a wrong format encoding (row 3 is a
> three-point fit, not established), produces an identical photograph. A
> never-tested address pair at `0x05600320/324` holds live DRAM addresses on the
> running board, so "the register space is covered" is false. Correctly scoped:
> *direct NV12 does not work through the tested AFBD_SRC channel recipe; whether
> another AFBD/DECD/video-plane configuration does is open.* See
> [ge2d-plane-open-re.md](ge2d-plane-open-re.md) § "SCOPE CORRECTION".
>
> **Patch 0066, as run.** Patch 0066 wrote the
> format selector, both plane strides, both Y/C plane addresses *and* the
> channel block's own stride and source in a single commit — the combination
> neither this attempt nor patch 0065 ever ran — and confirmed all of it in
> hardware live mid-stream. The 4x repeat came back. Sweeping the channel stride
> 1280 → 5120 then reproduced a packed 4-bytes/pixel fetch to the pixel: luma
> over chroma at a measured 1.9:1 against the 2:1 NV12 requires. `0x170` is
> honoured, `0x011` is inert, and the hardware walks the NV12 buffer linearly as
> one packed RGB surface. Full account in
> [ge2d-plane-open-re.md](ge2d-plane-open-re.md). This conclusion is retained
> only as history; the 2026-08-26 correction at the top of this file supersedes
> it.

**What was established anyway, and is durable:**

- `0x05600011` is a real format selector: it accepts and retains values.
- The code is the **`fmt_attr_tbl` row index**, not the `DEC_FORMAT_*` id. Three
  independent points fit: row 0 = RGB888 (matching the live ARGB path's `0`),
  row 6 = YUV420 10-bit and row 7 = AV1 10-bit (matching the vendor's writes of
  `6` and `7`). By that mapping 8-bit NV12 is row **3**.
- There are **three** stride registers, not one: the channel stride at
  `0x05600170` plus global plane strides at `0x05600040`/`0x44`. The first
  attempt's grey band was luma read at the wrong pitch through the two that were
  missed.
- `0x0560006c` is the config latch (vendor `dec_reg_set_dirty()`, and
  `dec_reg_bypass_config()` writes 1 there right after changing a config byte).
- `0x05600048`/`0x4c` already hold NV12-shaped plane geometry (1280x720 and
  1280x360), and the vendor's Y/C plane address registers at `0x05600070` /
  `0x05600084` read **zero** on our path — we feed AFBD through the channel
  block's single source at `+0x178` instead.

**Recommendation: do not chase this further as a register experiment.** Take the
cheap software wins first (overlapped read, NEON), which clear 30 fps with
margin, and revisit YUV when M4 decides between DECD and a DRM plane — at which
point the mixer channel type is a design input rather than something to poke.

**Method note.** Both diagnoses came from photographs, not the console. Every one
of these three runs reported success at every step: format written, strides
written, latch written, commit OK, registers restored. The panel said otherwise
each time, and the *specific* defect — band position, repeat count — is what
identified the register. This is the display bring-up's "prefer the photograph to
the metric" rule earning its place again.

### M3 RESULT — 2026-08-14. Sustained 28.3 fps, and the cap is the decoder buffer read.

**The CPU-conversion path cannot sustain 30 fps 720p.** Measured over 2700
frames (90 s of content, `v04-1280x720-high` concatenated 45x), four
independent runs, no thermal degradation (55 -> 71 C, fps flat start to end).

| run | fps | read | convert | blit | commit-wait |
| --- | --- | --- | --- | --- | --- |
| 2700 frames, 4 threads | **28.30** | 12.21 | 10.80 | 3.85 | 8.46 |
| 900 frames, 3 threads | 28.28 | 12.19 | 11.00 | 3.81 | 8.30 |
| 900 frames, 2 threads | 28.41 | 12.94 | 9.73 | 3.61 | 8.85 |
| 900 frames, 1 thread | 28.14 | 5.03 | 18.99 | 3.68 | 7.77 |

**`CONV_THREADS` is irrelevant** — the doc's standing suggestion to sweep it is
now answered. fps is flat within 1% across 1-4 threads; time only moves between
phases (1 thread: `read` 12.2->5.0, `convert` 10.8->19.0, total unchanged). That
is the signature of an external pacer, not a CPU bottleneck.

### What the pacer is

| pipeline | rate | what it proves |
| --- | --- | --- |
| `! fakesink` | **311 fps** | the VE has 10x headroom, sustained |
| `! filesink /dev/null` | **311 fps** | identical — `/dev/null` never copies, so the pixels are never touched |
| same, `sync=false` | 311 fps | GStreamer is **not** clock-pacing; that hypothesis is dead |
| `! filesink fifo` + `cat > /dev/null` | **31.7 fps** | a consumer doing NOTHING but draining. 3.73 GB in 85.1 s = **43.8 MB/s**, and 22.1 s of it is system time |
| full presenter | 28.30 fps | our entire convert+blit+present adds only ~3.7 ms/frame on top |

**The cap is the CPU read of the decoder's CMA output buffer**, at ~44 MB/s —
the same figure the 2026-08-12 A/B/C found (48 MB/s) and the reason `fakesink`
and `/dev/null` look fast: neither ever touches a pixel. It is charged to
whoever first reads the buffer, which is the kernel copying into the pipe,
before our code runs.

The clean A/B on our own side: the identical presenter reading page-cached NV12
runs at **51.62 fps** (`read` 0.52 ms) versus 28.30 fps from the decoder — same
conversion, same blit, same commit. Only the cost of obtaining pixels differs.

### The verdict, and what it decides

- **30 fps content fails by ~6%** (28.3 sustained). Not a stutter to tune away.
- **A perfect zero-cost consumer would still only reach 31.7 fps** — 5% of
  margin over 30, with a 44 MB/s wall behind it. Optimising our presenter
  cannot fix this; it is worth 3.7 ms/frame in total.
- **This justifies the zero-copy work.** Not touching the decoder's output on
  the CPU removes the 44 MB/s bottleneck, the conversion and the blit together,
  leaving the vsync ceiling (58.9 fps) as the limit.
- **Cheaper thing to try first:** the buffer is uncached because of how the V4L2
  CAPTURE buffers are mapped. If a cached mapping is possible, the same
  architecture gets real-time without any plane work. Worth an hour before
  committing to the `ge2d_dev.ko` RE.

### The GPU is bound and nobody noticed (2026-08-14)

Checked because M3 makes the CPU read the thing to eliminate, and the plane RE
is not the only way to eliminate it:

```
panfrost 1800000.gpu: clock rate = 864000000
panfrost 1800000.gpu: mali-g31 id 0x7093 major 0x0 minor 0x0 status 0x0
panfrost 1800000.gpu: shader_present=0x1 l2_present=0x1
[drm] Initialized panfrost 1.4.0 for 1800000.gpu on minor 0
```

**Mali-G31 Bifrost, bound by mainline panfrost, auto-loaded at boot.**
`/dev/dri/card0` and `renderD128` have existed every session. `panfrost_dri.so`,
`libEGL_mesa` and `libgbm` are all in the rootfs. The only missing piece is
`libGLESv2` (Debian `libgles2` / `libgles-dev`, ~100 KB — seconds over serial;
apt's lists do not have it, so send the .deb).

**Why this matters more than the plane RE.** A GLES pass that samples the
decoder's dma-buf as an NV12 texture and renders into the scanout region:

| M3 cost | GPU path |
| --- | --- |
| 44 MB/s uncached CPU read (the actual cap) | gone — the GPU reads over its own DMA path |
| 10.8 ms convert | gone — YUV->RGB in hardware |
| 3.85 ms blit | gone — renders straight into the target |

It targets the **ARGB scanout path that already works at 58.9 fps**, so it needs
no format field, no second plane, and no topology change — precisely the things
the plane hunt proved unreachable. `DECD_IOC_MAP_LINEAR_BUFFER` already wraps a
physical region as a dma_buf, which is the render target.

Capacity is not a concern: 921,600 px at 30 fps is 27.6 Mpixel/s of
sample-and-convert on a core clocked at 864 MHz, and ~153 MB/s of traffic
against a bus that already sustains 350 MB/s of CPU fill.

**Sequencing:** do this before `ge2d_dev.ko`. Its next checkpoint is one
session (send `libgles2`, import a decoder dma-buf, render one frame); the plane
RE's success chain is three stacked unknowns — find the plane-open sequence,
make it work against a U-Boot-initialised pipeline, then discover whether DECD
can feed it at all given its registers are not in the scanout path.

### GLES video pass: the import works, 0.64 ms/frame (2026-08-15)

**`PASS: GPU sampled a cedrus dma-buf and converted it`.** The question M3 left
open — can the GPU read the decoder's output without the CPU touching it — is
answered yes, on a real cedrus buffer.

```
cedrus CAPTURE: 1280x720 NV12 bytesperline=1280 sizeimage=1382400
EXPBUF ok: dmabuf fd=4
EGLImage from cedrus dma-buf: ok
bound as GL_TEXTURE_EXTERNAL_OES: ok
  red   got 255, 24,  0   ok
  green got   0,216,  0   ok
  blue  got   0, 15,255   ok
100 NV12->RGB passes at 1280x720: 63.5 ms (0.64 ms/frame, 1574 fps equivalent)
```

Instrument is `tools/video/gles-nv12.c`. The buffer is obtained with
`VIDIOC_REQBUFS` + `VIDIOC_EXPBUF` on `/dev/video0` — a genuine cedrus CAPTURE
allocation, because a buffer from anywhere else would not answer the question.
Neither ioctl needs streaming, so the import path is testable without also
driving a stateless decoder. The CPU fills it once as a test harness only.

| cost | CPU path (M3) | GPU |
| --- | --- | --- |
| read decoder output | ~31 ms (44 MB/s uncached) | **0** — GPU DMA |
| YUV->RGB convert | 10.8 ms | **0.64 ms** (whole pass) |
| blit to scanout | 3.85 ms | 0 once rendering direct |

`samplerExternalOES` applies the YUV->RGB itself, so the conversion that costs
10.8 ms of CPU is a texture unit's ordinary work.

**Capability probe** (`tools/video/gles-probe.c`), all present:
`EGL_EXT_image_dma_buf_import`, `..._modifiers`, `EGL_KHR_image_base`,
`GL_OES_EGL_image_external` (+`_essl3`), `GL_OES_rgb8_rgba8`, and
`EGL_MESA_image_dma_buf_export`.

**Two traps worth keeping.** `VIDIOC_S_FMT` on CAPTURE alone yields the 16x16
minimum (384 bytes) — a stateless decoder derives CAPTURE geometry from the
coded OUTPUT format, so `V4L2_PIX_FMT_H264_SLICE` must be set first. Writing a
1280x720 pattern into that 384-byte mapping segfaulted, and with stdout
redirected and fully buffered the log was **empty**, hiding every printf up to
the crash. Geometry now comes from the driver's readback, and the tool sets
`setvbuf(_IONBF)`.

### THE ZERO-COPY PATH WORKS — 59.73 fps, 2026-08-15

**Decoded H.264 through the GPU to the panel, with the CPU never touching a
pixel.** `tools/video/gles-play.c`:

```
decoded 1280x720 NV12, planes=2 memories=1 fd=12
2700 frames in 45216 ms (59.71 fps), 0 commit timeouts
  mean gpu 4.01 ms, commit-wait 12.60 ms
```

**Operator-confirmed on the panel: moving colour bars with the sweeping
diagonal**, for the full 45 s. That check is the point — the frame rate is
identical whether the picture is right or garbage, and most of this file's
history is about that distinction.

Against M3's **28.30 fps** on the CPU path. 59.71 fps is the vsync ceiling
(58.93 fps measured independently), so the limit is now the panel rather than
the 44 MB/s uncached read. Flat across three runs of increasing length —
60 frames 59.31, 600 frames 59.73, 2700 frames 59.71 — so no thermal or
buffer-pressure droop.

The chain: VE decodes into a CMA buffer -> GStreamer hands over that buffer's
dma-buf FD -> GPU imports it as an NV12 `EGLImage` and samples through
`samplerExternalOES` -> renders into a scanout slot imported from
`sunxi-scanout-dmabuf` -> `AFBD_SRC` points at the slot the GPU just filled ->
commit. Double buffered across `0x6c100000` / `0x6c500000`.

| stage | CPU path (M3) | zero-copy |
| --- | --- | --- |
| read decoder output | ~31 ms (44 MB/s uncached) | **0** |
| YUV->RGB convert | 10.8 ms | in the 4.1 ms GPU pass |
| blit to scanout | 3.85 ms | **0**, renders in place |
| **result** | **28.30 fps** | **59.73 fps** |

#### The (memory:DMABuf) caps feature is a red herring

Forcing `video/x-raw(memory:DMABuf)` looks like the way to make the decoder
hand out FDs. It is not, and it actively breaks the pipeline:

```
ERROR v4l2codecs-h264dec: DMABuf caps negotiated without the mandatory
                          support of VideoMeta
ERROR v4l2codecs-h264dec: Failed to negotiate with downstream
```

which surfaces to the user as the far less helpful **"No valid frames decoded
before end of stream"** — that is what a `not-negotiated (-4)` looks like from
outside. `fakesink` cannot advertise VideoMeta, so the gst-launch form of this
pipeline could never have worked, and adding the meta via appsink's
`propose-allocation` signal did not fix it either.

**Under plain `video/x-raw` caps the v4l2codecs decoder hands out dma-buf backed
memory anyway.** `gst_is_dmabuf_memory()` is true and the FD is real. So
`gles-play` uses plain caps and **verifies rather than negotiates**: it refuses
any buffer that is not dma-buf backed instead of silently falling back to a
copy, which is exactly the cost this path exists to remove. `GLES_CAPS`
overrides the caps for experiments.

Also note `format=DMA_DRM`, not `format=NV12`, if anyone retries the feature:
since GStreamer 1.24 the DMABuf caps carry a DRM fourcc plus modifier in
`drm-format` and `format` is the literal token `DMA_DRM`.

#### Geometry comes from GstVideoMeta

With dma-buf the real strides and offsets belong to the allocation, not to what
the caps format implies. `gles-play` prefers `gst_buffer_get_video_meta()` and
falls back to `GstVideoInfo` — the same meta the decoder insists downstream
support.

### The other end: the GPU renders into the scanout carveout (2026-08-15)

**`PASS: GPU rendered directly into the scanout carveout`.** Both ends of the
zero-copy path are now proven: GPU DMA in from the decoder, GPU DMA out to the
region AFBD fetches.

```
scanout-dmabuf: carveout 0x000000006c100000 + 8192 KiB
EGLImage over the carveout: ok
carveout is a complete FBO: ok
  phys (  64, 64) = ff0d1780  r= 13 g= 23  want ~13,23  ok
  phys ( 640,360) = ff808080  r=128 g=128  want ~128,128  ok
  phys (1216,656) = fff2e880  r=242 g=232  want ~242,232  ok
100 full-frame renders into the carveout: 62.2 ms (0.62 ms/frame)
```

`patches/kernel/0036` adds `sunxi-scanout-dmabuf`, a misc device whose one
ioctl hands out a dma-buf fd over the carveout. **The design constraint is that
`uboot-scanout@6c100000` is a `no-map` reservation with no `struct page`**, so
an sg_table built with `sg_set_page()` would be a lie; the exporter uses
`dma_map_resource()`, which exists for exactly this. panfrost walks the table
with `for_each_sgtable_dma_sg()` and consumes `sg_dma_address()`, so a
page-less table suits it. `CONFIG_SUNXI_SCANOUT_DMABUF=m`.

Verification is deliberately **not** through GL: `tools/video/gles-scanout.c`
renders a position-dependent gradient, then reads the same physical memory back
through `/dev/mem`. Reading back through GL would only prove GL is
self-consistent; the question is whether the bytes are where AFBD will fetch
them.

**A weak test caught and tightened.** The first revision expected `g=56` at
y=64 — an arithmetic slip, the right answer is 23 — and *passed anyway* on a
±40 tolerance. Tolerances are now ±4 and the expected values are computed
(`x/W*255`, `y/H*255`). The rising gradient in both axes also pins orientation:
a flipped image would read ~232 at y=64.

**What remains: feed it real decoded frames.** Either drive cedrus directly
(request API, H.264 slice controls) or take GStreamer's dma-buf fds from an
`appsink`. That is the last piece; both hard halves are done.

Projected against M3's 28.3 fps: decode is 3.2 ms/frame at 311 fps, the GPU
pass is 0.64 ms, and the vsync commit is ~8.5 ms — leaving the 58.9 fps panel
ceiling as the limit rather than a 44 MB/s memory wall.

**Do not shortcut this**: rendering to an ordinary FBO and reading back would
reintroduce a 3.7 MB/frame CPU read and be *worse* than the current CPU path.
That number would look like progress and would not be.

### GPU checkpoint: SOLVED 2026-08-15 — the PPU base address was wrong

**`PASS: GPU ran the job`.** Mali-G31 executes fragment shaders, 1252 Mpixel/s,
reproduced 3/3 after the fix below. The negative recorded in the next section
stands as the trail.

```
  ( 16, 16) =   0,  0, 51  expect ~16,16   ok
  (128,128) = 119,119, 51  expect ~128,128 ok
  (240,240) = 238,238, 51  expect ~240,240 ok
PASS: GPU ran the job
```

The gradient is computed, not cleared — 119 and 238 are the shader evaluating
`gl_FragCoord`, and the constant 51 is the 0.25 blue channel through RGBA4.

**The fix, in two parts.** Both came from the stock DTB
(`local/stock-boot/sunxi.fex`) after the operator vetoed reasoning from H616
mainline — which had led to the confident and wrong conclusion "the GPU domain
is already on, so power is not the problem".

1. **Patch 0020's register base was `0x07010014`**, a transposition of the PMU
   base `0x07001000` that landed inside R_CCU. Every domain register read zero,
   `h713_ppu_is_on()` reported every domain off, `power_on()` waited forever for
   a DONE bit that could never set, and the init writes went into unused R_CCU
   space. At the corrected base all five domains read `wait=0x8`,
   `delays=0x00080808`, `ctrl=1`, `status=0x00010000` — matching the driver's own
   constants exactly.
2. **The domain table was wrong at four of five positions.** Stock has
   `pd_gpu@0, pd_tvfe@1, pd_tvcap@2, pd_ve@3, pd_av1@4`; ours claimed
   `{CPUS, SYS, GPU, VE, DE}` with the GPU at index 2 mapped to `hw_id -1`. So
   the GPU node aimed at TVCAP *and* resolved to an always-on stub.

**Why "all domains read ON" was a red herring.** They were on because boot0 left
them on, not because Linux managed them. With `hw_id -1` the domain was a stub,
so panfrost's runtime PM could never sequence the GPU. Once the domain is real,
panfrost powers it down when idle and brings it up on demand — and jobs land.

**A prediction I got wrong, recorded because the reasoning was the error:** on
seeing every domain read ON I predicted this fix "probably won't fix the GPU".
Powered-at-boot and powered-by-a-driver-that-can-sequence-it are different
states, and only the second lets runtime PM work.

### The VE regression this exposed, and the loop it closed

Making the domains real broke H.264 decode: `cedrus: frame processing timed
out!`. An unclaimed domain gets powered off, and the `ve` node declared no
`power-domains`. Confirmed by hand — writing `CMD_ON` took VE from
`status=0x00020000` (off) to `0x00010002` (on + done) and decode returned.

`power-domains = <&ppu 3>` on the `ve` node had been **tried and reverted on
2026-08-09**, because cedrus stopped probing entirely. That revert's diagnosis
was correct and is now vindicated: *"the cause is in patch 0020, not here...
Restore this line only after the H713 PPU driver can actually report and control
these domains."* The base-address bug is exactly why `power_on()` deferred
forever. The line is restored and is now mandatory, not optional.

### Verified after the fix, 2026-08-15

| check | result |
| --- | --- |
| `gputest` | **PASS 3/3**, no sched timeout |
| cedrus probe | `Device registered as /dev/video0`, no deferral |
| H.264 decode | works, `VE_RC=0` |
| panel | boot logo displays normally (operator-confirmed) |
| genpd | `GPU, TVFE, TVCAP, VE, AV1`; gpu and video-codec both attached and `suspended` |

**RETRACTED 2026-08-15: the "M1 md5 drift" reported here never existed.**
This paragraph originally claimed all five ladder vectors had stopped matching
`reference-md5.txt` and needed re-baselining. They match. **M1 still passes
bit-exact on the current kernel**, verified across all five vectors:

```
v01-320x240-baseline PASS 921600      v04-1280x720-high  PASS 82944000
v02-1280x720-baseline PASS 82944000   v05-1920x1080-high PASS 186624000
v03-1280x720-main    PASS 82944000
```

The fault was in my ad-hoc test command, which omitted
`! video/x-raw,format=NV12 !`. Unconstrained, the decoder negotiates
**NV12_32L32** — Allwinner's 32x32 tiled layout — and emits `ALIGN(height,32)`
rows, so 320x240 becomes 122880 bytes/frame instead of 115200. That output is
correct but tiled, and can never match a linear reference.
`tools/video/m1-decode-test.sh` has always forced the caps, and its comment
predicts this exact byte count. I did not use the project's own instrument.

**The control failed to catch it, and that is the more useful lesson.** I ran
the old kernel against the new one and got byte-identical results, which is
true and proves the kernel change was not responsible — then I read it as
evidence the drift was real and pre-existing. Both runs carried the *same*
broken command, so the control varied the wrong thing. This file already
warns: *"a control must match the run in every respect except the variable
under test."* A control cannot validate a measurement it shares a defect with.

### The original negative (kept as trail): panfrost does NOT run jobs (2026-08-14)

The checkpoint proposed above was run the same evening. **Negative, with a
specific cause to chase.** The software stack is entirely fine:

```
EGL 1.5, EGL_VENDOR: Mesa Project
GL_RENDERER : Mali-G31 (Panfrost)
GL_VERSION  : OpenGL ES 3.1 Mesa 25.0.7-2+deb13u1
```

EGL initialises surfaceless, mesa targets the real hardware path (not llvmpipe),
shaders compile, the FBO is complete. Then:

```
panfrost 1800000.gpu: gpu sched timeout, js=1, config=0x7b00, status=0x8,
                      head=0xa027300, tail=0xa027300
```

`head == tail`: submitted, never advanced. All pixels read back zero.
Test is `tools/video/gputest.c` — a fragment shader whose output is a function
of `gl_FragCoord`, so a correct image cannot be faked by a clear or a memset.

**Getting there needed `libgles2` from Debian trixie** (`libGLESv2.so.2` +
GLES2/EGL headers, plus `KHR/khrplatform.h` from the Khronos registry — no
Debian package ships it). Sent over serial, ~79 KB tarball. That part is done
and lives on the target.

#### Not the clock

`gpu0` (CCU + 0x670, and **the H713 CCU base is 0x02001000**, not H616's
0x03001000) has a plain 2-bit M divider. Jobs fail identically at 864, 432 and
216 MHz. The draw-loop time scaled ~4x with the divider, so the change took
effect in hardware — this is a real negative, not a no-op.

| register | value | meaning |
| --- | --- | --- |
| `PLL_GPU` 0x02001030 | `b8002301` | enabled, locked, N=35 -> 36 x 24 = 864 MHz |
| `gpu0` 0x02001670 | `80000000` | gated on, mux = pll-gpu, M=0 -> /1 |

#### The live suspect: nothing ever powers the GPU domain

`patches/kernel/0020-pmdomain-add-h713-ppu-driver.patch`:

```c
static const int h713_ppu_hw_ids[5] = { 0, 1, -1, 3, 4 };
                             /* CPUS SYS  GPU  VE  DE */
```

Hardware IDs run 0, 1, **[2 skipped]**, 3, 4. The GPU is `-1` = always-on, so
`h713_ppu_set_power()` is **never called for it** and no code in Linux touches
its power hardware — whether it is on depends entirely on what U-Boot left.
`pm_genpd_summary` confirms the bookkeeping is vacuous: GPU reads `on` purely
from the flag, while VE reads `off-0` while decoding at 311 fps.

The justification for `-1` is an inherited RE claim, quoted in the DT node:
*"domain_info[2] is all-zeros in stock binary, meaning no hardware power
sequencer for GPU"*. That is the same shape as the claims in
[h713-inherited-claims-were-wrong] — an absence in a table read as a positive
fact. An equally consistent reading is that stock populates it elsewhere. The
conspicuous positional gap at hardware ID 2 is the tell.

**Next test:** perform the domain-2 power-on sequence by hand and re-run
`gputest`. Registers are at PPU base `0x07010014` + `id * 0x80`: wait_mode
`+0x00`, pwr_off_delay `+0x04`, pwr_on_delay `+0x08`, pwr_ctrl `+0x0c`
(1 = on), status `+0x10` (bit3 idle, bit1 done, bits[17:16] state, 01 = on).
Write the three init values (`0x8`, `0x00080808`, `0x00080808`), then 1 to
pwr_ctrl, then reload panfrost.

**A caution for whoever does it:** a first attempt read those status registers
at `0x07010014 + id*0x80 + 0x10` and got zeros for all five domains, including
CPUS and SYS, which are unquestionably powered. So either the offset or the
base is not what the driver comment implies, and **that dump is not a valid
diagnostic**. Establish a register view that reports CPUS/SYS as ON before
trusting anything it says about the GPU.

#### The stock DTB says our GPU wiring is wrong in two places

Checked against `local/stock-boot/sunxi.fex` — the DTB from the retail firmware,
not the research tree, and not H616 mainline. **Going to H616 first was a
mistake**; it is the assumption that has repeatedly burned this project, and the
operator called it before it cost anything.

Stock `gpu@0x01800000`:

```
compatible    = "arm,mali-midgard"
interrupts    = <0 0x75 4>, <0 0x76 4>, <0 0x4c 4>   /* SPI 117, 118, 76 */
clock-names   = "clk_parent", "clk_mali", "clk_bus"  /* CCU idx 7, 28, 29 */
power-domains = <&pd 0>
operating-points-v2 = <gpu_opp_table>
gpu-supply    = <&reg_vdd_sys>
```

| property | stock | ours | verdict |
| --- | --- | --- | --- |
| interrupts | SPI 117/118/76 | SPI 117/118/76 | **match** |
| supply | `reg_vdd_sys`, fixed 0.96 V, always-on | same | **match** |
| power domain | **`<&pd 0>`** | `<&ppu 2>` | **WRONG** |
| clocks | **three** (`clk_parent`, `clk_mali`, `clk_bus`) | two (`core`, `bus`) | **missing one** |
| frequency | OPP table, **max 700 MHz** | fixed 864 MHz, no OPP | over the vendor max |

**And the PPU driver's whole domain map is wrong.** Stock's controller is
`allwinner,tv303-power-controller` with children:

```
pd_gpu@0  pd_tvfe@1  pd_tvcap@2  pd_ve@3  pd_av1@4
```

against patch 0020's `{ "CPUS", "SYS", "GPU", "VE", "DE" }` / `{0, 1, -1, 3, 4}`.
Four of five names are wrong: index 0 is **GPU** (not CPUS), 1 is TVFE, 2 is
**TVCAP** (not GPU), 4 is AV1 (not DE). Only VE at 3 is right, by luck. So our
`power-domains = <&ppu 2>` aims the GPU at TVCAP *and* resolves to `hw_id -1`,
which is a no-op — nothing in Linux powers the GPU domain, and the "no hardware
power sequencer" claim in the DT comment is refuted by `pd_gpu@0` existing.

**Audit item beyond the GPU:** every `<&ppu N>` reference in our tree is suspect
until re-checked against this list.

#### Still unexplained

The GPU nonetheless *looks* powered: `GPU_ID` reads `0x70930000`, and
`SHADER_READY`/`TILER_READY`/`L2_READY` are all 1 with no faults raised
(`GPU_IRQ_RAWSTAT = 0x600`, POWER_CHANGED only). Jobs still time out at 864, 432
and 216 MHz, and the rail is fixed at 0.96 V for every vendor OPP, so neither
undervolt nor over-clock explains 216 MHz failing.

Note also that genpd's `off-0` for every domain is an **artifact of the broken
register map**, not a hardware reading — `h713_ppu_is_on()` polls a register
that reads zero, so every domain reports off. Do not treat that summary as
evidence either way.

**Next test:** correct patch 0020's domain table to the vendor's, point the GPU
at domain 0, add the third clock and an OPP table capped at 700 MHz, rebuild,
retest. That is a kernel rebuild rather than a poke, but it is ordinary work
against known-good vendor data.

#### What this does to the plan

The checkpoint was proposed as cheap, and it was — one evening, and it returned
a definite answer. But the answer means the GPU path now needs **its own
bring-up** (power domain, and possibly a supply and an OPP table) before it can
do anything for video. It is no longer obviously cheaper than the
`ge2d_dev.ko` RE. It is still a *known kind* of problem for this project, which
the plane RE is not, and its blocker is one testable hypothesis away.

### Tearing on the GPU path: none. Scored 2026-08-15

**`db` median 0.00% rows-with-no-bar against a positive control at 16.94%.**
The GPU presentation path does not tear.

| mode | interior rows | median | mean | worst |
| --- | --- | --- | --- | --- |
| `sb` single-buffered, positive control | 1260 | **16.94%** | 17.06 | 25.68 |
| `noflip` intended floor | 1465 | 16.42% | 10.85 | 21.74 |
| **`db` the real path** | 1239 | **0.00%** | 0.54 | 3.05 |

Instrument `tools/video/gles-tear.c`, scored with `tear-measure.py`. All three
recorded in **one continuous take** (`local/lcd-photos/test_56/IMG_0707.MOV`)
with 6 s solid-blue gaps between runs, because the metric's floor moves with
camera framing and "roughly the same position" cannot be compared across takes.
Segment boundaries were located from the blue gaps rather than from assumed
offsets — which caught that the recording began ~3 s early and ended ~3 s short.

Workload match across the three runs: 59.7 fps each, render means 3.11 / 3.01 /
3.00 ms. They differ only in which buffer is written and whether the flip
happens.

**The metric works here.** That was the open question: Mali is a tile-based
renderer, so a clear plus a draw resolve together and the two-phase window the
metric depends on would not exist naturally. `gles-tear` forces it with a
`glFinish()` between passes, and the positive control duly reads ~17% against a
predicted ~18% (3.0 ms of a 16.75 ms frame).

#### The floor run is flawed, and it does not change the result

`noflip` shows a **static** bar that cannot change, so it should score at or
below `db`. It read 16.42%. Two tells: the score varies frame to frame
(mean 10.85 vs median 16.42) although the image is pixel-identical, and the
static bar sits at the **left edge**, where keystone and lamp falloff make
detection marginal. That is a detection artifact, not a workload floor.

The conclusion survives because `db` is *below* the broken floor, and there is
no less corruption than "corruption impossible". A floor matters for
interpreting an elevated number; `db` is not elevated.

**Hypothesis, not a finding:** the CPU path's 23.03% floor used the same
left-edge static bar (`fill_bar(fb_front, 0)`), so it may have been inflated the
same way. That would explain why that floor sat so high, and it does not change
the CPU-path conclusion — double buffering worked there too. Testing it costs
one capture with the static bar centred.

### M3 — DONE 2026-08-15, via the GPU rather than the CPU

Sustained playback achieved at 59.71 fps zero-copy, vsync-limited, operator
confirmed. The original plan below (tear-measure against the fb-anim-db
reference) was written for the CPU path; the tearing question it targets is
still worth scoring on the GPU path, but the throughput question M3 existed to
answer is settled.

### M3 — sustained playback (original plan)

Double-buffered flip at the vsync-locked commit, scored with
`tools/display/tear-measure.py` against the `fb-anim-db` reference. Keeping the
synthetic moving bar on the same instrument is deliberate: a decoder fault must
not be able to present as a display fault.

### M4 — productize

DECD (`dec@5600000`) versus a real DRM plane. Deliberately last — both are large,
and the choice is uninformed until M1–M3 have run. Note that cedrus emits linear
NV12 or Allwinner tiled, **not** AFBC, so DECD's compressed path does not match
cedrus output as-is; its "raw" path is the relevant one. The evidence log's
Milestone 4 warning about resource ownership (shared display clocks, resets, IRQs
and overlapping register windows needing one clear owner) applies directly:
U-Boot currently owns the AFBD registers, and DECD would want them.

## Tooling changes made for this phase

- **`tools/rootfs/build.sh --extra-packages LIST`** — appends to the bootstrap
  set. The shipped product image stays minimal; bring-up images opt in. Used
  here for `v4l-utils`, the GStreamer stack, `ffmpeg`, `build-essential`,
  `libdrm-dev`, `libv4l-dev`, `python3` and `strace`.
- **An on-target compiler is deliberate.** M2/M3 are register-poking experiments
  against a framebuffer; cross-compiling and shipping each iteration over an
  11 KB/s UART is how this project has previously spent whole sessions. `gcc` on
  the board turns that into seconds.
- **`tools/video/make-test-streams.sh`** — the ladder above.
- **`tools/video/h713-present.c`** — the Linux-side presenter (`regs`, `fill`,
  `bar`, `nv12`). Build on the target: `gcc -O2 -o h713-present h713-present.c
  -lpthread`. Refuses to run unless the AFBD clock gate is open, because reading
  those blocks while gated hangs the board.
- **`tools/serial/send_file.py`** — copy a file to the target over the Linux
  serial console when the USB gadget is unavailable. Chunks base64 and verifies
  by md5. **The console is a canonical-mode tty, so a single input line is capped
  at ~4 KB by the line discipline** — anything longer is silently truncated,
  which presents as a corrupt file rather than a transfer error.

## Open items

- The `ve` node declares **no `power-domains`**, although the PPU driver defines
  a `"VE"` domain (index 3, patch 0020) and the GPU node uses `<&ppu 2>`. It
  works today only because `pd_ignore_unused` is on the command line — the same
  load-bearing flag the display handoff depends on. Worth wiring properly before
  anything depends on VE runtime PM.
- **AV1 is inert** and should stay that way until H.264 works. A driver exists
  in `local/allwinner-h713-linux/drivers/media/av1/` (never enabled, never
  tested); the DT node's compatible matches nothing in our tree.
- The bench board is a **WiFi AP at 192.168.4.1** with sshd running. Joining it
  from the host would give a fast file path, at the cost of the host's own
  network. `ums` from U-Boot is the transfer route used instead.

## mpv plays hardware-decoded video TODAY, with no source changes (2026-09-03)

The handoff recorded this as blocked: *"mpv cannot use the video plane. This
build has no drmprime hwdec, only vaapi, and mpv's VA-API route goes through
vo=gpu, which wants a render node the display-only driver has none of."*

**Both halves of that are wrong.** Measured on the board:

```sh
LIBVA_DRIVER_NAME=v4l2_request \
  mpv --vo=drm --hwdec=vaapi-copy clip.h264
```

```text
libva: Trying to open .../v4l2_request_drv_video.so
libva: va_openDriver() returns 0
Initialized VAAPI: version 1.22
Using hardware decoding (vaapi-copy).
VO: [drm] 1280x720 nv12
Exiting... (End of file)
```

Hardware decode on the VE plus display, no rebuild of ffmpeg, mpv or anything
else. The only missing piece was `LIBVA_DRIVER_NAME=v4l2_request`, because
libva otherwise derives the driver name from the DRM device and looks for a
`sun50i-h713-afbd_drv_video.so` that does not exist.

### And `vo=gpu` works too — the render-node claim was false

```text
GL_VERSION  = '3.1 Mesa 25.0.7-2+deb13u1'
GL_RENDERER = 'Mali-G31 (Panfrost)'
VO: [gpu] 1280x720 yuv420p
```

Mesa pairs the two devices by itself — `card0` is `sun50i-h713-afbd`
(display-only, no `DRIVER_RENDER`, correctly) and `card1`/`renderD128` is
`panfrost`. GBM allocates on the display device, Panfrost renders, EGL comes up.
This is the ordinary split render/display arrangement every ARM SBC uses, and it
needed no configuration at all.

So the driver was never missing anything: it already advertises
`DRIVER_GEM | DRIVER_MODESET | DRIVER_ATOMIC` with `DRM_GEM_DMA_DRIVER_OPS`
(PRIME import/export plus dumb buffers), which is exactly what GBM and a
compositor need.

### What is still not working

`--hwdec=vaapi` (zero-copy) with `vo=gpu` fails at *"Could not create a VA
display"* — before `vaInitialize`, since no `libva info:` lines appear at all.
Note `vo=drm` creates the VA display fine with the same driver and env, so this
is mpv's `vo=gpu` VA-display path specifically, not the VA driver.

The gap between the two paths:

| | works | copy |
| --- | --- | --- |
| `vo=drm` + `vaapi-copy` | **yes** | frame copied back to CPU, software scaled |
| `vo=gpu` + `vaapi` | no | would be zero-copy via EGL dmabuf interop |
| `vo=gpu` + `vaapi-copy` | untested | GPU-composited, still a readback |

`GL_EXT_EGL_image_storage` interop is present, so the zero-copy path is
plausible once the display is created.

### Upstream note: v4l2request is NOT in FFmpeg

Checked FFmpeg master's `configure`: no `--enable-v4l2-request`, no
`v4l2request` hwaccel entries, nothing. The `*_v4l2m2m` decoders that *are*
present are the **stateful** M2M wrappers and cannot drive Cedrus, which is a
**stateless** Request-API decoder. So "build ffmpeg with v4l2request" means
applying an out-of-tree patchset — which is now unnecessary anyway.

### Remaining rough edge

`vo=drm` prints `Failed to commit atomic request: Error number 22` (EINVAL) on
exit, after playing to EOF. Teardown only, but it is our driver returning
EINVAL to an atomic commit and worth understanding.

### `vaapi-copy` + `vo=gpu` also works, and the numbers are the real story

Both outputs work with hardware decode. Measured with `--untimed --no-audio`,
300 frames (`--loop-file=4`) so mpv's ~1.9 s startup is amortised — the first
attempt used 60-frame clips and was almost entirely startup, reporting 8 fps for
a path that actually does 40:

```text
720p                              1080p high
  vaapi-copy vo=null   137.3 fps    vaapi-copy vo=null    90.6 fps
  software   vo=null   206.9 fps    software   vo=null   174.5 fps
  vaapi-copy vo=drm     96.7 fps    vaapi-copy vo=drm     57.5 fps
                                    vaapi-copy vo=gpu     40.7 fps
```

**Software decode beats hardware-decode-plus-copy at both resolutions.** The VE
decodes fine; the readback of the decoded frame out of its buffer costs more
than four A53s spend decoding H.264 in the first place. That is the whole
result, and it reframes what `vaapi-copy` is for: it is not a throughput win, it
is a **CPU-offload** win, and the copy erases most of even that.

Displayed playback is comfortably realtime either way — 57.5 fps at 1080p
through `vo=drm`, 40.7 through `vo=gpu` — so this is a usable player today. But
hardware decode only *pays* once the copy is gone.

Two caveats on the numbers: the clips are 60 frames looped, so they sit in cache
and likely flatter software decode; and `--untimed` measures throughput, not
sustained realtime playback with audio and a UI competing for CPU.

### So zero-copy is the point, not an optimisation

This is what the DECD/KMS NV12 plane already demonstrated at **59.71 fps
unpaced with the GPU idle** — no readback, no CPU in the frame path. Getting
mpv onto that path is worth real effort, because it is the only configuration
where the VE is actually earning its keep.

### The VA-display failure: root-caused, fixed, and still not enough

The cause was **this device having no render node**. mpv's DRM/EGL context calls
`drmGetRenderDeviceNameFromFd()` on the *display* device to find a render node
for VA interop, and ours has none:

```text
/dev/dri/by-path/platform-5600000.display-card -> card0      (only card0 + controlD64)
/dev/dri/by-path/platform-1800000.gpu-render   -> renderD128 (panfrost)
```

The node mpv wants belongs to panfrost, and mpv gives no way to point it there —
`--vaapi-device` is honoured for the copy path and **ignored for interop**
(tested).

Patch 0092 (out of series) adds `DRIVER_RENDER`, giving `renderD129`. Results:

- **VA display now creates** on the interop path: `va_openDriver() returns 0`,
  `Initialized VAAPI: version 1.22`. So the diagnosis was right.
- **Mesa's pairing survived** — `GL_RENDERER='Mali-G31 (Panfrost)'` still, so
  the flagged risk of breaking kmsro did not materialise.
- **No regression**: `vaapi-copy` still decodes in hardware, 75.7 fps at 720p
  through `vo=gpu`.
- **But zero-copy still does not decode.** It now fails one layer deeper:

```text
h264: Failed to end picture decode issue: 1 (operation failed)
h264: hardware accelerator failed to decode picture
Attempting next decoding method after failure of h264-vaapi.
```

`vaEndPicture` — the actual decode submission — fails, repeatedly, and ffmpeg
falls back to software. So the render node was **necessary but not sufficient**.

Worth weighing before keeping 0092: `DRIVER_RENDER` on a display-only device
advertises a capability the hardware lacks, purely to satisfy a userspace
assumption. It bought a real step forward and broke nothing, but it does not
complete the job, so it earns its place only if the `vaEndPicture` failure turns
out to be solvable.

Next question for that: the copy path builds its VA device on `renderD128`
(panfrost) while interop now builds it on `renderD129` (this driver). If
`libva-v4l2-request` uses the DRM fd for surface allocation, those are not
equivalent, and that difference is the first thing to check.

### Method note

The first check after installing 0092 reported "no render node" and was wrong.
`install-kernel-fit.sh --reboot` returns immediately, so a ping-poll can find
the board still up on the OLD kernel and query that. Always confirm
`/proc/version` matches the FIT's build time before believing a post-install
measurement.

### The render node is NOT the discriminator — decode works on both

Compared the two VA devices directly with ffmpeg, taking mpv out of the picture:

```text
LIBVA_DRIVER_NAME=v4l2_request ffmpeg -hwaccel vaapi \
  -hwaccel_device /dev/dri/renderD128 -i clip.h264 -f null -    exit 0
  -hwaccel_device /dev/dri/renderD129 -i clip.h264 -f null -    exit 0
```

**Both decode cleanly.** So the earlier hypothesis — that the copy path works
because it uses panfrost's node while interop fails on ours — is **refuted**.
Decode does not care which DRM fd the VA device was built on.

What does fail is the interop plumbing:

```text
-vf hwmap=derive_device=drm,format=drm_prime
  Failed to created derived device context: -38   (ENOSYS)
```

ffmpeg cannot derive a DRM device from this VA-API device, which is precisely
the capability zero-copy needs. Note the driver *does* export the symbol —
`ExportSurfaceHandle`, `AcquireBufferHandle`, `DeriveImage` are all present in
`v4l2_request_drv_video.so` — so this is not a missing entry point.

### Where the zero-copy blocker actually is

Bounded, after eliminating the alternatives:

- **not the render node** — decode works on both, proven above;
- **not the VA driver's decode** — ffmpeg decodes on both nodes, and mpv's
  `vaapi-copy` decodes through the same driver at 75.7 fps;
- **not a missing export entry point** — the symbols are there.

It is the **VA-API ↔ DRM interop layer**: ffmpeg's device derivation returns
ENOSYS, and mpv's interop decode fails at `vaEndPicture` while the identical
driver decodes fine when nothing asks for exportable surfaces. The live
hypothesis is that mpv's interop path requests surface attributes the driver
allocates differently, and Cedrus then rejects the submission.

The full `libva-v4l2-request` source is built **on the board**, not in this
tree, which is where that thread continues.

### EndPicture has four failure paths, and one fits

Source is on the board at `/root/libva-v4l2-request/src/picture.c`
(`RequestEndPicture`, line 252). It returns `VA_STATUS_ERROR_OPERATION_FAILED`
from exactly four places:

```c
1. video_format == NULL                             format lookup failed
2. media_request_alloc(media_fd) < 0                no request fd
3. v4l2_queue_buffer(video_fd, -1, capture_type,…)  queueing the CAPTURE buffer
4. v4l2_queue_buffer(video_fd, request_fd, output_type,…)  the OUTPUT buffer
```

**Path 3 is the one that fits the evidence**, and the reasoning is the useful
part:

- Paths 1 and 2 are set up per context, not per frame, and would fail
  identically under `vaapi-copy` — which decodes fine at 75.7 fps through this
  same driver. They do not discriminate.
- Path 3 queues the **capture** buffer, the one holding decoded output. Under
  zero-copy that buffer is exported as a dma-buf and **held by EGL/GL for
  display**, so it cannot be re-queued while still referenced — `EBUSY`, and
  the pool runs dry. Under `vaapi-copy` the frame is copied out immediately and
  the buffer returns to the pool at once.

That is exactly the difference between the two paths, and it explains why the
failure repeats every frame rather than failing once at init.

It also rhymes with a problem this project already solved once: the DECD work
hit the same shape — surfaces returned to Cedrus while still being scanned out —
and the fix was a release fence. See the display notes.

**This is a ranked hypothesis, not a proven cause.** The decisive test is one
`printf` per path in `RequestEndPicture` and a rebuild on the board, which names
the branch directly instead of reasoning about it.

### Instrumented: it is `RequestSyncSurface`, by elimination

Marked every `OPERATION_FAILED`-capable exit of `RequestEndPicture` in the
on-board driver, rebuilt and ran `--hwdec=vaapi`. **None of them fired**, while
the decode failed three times. Complete exit coverage of the function:

```text
P1 video_format NULL          marked   did not fire
P2 media_request_alloc        marked   did not fire
P5 codec_set_controls rc      marked   did not fire
P3 queue CAPTURE buffer       marked   did not fire
P4 queue OUTPUT buffer        marked   did not fire
INVALID_CONTEXT/CONFIG/SURFACE  --     wrong code; ffmpeg reported 1
return status;  <- RequestSyncSurface  UNMARKED, the only path left
return VA_STATUS_SUCCESS
```

So the `OPERATION_FAILED` propagates out of **`RequestSyncSurface`**, which is
where the driver *waits for the decode and dequeues the capture buffer*.

That refines the earlier hypothesis rather than overturning it. The guess was
path 3, queueing the capture buffer; the reality is one step later, at
dequeue/sync. The underlying story is the same and now better located: under
zero-copy the capture buffer is exported as a dma-buf and held by EGL, so the
driver cannot complete the round trip on it. Under `vaapi-copy` the frame is
copied out immediately and the buffer comes straight back.

**Two method notes, both of which nearly produced a wrong answer:**

- The first instrumentation went into `/root/libva-v4l2-request`, which is
  **not** the tree that builds the installed driver — that is
  `/root/va-driver-build`. `ninja` reporting "no work to do" and the marker
  being absent from the binary is what caught it. Check which tree produces the
  installed artifact before editing.
- Marking only the literal `return VA_STATUS_ERROR_OPERATION_FAILED` statements
  missed two exits that propagate a status from a callee. Enumerate *every*
  return in the function, not just the ones matching the error you are chasing.

### State of the board

The instrumented driver is installed; the original is at
`/usr/lib/aarch64-linux-gnu/dri/v4l2_request_drv_video.so.orig-preprintf`, and
the pristine source at `/root/va-driver-build/src/picture.c.orig-preprintf`. The
markers only print on failure, so `vaapi-copy` is unaffected.

### ROOT CAUSE: the surface reaches sync with no media-request fd

Instrumented all seven failure exits of `RequestSyncSurface` (`surface.c`) the
same way. Exactly one fires:

```text
H713-SYNC: unknown failed rc=65535 errno=0
```

`rc` is uninitialised garbage and `errno` is 0, so this is a **state check, not
a syscall failure**. It is this one:

```c
request_fd = surface_object->request_fd;
if (request_fd < 0) {
        status = VA_STATUS_ERROR_OPERATION_FAILED;
        goto error;
}
```

**The surface arrives at sync with no media-request fd.** Note the branch just
above returns `VA_STATUS_SUCCESS` for any surface not in `VASurfaceRendering`,
so this surface *is* marked Rendering while carrying `request_fd < 0` — an
inconsistent state rather than a resource or timing problem.

That is a real narrowing, and it moves the diagnosis off the buffer-lifetime
theory. Nothing here is starved, busy or timing out: `media_request_wait_completion`
and both `v4l2_dequeue_buffer` calls never even run. The earlier reasoning
about EGL holding capture buffers was plausible and is **not** what is
happening.

`RequestEndPicture` allocates the fd and stores it on the surface, so the
question is what clears or bypasses it on the interop path. Two candidates,
neither yet tested:

- **a double sync.** `picture.c:236` calls `RequestSyncSurface` internally, and
  mpv's interop also syncs explicitly before exporting the surface for EGL. If
  the first sync releases the fd without moving the surface out of
  `VASurfaceRendering`, the second finds `-1`.
- **a surface that never went through EndPicture** — e.g. one taken from the
  pool and synced before being rendered.

The asymmetry to explain: 3 decode failures but only 1 sync marker, so the other
two failures leave by some path that is still unaccounted for.

### State of the board

Instrumented driver installed. Pristine copies kept alongside:
`picture.c.orig-preprintf`, `surface.c.orig-preprintf`, and
`v4l2_request_drv_video.so.orig-preprintf`. Markers print only on failure, so
`vaapi-copy` playback is unaffected.

### CORRECTION: EndPicture never runs, and the sync failure is a symptom

Entry logging settles it and **overturns the conclusion above**:

```text
H713-ENTRY sync:   surface=67108865 state=4 request_fd=-1
H713-ENTRY sync:   surface=67108864 state=1 request_fd=-1
H713-SYNC: unknown failed

ENTRY endpic     0      <- RequestEndPicture's body NEVER runs
ENTRY sync       2
decode failures  3
```

`RequestEndPicture` never reaches its body across all three failures. The
earlier "by elimination it must be `RequestSyncSurface`" reasoning silently
assumed EndPicture was running; it is not, so the elimination was invalid even
though every individual observation in it was correct.

The sync failure is a **consequence, not the cause**. Surface `67108864` sits in
state 1 (`VASurfaceRendering`) with `request_fd = -1` because EndPicture never
got far enough to allocate one. Surface `67108865` is state 4
(`VASurfaceReady`) and returns SUCCESS through the early branch, which is why
only one of the two syncs fails.

**The instrumentation flaw that hid this**: the entry log was placed before
`gettimeofday`, which is *after* the `INVALID_CONTEXT` / `INVALID_CONFIG` /
`INVALID_SURFACE` early returns. An exit through any of those is invisible to
it. Marking only the paths that return the error you are chasing, and logging
"entry" somewhere other than the first line, both hide exits.

### Where it actually stands

`vaEndPicture` returns `VA_STATUS_ERROR_OPERATION_FAILED` (ffmpeg reports code
1) while the driver's implementation never reaches its body. Only two things can
produce that:

- an exit through one of the three unmarked `INVALID_*` returns — but those
  return codes 4, 5 and 6, not 1, so they do not match what ffmpeg reported;
- **the failure happens inside libva, before dispatch to the driver at all.**

The second is now the leading candidate, and it is a different problem from
everything investigated so far — not the render node, not buffer lifetime, not
the driver's decode path.

### It IS dispatched — and exits through an unmarked INVALID_* return

Moving the entry log to the first line corrects the previous section as well:

```text
H713-ENTRY sync:   surface=67108865 state=4 request_fd=-1   -> SUCCESS (Ready)
H713-ENTRY endpic: CALLED ctx=33554432
H713-ENTRY endpic: CALLED ctx=33554432
H713-ENTRY sync:   surface=67108864 state=1 request_fd=-1   -> FAILS
H713-ENTRY endpic: CALLED ctx=33554432

ENTRY endpic: CALLED   3     matching the 3 decode failures
H713-ENDPIC            0     no OPERATION_FAILED path fires
```

So "never dispatched" was wrong too. `RequestEndPicture` **is** called, three
times, once per failure. It exits before its main body — it never reaches
`gettimeofday`, which is why the earlier entry log was silent, and never reaches
the internal `RequestSyncSurface` at the end, which is why only two syncs appear
instead of five.

By order of the exits, and with `P1` (`video_format NULL`) instrumented and
silent, the only remaining ways out before the body are the three **unmarked**
returns:

```c
return VA_STATUS_ERROR_INVALID_CONTEXT;   /* context_object == NULL */
return VA_STATUS_ERROR_INVALID_CONFIG;    /* config_object  == NULL */
return VA_STATUS_ERROR_INVALID_SURFACE;   /* surface_object == NULL */
```

**One thing does not add up and is left open honestly.** Those return codes are
5, 4 and 6, while ffmpeg reports `issue: 1`, which is
`VA_STATUS_ERROR_OPERATION_FAILED`. Either ffmpeg's message is not reporting the
driver's return directly, or something between the driver and ffmpeg
substitutes the code. That discrepancy should be resolved rather than assumed
away — it is the kind of gap that has already invalidated two conclusions in
this investigation.

Note the context id is stable at `33554432` across all three calls, so the
context handle itself is not obviously being lost between calls.

### RETRACTION: the instrumentation broke the driver

Marking the three `INVALID_*` returns produced a run where **nothing at all
fired** — not `P1`, not the `INVALID_*` markers, not the mid-function entry log
— while EndPicture was entered three times. Reading the patched source explains
why, and invalidates everything measured since the first instrumented build:

```c
	if (video_format == NULL)
		fprintf(stderr, "H713-ENDPIC: P1 video_format NULL\n");
		return VA_STATUS_ERROR_OPERATION_FAILED;   /* now UNCONDITIONAL */
```

The original is a **braceless `if`**. Inserting a line before the return left
the `if` guarding only the `fprintf` and made the return unconditional, so
`RequestEndPicture` failed immediately on every call — returning exactly
`VA_STATUS_ERROR_OPERATION_FAILED`, which is precisely the symptom under
investigation.

**Everything measured after the first instrumented driver was installed is
void:**

- "the failure is in `RequestSyncSurface`, by elimination" — void;
- "EndPicture never runs" — void;
- "EndPicture exits via an unmarked `INVALID_*` return" — void.

Each was reasoned correctly from observations that were themselves artefacts.
The one genuine clue in the whole sequence — that the marked paths stayed silent
— had a much simpler explanation than any of the theories built on it.

Also note the "discrepancy" flagged earlier, that the `INVALID_*` codes are
4/5/6 while ffmpeg reported 1, was the tell. It was recorded as unresolved
rather than explained away, and it was pointing straight at this.

**What survives**: the pre-instrumentation observation stands, because it was
taken against the pristine driver — `--hwdec=vaapi` fails with
`Failed to end picture decode issue: 1` while `--hwdec=vaapi-copy` works. That
is still the real bug, and it is still uninvestigated.

The driver has been restored from `picture.c.orig-preprintf` and
`surface.c.orig-preprintf`, rebuilt and reinstalled; `vaapi-copy` verified
working again with zero decode failures.

### The lesson, which is the durable part

**Never insert a statement before a `return` without checking for braces.** A
text-level edit that is syntactically valid can silently change control flow. If
instrumenting, either add the braces or log from inside an existing block — and
after patching, *read the patched source* rather than trusting that the edit did
what was intended. The project already had a rule for this ("verify edits, not
strings"); this is the same failure in a new form, and it cost four rounds.

### Correctly instrumented: queueing the CAPTURE buffer fails with EINVAL

Re-instrumented converting each braceless `if` into a braced block in the same
edit, and **read the patched source before building** this time. Seven exits
instrumented, each with a distinct label, plus a control run:

```text
control (vaapi-copy):  hw decode 1, failures 0, markers 0   <- driver healthy
zero-copy (vaapi):     H713-ENDPIC: E6 queue CAPTURE failed
                       rc=-1 errno=22 (Invalid argument)
```

So the failure is at **`v4l2_queue_buffer(video_fd, -1, capture_type, ...)`** —
queueing the capture buffer — which was the original hypothesis before the
broken instrumentation buried it.

**But the errno refutes the reasoning behind that hypothesis.** The story was
that EGL holds the exported dma-buf so the buffer cannot be re-queued; that
would give **EBUSY**. It gives **EINVAL**. Nothing is held or busy — the driver
is passing an argument V4L2 rejects.

EINVAL from `VIDIOC_QBUF` usually means the buffer index is out of range, the
buffer type is wrong, or **the memory type does not match how the queue was set
up** — e.g. queueing `V4L2_MEMORY_MMAP` against a queue configured for
`V4L2_MEMORY_DMABUF`, or the reverse. That last one is exactly the kind of
mismatch zero-copy interop would introduce and the copy path would not, which
makes it the strongest candidate.

The control run matters as much as the result: `vaapi-copy` produces **zero
markers and zero failures** on the same instrumented driver, so the
instrumentation is not itself changing behaviour this time.

One asymmetry still unexplained: one marker against three decode failures. The
other two may fail after the first leaves the queue in a different state, or
may fail elsewhere entirely. Do not assume all three share a cause.

### The failing QBUF, with arguments

```text
H713-ENDPIC: E6 queue CAPTURE failed rc=-1 errno=22 (Invalid argument)
             type=1  index=2  count=1  surface=67108864
```

`v4l2_queue_buffer` hardcodes `buffer.memory = V4L2_MEMORY_MMAP` and sets
`buffer.index = index`, `buffer.length = buffers_count`. So a memory-type
mismatch is **ruled out** — the copy path uses the same hardcoded value and
works. `type=1` is `V4L2_BUF_TYPE_VIDEO_CAPTURE` (non-mplane) and `count=1`,
both identical in principle between the paths since the same function computes
them.

That leaves **`index=2`**.

### The ordering is the clue

Instrumenting `VIDIOC_REQBUFS` shows the failing queue happens **before the
buffers exist**:

```text
zero-copy:  E6 queue CAPTURE failed ... index=2      <- FIRST
            H713-REQBUFS: type=2 asked=0 granted=0
            H713-REQBUFS: type=1 asked=0 granted=0

control:    H713-REQBUFS: type=2 asked=0 granted=0
            H713-REQBUFS: type=1 asked=0 granted=0
            (no E6, no failures)
```

Note both runs only ever log `asked=0`, which is REQBUFS' *free* operation, so
these are teardown. **No allocating REQBUFS is logged at all in either run** —
the capture buffers are not allocated through `v4l2_request_buffers` on this
path, and where `destination_index = 2` comes from is therefore still unknown.

The working reading of the evidence: under interop the surface carries a
`destination_index` that does not correspond to an allocated buffer at the
moment EndPicture queues it, and `VIDIOC_QBUF` rejects the index with EINVAL.
That is consistent with EINVAL rather than EBUSY, and with the copy path never
hitting it.

**Still unexplained, and worth not papering over:** one E6 marker against three
decode failures. If every frame took this path there should be three.

### ROOT CAUSE: the third surface is half-allocated

The buffers come from **`v4l2_create_buffers` (`VIDIOC_CREATE_BUFS`)**, not
REQBUFS — which is why the earlier REQBUFS instrumentation only ever saw
teardown. Instrumenting the real allocator and the `destination_index`
assignment shows the two paths diverging on the third surface:

```text
CONTROL (vaapi-copy, works)          ZERO-COPY (vaapi, fails)
CREATEBUFS type=1 -> index_base=0    CREATEBUFS type=1 -> index_base=0
CREATEBUFS type=2 -> index_base=0    CREATEBUFS type=2 -> index_base=0
ASSIGN destination_index=0           ASSIGN destination_index=0
CREATEBUFS type=1 -> index_base=1    CREATEBUFS type=1 -> index_base=1
CREATEBUFS type=2 -> index_base=1    CREATEBUFS type=2 -> index_base=1
ASSIGN destination_index=1           ASSIGN destination_index=1
(stops -- 2 surfaces)                CREATEBUFS type=1 -> index_base=2
                                     (no type=2, no ASSIGN)
```

Every `CREATE_BUFS` succeeds (`rc=0 granted=1`). The difference is that
zero-copy requests a **third** surface, and its setup **aborts after the capture
buffer is created and before the output buffer is created** — so
`destination_index` is never assigned for it.

That produces exactly the observed failure: a half-built surface whose capture
buffer exists at index 2 while the surface itself was never completed, queued
later by `EndPicture` and rejected with **EINVAL**.

It also explains the 1-marker/3-failure asymmetry that had been outstanding:
only the third surface is broken, so only one queue attempt hits E6 while
ffmpeg retries and reports three.

**Where the abort happens** is now the narrow question. Between the two
`v4l2_create_buffers` calls, `surface.c` does a `v4l2_query_buffer` on the
output queue and an `mmap`, either of which returns
`VA_STATUS_ERROR_ALLOCATION_FAILED`:

```c
rc = v4l2_query_buffer(driver_data->video_fd, output_type, ...);
if (rc < 0) return VA_STATUS_ERROR_ALLOCATION_FAILED;
source_data = mmap(...);
if (source_data == MAP_FAILED) return VA_STATUS_ERROR_ALLOCATION_FAILED;
```

Neither is instrumented yet, and the type=2 `CREATE_BUFS` for surface 3 never
even logs its "asked" line, so the abort is at or before that call.

### RETRACTION: the third surface is NOT half-allocated

The section above is wrong, and the cause was **my own truncated output** — the
trace was read through `head -12`, which cut it mid-sequence. The full log:

```text
CREATEBUFS type=1 -> index_base=2
CREATEBUFS type=2 -> index_base=2      <- the "missing" output buffer
ASSIGN destination_index=2             <- the "missing" assignment
CREATEBUFS type=1 -> index_base=3
CREATEBUFS type=2 -> index_base=3
ASSIGN destination_index=3
E6 queue CAPTURE failed ... index=2
```

**All four surfaces are fully built**, capture and output and assignment, and
every `CREATE_BUFS` returns `rc=0 granted=1`. The queue failure happens *after*
allocation completes, on a buffer that genuinely exists and is genuinely
assigned.

So "half-allocated surface" is void, and with it the tidy explanation it gave
for the 1-marker/3-failure asymmetry. That asymmetry is **open again**.

### What is actually established

- Buffers are created with `VIDIOC_CREATE_BUFS`, one capture and one output per
  surface, indices 0..3. Zero-copy builds four surfaces; copy builds two.
- The failing call queues **capture index 2**, which exists, with EINVAL.
- `buffer.memory` is hardcoded `V4L2_MEMORY_MMAP` on both paths, so that is not
  the difference.

### The candidate this reopens

`VIDIOC_QBUF` on a buffer that is **already queued** is rejected, and several
V4L2 drivers report that as EINVAL rather than EBUSY. That is the original
buffer-lifetime hypothesis, which was dismissed earlier *on the grounds that
EINVAL is not EBUSY* — reasoning that was never verified against what this
driver actually returns. Under interop the decoded frame is exported and held
by EGL, so the buffer would still be queued when EndPicture tries to queue it
again; under copy it is dequeued immediately.

That is now the leading explanation and it has not been tested.

### CONFIRMED: the capture buffer is queued twice and never dequeued

Logging every `VIDIOC_QBUF` and `VIDIOC_DQBUF` on the capture queue settles it,
with the working path as the control:

```text
CONTROL (vaapi-copy, works)        ZERO-COPY (vaapi, fails)
QBUF  index=0                      QBUF  index=2   rc=0
DQBUF index=0                      QBUF  index=3   rc=0
QBUF  index=1                      QBUF  index=2   rc=-1 errno=22
DQBUF index=1
QBUF  index=2                      60 QBUF / 60 DQBUF  vs  3 QBUF / 0 DQBUF
DQBUF index=2   ... strict 1:1
```

**The copy path queues and dequeues each buffer exactly once, 1:1. The interop
path never dequeues at all**, and the third queue reuses index 2 while it is
still queued — which V4L2 rejects with **EINVAL**.

So the original buffer-lifetime hypothesis was right, and the reasoning that
dismissed it was wrong. It was dismissed because the errno was EINVAL rather
than EBUSY; **V4L2 returns EINVAL for queueing an already-queued buffer**, so
the errno never contradicted the theory. Assuming a specific errno for a
condition, without checking what the interface actually returns, cost several
rounds.

This also explains the 1-marker/3-failure asymmetry that has been open
throughout: only one re-queue collides before decoding stops.

### Why it happens

Under `vaapi-copy` the decoded frame is copied out immediately, so the buffer is
dequeued and returns to the pool. Under interop the frame is exported as a
dma-buf for EGL and **nothing ever completes the round trip** — no dequeue
happens, buffers are never recycled, and the driver eventually re-queues an
index that is still outstanding.

That is the same class of bug as the DECD release fence this project already
solved once: a consumer holds a buffer and the producer is never told it is
free.

### Who should dequeue: `RequestSyncSurface` — and it early-exits instead

`RequestSyncSurface` owns the dequeue. It **is** being called on the interop
path; it simply never reaches the dequeue:

```text
CONTROL (vaapi-copy):  120 SyncSurface calls -> 60 DQBUF
ZERO-COPY (vaapi):       4 SyncSurface calls ->  0 DQBUF
```

The sequence shows the shape of it:

```text
SYNC surface=67108865        <- sync before any queue
QBUF index=2 rc=0
SYNC surface=67108864
QBUF index=3 rc=0
SYNC surface=67108865
SYNC surface=67108864
QBUF index=2 rc=-1 errno=22
```

The function opens with a state guard:

```c
if (surface_object->status != VASurfaceRendering) {
        status = VA_STATUS_SUCCESS;
        goto complete;          /* returns SUCCESS without dequeuing */
}
```

Every interop sync takes that branch, because the surfaces are not in
`VASurfaceRendering`. The guard is reasonable in itself — syncing a surface that
was never rendered should be a no-op — so the fault is upstream of it: **nothing
is putting these surfaces into `Rendering` state.**

That is consistent with the whole chain. `EndPicture` is what would normally
drive a surface through rendering, and on this path its capture queue fails, so
the surface never advances; the next sync sees a non-Rendering surface, returns
SUCCESS, no dequeue happens, the buffer stays queued, and the following queue of
the same index is rejected. Cause and symptom sit in a loop, which is why each
individual step looked like the culprit in turn.

### The open question, stated precisely

Which is first: does the surface fail to enter `Rendering` because the queue
failed, or does the queue fail because the surface was never in `Rendering`?
The very first `QBUF index=2` **succeeds** (`rc=0`), so at least one queue
happens before any failure — meaning the state problem is not merely downstream
of a failed queue.

Worth noting the timing too: the first sync happens *before* any queue at all,
which suggests mpv syncs a surface it is about to reuse. In the copy path that
sync finds a rendered surface and dequeues it; here it finds nothing to do.

### Suggested next steps, cheapest first

1. Log `surface_object->status` at every transition — where it is set to
   `Rendering`, `Displaying` and `Ready` — and correlate with the sync calls.
   That resolves the ordering question directly.
2. Check whether `vaExportSurfaceHandle` (the interop-only call) moves the
   surface out of `Rendering` without dequeuing. It is the one operation the
   copy path never performs, which makes it the prime suspect for breaking the
   state machine.
2. Compare the surface release path: `vaapi-copy` presumably syncs and
   dequeues, while interop's exported surfaces may never reach that code.
3. Whether the eventual fix belongs in `libva-v4l2-request` or in how mpv
   releases surfaces is open, but the missing operation is now specific.
2. Confirm what the Cedrus/V4L2 core returns for a double `QBUF`, rather than
   assuming EINVAL means "invalid argument" in the narrow sense.
3. Re-explain the 1-marker/3-failure gap, which no longer has an account.
2. Ask why interop wants three surfaces where copy wants two. If the third is
   simply one more than the driver can build, the fix may be a pool-size limit
   rather than a bug in the failing call.
2. Trace the real allocation path, since `v4l2_request_buffers` is only being
   called with count=0 — the buffers are created somewhere else, and that
   somewhere is what differs between interop and copy.
3. Explain the 1-marker/3-failure discrepancy before treating this as solved.
2. Check how the capture queue is configured (`VIDIOC_REQBUFS` memory type)
   versus what the surfaces are exported as under interop.
3. Explain the 1-marker/3-failure gap before treating the cause as settled.
2. Then resolve the code mismatch: log the value `RequestEndPicture` actually
   returns, and compare it against what ffmpeg prints. If they differ, the
   problem is between libva and ffmpeg, not in the driver.
3. Note the failing surface reaches sync in `VASurfaceRendering`, so
   `BeginPicture` ran and set that state. Whatever lookup fails in EndPicture
   succeeded in Begin, which is a useful asymmetry to exploit.
2. If it is never dispatched, instrument `RequestBeginPicture` and
   `RequestRenderPicture` too — the surface reaching sync in `Rendering` state
   means Begin ran, so the break is between Begin and End.
3. Only then look at libva's dispatch layer.
2. Only then decide whether the fix belongs in the driver (keep the fd, or
   return SUCCESS for an already-synced surface) or in how mpv drives it.
2. If it is buffer starvation, count the capture buffers the pool is given and
   whether mpv/EGL ever release them. This is the same class of problem as the
   DECD release fence, which this project has already solved once.
2. If it is path 3, the question becomes buffer lifetime: how many capture
   buffers the pool has, and whether mpv/EGL release them. That is the same
   class of problem as the DECD release fence. `vo=gpu` +
   `vaapi-copy` creates a VA display fine with the same driver and env, so the
   fault is narrow and the `GL_EXT_EGL_image_storage` interop is present.
2. A Wayland compositor plus mpv's `dmabuf-wayland` vo (already compiled in) is
   the other zero-copy route needing no media-stack changes.
3. Investigate the EINVAL our driver returns on `vo=drm` atomic teardown.
   `vo=gpu` does not provoke it.
4. Re-measure with longer, non-looping content before drawing conclusions about
   sustained playback.
