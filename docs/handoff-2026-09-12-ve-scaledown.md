# Handoff — 2026-09-12: the VE scale-down, and where 1080p-on-720p now stands

Successor to [the scaling and display handoff](handoff-2026-09-04-video-scaling-and-display.md)
and [the composition-block handoff](handoff-2026-09-06-composition-block.md).

**The question this session answered: can the H713 put a 1920x1080 video on its
1280x720 panel, with no GPU?**

**Yes, by one route, and that route is now fully characterised — but it is not
built.** Both of its hardware halves are confirmed on the board. What remains is
two pieces of driver work, described at the bottom.

The session also closed the more attractive alternative for good: the VE's
arbitrary-ratio scaler exists in the vendor code, its register block is present
and writable on this silicon, and **the datapath behind it is not implemented.**

---

## 1. The route that survives

```
1920x1080  --[ VE, power-of-two, decode-time ]-->  960x544
           --[ proc upscaler 0x05180000, 1.333x ]-->  1280x720
```

Both stages are hardware-confirmed. Exact values, all verified by readback:

### Stage 1 — VE decode-time scale-down (cedrus)

The registers live in the **H.264 engine block**, not the top-level VE file:

| register | offset | note |
| --- | --- | --- |
| `VE_H264_SDROT_CTRL` | `0x240` | mainline already names this |
| `VE_H264_SDROT_LUMA_ADDR` | `0x244` | unnamed gap in mainline; we name it |
| `VE_H264_SDROT_CHROMA_ADDR` | `0x248` | ditto |

Control word is **two independent 2-bit fields**:

```
[9:8]    horizontal   0 = 1:1,  1 = 1/2,  2 = 1/4,  3 = invalid (partial write)
[11:10]  vertical     0 = 1:1,  1 = 1/2,  2 = 1/4,  3 = invalid
```

So `0x500` gives 960x544 from 1920x1088. **Power-of-two per axis — there is no
1280x720.** Twelve control words were swept and every output size matched that
model, including two nulls and two invalid-field partials.

Three things must be right or it silently produces nothing:

1. **Program AFTER the codec's own setup**, where `cedrus_engine_enable()` writes
   `VE_MODE`. A disabled engine takes the control write and **drops the
   addresses, which read back zero**.
2. **Addresses go in raw and unshifted**, unlike several other engine registers.
3. **The secondary output format defaults to `TILED_32_NV12`.** Linear NV12 needs
   `VE_CHROMA_BUF_LEN[31:30] = 1` (the EXT table) **and**
   `VE_PRIMARY_OUT_FMT[3:0] = 4`. Clearing those two bits selects the tiled
   default, which yields a striped dump from a scaler that is working perfectly.

Also useful: top-level **`0xcc` is the secondary line stride**, `{chroma<<16,
luma}` — same packing as `VE_PRIMARY_FB_LINE_STRIDE` at `0xc8`, which it follows.

### Stage 2 — proc upscaler at `0x05180000` (instance 0 or 1)

This block **magnifies by `1/ratio`**; it cannot shrink. For 960x544 -> 1280x720:

```
0x34 = 0x03c00220   INPUT WINDOW (w<<16)|h  = 960x544     <-- this is the fix
0x2c = 0x...0500    out_w 1280   (low 16 bits only)
0x30 = 0x...02D0    out_h 720    (low 16 bits only)
0x08 = 0x...0c000   ratio_h 0xC000  -> 1.3333x  (bits [21:0])
0x3c = 0x...0c16c   ratio_v 0xC16C  -> 1.3235x  (bits [21:0])
0x00 = 0x...7000    H phase = (unity + ratio_h) >> 2   (bits [15:0])
0x38 = 0x...e0b6    V phase = (unity + ratio_v) >> 1   (bits [15:0])
0x14 bit 27 = 0     bypass CLEARED
```

**`0x34` was the whole clipping mystery.** Every earlier magnification run left
the geometry alone and got a picture clipped inside a hard-edged rectangle with
flat grey outside. `0x34` reads `0x050002D0` = {1280,720} on the live raster, so
the block was being told its input was 1280x720 while the ratio said magnify. Set
it to the real input size and the magnified picture fills the whole panel
cleanly. Operator-confirmed 2026-09-12.

> **These registers carry live upper bits.** `0x08` reads `0x43010000`, `0x00`
> reads `0x0F008000`, `0x2c` = `0x0035xxxx`, `0x30` = `0x0001xxxx`. **Always
> read-modify-write the field.** A bare store clobbers them.
>
> **V phase at unity is 0, not 0x10000** — `(unity+unity)>>1` overflows the
> 16-bit field and truncates, and 0 is what the firmware leaves there. Mask phase
> writes to `0xffff`.

### What the route costs

Measured, not guessed — `tools/video/compare-scale-routes.py`:

| route | PSNR vs lanczos | SSIM vs lanczos |
| --- | --- | --- |
| composite + bilinear upscale | 27.59 | 0.9627 |
| composite + lanczos upscale | 29.86 | 0.9678 |
| *arbitrary-ratio 1.5x (unavailable)* | *38.31* | *0.9947* |

**~8.5 dB worse than the path this silicon does not have**, and it carries
**56% of the panel's luma samples** (960x540 of 1280x720). The loss is the 2x
downscale, not the interpolation after it — swapping bilinear for Lanczos moves
it only ~2 dB. Full method and caveats in
[ROUTE-COMPARISON.md](reference/ve-scaledown-2026-09-11/ROUTE-COMPARISON.md).

It is viable, it is the only no-GPU option, and it is not good.

---

## 2. What is closed — do not re-test these

### The display pipeline has no downscaler at all

An exhaustive census of `display.bin` found **exactly three** ratio-carrying
blocks (22-bit ratio field, `ins rt, rs, 0, 0x16` signature, whole-image scan):

| block | what | status |
| --- | --- | --- |
| `0x05180000` | proc, two-axis, on our raster | **upscale only** — measured |
| `0x051c0138` | panel down-scaler | **vertical only** |
| `0x06940000` | capture-side | **wrong side of memory** — cannot be fed from DRAM, and behind an unpowered domain. **Never read this address.** |

No scaler exists in composition (`0x05000000`), DETN (`0x050c0000`), route
(`0x05140000`) or AFBD (`0x05600000`). `0x050c0000` is noise reduction /
motion estimation. The composition block's "ratio" registers are line buffers
(Rowbyte / LineBufLevel / LineNumber).

### The VE's arbitrary-ratio scaler is not implemented on the H713

This took four rounds and is worth not repeating. The capability is **real in
the vendor code**: `H264ConfigNewScaler` computes its ratio with a
floating-point divide and a 12-fractional-bit conversion, and `ScaleCopyCoef`
buckets ratios into **14 classes from 1.125x to 5x**. 1920->1280 is 1.5x =
bucket 4, squarely supported.

Everything it writes was reproduced on hardware and verified by readback:

- register block is **`getRegBase(7)` = VE + `0xf00`** — inside our 4 KiB window
  all along. Group offsets are `0x000/0x100/0x200/0x300/0x400/0x500/0xe00/0xf00`,
  and groups 1/2/5 match mainline's MPEG/H264/H265 engine bases, which is the
  check that the table was decoded correctly.
- `0xf10` = `(dst_w<<16)|dst_h`; `0xf14` = src/dst ratios; `0xf18` = dst/src
  inverses (1920->1280 gives **`0xAAA` = 2/3**, agreeing with the display side's
  independent `0xAAAA`); `0xfe4` = working buffer >> 8.
- coefficients stream through **group 7's own SRAM port**, `0xff8` (address in
  `[11:2]`, vendor uses `0x340`) and `0xffc` (data, 32 words per axis,
  auto-incrementing across both). **Not** the AVC port at `0x2e0/0x2e4`.
- the real coefficients are extracted and committed:
  [ve-scaler-coefficients.bin](reference/ve-scaledown-2026-09-11/ve-scaler-coefficients.bin)
  / [.txt](reference/ve-scaledown-2026-09-11/ve-scaler-coefficients.txt) —
  14 sets x 128 bytes, 32 phases x 4 int8 taps, every phase summing to 128.

**And nothing comes out.** Group 7 latches every write and produces no
observable effect, under every enable tried: SDROT off, `0xf20` bit 11,
`0xf20 = 0xf00`, `0xf00 = 1`, addresses relocated to `0xf44/0xf48`, and **every
bit of `SDROT_CTRL` from `0x1000` to `0x80000000`**.

The selection turns out to be **pure software** — `libawh264.so` at `0xe91c`:

```
ldrb.w r0, [r7, #0x2e2]   ; per-stream gate; 0 -> configure NEITHER scaler
cbz    r0, #0xe940
ldr    r0, [r4, #0x40]    ; scale MODE from userspace
cmp    r0, #2
bne    #0xe936
blx    #0x17090           ; mode == 2 -> H264ConfigNewScaler
blx    #0x170a0           ; otherwise -> H264ConfigureScaleRotateRegister
```

There is **no hardware enable bit**, so reproducing `ConfigNewScaler`'s writes
*is* the entire configuration. Supporting evidence that the logic is absent:
`libawh265.so` carries `this hardware not support fixratio scale`, `libVE.so`
gates on `ic_version` and asserts `You should know ic version!`, and
**`VE_VERSION` (`0x0f0`) reads `0x00000000`** on our part.

> **A register file latching values is not proof the logic behind it exists.**
> That was flagged as a risk when group 7 first accepted writes; it is now the
> conclusion.

**The one remaining falsifier** needs no register work: boot the vendor stack,
play a 1080p file, and see whether it emits a non-power-of-two secondary output.
Blocked on the vendor stack booting at all — as of 2026-08-26 `switch_vendor`
gave red->blue LED and zero UART, with slot B and `misc` zeroed. Separate
errand.

### Two dead leads worth naming

- **`VE_H264_CTRL` (`0x220`) bit 11** — the one explicit set-bit in the vendor
  sequence — does not enable anything. It **breaks the decode**: `frame
  processing timed out!`, one frame instead of 25. Group 7's own `0xf20` bit 11
  is harmless *and* inert.
- **`H264JudgeScaleMode` does not exist.** It was invented in an earlier
  session's notes and then cited as fact in the static doc. No such symbol in
  `libawh264.so`. That document is corrected.

---

## 3. What still needs doing

Two pieces of driver work. Neither is small, and the first carries real risk.

### 3.1 cedrus: make the 960x544 secondary output the V4L2 capture buffer

Today the secondary output lands in a private debugfs buffer
(`/sys/kernel/debug/cedrus_sd_buf`). To reach the display it has to *be* the
V4L2 capture buffer, so the existing zero-copy dma-buf path to DECD works
unchanged. That means:

- allocate **internal** full-size buffers for the primary reconstruction and
  point `VE_PRIMARY_*` at them;
- point `VE_H264_SDROT_LUMA_ADDR`/`CHROMA_ADDR` at the V4L2 dst;
- report 960x544 in `TRY_FMT`/`G_FMT`/`S_FMT`;
- **keep every DPB reference pointer aimed at the internal primaries.** The
  H.264 frame list is written into AVC SRAM with per-entry luma/chroma pointers
  (`cedrus_write_frame_list`), and this is what makes decoding correct at all.
  Getting it wrong produces plausible-looking corruption, not a clean failure.

That last point is why this is the risky half. Budget for a bisect harness
against known-good MD5s before changing it — `tools/video/va-decode-test.sh`
already has reference vectors.

An alternative worth considering first: expose the secondary output as a
**second capture queue** or a `V4L2_SEL_TGT_COMPOSE` target rather than
replacing the primary. More V4L2 surface area, but it does not touch the
reference-frame plumbing.

### 3.2 KMS: accept 960x544 and program the upscaler

`drivers/gpu/drm/tiny/sun50i-h713-afbd.c`:

- `h713_afbd_video_atomic_check()` passes `DRM_PLANE_NO_SCALING` for both min and
  max, and then hard-rejects any fb / `src` / `crtc` rectangle that is not
  exactly `H713_VIDEO_WIDTH` x `H713_VIDEO_HEIGHT` (1280x720). It needs to
  accept a 960x544 source and advertise a scaling range.
- `atomic_update` needs to program `0x05180000` with the geometry, both ratios,
  both phases and the bypass clear — the exact sequence in section 1, with
  read-modify-write on every field.
- The **DECD source geometry** for the smaller raster also needs setting; the
  source block at `0x05600000` currently carries 1920x1088 geometry (see
  [iommu-runtime-flip-ordering-2026-09-01.md](reference/iommu-runtime-flip-ordering-2026-09-01.md))
  and the composition block owns the panel timing.

### 3.3 A gap in the validation

The upscaler was validated by magnifying a 960x544 **window of a 1280x720
framebuffer**, because `kms-nv12-plane-test` hardcodes `WIDTH 1280`/`HEIGHT 720`
and the KMS driver rejects other sizes. The configuration is identical, but **a
genuine 960x544 framebuffer has never been scanned out.** That gap closes with
3.2, not before — do not treat it as already proven.

### 3.4 Optional: a better upscaler model

The comparison models stage 2 with bilinear and Lanczos because the proc
upscaler's tap set is unknown. If it matters, the taps are presumably reachable
the same way the VE's were (a coefficient table plus an SRAM port in that block).
Low priority — the measured spread between bilinear and Lanczos is only ~2 dB,
so the answer barely moves.

---

## 4. Method lessons from this session

These cost real time and all of them generalise.

### The ELF traps — three of them, same family

All three are now tooled; the rationale also lives in the tool headers:

1. **The vaddr/file-offset skew is per-SEGMENT, not per-file.** In `libVE.so`
   `.text` is 0x1000, `.rodata` is **0**, `.data` is 0x3000. Use
   `tools/mips/elf-addr.py`, never a constant.
2. **Linear Thumb disassembly desynchronises.** `.text` carries inline literal
   pools, so a sweep from the section start goes out of phase almost
   immediately. Decoding the BL/BLX encoding at every 2-byte slot turned
   "0 call sites" into **681**.
3. **Exported functions are PLT-called from inside their own library.** Call
   sites branch to a stub, not to `st_value`. Resolve stub -> GOT slot ->
   `.rel.plt` symbol. Use `tools/mips/arm-callsites.py`, which does 2 and 3.

Traps 2 and 3 together hid the scaler selection site through **two full rounds
of work**, each time as a confident "no call sites". Trap 1 produced a
withdrawn conclusion: misaligned Thumb decoded as a coherent bitstream reader
and I reasoned from it.

**The tell, in all three cases:** a scan reporting zero callers for a function
that must have some is broken, not informative.

### A null is only evidence once the stimulus is shown to have reached the hardware

The first full 16-value `SDROT_CTRL` sweep came back uniformly null because it
was programming the *top-level* `VE+0x40/0x44/0x48` instead of the engine's
`0x240/0x244/0x248`. The control register there is real and writable, so it read
back fine — but **the address registers read back zero** and the scaler had
nowhere to write. Sixteen clean nulls looked exactly like "this SoC does not
implement it".

Everything now reads registers back, and `ve-scaledown-sweep.sh` **aborts** if
the luma address reads zero.

### Render the bytes; do not trust a scalar

The first genuine hit rendered as horizontal stripes and read naturally as "the
scaler is producing garbage". It was producing a perfect picture in
`TILED_32_NV12`. Related: byte-difference counts **understate** the written
region, because real video contains bytes equal to the `0xa5` poison — extent is
the reliable measure, not count.

### A harness that has never run is itself untested

Both failures in the first run of `composite-route-test.sh` were mine, and both
read as "the hardware refused the write":

- **`busybox devmem` prints UPPERCASE hex** while `printf '0x%08x'` emits
  lowercase, so a string compare reported `DID NOT STICK` for any value
  containing `a`-`f`. It looked selective — and therefore credible — because the
  preceding register had no hex letters.
- **An unmasked V-phase write** would have put `0x00110000` where `0x00100000`
  belongs, corrupting the restore.

### Other traps

- **`-qp 0` makes libx264 emit a lossless profile the VE cannot decode.** ffmpeg
  falls back to software, the harness never runs, and the dump is pure poison —
  indistinguishable from "the scaler did nothing". Tell:
  `Failed setup for format vaapi: hwaccel initialisation returned error`. Use
  `-crf 12 -profile:v high`.
- **SRAM ports walk an internal pointer.** Reading `0xffc` in a register sweep
  advances it. The snapshot and poke list refuse `0x1e0/0x1e4`, `0x2e0/0x2e4`,
  `0x5e0/0x5e4` and `0xff8/0xffc`; only the deliberate `sd_coef` path writes
  group 7's pair.
- **A VE timeout does not wedge the board.** Recovered every time with the
  harness disarmed — 60 frames at 3.3x, CMA fully free. Stop rebooting for it.

---

## 5. Tools and artefacts

| path | what |
| --- | --- |
| `patches/kernel/0097-...scale-down.patch` | the cedrus harness. **Inert unless `sd_w` and `sd_h` are both set** — with the defaults not one register write changes |
| `tools/video/ve-scaledown-sweep.sh` | sweeps `SDROT_CTRL`, aborts if writes do not land |
| `tools/video/ve-newscaler-probe.sh` | probes the arbitrary-ratio path |
| `tools/video/compare-scale-routes.py` | the route quality comparison |
| `tools/display/composite-route-test.sh` | the upscaler panel test, with gates and restore |
| `tools/mips/elf-addr.py` | per-segment vaddr -> file offset |
| `tools/mips/arm-callsites.py` | real call sites, PLT-aware |
| `tools/display/make-scaler-testcard.py` | the vector test card, rasterised natively per size |

Harness parameters (all default off):

```
sd_w, sd_h        target size; 0 disables everything
sd_ctrl           raw VE_H264_SDROT_CTRL
sd_fmt=1          linear NV12 instead of the tiled default
sd_stage=1        program after the codec setup (required)
sd_shift=0        address shift (raw is correct)
sd_poke="off=val" arbitrary register writes
sd_coef=1         upload the group 7 coefficient blob
sd_sram_off=0x340 coefficient SRAM address
sd_scratch_kb=N   working buffer for VE_G7_WORK_BUF
```

Debugfs: `cedrus_sd_buf` (the secondary output, re-poisoned `0xa5` on every
`sd_ctrl` change, with a shadow copy taken on context release so the result
outlives the player), `cedrus_sd_regs` (the whole 4 KiB at decode trigger),
`cedrus_sd_coef` (write the coefficient blob).

### Documents

All under `docs/reference/ve-scaledown-2026-09-11/`, in reading order:

1. [RESULT.md](reference/ve-scaledown-2026-09-11/RESULT.md) — the power-of-two scale-down works
2. [ARBITRARY-RATIO.md](reference/ve-scaledown-2026-09-11/ARBITRARY-RATIO.md) — first attempt, and the skew correction
3. [BLOCK7-FOUND.md](reference/ve-scaledown-2026-09-11/BLOCK7-FOUND.md) — block 7 = VE+0xf00, coefficients extracted
4. [COEF-UPLOAD.md](reference/ve-scaledown-2026-09-11/COEF-UPLOAD.md) — coefficients uploaded, still inert
5. [SELECTION-FOUND.md](reference/ve-scaledown-2026-09-11/SELECTION-FOUND.md) — selection is software; route closed
6. [ROUTE-COMPARISON.md](reference/ve-scaledown-2026-09-11/ROUTE-COMPARISON.md) — the composite route priced
7. [UPSCALE-GEOMETRY-CONFIRMED.md](reference/ve-scaledown-2026-09-11/UPSCALE-GEOMETRY-CONFIRMED.md) — the panel test

Also [scaler-census-2026-09-11.md](reference/scaler-census-2026-09-11.md) (the
complete census) and
[ve-decode-time-scaledown-2026-09-11.md](reference/ve-decode-time-scaledown-2026-09-11.md)
(the original static RE, **carrying a correction** — see the `H264JudgeScaleMode`
note in it).

### Commits

`a79aa97` `5d0cb7a` `3a4409f` `b590e22` `e6713ff` `46ab97a` `e0b071e` `820fa41`
`9d556a4`, on `h713-display-video-path`.

---

## 6. Standing hazards, unchanged

- **Never read `0x06940000`** — TVFE/TVCAP capture domain, unpowered at boot.
- **A plain read of `0x07091000` wedges the SoC** (power cycle only). The RTC at
  `0x07090000` is fine.
- **Read VE registers only while a decode is in flight.** Runtime-suspended, the
  whole 4 KiB window reads zero — indistinguishable from absence.
- **`decd-scale-test.sh PHASE=scale` is refuted and costs a reboot.** Do not run
  it casually.
- **`pkill -f <pattern>` matches the ssh command line running it** and kills its
  own session. Use a pid file or `pkill -x` with the 15-char comm.
- **Nothing may be written to a display block until the card is demonstrably on
  the panel.** A five-step sequence once ran against a console login prompt.
- **`0x05180000`'s registers carry live upper bits** — read-modify-write only.

## 7. Board state at handoff

Clean. Harness fully disarmed (`sd_w=0`, `sd_ctrl=0`, `sd_poke` empty), proc
scaler block restored byte-for-byte to its pre-run values, plane released.
652 MB free, CmaFree 130176 kB of 131072, zero errors in dmesg. The last clean
decode ran 60 frames at 3.3x.
