# Handoff — 2026-09-12: the scaling driver, on hardware

Successor to [the VE scale-down handoff](handoff-2026-09-12-ve-scaledown.md),
written the same day. That one answered *whether* 1080p can reach this panel
without a GPU and left two pieces of driver work specified but unwritten. This
one is what happened when they were written and run on the board.

**A framebuffer smaller than the panel now renders on the glass.** That was
§3.3 of the previous handoff — the gap it explicitly said was not closed. It is
now mostly closed, with one characterised defect remaining.

Commits: `4c7db0e` (both halves written), `7742033` (geometry fix — first
picture), `af5b265` (shear characterised), `e761f87` (firmware RE).

---

## 1. The goal, unchanged

Put 1920x1080 video on a 1280x720 panel with **no GPU**. Exactly one route
exists on this silicon:

```
1920x1080  --[ VE, power-of-two, decode-time ]-->  960x544
           --[ proc upscaler 0x05180000, 1.333x ]-->  1280x720
```

Costs ~8.5 dB against a true 1.5x downscale and carries 56% of the panel's luma
samples. It is the only no-GPU option. Everything about *why* — the closed
arbitrary-ratio scaler, the display-side census, the register semantics — is in
the previous handoff and is not repeated here.

---

## 2. What is built

| patch | what |
| --- | --- |
| `0098` | drm/h713-afbd: accept a source below panel size, program the proc upscaler, derive source geometry from the framebuffer. Adds a DT reg range (`proc` at `0x05180000`, previously unmapped) |
| `0099` | media/cedrus: VE secondary output into the V4L2 capture buffer via `V4L2_SEL_TGT_COMPOSE`, with internal full-size reconstruction frames |
| `0100` | **EXPERIMENT**, drop when done: runtime knobs `vi_follow` / `vi_crop` / `proc_en` under `/sys/module/sun50i_h713_afbd/parameters/` |

`tools/display/kms-nv12-plane-test.c` takes `SRC=WxH`; the CRTC rectangle stays
pinned to the panel. Without that, no tool on the board could create a source
smaller than 1280x720 at all.

---

## 3. What is PROVEN on hardware

### cedrus (0099) — the decode half

- **Compose selection works.** Asking for 1280x720 on a 1920x1080 H.264 stream
  returns **960x544** and resizes the capture format to match (783,360 bytes =
  960x544x1.5). Rounding verified across five cases including the ÷4 clamp
  (400x300 -> 480x272) and correct refusal for HEVC.
- **Internal reconstruction frames are really allocated:** with compose set,
  24 buffers consume **~55 MB beyond** the capture buffers; without it, 4.7 MB.
- **No decode regression.** 60 frames of 1080p decoded on the VE are
  `879fb65957fff181941ef5d06d0ab4d6` — **bit-identical to the software control**
  after the `cedrus_frame_addr()` refactor that rerouted every DPB pointer.

**Not yet run: a scaled decode.** Nothing on the board sets a compose rectangle
(ffmpeg/libva has no path to one), so `cedrus_sd_program()` has never executed.

### drm/h713-afbd (0098) — the display half

- **A genuine 960x544 framebuffer reaches the panel and renders a legible card.**
- **The proc upscaler works horizontally**, measured: engaging it moves the
  repeat count from 4 to 3, exactly the 1.333x it is programmed for. Its
  registers read back with every live upper bit preserved
  (`0x4300C000`, `0x0F007000`, `0x0010E0B6`), and the block is restored
  byte-for-byte on plane disable.

---

## 4. What is WRONG, precisely

### 4.1 A narrower source SHEARS

Not tiling — a line-to-line shear. **The consumer steps 1280 pixels per output
line whatever the source width**, so each line starts `(1280 - W)` pixels
further into the buffer. Where `1280 / (1280 - W)` is a whole number the shear
realigns and reads as clean vertical tiles; where it is not, the picture
shreds.

| source | 1280 - W | predicted | observed |
| --- | --- | --- | --- |
| 1280x544 | 0 | 1 | **1, clean and sharp** |
| 1024x544 | 256 | 5 | **5** |
| 960x544 | 320 | 4 | **4** |
| 896x544 | 384 | 3.33, never realigns | **shredded / interlaced** |

Four for four, including the non-integer case predicting a *qualitatively*
different failure. Stride alignment is dead as a theory: 1024 is 128- and
256-byte aligned and still shears.

### 4.2 Vertical magnification does nothing

`ratio_v = 0xC16C` latches, and the green bar — the 176 unfetched lines below
the 544 real ones — is identical with the block engaged or bypassed. The
horizontal axis of the same block demonstrably works, so this is not "the
upscaler is not in the path".

---

## 5. The live lead

The firmware's own source-configuration routine is at **`0x8b1a3ea0`–`0x8b1a4408`**
(MIPS address = ARM physical + `0xB5000000`), reached with
`tools/mips/block-map.py`. Field layouts, from the `ins` masks:

```
0x05600020  [12:0] align16(width) - 1     [28:16] align16(height) - 1
0x05600030  [12:0] width, forced EVEN     [28:16] height
0x05600048  [15:0] luma width, align 4    [28:16] height (13 bits)
0x0560004c  [15:0] chroma width, align 4  [28:16] height
0x05600040  [15:0] luma stride, align 16  -- UPPER HALF PRESERVED
0x05600044  [15:0] chroma stride, align 16
```

**`0x020` and `0x030` are loaded from two DIFFERENT geometry structures:**

```
lw  $a3, 4($a2)     -> width  feeding 0x020        (struct A)
lw  $a2, 0xc($a2)   -> height feeding 0x020
lw  $t0, 0xc($a1)   -> height feeding 0x030        (struct B)
lw  $a1, 4($a1)     -> width  feeding 0x030
```

That is the picture-window versus output-window split `ProcWinNode` already
exposes (`m_out_win`, `m_video_win`, `m_picture_win`). **Patch 0098 sets both to
the source size.** That is what first got a picture onto the glass, so it beats
the inherited panel values, but conflating the two is the likeliest reason the
row length is still 1280.

**Start the next session here.** Type the two structures from this routine's
callers, decide what each register should hold for a source smaller than the
panel, and change 0098 accordingly. Desk work — no board, no operator.

A second, currently latent difference: the firmware read-modify-writes a
**single field** with `ins` for every one of these registers, while our driver
writes whole words. The discarded upper bits are zero at the sizes tested.

---

## 6. Do not re-test these

**Nine registers eliminated by live poking**, each written with readback
confirming the value stuck and a verified restore, during a shearing 960x544
run:

| poked to the real source width | result |
| --- | --- |
| `route+14c`, `route+164` (bare 1280) | no change |
| `route+518`, `route+528` ({1280,720}) | no change |
| `afbd+160` channel size | no change |
| `layer+080`, `layer+084` ({720,1280}) | no change |
| `comp+224` | no change |
| `b040+500`, `b040+524`, `b040+538`, `b040+53c` | no change |

Also eliminated:

- **Stride alignment** (see the table in §4.1).
- **The composition block** is byte-identical between a working and a failing
  run — it is not reconfigured at all.
- **The layer block `0x05280000`** is not touched by the firmware at all, which
  is why poking it was inert.
- **`0x05600028/2c/3c/50/54`** — the firmware writes them, we do not, and they
  read zero in both runs. Almost certainly source 1's copies.

That poking-is-inert signature — writes land, readback confirms, nothing moves
— is the same one 2026-09-04 produced on the composition ratio registers, where
the cause was that **the MIPS owns presentation through its own window state**.

---

## 7. Method lessons that cost real time

- **A WARM REBOOT LEAVES THIS DISPLAY UNABLE TO RENDER ANYTHING.** No console,
  white or green fields, every test result uninterpretable. Every driver change
  needs a full power cycle. This cost most of a session before it was
  recognised, and it is why patch 0100's runtime knobs are worth far more than
  they look.
- **Confirm the console is on the glass before every visible test**, and
  **prompt the operator BEFORE the observation window, not after.** Two windows
  were burned by asking afterwards.
- **`git status`-style gates lie about display.** The DRM state gate (plane has
  a CRTC, non-zero fb) passed while the panel was black. Photons are the
  instrument.
- **Do not read a pipeline's exit code as the build's.** `build.sh | tail`
  returns tail's status; a build that died with *"Only garbage was found in the
  patch input"* read as success and a kernel that had not been rebuilt was
  deployed and power-cycled for nothing.
- **The `/tmp` scratchpad does not survive overnight.** A patch regenerated by
  diffing against snapshots that had evaporated was silently truncated to its
  header. Rebuild baselines deterministically from the repo (extract the pinned
  tarball, apply the series up to the patch) instead.
- **`mmap` bases must be page aligned.** An unaligned base fails the whole dump
  with `EINVAL` and leaves an empty file that reads as "no suspects found".
- **`busybox devmem` is one process per register** — far too slow to sweep
  inside a 10 s window. Use `tools/display/blockdump.py`.
- **Two DRM traps**, both of which reject a smaller framebuffer before the
  driver ever sees it:
  - `mode_config.min_width/min_height` gate `drm_internal_framebuffer_create()`
    for every plane, ahead of any `atomic_check`.
  - **Plane scale is SOURCE/DEST.** Magnifying wants values *below*
    `DRM_PLANE_NO_SCALING`; asking for `[NO_SCALING, 4<<16]` permits only
    downscaling and rejects everything but an exact panel-size source, with
    `-ERANGE` from the helper rather than from our code.

---

## 8. Tools and board state

| path | what |
| --- | --- |
| `tools/display/kms-nv12-plane-test.c` | `SRC=WxH ARMED=yes ... FRAME.nv12 [dwell]` |
| `tools/display/blockdump.py` | fast mmap dump of every display block |
| `tools/display/make-scaler-testcard.py` | cards rasterised natively per size |
| `/root/composite-run.sh` (board) | control / scaled run with gates and restore |

Cards staged on the board: 1280x720, 1280x544, 1024x544, 960x720, 960x544,
896x544.

**Board (bench, 192.168.4.1) at handoff:**

- Running the bisect kernel, `#1 SMP Sat Sep 12 14:41:43 PDT 2026`.
- **`proc_en=0` is left set** from the last test. A power cycle restores the
  defaults (`vi_follow=1 vi_crop=0 proc_en=1`).
- Rollback FITs in `/root/fits`: `replaced-20260912-043746.fit` is the Sep 3
  kernel from before any of this work.
- **Rootfs is ~27 MB free (100% used.)** ~120 MB of historical FITs sit in
  `/root/fits`; they are the operator's, and were left alone. Clear space before
  any decode work — a 1080p raw decode is 186 MB.

## 9. Standing hazards, unchanged

- **Never read `0x06940000`** — unpowered capture domain.
- **A plain read of `0x07091000` wedges the SoC.** The RTC at `0x07090000` is fine.
- **Read VE registers only while a decode is in flight** — otherwise the whole
  4 KiB window reads zero, indistinguishable from absence.
- **Nothing may be written to a display block until the card is demonstrably on
  the panel.**
- **`0x05180000`'s registers carry live upper bits** — read-modify-write only.
