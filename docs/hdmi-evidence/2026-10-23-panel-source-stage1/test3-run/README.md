# Test 3: NV16 on the KMS video plane (10-24)

§10.25.1 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).
* **Kernel:** the experiment kernel from patch `0189` (clang 23.1.3,
  `#2 SMP Sat Oct 24 02:39:05`), with the production DTB, in test FIT
  `273a4592`.
* **Boot:** the T4 cold path. The catcher stopped U-Boot at a cold prompt
  (GP6 0, MIPS 0; `../test3-boot/`). Linux boot `93e21e0d…`.
* **Health:** all four HDMI modules loaded, no failed units, no IOMMU
  faults.
* **Tool:** `tools/display/kms-yuv-still.c`
  (`ARMED=yes kms-yuv-still 15 band.nv12 band.nv16 chart.nv12 chart.nv16`),
  log in `kms-yuv-still.log`.

| Still | AFBD `0x10` | `0x4c` chroma rows |
| --- | --- | --- |
| band NV12 | `03000013` (format 0) | 360 |
| band NV16 | `03000213` (format 2) | 720 |
| chart NV12 | `03000013` (format 0) | 360 |
| chart NV16 | `03000213` (format 2) | 720 |

No faults; the plane was disabled and the console restored.

## Video: `local/lcd-photos/test_107/IMG_1069.mov`

The operator reported "the frames seemed incorrectly wrapped".

* `stills-video-frames.png`: band NV12, band NV16, chart NV12, chart NV16
  (left to right, top to bottom).
* `stills-decoded-offline.png`: the still **files** decoded back on the
  host. They're exact (bars, squares, bands and labels all correct), so
  every defect below is on the display side.

**NV16 (format 2, chroma rows 720): not linear NV16.**
* The chart shows the same picture as Test 2's decoder-routing cells:
  the image squeezed into narrow repeated tiles across the top third,
  then a flat green field.
* The band chart shows wrong colours, with the labels repeated and
  squeezed.
* So AFBD format 2 in queue mode fetches a different layout from linear
  semi-planar 4:2:2 (possibly packed or blocked 4:2:2; not determined).
* **Route A (direct NV16 scanout) doesn't work as-is.**

**NV12 (format 0): vertically correct, but chroma shifted horizontally**
(`chart-nv12-crop.png`, `band-nv12-left.png`).
* **Chart:** squares are coloured only in their own row and the bars only
  in theirs, so vertical alignment is right. But each square shows the
  colour of the square to its **left**, the first (red) square shows the
  **last** square's rose, and saturated bar colour appears at the far
  left, where the bars are black.
* **Band chart:** each band's colour is right behind its sharp label. But
  grey, digit-shaped smudges, the labels' neutral chroma, sit about one
  square to the **right** of each label, and a second column of smudges
  at the far left is the right-hand labels' chroma, wrapped around.
* **Reading:** chroma is displaced about 100 px to the right of luma,
  wrapping within the line. That's consistent with AFBD's chroma fetch
  starting about 100–128 bytes early (the start of each chroma line comes
  from the end of the previous one).
* **This affects every NV12 user of the plane**, so it matters for route
  B. Whether it's specific to this test kernel or dumb buffers, or has
  always been there (earlier NV12 checks judged bar order and geometry,
  not chroma alignment at edges), is open. Next check: the same NV12
  stills on the production kernel.
