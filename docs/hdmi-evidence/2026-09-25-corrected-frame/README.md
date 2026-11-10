# Full-frame HDMI capture: one-page base-address correction

The horizontal wrap and green bottom strip in the first color snapshot had a
single cause in our **read-only DRAM sampler**. The page-hash trial identified
the first *changing* 4 KiB page of each plane as its base. The preceding page
can remain constant when it holds an unchanging part of the desktop, but is
still part of the frame. Each actual NV16 plane begins `0x1000` bytes earlier:

| Pair | Y base | UV base |
| --- | --- | --- |
| 0 | `0x4c3ef000` | `0x4c9ec000` |
| 1 | `0x4c5ee000` | `0x4cbeb000` |
| 2 | `0x4c7ed000` | `0x4cdea000` |

The six planes remain `0x1ff000` bytes apart, and each plane contains exactly
`640 * 480 = 307200` image bytes. Our old read started 4096 bytes late.
Because `4096 = 6 * 640 + 256`, it began at pixel 256 of a later row: the
apparent row wrap occurred after the remaining **384** pixels. Reading 307200
bytes from there also included a zero page after the frame while omitting its
actual first page. That created the apparent 473-row limit and green strip.
Rotating and cropping the old PNG improved its appearance but mixed adjacent
rows at the seam and discarded real image pixels.

[`candidate-nv16.bin`](candidate-nv16.bin) is a fresh read from corrected
pair 0/3 during a bounded 12-second HDMI window. Direct BT.601 conversion,
with **no rotation or crop**, produces the complete
[`candidate-nv16.png`](candidate-nv16.png) at **640×480**. Its wallpaper rows
30..479 have RGB correlation **0.9980** with the earlier
[source-side HDMI screenshot](../2026-09-25-row-alignment/source-hdmi-output.png).
The top menu is also in its source position; its clock differs because the
source screenshot was taken earlier. Independent reads of pairs 1/4 and 2/5
both decode as full 640×480 images and have the same approximately 0.998
wallpaper correlation. All seven bottom rows contain real image data.

`tools/hdmi/read-nv16-pair.py` and the other diagnostic samplers now use the
corrected bases. `run-detection-trial.py --dump-nv16` and `capture-once.py`
write the direct full-frame PNG. The SCP trial's
[`target.log`](target.log) reports `peripheral_restored=1`,
`edid_mismatch=0`; [`cleanup.log`](cleanup.log) records the restored pin
state. The projector remained responsive and the installed kernel was not
changed. This establishes the buffer geometry, but the DRAM read is still an
unsynchronized snapshot; frame completion and live streaming remain separate
capture tasks.
