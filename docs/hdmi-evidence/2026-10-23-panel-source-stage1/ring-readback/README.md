# Capture-ring readback: the input to AFBD is correct NV16 (10-23)

§10.18 step 1 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).
Read-only. Boot `34ee92bd…`, HDMI locked, host showing the test chart
full-screen on HDMI-A-1. Source 0 was off at the time; the capture ring
is written whatever the selector.

## Method

* **Read:** the three ring pairs (Y at `0x4C3EF000 + n·0x1FF000`, UV at
  `+3` slots), 1280×720 each plane, every pair copied twice through a
  read-only `/dev/mem` mapping.
  * Raw data: `local/panel-source-t5/ring/ring3.nv16`, not in git
    (hashes in `hashes.txt`).
  * The repo's `read-coherent-frame.py` needs a *changing* pair to
    detect completion, and a static chart never changes, so the
    double-copy comparison was done directly.
* **Copies:** they differ by at most 1 LSB (mean 0.18 Y, 0.12 UV), which
  is capture noise. The frame is effectively pristine (`measure.json`).
* **Reference:** the chart (`chart.webp`, the image the operator set as
  wallpaper) scaled to 1280×720, converted to NV16.
* **Row-map scoring:** mean |ring − reference| over rows 40–719 (below
  the top bar), with reference row = round(s·y + o), for s ∈ {0.5, 1} and
  o ∈ [−24, 24] (`rowmap.json`).

## Result

| Plane | Best map | Mean error | Best *y/2* map | Mean error |
| --- | --- | --- | --- | --- |
| Y | s = 1, o = 0 | 4.49 | s = 0.5, o = 24 | 59.85 |
| UV | **s = 1, o = 0** | **1.63** | s = 0.5, o = 24 | 29.09 |

`pair0.png` (the ring frame rendered as NV16) shows the chart exactly:
* hue squares in their own row, in the right colours;
* the gradient bars only in their own rows;
* the grey rows neutral.

**The capture ring holds correct 4:2:2 data, chroma 1:1.** The half-rate
chroma seen on the panel in T5/T6 is introduced **after** the ring: in
AFBD's handling of format 2, or downstream (composition / proc / panel).
That's row 1 of §10.18's table.
