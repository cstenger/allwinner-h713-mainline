# SOLVED — linear NV12 on the panel through DECD, with the MIPS alive

2026-09-08. `test_80/IMG_0806.JPEG` shows the colour-bar test pattern rendered
correctly: bars in the right order, legible timecode readout top-left, diagonal
sweep lines, checkerboard patches. Straight vertical bars (no shear), saturated
colours (no green cast), correct size, full window.

Content cross-checks against the buffer: `decd-test-frame.nv12` begins
`4a 49 4b 4b ...` — dark bytes — which is the dark timecode box in the
top-left corner.

## The two faults

| | what we had | correct |
| --- | --- | --- |
| format byte `0x05600011` | `0` = **RGB888** | **`3` = NV12** |
| publish latch | `0x05600014` (packed path) | **`0x0560006c`** (two-plane path) |

Both were already written down in
`patches/kernel/0065-drm-h713-afbd-scan-out-nv12-directly.patch`, whose comment
describes this exact trap:

> they set the format byte and kept feeding AFBD_SRC, so the fetch stayed
> 4 bytes/pixel and packed four source rows into every display row

That 4-bytes-per-pixel signature is precisely what test_79 showed: structure
over the top ~55% and a flat field below, because a 921,600-byte luma plane read
at 4 bytes/pixel covers only ~half of 720 lines.

## The working sequence

Preconditions: MIPS alive (`h713_disp init 0x34`, no quiesce), DECD test FIT with
`initcall_blacklist=h713_afbd_platform_driver_init`, `sunxi-decd-budget.ko
ring_writes_max=1`, CPU_COMM loaded, frame staged by `decd-client.coord1080`.

```sh
busybox devmem 0x02010030 32 0x7C          # IOMMU m2 bypass BEFORE addresses
busybox devmem 0x05600011  8 3             # AFBD_FORMAT = NV12   (byte write)
busybox devmem 0x05600040 32 0x00000500    # AFBD_PLANE_STRIDE0
busybox devmem 0x05600044 32 0x00000500    # AFBD_PLANE_STRIDE1
busybox devmem 0x05600070 32 0x6c500000    # AFBD_PLANE_ADDR0  (Y)
busybox devmem 0x05600084 32 0x6c5E1000    # AFBD_PLANE_ADDR1  (C)
busybox devmem 0x0560006c 32 1             # AFBD_DIRTY -- the publish
busybox devmem 0x05140508 32 0x144C0000    # chroma gain
busybox devmem 0x051c006c 32 0x39000000    # selector -> VIDEO
```

`0x0560006c` self-clears on read-back, confirming it is a real consume-on-write
latch. Composition at `0x05000000` needs no writes: on a normal boot all
seventeen registers already hold the 1280x720 values.

Reproduce with `tools/video/decd-all-preconditions.sh` (`NV12_SEQ=1`).

## Why it took so long

**Stock playback was a false friend.** `stock-android-playback-2026-08-28.txt`
has `0x05600010 = 0x03000013` — format 0 — and that was cited as proof format 0
was correct. Stock composites video into an RGB surface, so format 0 is right
*for stock* and wrong for us. A matching register is only evidence if the two
sides are doing the same thing.

**Every script in the tree published via `0x05600014`.** That latch is real and
consumes, so a run looked successful at every checkpoint while the two-plane
configuration was never published.

## Corrections to the record

- The **composition-block hypothesis (2026-09-06) was wrong** as a cause. On a
  normal boot all seventeen registers are already correct; the 852x480 state was
  self-inflicted by running the source-coordinate client during that session's
  physaddr test. It explained test_76/77 only.
- Composition *does* own the displayed **footprint** — confirmed here, since
  correcting it fixed the size while the content stayed wrong.
- The **logo OSD layer is not a factor**. `0x05600140` bit 0 was enabled in every
  earlier test while stock has it disabled; clearing it changed nothing.
- The eight-format sweep is **complete and negative for format 0 publishing**:
  no format renders correctly through the `0x05600014` latch.

## Tooling bugs found today, all of which silently invalidated results

1. **`grep '^056000'` hid half the register block.** Addresses `0x05600100`+
   render as `056001xx`, so two sessions of "full block" diffs compared only
   `0x00-0xFC`. The OSD channel differences were all in the half never examined.
2. **Snapshot-before-PM_HINT captured gating, not state.** Every register reads
   `0x00000000` before the client's PM_HINT, so "restore" wrote zeroes and left
   the panel black — indistinguishable from a failed test.
3. **`tr -d 'x'` on `0x051c006c` yields `0051c006c`, not `051c006c`.** The
   hard-coded shorter name left the variable unset; under `set -u` that aborted
   `restore()` on its first line, so a run ended with the video route still live.

## The harness

`tools/video/decd-all-preconditions.sh` verifies **38 preconditions** — core,
bypass, selector, gain, all seven geometry words, all eight ring slots, all
seventeen composition registers, and that the frame bytes are present at the
fetch address — and **refuses to hold for a visual test unless every one
passes**. A refusal costs no operator attention. Three of the four operator
looks before it existed were spent on runs that were void for reasons a register
read would have shown.

## Addendum — the two latches, and four wasted green frames

`0x05600014` and `0x0560006c` are **both** required, and they do different jobs:

| latch | commits |
| --- | --- |
| `0x05600014` | the **source configuration** — the seven geometry words and the source enable |
| `0x0560006c` | the **plane addresses** of the two-plane YUV path |

The working run writes both, in this order: geometry/ring/gain, then
`ctrl = 0x03000013` and `0x05600014 = 1`, then the selector, then the format
byte to 3, the plane addresses, and `0x0560006c = 1`.

Having just discovered that `0x0560006c` was the missing publish, the first
Cedrus scripts were built around it and **dropped `0x05600014` entirely**. The
seven geometry words and the source enable were written, read back correct, and
never committed. The fetcher therefore had no valid picture configuration,
fetched nothing, and zeroes render as solid green.

That is all four green frames on the Cedrus path, one cause, and it was
self-inflicted by over-correcting a real finding into "0x05600014 is the wrong
latch" when the truth is "it is the wrong latch *for plane addresses*".

### This voids an earlier conclusion

`decd-static-via-iova.sh` was presented as a clean one-variable isolation of
translation vs bypass, and it returned solid green. It had the same missing
commit, so it did not test translation at all. **Translation is not proven
guilty; that result is void** and must be re-run with both latches before any
conclusion about IOVA support is drawn.

### Also worth keeping

- **The 60 Hz hard-lock did not reproduce.** Two full playback runs with real
  Cedrus traffic, a live MIPS and ~1000 ring writes left `0x0306101c = 1`
  throughout. That hazard has shaped experiment design since 2026-09-04.
- **Cedrus output matches our static layout exactly**: 1280x720 NV12, one
  dma-buf, stride 1280, chroma offset 921600.
- **The player must outlive the hold.** `decd-play` exiting drops its PM hint
  and the display block gates off; `DECD_FREEZE=1` with a large frame count
  keeps it alive without decoding anything new.
- **`decd-play` requests VideoInfo format selector 0**, which the firmware
  resolver maps to hardware format 0 = RGB888. It only works because the driver
  never programs the format byte and our manual `3` persists.
