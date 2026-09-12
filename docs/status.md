# Status

What works on the H713 mainline stack, and what's next. All hardware results are
on the **HY200 bench board (DDR3)** unless noted — the HY200 QZ713_V2 projector (LPDDR3)
is not risked for bring-up.

_Last updated: 2026-09-12._

## Video playback — where it stands (scaling answered 2026-09-12)

> ## SCALING: ANSWERED 2026-09-12 — read this before the narrative below
>
> Full handoff: **[handoff-2026-09-12-ve-scaledown.md](handoff-2026-09-12-ve-scaledown.md)**
>
> **1080p on the 720p panel is possible by exactly one no-GPU route, and both of
> its hardware halves are now confirmed on the board. It is not built.**
>
> ```
> 1920x1080 --[ VE power-of-two, decode-time ]--> 960x544
>           --[ proc upscaler 0x05180000, 1.333x ]--> 1280x720
> ```
>
> - **Stage 1** is `VE_H264_SDROT_CTRL` at **`0x240`** (the H.264 *engine* block,
>   not the top-level VE), with luma/chroma addresses at `0x244`/`0x248`. Two
>   2-bit fields: `[9:8]` horizontal, `[11:10]` vertical, each 1:1 / 1/2 / 1/4.
>   **Power-of-two per axis, so there is no 1280x720 from the decoder.**
> - **Stage 2** needed one register nobody had ever set: **`0x34`, the input
>   window**. Every earlier magnification run left it at {1280,720} and got a
>   clipped picture; set it to the real input size and the magnified image fills
>   the panel. Operator-confirmed.
> - **Cost: ~8.5 dB** against the arbitrary-ratio path, carrying **56%** of the
>   panel's luma samples. Measured, not estimated.
>
> **The VE's arbitrary-ratio scaler is CLOSED — the datapath is not implemented
> on this part.** Its register block is real (`getRegBase(7)` = **VE + `0xf00`**),
> every write latches and holds, the genuine polyphase coefficients are extracted
> and committed, the selection is pure software with **no hardware enable bit** —
> and nothing ever comes out. `VE_VERSION` reads `0`. Do not re-probe it; the only
> remaining falsifier is booting the vendor stack and watching what it emits.
>
> **The display pipeline has no downscaler at all** — census complete, exactly
> three ratio-carrying blocks, all ruled out. See
> [reference/scaler-census-2026-09-11.md](reference/scaler-census-2026-09-11.md).
>
> **What is left is entirely software**, and both pieces are specified in the
> handoff: cedrus must make the 960x544 secondary output the V4L2 capture buffer
> (the risky part — DPB reference pointers), and `sun50i-h713-afbd.c` declares
> `DRM_PLANE_NO_SCALING` and rejects anything that is not exactly 1280x720.
>
> Everything from "2026-09-10, statically" down to the end of this section is
> **historical** — the reasoning that led here, including several corrections.
> It is kept because the corrections are instructive, not because it is current.


**A file plays on the panel with picture and sound, hardware-decoded, no GPU.**
`mpv --vo=drm --hwdec=vaapi` on the patched mpv, operator-confirmed on 720p
H.264 + AAC. The build is reproducible (`tools/video/build-mpv.sh`, an emulated
arm64 container) and drift-checked (`tools/video/check-video-stack.sh`).

**It works at 1280×720 and no other resolution, and that is still the headline
limit.** What changed on 09-04 is that we now know *how stock does it*.

> **2026-09-10, statically, no board time — the scaling investigation has been
> chasing the wrong registers since 09-05.**
> [reference/composition-ratio-registers-are-line-buffers-2026-09-10.md](reference/composition-ratio-registers-are-line-buffers-2026-09-10.md)
>
> - `0x05000174`, `0x050001b4`, `0x050000f0` (and the channel-B `0x274`,
>   `0x2b4`, `0x210`) are **not scaler ratios**. They are the AFBD fetch
>   line-buffer descriptor — **Rowbyte, LineBufLevel, LineNumber** for Y and C —
>   named in the producing function's own log line
>   (`FrameBuffer::GetPsuPfuWin`, `0x8b1a2668`). Nothing else in the image writes
>   them. **There is no ratio value to find, and `PHASE=scale` is dead.**
> - The "`0x2B`/`0x40` = `852/1280`" evidence is an artefact: Rowbyte is linear
>   in the picture width, so any two widths reproduce the width ratio whether or
>   not anything scales.
> - What the 09-05 firmware run actually did with an 852x480 picture on a
>   1280x720 panel was **letterbox it** — borders of exactly `1280-852` and
>   `720-480`, in that same capture.
> - **The panel down-scaler negative below is WITHDRAWN.** The branch decode in
>   `WriteDownScalerRatio` was inverted: `0x051c0124[26:25] = 3` is **bypass**.
>   Both 09-04 runs wrote `0x051c0138` alone and left the stage switched off.
>   `0x051c0120`–`0x051c0138` is now the live scaling lead — unity is
>   `0x00010000`, 16.16, confirmed on stock and on our board.
> - **The ratio producer is traced.** `CalcScalingRatio_2` (`0x8b19fb50`):
>   `ratio = (out_vSize << 16) / in_vSize`, clamped to unity when `out >= in`.
>   **`dst/src`, always ≤ `0x10000`, downscale-only** — the 09-04 test's
>   `0x18000` is a value this firmware can never emit. 1080→720 is **`0xAAAA`**.
>   Not pre-computed, so the CPU_COMM lead for it is closed.
> - **The panel down-scaler is VERTICAL ONLY** — one ratio, no output width, no
>   horizontal ratio anywhere in the block. It can do `1080 → 720`; it cannot do
>   `1920 → 1280`. Treat it as an aspect-fitting squeezer, not a resizer.
> - **The corrected test ran 2026-09-10 on the RGB path: NEGATIVE.** Stage
>   enabled (`0x051c0124[26:25] = 0`, verified), the firmware's own ratio
>   `0xAAAA`, all seven registers, all seven readbacks matched, text pattern
>   operator-confirmed on the glass, pulsed 4×8 s. **No change.** The field is
>   **not gated** with the MIPS parked — that part is a positive.
>   `tools/display/panel-downscaler-engage.sh`.
> - Not "route closed": the **video** side of the `0x051c006c` mux is still
>   untested with the stage on, and we cannot yet place this stage relative to
>   where we inject. But the ceiling on the whole route is a vertical aspect-fit,
>   so neither residual earns a run on its own.
>
> **NEW LEAD, and the best one yet — a TWO-AXIS scaler at `0x05180000`.**
> [reference/two-axis-scaler-found-2026-09-10.md](reference/two-axis-scaler-found-2026-09-10.md)
>
> - Separate **H ratio** `0x05180008[21:0]` and **V ratio** `0x0518003c[21:0]`,
>   16.16, unity `0x10000`, written by `ProcWinNode::WriteReg` via `0x8b1a66d0`.
>   Four instances at `0x100` stride — the firmware's stage table names
>   `proc-vs_upscaler` and `proc-vde_upscaler`.
> - **Confirmed against hardware before any experiment**: the 08-31 MIPS-alive
>   capture and our cold-booted board today read identically, and every derived
>   field matches — including the H phase reading exactly `0x8000`, which the
>   code computes as `(unity + ratio) >> 2`.
> - Reachable with `devmem`; our driver does not map it, so no kernel change.
> - **`0x05180014[27]` is a bypass and is currently set.** Writing a ratio
>   without clearing it would repeat the error made twice already.
> - Open: whether it is on our path, which instance carries our raster, and
>   which size registers are input vs output. The last is static work.
>
> **`block-survey.py` counts `lui` sites, not accesses**, so this block scored
> "1, not characterised" and sat at the bottom of the table for months. Use
> `tools/mips/block-map.py` for size; the survey is still sound for proving a
> block is *unreachable*.
>
> ## POSITIVE, 2026-09-11 — the scaler IS on our video raster
> [reference/proc-scaler-video-2026-09-11/RESULT.md](reference/proc-scaler-video-2026-09-11/RESULT.md)
>
> **The first positive control on a scaler in this project.** The sweep was
> filmed and measured frame by frame. Engaging `0x05180000` grossly and
> repeatably changes the picture on the DECD video path; disengaging restores it.
>
> Whole-frame mean luminance at 5 fps separates the states cleanly (engaged = a
> flat light field ≈ 69, normal ≈ 30). Three sustained windows of 16.8 s, 17.0 s
> and 11.6 s, alternating with normal video, matching the script's blink
> structure to **within 0.3 s** under an independently measured ssh latency of
> 0.62 s per write.
>
> - **instance 0 — LIVE** (1 blink, 16.8 s)
> - **instance 1 — LIVE** (2 blinks, 17.0 s and 11.6 s)
> - **instance 2 — not on our raster** (3.0 s transient during the write
>   sequence, then normal for 69 s through two more blinks)
> - instance 3 — never ran
>
> **The effect is not a clean 2× downscale.** Engaged, the panel shows a flat
> light-grey field with the picture crushed into a narrow sliver hard against the
> right edge, full height. The block is in the path, but
> `in 1280x720 / out 640x360 / ratio 0x8000` is not a configuration the rest of
> the pipeline agrees with.
>
> **This refutes "we inject downstream of the whole WCE chain"** for this block,
> and it positively explains the 09-10 null: those stills were taken after mpv
> fell back to software decode into the primary XR24 plane, which reaches the
> panel by the RGB/OSD route. **That route does not traverse `0x05180000`; the
> DECD video raster does.**
>
> Next: sweep `ratio_h` alone with geometry at 1280x720 and `ratio_v` at unity;
> and vary `0x0518002c[31:16]` and `0x05180044` (the 53 and 49 offsets), which
> the right-edge displacement points at. Use instance 0 or 1.
>
> ---
>
> **CORRECTION, 2026-09-10: the test below is RGB-path evidence only, and the
> "three blocks, one explanation" conclusion drawn from it is WITHDRAWN.**
> The 77 s clip looped mid-run; VAAPI failed to re-initialise
> (`Failed to create decode context: 1`) and mpv fell back to **software decode
> into the primary XR24 plane**. Both photographs were taken after that, so they
> compare scaler-engaged vs bypassed on the **RGB/OSD raster** — the gate this
> block's own test calls the weaker one, because `0x05180000` sits on the
> proc/video stage. **The video path is unresolved.** The sweep's first pass did
> run on hardware decode with the operator watching, but nothing was recorded.
> The gate checked the raster once at t≈10 s and never rechecked; it now
> re-verifies between instances and refuses a clip shorter than the run.
>
> Also corrected: **`block-map.py` had a false-positive bug** — it did not
> invalidate a base register when something else defined it, so
> `move $s0, $a0` followed by `sw $t3, 0x6c($s0)` was reported as a write to
> `0x051c006c` that does not exist. Fixed. The `0x05180000` finding is unchanged
> (13 registers, verified by direct disassembly and live register match), but
> the inflated counts quoted for `0x050c0000` (83) and `0x05140000` (72) were
> wrong; corrected figures are 51 and 18.
>
> **TESTED 2026-09-10 — negative on the RGB raster.**
> [reference/proc-scaler-2026-09-10/RESULT.md](reference/proc-scaler-2026-09-10/RESULT.md)
> All four instances engaged at ratio `0x8000` (exactly one half, both axes),
> bypass cleared, photographed engaged and restored with nothing else changed.
> The face spans the same fraction of the lit rectangle in both — it would have
> been half the linear size. Frames were live (the pose differs between shots).
> Writes stick and restore is exact, so the block is not gated.
>
> ### ~~The real finding: three blocks, three nulls~~ — WITHDRAWN
>
> | block | claimed | what the test actually exercised |
> | --- | --- | --- |
> | `0x05000000` | no scaler | **stands** — static, unrelated to injection |
> | `0x051c0120` | negative, stage on | **RGB raster only** |
> | `0x05180000` | negative, bypass cleared | **RGB raster only** |
>
> One static fact and two RGB-path nulls, on blocks that both sit on the
> **video** stage. Not three legs. The downstream-injection hypothesis may still
> be right — it was raised on 09-04 for good reasons — but this does not confirm
> it, and "stop testing blocks one at a time" was the wrong call to draw.
>
> ### What the `0x051c006c` trace did establish
>
> **The display firmware never writes `0x051c006c`.** A corrected whole-image
> scan finds 57 registers written in the LVDS block and the selector is not one
> of them; nothing in `0x051c0060`–`0x051c0078` is touched. So the mux we use to
> route video to the panel is not part of the MIPS window pipeline's own
> configuration — on stock it must be set by the ARM-side Android driver, which
> matches `lvds-006c-stock-causal-2026-08-31.md`: forcing it to our value blacked
> out stock video for exactly the hold window.
>
> Still open: what its sources are and where they tap. That is the question, and
> it is still static.

### Why our path cannot scale: we own the fetcher, not the pipeline

The silicon has a full display pipeline — fetch, then a manipulation chain
(scale, blend, compose), then serialize. Our KMS driver maps **three** windows:
`afbd` (`0x5600000`), `route` (`0x5140000`), `lvds` (`0x51c0000`). It does not
map the scaler, the vblender (`0x5200000`), the mixer (`0x525c000`) or the TCON
(`0x5880000`). Those are configured once during U-Boot/MIPS bring-up into a
fixed 1280×720 single-window setup and never touched again.

So on our path the middle stage is absent: stage 1 hands straight to stage 3.
Two consequences, both load-bearing:

- **No scaling.** DECD is a fetcher — one coordinate space, geometry and stride,
  no ratio register anywhere in its 1 KiB window.
- **No compositing.** The two DECD sources are a **switch, not a blender**: the
  driver quiesces RGB before enabling video and flips the selector at
  `0x051c006c` between `0x29000000` and `0x39000000`. Subtitles or an OSD over
  video are therefore the same class of problem as scaling.

### How stock scales: the inline scaler, MIPS-driven (settled 2026-09-04)

Static analysis of `display.bin`, no board time. A `lui`-immediate scan
(little-endian; `0xba60`/AFBD as positive control) over the MIPS address space
(**MIPS = ARM + `0xB5000000`**):

| block | MIPS `lui` | sites | verdict |
| --- | --- | --- | --- |
| scaler `0x05000000` | `0xba00` | **45** | most-referenced display block in the firmware |
| LVDS `0x051c0000` | `0xba1c` | 35 | |
| AFBD `0x05600000` | `0xba60` | 29 | positive control |
| route `0x05140000` | `0xba14` | 16 | |
| **GE2D `0x05240000`** | `0xba24` | **0** | never referenced |

At the 45 scaler sites the firmware **writes** exactly the registers sampled
live on 09-03 — `+0x174` (ratio `0x00400040`), `+0x178` (540), `+0x1b8` (1080),
and the second coordinate space at `+0x274`/`+0x278` (360)/`+0x2b8` (720).
**Stock scales inline, in the scanout path, with the MIPS driving it.**

The absence of GE2D is not a method artifact: no block address appears as an
aligned data constant anywhere in the binary — including the scaler's and
AFBD's — so this firmware forms every MMIO address from a `lui` immediate.

Bonus confirmation from the same scan: at the AFBD sites stock writes `+0x30`,
`+0x48` and `+0x4c`, the three source-geometry words our driver never touches.
See [handoff-2026-09-04-video-scaling-and-display.md](handoff-2026-09-04-video-scaling-and-display.md) §6.

### GE2D is dead, permanently — do not revive it

`ge2d@5240000` **is the projector's display controller, not a 2D engine.**
`compatible = "trix,ge2d"`; its reg windows are OSD/LVDS/AFBD; its vendor
sources are `sunxi_ge2d_panel.c`, `_backlight.c`, `_dlpc3435.c` (a TI DLP
controller), `_osd.c`. `ge2d_dev.ko` has **1111 symbols and zero** matching
scale/resize/ratio/zoom/stretch/blit/rotate — what it has is `ge2d_fb_init`,
`ge2d_create_osd_frame`, `tgd_vblender_irq`, `wait_for_disp_vsync`. There is no
Allwinner G2D on this SoC either.

This was established **2026-08-25** and marked "DEAD — do not spend a session on
this" in [handoff-2026-08-24-display.md](handoff-2026-08-24-display.md) under
"Hardware colour conversion", with a matching retraction in
[kms-display.md](kms-display.md). It was then re-introduced as "the
architecturally right answer" in the 09-03 revision of this file and re-confirmed
dead on 09-04. **The name carried the wrong expectation over — Amlogic's GE2D is
a blitter, this one is a display engine.** If a future revision proposes a GE2D
driver, that is a regression, not a plan.

### CPU_COMM cannot carry frames — the data path is the DECD ring

Asked and answered 2026-09-04, before any implementation. Handing the scaling to
the MIPS over CPU_COMM does not work, for three independent reasons:

1. **There is no frame-submit routine.** `THal_Vp_SetImageBufferAddr`
   (`0x8b10ada8`) and `GetImageBufferAddr` (`0x8b10adb0`) are verified **stubs**
   (`03e00008 00000000` = `jr ra; nop`). `Wce_SetWindow` has a real prologue but
   bottoms out in a stub at `0x8b1099c8`. See
   [reference/cpu-comm-call-table.md](reference/cpu-comm-call-table.md).
2. **CPU_COMM is a control channel, not a data path.** Stock's frame handoff to
   the MIPS is the **DECD four-slot Y/C ring** — the same registers our Linux
   driver now owns. There is nothing to "send".
3. **The scaler is inline, so there is no result to get back.** It scales during
   scanout; the output is pixels on the panel, not a buffer.

And the configuration it would require is the one that hard-locks the board:
live display MIPS + real Cedrus/DECD traffic is a **reproducible whole-SoC lock
with no watchdog recovery** — physical power cycle
([reference/cedrus-decd-first-visible-playback-2026-08-31.md](reference/cedrus-decd-first-visible-playback-2026-08-31.md)).
Note the open caveat: stock runs decode and MIPS display together successfully,
so that lock is plausibly *our* dual-ownership contention rather than a hardware
law — but testing it costs a power cycle per attempt.

### What remains for 1080p, in the order worth trying

1. **Drive the inline scaler from Linux, MIPS parked.** Still the live lead, and
   [tools/display/scaler-probe.sh](../tools/display/scaler-probe.sh) has now
   measured both halves of it (2026-09-04, MIPS parked, no operator time):

   - **The block is live and fully programmable from Linux.** All six ratio and
     coordinate registers (`+0x174`/`+0x178`/`+0x1b8`, `+0x274`/`+0x278`/`+0x2b8`)
     accept `0xDEADBEEF` verbatim — unmasked, full 32-bit — and restore cleanly,
     with zero IOMMU faults. It is neither held in reset nor register-gated.
     **Caveat, not yet separated:** this proves the *bus/register* interface is
     clocked. It does not prove the pixel-processing core is.
   - **Nothing in it moves under our traffic** — zero of 55 registers changed
     across a confirmed-scanning-out 720p DECD playback, and zero move at idle.
     **This does NOT mean it is off our path, and the probe's own first reading
     of it as such was wrong.** Phase 1 established the block has no
     free-running state *anywhere* — no counters, no status bits — and both
     ratio registers read `0x00400040`, **unity**. An inline pass-through
     configured to do nothing produces exactly this null whether or not pixels
     flow through it. The measurement does not discriminate.

   **The scaler is INLINE, and coupled to the AFBD fetch — settled by
   disassembly, no board time.** The 45 call sites fall in 23 functions, and
   `0x8b1a4810..0x8b1a4dbc` (364 instructions) programs **both** blocks: it opens
   by read-modify-writing `0x0010(AFBD)` — the video source control — calls three
   AFBD-only helpers, then programs the scaler's space A
   (`0x1b8`/`0x178`/`0x1b4`/`0x174`), space B (`0x2b4`/`0x2b8`/`0x274`/`0x278`),
   the `0x08xx` group, and finishes on `0x0040`. One routine, one pipeline.

   **It is not a fetcher.** Every one of the 45 accesses is `lw` then `sw` to the
   same offset — pure read-modify-write bit-field configuration. No fresh 32-bit
   value is ever stored and no address-like value appears anywhere in the window,
   so the "parallel fetch-and-scale path" reading of its IOMMU master-3 port is
   **refuted**.

   **The visible ratio test ran 2026-09-04 and is NEGATIVE.** With 720p playing
   and confirmed scanning out (4 distinct fbs cycling), `0x00800080` (2:1) was
   held for 8 s in each ratio register — `+0x274` (space B) then `+0x174`
   (space A) — and restored and verified each time. **Operator watched
   throughout: no change to the picture on either.** Zero IOMMU faults.

   **What the null does and does not mean.** It is not "the block cannot scale",
   and it is only weakly "the block is off our path", because a ratio written
   alone may never be latched. What the disassembly of the configuring routine
   now shows is more useful than another guess:

   - **The scaler's registers are filled from a window descriptor, gated by
     dirty bits** — `+0x01b4`/`+0x0174` take `lw` of `s0+0x90`/`+0x94`
     and `s0+0x9c`/`+0xa0`, `+0x00f0` takes `s0+0xa8`/`+0xac`. The firmware does
     no ratio arithmetic here; it copies precomputed fields. The scaler is part
     of the **window/composition layer**, not a standalone block.

     > **Corrected 2026-09-04.** The descriptor is an **`NRWinNode`**, not a
     > PanelWinNode, and the routine is `0x8b1a48cc` — `NRWinNode` vtable slot 4.
     > `0x8b1a4810` is an out-of-line cold block of a *different*, AFBD-only
     > function that starts at `0x8b1a4538`; the "364-instruction routine that
     > programs both blocks" read across a function boundary. Also **there is a
     > second scaler**, `PanelWinNode`'s panel down-scaler at
     > `0x051c0124`–`0x051c0138`, inside the LVDS window our driver already maps.
     > [reference/mips-wce-window-layer-2026-09-04.md](reference/mips-wce-window-layer-2026-09-04.md)
   - **Field layout, from the `ins` masks:** `+0x0174` and `+0x01b4` are
     `{[27:16] 12-bit, [15:0] 16-bit}` — *not* two 16-bit halves as assumed.
     `+0x00f0` is two 8-bit fields at `[7:0]` and `[15:8]`. `+0x0178`/`+0x01b8`
     are 16-bit at `[15:0]`.
   - **Space A's 1080/540 are hardcoded constants, not live geometry.** The
     branch at `0x8b1a4988` writes literal `1080` into `+0x01b8` and `540` into
     `+0x0178` as a fallback. Our live readings (`0x60020438`, `0x6002021C`) are
     exactly that default — the same class of inherited bring-up fallback as
     AFBD's 1920x1088, and not evidence of an active 1080p pipeline.
   - **`+0x0840`/`+0x0844` carry destination-shaped geometry** computed as
     `field-1`, `field+1` and round-to-even: live `0x05000030` = 1280 wide,
     `0x02D10015` = 721. There is a second identical pair at
     `+0x0858`/`+0x085c`.
   - Enable-shaped bits: `+0x0138` bit 27 and `+0x0040` bit 25 (currently set).
     Per the U-Boot RE the actual frame commit is on the **AFBD** side
     (`0x05600014` latch + `0x0560006c` dirty) — which our driver already writes
     every atomic update, so "never committed" is a weaker explanation than it
     first appears.

   **Leading hypothesis, explicitly not yet a finding:** the scaler sits in the
   MIPS's window/composition layer, and that layer is inert with the MIPS parked.
   Our driver injects at AFBD and takes the output at the LVDS selector
   (`0x051c006c`), bypassing the window pipeline the scaler belongs to. That
   would explain every observation at once — writable registers, no response to
   traffic, no effect from a ratio change — without requiring the block to be
   broken or unrouted in silicon.

   If that is right, using this scaler from Linux means reimplementing enough of
   the window layer to own composition, which is a much larger port than "map one
   more register window". **Weigh that against route 2 before spending on it.**

   **Testing that hypothesis needs "image on the panel AND MIPS alive", and that
   state is NOT CONSTRUCTIBLE with the current U-Boot command surface
   (established 2026-09-04, `tools/display/mips-alive-scaler-test.py`):**

   | command | image on glass | MIPS after |
   | --- | --- | --- |
   | preboot `auto <id> logo` | yes | **quiesced** |
   | `h713_disp init <id>` | **no — it renders nothing** | alive (`0x0306101c=1`) |
   | `h713_disp panel-test <id> vendor-logo` | yes, 15 s only | **quiesced** |

   Every ARM-side render path parks the MIPS first, which is the same
   ARM/MIPS exclusivity seen elsewhere on this display — and the RPC surface
   cannot substitute, because the frame-submit routines are stubs. `quiesce`
   being listed as an opt-in *mode* of `panel-test` does not mean the other
   modes leave the core running; measured, it reads `0x00000000`.

   **Correction worth carrying:** a black panel after `h713_disp init` is
   **expected** — that command brings the display up "ready for diagnostics" and
   draws nothing. It was misread here as the documented warm-reboot panel
   power-on no-op, and cost a power cycle. Check whether anything published an
   image before blaming the panel rail.

   **RESOLVED 2026-09-04 without reflashing, and the answer is architectural.**
   `h713_mips_release_reset()` is only seven register writes, and after the
   preboot has run, the firmware is already resident at `0x4b100000` with its
   shared memory published — so the core can be **un-quiesced from the U-Boot
   prompt with `mw.l`**, underneath a logo the preboot already put on the glass
   (`tools/display/mips-alive-scaler-test.py --release-mips`):

   ```
   0x02001600 = 0x80000002   clock        0x0200160c = 0x00030001   stage 3
   0x0200160c = 0x00000000   assert       0x03061030 = 0x4b100000   boot address
   0x0200160c = 0x00010000   stage 1      0x0200160c = 0x00070001   RELEASED
   0x0200160c = 0x00030000   stage 2
   ```

   `0x0306101c` went `0` → `1`, the core came up — **and the logo vanished. The
   panel went black while the TCON scan counter kept advancing**
   (`005502e6` → `02840115`), so the display was not broken: it was actively
   scanning *black*.

   > **The ARM framebuffer route and the live MIPS window layer are mutually
   > exclusive.** When the window layer comes up it takes ownership of the
   > display, and what U-Boot published stops being what is scanned. The layer
   > then shows nothing, because no frame has ever been submitted to it.

   That explains the entire run of nulls: with the MIPS parked the scaler is a
   dead register file in a path that bypasses it, and with the MIPS live there is
   no ARM-published image left to scale.

   **And feeding the live core through the AFBD registers does not work either
   — tested, not assumed.** With the core running and the panel lit but blank, a
   fresh OSD commit was issued using stock's own two-step (`0x05600140` bit 0,
   then 1 to `0x05600144`, which reads back 0 because it is a self-clearing
   latch — success, not failure), aimed at a framebuffer verified intact
   (`0x6c100000` still held the grey logo pixels). **No change on the panel.**

   The blanking is invisible to every measurement available. `h713_disp dump`
   walks 22 blocks — tvtop, lvds-lane, TCON, disp-pll, three lvds-phy windows,
   **mixer**, display-route, **vblender**, osd-ch0, de-top, de-layers, de2-ch0/1,
   de, four afbd windows, pll-video2, disp-modclk — and a before/after diff
   across the release differed *only* in the TCON scan counter. The scaler's 28
   registers were identical. The AFBD *video* block (`0x05600010`–`0x0560003c`,
   which no dump covers) had the source disabled and an empty ring. The LVDS
   selector stayed `0x29000000` (RGB/OSD — the mux was not stolen). PB5, PF6 and
   PH16 were all correct.

   > **The MIPS owns presentation through its own window state, not through the
   > AFBD registers. Our path works only because the MIPS is parked.**

   | | owner of presentation | scaler | status |
   | --- | --- | --- | --- |
   | MIPS parked | ARM, via AFBD registers | bypassed, inert | ours: 720p, no scaling |
   | MIPS alive | MIPS, via window descriptors | in its path | stock's: scaling available |

   The two cannot be mixed, and that is now measured rather than inferred.

   **What it would now cost.** Using the scaler means driving the window layer
   the way stock's ARM side does — window/plane descriptors plus the MIPS
   handshake, i.e. the ARM half of stock's display HAL (`svp_ioctl` /
   `tgd_put_plane_info`, PanelWinNode format). CPU_COMM cannot substitute; its
   frame routines are stubs. That is a substantial RE and driver effort, not a
   register mapping — but it is a *known* effort now, with an identified entry
   point, rather than an open question.

   Also built and available, unused: `h713_disp logo-live <id>` in
   `h713_mips.c` — the `auto <id> logo` sequence without the quiesce. The `mw.l`
   replay reached the same state without reflashing, so it was never needed; it
   is kept because it renders *and* leaves the core running in one command.
2. **Fix the GPU path's artifacts.** `vo=gpu` on the *stock* mpv is the only
   thing that puts 1080p on the panel today — ~0.83× realtime, sync intact, but
   481 dropped frames and visible artifacts. Costs the no-GPU property only
   while in use. Note there is no 2D engine to fall back on: after the GPU, the
   only other stage-1 scaler is the CPU.

Full account, including the hazard that a rejected plane commit retried
unbounded will wedge the display:
[handoff-2026-09-03-video-playback.md](handoff-2026-09-03-video-playback.md).

## Summary

A fully open boot chain — U-Boot SPL → TF-A BL31 → U-Boot → Linux **6.18.38
LTS** — boots a **64-bit Debian 13** userland from eMMC to a **root login**, on
all four cores, with HS400 eMMC. It boots **standalone** (power-on → Debian, no
host), replacing the vendor Android stack end to end. All hardware-verified on
the HY200 bench board.

**Display bring-up is complete (2026-08-07).** The 1280×720 LVDS panel renders
correctly through the MIPS coprocessor path: the vendor boot logo and a custom
logo both display, double-buffered animation is tear-free, the frame survives
the handoff into Linux, teardown cleans up on failure, and a boot logo can be
published from U-Boot (`h713_disp auto <id> logo [file.bmp]`). Backlight dimming
is understood (PB5 enable-PWM of an on-board 36→52.6 V boost; the shipped path
never dims) and the fix is an inline MOSFET, hardware not yet fitted. The
firmware's MIPS-side debug shell is confirmed reachable for register access.
Full detail in [claude-display-handoff.md](claude-display-handoff.md) and
[mips-display-recovery.md](mips-display-recovery.md).

**Hardware H.264 decode works (2026-08-09).** Mainline `cedrus` drives the H713
VE with no driver changes: Constrained Baseline, Main (B-frames + CABAC) and High
(8x8 transform) all decode **bit-exact** against host software references, 320x240
through 1920x1080. The whole failure was one device-tree property — `iommus` on
the `ve` node pointed at an IOMMU that does not exist at that address, so the DMA
layer handed the VE untranslated IOVAs; it corrupted the kernel's printk
ringbuffer and panicked before emitting a frame. Removing it fixed both symptoms
at once. Patch 0074 provided physically contiguous Cedrus CAPTURE buffers and
passed its still, moving and repeated-session hardware acceptance, but it was
**dropped from the series on 2026-09-01**: with master 2 translating, fragmented
capture buffers display correctly, so its 64 MiB permanent DRAM reservation buys
nothing. It is kept out of series as a fallback control for a bypass kernel. See
[video-decode.md](video-decode.md).

**Moving decoded video renders on the panel, the vendor's way, with the GPU
idle (2026-09-01).** 300 frames of decoded H.264 at **27.13 fps, zero IOMMU
faults**, logo restored, operator-confirmed. This closes the corruption
investigation that ran from 2026-08-26. The buffer that played was
`pages=338 contiguous=NO breaks=56 longest-run=8(32KiB)` — *more* scattered than
the 31-break / 64 KiB buffer that produced green corruption on a bypass kernel —
which confirms root cause and fix end to end: DECD scans linearly from one base,
and IOMMU translation is what makes a scattered buffer scannable.

The whole difficulty turned out to be **ordering, not addressing**. The master-2
`IOMMU_BYPASS 0x7c -> 0x78` transition must happen while the DECD **video source
is disabled** — only the inherited logo route live. The source rests at base
`0x00000000` with inherited 1920×1088 geometry, so enabling it starts a raster
scan through the first ~2 MB of physical memory: harmless under bypass,
L1-invalid the instant translation arrives. Four visible runs faulted at
`0x29000`, `0x26000`, `0x81000` and `0x16000`, all inside that window. Two
consequences worth carrying: **the banding was never a surface-reuse race** (none
appeared in moving playback), and **"one master-2 fault wedges AFBD for the boot"
is the wrong rule** — the fault is avoidable, so design for zero rather than
budgeting one per boot.

**Patch 0076 makes that a driver behaviour, and it is hardware-validated.** It
parks source 0 across the transition and re-enables it after `dec_reg_enable()`,
gated on the Y ring holding a real address. Run as the *first* DECD session of a
boot with no operator procedure: a frozen still and a 300-frame moving clip both
rendered correctly with zero faults and restored the logo. The diagnostic wrapper
was fixed alongside — it used to enable the video source at a fixed 200 ms, long
before any frame existed, showing up to two seconds of garbage; it now waits for
the ring. With that in place the moving run needed no park at all, so the wrapper
ordering is the mechanism and 0076 is the safety net.
[iommu-runtime-flip-ordering-2026-09-01.md](reference/iommu-runtime-flip-ordering-2026-09-01.md),
[handoff-2026-09-01-iommu-runtime.md](handoff-2026-09-01-iommu-runtime.md).

**The no-GPU video path reaches the panel (2026-08-31) — the black screen is
solved.** Video already reaches the panel through the GPU (below); the open goal
was doing it the vendor's way, with the display hardware performing YUV→RGB and
the GPU idle. A bounded DECD-exclusive Linux test displayed a 1280×720 NV12 test
card in full colour and correct geometry, then restored the boot logo. The state
the black runs were missing is small: **four source-geometry words** — the source
block still held an inherited 1920×1088 / stride-1920 fallback, which is what
produced the earlier horizontally repeated image — **source enable plus its
commit**, the YUV **chroma gain `0x05140508 = 0x144C0000`** (bits 23:16 are a
linear gain; `0x00` is greyscale, which is why the earlier result had no colour),
and the **plane-1 downstream selector `0x051C006C = 0x39000000`**. A 30-fps
two-buffer follow-up completed 150/150 submissions while visibly alternating red
and green, so the route is per-stream state, not a per-frame register dance.
[linux-decd-scanout-confirmed-2026-08-31.md](reference/linux-decd-scanout-confirmed-2026-08-31.md).

**A known-visible hardware-decoded frame is correct through that route when its
bytes are copied into one contiguous physical buffer (2026-09-01).** A strict
target-side player passes Cedrus-owned NV12 dma-buf FDs straight
into the 112-byte DECD descriptor — no CPU copy, no Mali render — and sustained
300 nonvisual frames at 29.95 fps. Two-second visible runs showed recognizable
moving decoded content under horizontal bands. The bands initially looked like
mixed decoder surfaces, but the returned release fence disproved that cause.
Its reconstructed kernel lifetime was unsafe; patch 0071 corrects it and
`decd-play` now retires by signalled fence. **Measured on hardware: 299 of 300
surfaces retired on a signalled fence, zero stalls — and the picture is
unchanged** (`test_60`), so premature surface reuse is *eliminated*. The UAF was
real and the fix stands. **A frozen-buffer test then eliminated timing
altogether**: one complete, quiescent decoder buffer resubmitted 89 times at a
fixed address gives a *steady* corrupt image — all green (zero chroma), data-like
banding over the top half, flat below. **Dumping that buffer from the CPU then
proved its contents bit-exact** — SHA-256 identical to a host software decode —
so the tiling hypothesis is refuted and content and layout are excluded too.
**Root cause found:** Cedrus's buffer is **not physically contiguous** — 338
pages, 31 breaks, longest run 64 KiB — while `dec_dma_map()` keeps only
`sg_dma_address(sgt->sgl)` and the hardware scans linearly from that one base.
DECD starts at the right address (`0x05600070 = 0x46F7A000`, the buffer's first
page) but only the first 64 KiB — 51 of 720 luma lines — is really there; chroma
at `y + 0xE1000` is 924 KiB past the start and never in the buffer, which is why
the frame is overwhelmingly green. Carveout frames always worked because they
map as a single segment. Patch 0072 turns the silent corruption into a refusal,
and 0073 declares the constraint (`dma_set_max_seg_size`) so the mapping is
deterministic instead of depending on how fragmented memory happens to be.
The first bypass carveout copy appeared black only because this clip's decoded
frame 0 is black (Y≈16, U=V=128). `DECD_FREEZE_AT=60` then selected a close-up
face whose target dump is byte-for-byte the host software reference
(`70bddcf8…`). Copied to physical `0x6c500000` and held for 300 submissions, it
was operator-confirmed as recognizable and apparently correct; the logo state
was restored afterwards. **That resolves the cause as physical-buffer
provenance.** Patch 0074 implements physically contiguous Cedrus CAPTURE
buffers: a 64 MiB reusable `shared-dma-pool` on the VE **plus**
`DMA_ATTR_FORCE_CONTIGUOUS` on the CAPTURE queue, with 0072 checking that the
export is one complete segment. The normal series and the out-of-series 0068
test configuration both build cleanly. A RAM-only hardware boot reserved the
pool at `0x7c000000`, attached Cedrus to it, and accepted direct imports that
0072 rejected on the segmented build. Known-visible frame 60 remained
byte-exact (`70bddcf8…`) through a 90-submit frozen run; a separate 150-frame
moving run retired 149 surfaces by fence with peak depth 4 and zero stalls.
There were no 0072 refusals, kernel warnings, or IOMMU faults, and the logo
selector stayed unchanged. **The bypass direct path is now hardware-proven.**
Direct frame 60 held for 300 submissions and looked good to the operator; a
300-frame moving clip had no noticed issues. Both runs restored the logo. The
moving run completed at 27.09 fps with 299 fence retirements, peak depth 4 and
zero stalls. Three more consecutive 300-frame sessions passed with the same
fence statistics, no new kernel log entries, and selector `0x29000000` still
selected.

**The exact early-attachment IOMMU route implemented by 0069/0070 remains a
tested negative — and the runtime transition it pointed at is now proven.**
Attaching translated from probe coalesces the import but produced black with the
adopted-display route and no faults. The vendor DTB starts master 2 in bypass
(`<&mmu_aw 2 0>`), while HWC was reverse-engineered calling
`sunxi_enable_device_iommu(2, 1)` at the playback boundary. Patch 0075 reproduces
exactly that runtime transition and **works on hardware**, given the flip
ordering described above. Do **not**
run real Cedrus traffic with the display MIPS alive — that combination hard-locked
the SoC and needed a power cycle, even though static carveout frames with MIPS
alive ran for over an hour.
[cedrus-decd-first-visible-playback-2026-08-31.md](reference/cedrus-decd-first-visible-playback-2026-08-31.md).

The premise behind the goal was confirmed on hardware first (2026-08-29). That
the vendor stack plays video with the GPU asleep had been inferred from
`hwcomposer` reverse-engineering; it is now measured: with stock Android playing
and the player's transport controls auto-hidden, the Mali runtime-PM counters
read **`active +0 ms, suspended +15115 ms` across 15 seconds**. The same
measurement with the controls *visible* reads 100% active, which is the player's
UI and nearly produced the opposite conclusion from a single sample.

Two things follow. **Scope: only AFBD is driven per frame** — a sweep of eleven
register windows at idle and during playback found the sole video-driven
registers are AFBD's Y and C buffer bases, cycling as a ring; TVTOP, the mixer,
DE/OSD, GE2D, the PLL and the LVDS PHY are byte-identical between the two states.
They are load-bearing but *configured once*, so the runtime surface is much
smaller than "implement the display pipeline". **Overlays: stock wakes the GPU
and composites** video and UI into one buffer that AFBD scans out — there is no
hardware subtitle blending to find, which closes a product question that had been
open.

**How it was found, and what stays eliminated.** The cross-stack campaign that
preceded the fix is still valid as a set of negatives, and none of it should be
re-tried: bit 31 on the AFBD channel controls does nothing; fmt 4 versus stock's
fmt 0 is real but yields visible garbage, not blackness; IOMMU bypass gives
coloured static; the mixer is not in the video path at all (the firmware contains
no `lui` immediate that can even form its base address); the suppression latches
return cleanly and change nothing; and every writable cross-stack difference in
the six captured windows except the chroma gain replayed onto stock with no
visual effect. What actually produced the answer was **writability triage** —
write `0xDEADBEEF`, read back, restore, because a register that will not take a
write cannot be a cause — which cut 150 differences to 29 writable ones at the
cost of zero operator observations, and then bisection down to the chroma gain
and a one-register stock test that proved `0x051C006C` causal by removing a
*playing* picture. Full account in
[handoff-2026-08-31.md](handoff-2026-08-31.md),
[handoff-2026-08-29.md](handoff-2026-08-29.md) and
[plane-brief-for-external-review.md](plane-brief-for-external-review.md).

Two operational rules came out of it. **Writes to the AFBD block are inert until
the per-register commit latch is pulsed** (control at `+0x00`, latch at `+0x04`);
an uncommitted write lands, reads back, holds indefinitely and does nothing, so
readback proves nothing there. And **the mixer, DE and TCON H/V totals are
coupled** — changing two of the three to match stock blanked the panel, and the
revert restored it.

**WiFi and Bluetooth are done (2026-08-21).** The AIC8800D80 SDIO link runs at
the stock configuration — four-bit UHS-SDR104 at a **verified** 50 MHz — after
patch 0048 removed two compensating errors that had been driving the bus at 4x
its nominal rate. 128 MiB transfers pass in both directions with SHA-256 exact
and zero SDIO faults, in **both AP and STA mode**; the long-standing "WiFi cannot
carry a file" rule is refuted. The hotspot was silently emitting 802.11g, capping
throughput at a tenth of the bus; with HT enabled it does 5.1–7.7 MB/s on
2.4 GHz HT40 (13.2/14.4 on 5 GHz VHT80, one line away). The radio now runs under
a real regulatory domain instead of a permissive world default, a firmware crash
recovers itself rather than waiting for a human, and Bluetooth attaches cleanly
with no HCI timeouts. Full detail in
[handoff-wifi-sdio-2026-08-17.md](handoff-wifi-sdio-2026-08-17.md).

## Boot chain

```
BROM → U-Boot SPL (DRAM init) → TF-A BL31 (EL3, @0x40000000)
     → U-Boot proper (AArch64 EL2) → FIT (bootm):
         arch=arm64 → EL1 AArch64  — native, 4-core SMP     ✅
         arch=arm   → EL1 AArch32  — via el2_to_aarch32      ✅ (single-core)
```

## Works

| Area | State |
|------|-------|
| DRAM init | ✅ DDR3 (HY200) hardware-proven; LPDDR3 (HY200 QZ713_V2) replay-verified, untested on HW |
| U-Boot proper | ✅ clean `g8a601c1` installed at LBA 16; correct HY200 model, persistent env (raw eMMC @4 MiB), `reset` via PSCI + `wdt` |
| BL31 / PSCI | ✅ `SYSTEM_RESET`, `CPU_ON` (all 4 cores), `CPU_SUSPEND` |
| arm64 Linux | ✅ **mainline 6.18.38 LTS** boots to Debian root login, **4-core SMP** (HW-verified) |
| 32-bit Linux | ✅ boots to userspace, **single-core** (see limitations) |
| eMMC | ✅ HS400, 26-partition Android GPT, read+write verified across reboots |
| Debian 13 rootfs | ✅ signed, key-only image boots from UDISK; growfs, serial autologin, persistent first-boot identity, modules, and sshd HW-verified. Since 2026-08-15 the base set also carries the **video runtime** (mesa/GLES, the GStreamer stack incl. `v4l2slh264dec`, `v4l-utils`, `mpv`) and autoloads `sunxi_scanout_dmabuf`, with `--profile dev` for an on-target compiler — built and compile-verified under qemu, not yet booted on hardware |
| Standalone boot | ✅ power-on/reset → `boot_a` FIT → Debian, **no host attached** (HW-verified) |
| USB gadget | ✅ serial-default console; opt-in CDC ACM, UMS, and fastboot modes; ACM→fastboot transition and bounded raw bootloader target HW-verified |
| CPU frequency/thermal | ✅ PWM DVFS from 480 MHz/0.90 V through **1296 MHz/1.06 V**; cpufreq cooling device backs 75/85 C passive trips. **1416 MHz was removed 2026-08-22 (patch 0055): it corrupts kernel memory under sustained GPU+display load, and the vendor never uses that point at any voltage** |
| Crypto Engine + RNG | ⚠️ **disabled — mainline `sun8i-ce` can't drive the H713 CE** (bench-proven). Enabling it registers every algorithm, then each fails its known-answer self-test. Wiring the stock's 2nd interrupt fixes task completion, but the CE then rejects mainline's descriptors — ciphers `address invalid`, AES/SHA `algorithm not supported` — a different descriptor **format** (vendor two-bank block), not an IRQ/clock/addressing gap. No CE TRNG. The A53's ARMv8 AES/SHA (software ~2 GB/s) is faster anyway. Re-enabling needs descriptor-level RE of the vendor `sunxi-ce` (no source). |
| Reboot → fastboot / U-Boot | ✅ **done, both modes HW-validated (2026-07-23).** Two `nvmem-reboot-mode` modes over RTC GP7: `reboot fastboot` (magic `0xfa57b007`) → U-Boot `preboot` → fastboot, and `reboot bootloader` (magic `0xb007c0de`) → `preboot` sets `bootdelay -1` → U-Boot `=>` prompt — both confirmed console-free on the bench. `RTC_DRV_SUN6I` owns the region and exposes GP7 as an nvmem cell (`nvmem-cells` → `reboot-mode-magic@1c`); the old overlapping `syscon-reboot-mode` is gone. |
| KMS / `/dev/dri/card0` | ✅ **DONE 2026-08-16, HW-verified — `mpv --vo=drm` plays 720p to the panel, 0 dropped frames; 1320 page flips at 59.71 fps, 0 timeouts.** `sun50i-h713-afbd` (patches 0037/0038) is a simple-KMS driver over the AFBD scanout engine: one CRTC, one plane, page flip via the same `0x05600178` + `READY` sequence that measured 0.00% tearing in gles-play, vblank off SPI 110 (bits confirmed by 2254 IRQs and zero stalled flips). Probe reads geometry back from the hardware (`adopting 1280x720, stride 5120`). Framebuffers come from **system CMA** — a reserved dma-pool allocates in power-of-two page orders, so a 16 MiB pool yielded exactly 4 buffers and mpv ran out of them. **`card0` since 2026-08-24** — the driver became `=y` so the boot log would reach the panel, so it now probes before panfrost's module and takes minor 0; it was `card1` while it was a module, which is what older docs record. Resolve it at runtime via `/sys/class/drm/card*/device/driver` rather than hardcoding either. It **adopts** the display U-Boot brought up and never touches timing, the LVDS PHY or `rst_bus_disp`, so it does not remove the U-Boot dependency. Took the AFBD window and IRQ from DECD, now `disabled`. **The whole Linux boot now renders on the projector** (2026-08-24): fbcon takes over at 1.25 s instead of 6.49 s, `getty@tty1` no longer wipes it (`TTYVTDisallocate=no`), the WiFi driver no longer floods it (aic8800 patches 0007/0009), and dummycon is matched to the panel at 160x45 so the handover keeps ~45 lines instead of ~13. Operator-confirmed on the glass: the systemd `[ OK ]` lines scroll past during boot, and the login prompt stays put afterwards. `kmssink` needs `driver-name=sun50i-h713-afbd`; its auto-detect never worked here. [kms-display.md](kms-display.md), [handoff-2026-08-24-display.md](handoff-2026-08-24-display.md) |
| Video on the panel | ✅ **NO-GPU PATH DONE 2026-09-08 — real Cedrus video renders correctly on the panel with the display MIPS ALIVE.** Cedrus decode → zero-copy dma-buf → IOMMU translation → DECD fetch → MIPS window layer → panel, 29.96 fps, core alive throughout. Three faults, all found by reading our own record rather than photographing: the format byte `0x05600011` must be **3 (NV12)**, not 0 (= RGB888, which stock uses only because it composites video into an RGB surface); `0x0560006c` publishes the **plane addresses**; and `0x05600014` commits the **source config** — *and it retires on vsync*. Shell recipes worked by accident of their 100 ms sleep; back-to-back kernel writes never latch, the hardware silently ignores the configuration, and **every register still reads back correct** — the frame renders doubled at half height. Proving that needed the afbd, `top` (`0x05700000`, never compared before) and composition regions all dumped and found byte-identical between a working and a broken run. The route now lives in the driver (patch 0095, `auto_route=1`); only the display-side gain and selector stay in shell, by design. **Two earlier causal claims are withdrawn**: composition was not the cause (it owns the footprint only), and IOMMU translation is not the fault — it works. **The hard-lock is very likely a missing patch, not a hardware hazard.** The DECD build tree predated 0071 (release fence lifetime), 0072 and 0073, so `frame_item_release()` was doing a bare `kfree()` on a `dma_fence` userspace still held — on every retirement, i.e. ~30/s during playback and almost never during static tests. Rebuilding with all three: **nine clean live runs, three inside the first 100 s of uptime**, against two locks in two attempts in that same window immediately before. Fence retirement now completes instead of timing out, and the client segfault is gone. **Mechanism unproven** — a dangling fence causing a *silent* whole-SoC wedge with no oops or serial is not an obvious failure mode — so this is absence-of-failure evidence, not a closed case. Build the module from a tree with 0071/0072/0073 applied. **Flipping measured 2026-09-08 and already correct**: the plane-address publish retires uniformly over 0-16.7 ms (never microseconds), so it latches on the frame boundary and cannot tear; cadence is 116/119 frames at exactly 2 vsyncs with displayed rate 29.98 vs source 29.97 fps. Gaps: `decd-play` still requests selector 0, `0x05600024` undecoded. [handoff-2026-09-08-video-playing.md](handoff-2026-09-08-video-playing.md), [nv12-scanout-solved-2026-09-08.md](reference/nv12-scanout-solved-2026-09-08.md). Historical GPU path (2026-08-15, 59.71 fps, zero-copy through Mali-G31) remains valid and is unchanged. |
| Video decode (Cedrus / VE) | ✅ **PRODUCTION-HARDENED 2026-08-24.** Stock ffmpeg decodes H.264 (5/5) and 8-bit HEVC (6/6 — scaling lists and lossless included) on the VE through `libva-v4l2-request` + our 5 patches. Beyond bit-exactness: **2 h soak, 5238/5238 iterations, 195,332 frames**, no drift and no leak; **16/16 malformed streams** survived with the engine usable after each; **3 concurrent clients 18/18**. Two driver defects found and fixed getting there — patch 0040's device-wide reset deadlocked concurrent contexts in `v4l2_m2m_cancel_job()` (dropped from `series`), and `cedrus_irq()` orphaned jobs by disarming the watchdog before claiming the interrupt (patch 0059, landed). The old rule "a timeout wedges the VE, reboot between runs" is **refuted** — ten consecutive timeouts, then bit-exact for both the shim and GStreamer. **Main10 plays too** (patch 0006, `ve+10`, 57 dB PSNR, byte-identical to the GStreamer oracle) — the old "10-bit does not decode" claim was wrong; the engine writes an 8-bit plane plus a 2-bit plane and the 8-bit part is correct. Remaining gaps: *full* 10-bit output, which needs a V4L2 fourcc for that 8+2 layout (the engine's second output cannot emit P010 — measured, four arms, zero bytes), and tiles (no encoder here emits them). See [decode-production-readiness.md](decode-production-readiness.md) and [handoff-2026-08-24.md](handoff-2026-08-24.md). Historical detail below. ✅ **H.264 hardware decode, bit-exact** (2026-08-09). Mainline `cedrus`, unmodified, via GStreamer `v4l2slh264dec`. All five ladder vectors match their host software references byte-for-byte: 320x240 Constrained Baseline, 1280x720 Baseline/Main/High, 1920x1080 High. Force `video/x-raw,format=NV12` — unforced it negotiates `NV12_32L32` (32x32 tiled), which is correct output but will not match a linear reference. **The `iommus` property must stay off the `ve` node** until the real IOMMU (stock DTB: `0x2010000`, `allwinner,sunxi-iommu`, `#iommu-cells = <2>`) is verified live; ours pointed at the H6 address `0x030f0000`, which reads all zeros. Re-verified bit-exact on the current kernel 2026-08-15. On the panel via the GPU path — see the row above. |
| WiFi (AIC8800D80 / SDIO) | ✅ **DONE 2026-08-21.** Four-bit UHS-SDR104 at a register-verified 50 MHz — stock parity. 8 MiB and 128 MiB both directions, SHA-256 exact, **zero** cmd53/CRC/FIFO/hardware-lock/timeout messages, on a production kernel from a cold boot, autobooting unattended from eMMC. Three defects were fixed to get here: the v5p3x IDMA descriptor encoding for an exact 4096-byte segment (0046, the bulk-RX failure); a 4x clock-accounting error — the driver doubled the module clock *and* the CCU carried a fictional /2 post-divider, so `max-frequency` meant a quarter of the real rate (0048); and an AP emitting plain 802.11g, which capped transfers at 1.33/2.37 MB/s against a 24.4 MB/s bus. With HT: **5.1–7.7 MB/s** (2.4 GHz HT40, the shipped default for client compatibility) or **13.2/14.4 MB/s** (5 GHz VHT80, `HOTSPOT_BAND=5`). Running both bands at once works but is *slower* than either alone — 1x1 radio, time-sliced. STA mode retested and equally good (8.9/9.6 MB/s). |
| WiFi regulatory | ✅ **DONE 2026-08-21.** The wiphy is self-managed, so cfg80211's `regulatory.db` never applied to it — the driver installed its own domain from a compiled-in `"00"`, i.e. `DFS-UNSET`, 2380–2520 and 5140–5980 MHz at 20 dBm with no DFS or passive-scan constraint. The driver's own table is fine (185 countries, 98 distinct rule sets); only the selector was stuck. `aic8800-0006` exposes it; the rootfs sets `WIFI_REGDOMAIN` (default `US`) and the radio now reports `country US: DFS-FCC`. ⚠️ The driver still prints `CAUTION: USING PERMISSIVE CUSTOM REGULATORY RULES` afterwards — that line is on the *success* branch, so judge with `iw reg get`, not the log. |
| WiFi crash recovery | ✅ **DONE 2026-08-21.** There is still no safe in-place recovery (unbind/reload Oopses the mmc core), so the recovery *is* the reboot — the job was making it reliable. `h713-wifi-recover` reboots on `DHDISDOWN` (policy in `/etc/default/h713-wifi-recovery`), `h713-bt-attach` gets a 10 s stop timeout so a dead chip cannot stall shutdown, and `RebootWatchdogSec=16s` arms the sunxi watchdog across the transition. Board returns in ~30 s. ⚠️ Verified with a synthetic trigger only — the real firmware crash would not reproduce under 4 minutes of the documented starvation recipe. |
| Bluetooth (AIC8800 / UART) | ✅ **DONE 2026-08-21.** `hci0` UP RUNNING, HCI 5.4, BR/EDR + LE, scanning discovers real devices. The `opcode 0x1003 tx timeout` on every cold boot is gone: it was never a timing race (a 5 s settle moved it without removing it) and never a baud race (115200 fails outright — the chip is at 1.5 Mbaud from power-on, contradicting the RE port notes). The first `N_HCI` attach after power-on leaves the controller unable to answer the first HCI command, so `h713-bt-attach` now drains `ttyS1` and primes with a throwaway attach/detach. 0 timeouts, up on attempt 1, 3 cold boots of 3; MGMT at ~9.0 s instead of ~13.9 s. Baud and flow-control settings confirmed against the vendor Android binaries. |
| Peripherals (drivers probe) | pinctrl, PWM, PPU (5 power domains), both MMC, EHCI/OHCI ×3, LRADC, IR, board-mgr, watchdog, **RTC** (`sun6i-rtc`, enabled — the canonical osc32k/iosc clock provider and the GP-register nvmem device, both HW-confirmed; `rtc0` reads back but the RTC is unset at first boot; set/read timekeeping is now HW-confirmed via the H713 linear-day variant (patch 0031) — `hwclock`/`timedatectl` read the correct date). (Crypto engine deliberately disabled — see above.) |

## Limitations / open items

- **32-bit SMP** — secondaries don't come up for a 32-bit kernel (BL31 brings
  cores up in AArch64; a 32-bit caller needs AArch32 secondaries). arm64 gets
  all four cores, so this is shelved.
- **One peripheral USB controller** — CDC ACM, UMS, and fastboot are deliberate
  successive modes, not a composite gadget. UART remains available throughout.
  Some Linux hosts retain a stale gadget identity across a warm reset; close
  the old device handle and power-cycle the board if re-enumeration is stale.
- **Main-PWM output validated; cooling fan is a power-enable, not PWM.** Patch
  0007's second-generation PWM map (previously proven only indirectly via the
  R_PWM `vdd-cpu` rail, patch 0028) was confirmed on real output during fan
  bring-up: on the bench, main `pwm@2000c00` channel 0 read back `enabled,
  39958/40000 ns` in `/sys/kernel/debug/pwm` with PH17 muxed to `pwm0`. But the
  fan itself is a **3-wire (VCC/GND/tach) on/off part**, not PWM-speed-controlled
  — DMM on the header showed the tach line at its 3.3 V pull-up (sense wired) and
  the +V pin floating (~1.1 V, decaying = unpowered). It stayed dead because the
  `fan_power_hog` for PB5 (shared backlight/fan enable) was malformed (linear
  `<37>` on a 3-cell controller → hog skipped → rail off). Patch 0030 fixes the
  hog to `<1 5>`; the earlier `pwm-fan`-on-PWM0 model was dropped (PH17 is the
  tach). **Bench-confirmed: the fan spins.** The fan and the LED backlight now
  both come up **at power-on from U-Boot** — `board_init` drives the shared PB5
  fan/backlight-enable under a bench-only `CONFIG_H713_POWERON_LIGHT_FAN`, so the
  panel is lit and cooled from reset (projector-as-boot-monitor), with the fan a
  hard interlock for the light. **Backlight brightness is open, PB4/PWM2 now
  re-opened (patch 0032, awaiting bench test).** The earlier "PB4/PWM2 changed
  nothing" result is contradicted by the stock config: the vendor DTB sets
  `panel_pwm_ch = 2` at 25 kHz (`panel_backlight = 75` on a 0..100 scale), stock
  fastlogo drives it via `pwm_request(2, "fastlogo")`, and the vendor Linux port
  dims on PWM ch2. Most likely the bench negative came from the panel's
  serial-init (run by fastlogo, not on mainline) never enabling the PWM-dim path,
  so the un-initialized panel ignores PB4 and holds its power-on-default level.
  Patch 0032 adds a mainline `pwm-backlight` on PWM2/PB4 (25 kHz, 0..100 duty,
  PB5 left hogged so the fan is untouched). **Bench-tested 2026-07-24 — gate
  confirmed panel-side.** With 0032 the PWM is provably correct on PB4:
  `/sys/kernel/debug/pwm` shows channel 2 (`backlight`) duty scaling exactly
  0/20000/40000 ns for brightness 0/50/100 with `actual` matching `requested`,
  and PB4 is muxed to `function pwm2` owned by the backlight — yet the panel's
  light output does not change at any level. So the SoC emits the stock waveform
  and the panel ignores it: brightness is gated on the panel-side init (LED-driver
  PWM-dim enable / LVDS panel serial program) that stock fastlogo runs before
  Linux and mainline does not. That init is part of the Phase-4 MIPS display
  bring-up. 0032 is correct and kept as the foundation — dimming will work through
  this exact node, unchanged, once the panel init lands.

The July 19 cleanup removed the CCU `MIPS_DIAG` mappings, enabled autofs in the
kernel, modeled the fixed 0.96 V `vdd-sys`/Mali supply from the stock DT, and
installed the clean U-Boot build through a bounded backup/write/readback path.
The rebuilt FIT boots with no diagnostic ioremap, autofs, or dummy-regulator
warning; Cedrus and Panfrost still bind and zero systemd units fail.

The July 21 thermal work added safe PLL_CPUX clock transitions, recovered the
R_PWM functional clock from the captured stock kernel, and wired the PL7 PWM
to VDD-CPU. DMM measurements validated 0.909 V for a 0.901 V request, 1.005 V
for a 0.999 V request, and 1.107 V idle for a 1.1005 V request. Every OPP from
480 to 1416 MHz transitions correctly. A two-minute four-core peak-frequency
load held 1416 MHz, raised the measured rail only to 1.127 V (below the 1.16 V
regulator ceiling), stayed below the 75 C passive trip at 68 C, and produced no
thermal, cpufreq, OPP, PWM, clock, or PLL errors. Both 75/85 C passive trips
are bound to the eight-state cpufreq cooling device.

**The flashed production kernel carries patch 0055 and Magic SysRq as of
2026-08-22.** `h713-kernel.fit` on the FAT at `mmc 1:2` was replaced in place
(7,745,120 bytes, SHA-256 verified by re-reading from disk after unmount) and
`bootcmd` autoboots it unattended. The previous 0048-era kernel is kept at
`/root/fits/h713-kernel-prev-20260822.fit` on the board. Note the FAT has only
~3.4 MiB free, so a kernel can only be replaced in place, never staged
alongside -- back the old one up to the rootfs first.

**1416 MHz has since been removed (2026-08-22, patch 0055).** It corrupts
kernel memory under sustained load, which surfaced as the display path killing
the board in 40-90 s and cost most of a session searching the video stack --
cedrus, VA-API, the IOMMU, panfrost and CMA were each excluded by experiment
before the operating point was suspected. Capping the ceiling at 1296 MHz, or
at 1200, turns that into 20 minutes clean; frequency *transitions* are innocent,
since the capped arms ran schedutil throughout. The vendor never uses 1416 at
any voltage: its `allwinner,sun50i-operating-points` driver keys
`opp-microvolt-<efuse>` off a two-byte cell, every key in the stock CPU table
exceeds 0xFFFF and so can never match, and in the fallback column 1416 reads
`<0x00>`. Details and traces in [vaapi-scope.md](vaapi-scope.md).

**The measurement above is not wrong, it was over-generalised** -- and that is
the transferable lesson. Two minutes of four-core CPU load at 68 C is a
different power and thermal envelope from tens of minutes of GPU + display +
scanout at 78 C. The DMM voltages were correct; the frequency point was never
in the vendor's table to begin with. 1392 MHz at 1100 mV is the vendor's top
usable point and would recover most of the loss, but it is untested here.

The Crypto Engine was investigated to a definitive dead end (2026-07-23) and is
disabled (`# CONFIG_CRYPTO_DEV_SUN8I_CE is not set`, `HW_RANDOM` off); the CE node
stays in the DTS but inert (H6-compatible `allwinner,sun50i-h6-crypto`). The
investigation, in order:

- **Baseline.** The four A53s carry the ARMv8 crypto extensions (`aes pmull sha1
  sha2`), so software AES/SHA run in-core at ~2 GB/s across the four cores —
  10–50× the device's eMMC/WiFi throughput. The CE offers no performance benefit;
  driving it is a completeness question, not a speed one.
- **Enable + real self-tests.** With `CRYPTO_SELFTESTS=y` the driver binds, sets
  its clocks, registers every algorithm — then each fails its known-answer test.
  (The earlier `/proc/crypto` `selftest: passed` was a vacuous default with
  `CRYPTO_SELFTESTS` off, never a real KAT.)
- **The stock CE has two interrupts** (SPI 73 + 74); mainline requests only the
  first, and the first operation used to hang. Wiring the second (same handler)
  **fixes completion** — operations now return status. But the CE's error status
  is then damning: ciphers report `address invalid` + every error bit, hashes
  report `algorithm not supported` — for *standard* AES and SHA. That only happens
  if the engine reads a bogus algorithm ID and bogus buffer addresses out of the
  descriptor: the H713 uses a different **task-descriptor format** (the vendor
  two-register-bank block), not a different IRQ, clock, or byte-vs-word address.
- **No CE TRNG:** it returns `algorithm not supported`; with `HW_RANDOM` the
  kernel's hwrng core just spam-polls it.

So mainline `sun8i-ce` fundamentally cannot drive this CE. Making it work would
mean reverse-engineering the H713 descriptor format from the vendor
`allwinner,sunxi-ce` driver (whose source we don't have — full BSP or `boot_a`
RE) and adding a new descriptor path: a large effort for zero gain, so it is left
disabled. Software crypto is correct and faster. See [roadmap.md](roadmap.md).

The July 23 reboot→fastboot work finished the mechanism in code. `RTC_DRV_SUN6I`
is now enabled: the H713 RTC (H6-compatible block at `0x07090000`) gets a real
`sun6i-rtc` driver, which registers the previously-orphaned osc32k/iosc clocks,
provides timekeeping, and exposes the eight general-purpose registers as a
battery-backed nvmem device. The reboot handoff moved off the `syscon-reboot-mode`
window (which overlapped the RTC register region) onto **`nvmem-reboot-mode`** over
a fixed nvmem cell (`reboot-mode-magic@1c` → GP7, physical `0x0709011c`) defined
as a child of the rtc node; mainline's `add_legacy_fixed_of_cells` makes the cell
phandle-referenceable with no driver change. The magic (`0xfa57b007`), the
physical address, and the entire U-Boot side are unchanged, so no U-Boot rework
was needed. **Hardware-validated on the bench (2026-07-23):** the new kernel
boots to Debian, `sun6i-rtc` binds as `rtc0`, the RTC nvmem device
(`7090000.rtc/nvmem0`) and the `reboot-mode-magic@1c` cell both register, and the
`nvmem-reboot-mode` consumer binds to that cell; the reboot trigger then landed
the board in U-Boot fastboot with no console interaction (host saw the fastboot
device). One loose end, not blocking: `rtc0` read back as unset at first boot
(hctosys `unable to read` = an invalid, never-set time — expected), and full
set/read timekeeping is now HW-validated: with `hwclock` (`util-linux-extra`)
shipped and the H713 modeled as a linear-day RTC (patch 0031 — the H6 model
read the year as 1970 because the sun50iw12 stores a linear day count),
`date`/`hwclock`/`timedatectl` set and read the correct 2026 date.

A follow-on refinement (2026-07-23) split the single handoff into **two modes**
so the two reboot verbs mean different things: `reboot fastboot` keeps magic
`0xfa57b007` → fastboot, while `reboot bootloader` now uses magic `0xb007c0de`
and, in `preboot`, runs `setenv bootdelay -1` to fall through to the U-Boot
prompt instead of fastboot. The DTS `reboot-mode` node carries both
(`mode-fastboot`/`mode-bootloader`); the U-Boot side is the runtime `preboot` env
(MMC @ `0x400000`):
`if itest.l *0x0709011c == 0xfa57b007; then mw.l 0x0709011c 0; run fastboot_mode; elif itest.l *0x0709011c == 0xb007c0de; then mw.l 0x0709011c 0; setenv bootdelay -1; fi; usb start`.
Both verbs were **hardware-validated on the bench (2026-07-23):** `reboot
fastboot` lands in fastboot and `reboot bootloader` drops to the U-Boot `=>`
prompt, each console-free.

## Board matrix

| Board | Silkscreen | DRAM | Bring-up status |
|-------|-----------|------|-----------------|
| Bench | HY200_QZ713DF_A1 | DDR3 (1 GiB) | primary target — everything above validated here |
| Projector | HY200_QZ713_V2 | LPDDR3 (1 GiB) | DRAM replay-verified only; **do not risk it first** |

See [bringup-notes.md](bringup-notes.md) for the driver-level findings behind
this, and [build.md](build.md) / [flash.md](flash.md) to reproduce it.
