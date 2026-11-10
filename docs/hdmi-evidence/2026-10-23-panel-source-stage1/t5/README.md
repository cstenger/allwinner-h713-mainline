# T5: the selector flip (10-23)

T5 from §10.14 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).

## Setup

* Boot `34ee92bd-95ac-46cd-a066-628f389ad507`: the T4 cold path, with
  `0188`'s pool identity map.
* `t5-board.py` was staged at `/run/h713-t5/` (sha256 in
  `board-script.sha256`) and ran as the transient unit `h713-t5`.
  * All 9 preconditions passed.
  * Operator: test image full-screen on the host's HDMI-A-1 (1280×720),
    filming the panel.

## Register record (`events.jsonl`)

| Board time (s) | Step | selector | gain | AFBD `0x10` | IOMMU sta | TCON 20/24 | faults |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3359.95 | pre | `29000000` | `04000000` | `03000200` | 0 | 720p | 0 |
| 3362.23 | `memory_agent en 4` | | | | | | |
| 3365.28 | en4 | `29000000` | `04000000` | `03000203` | 0 | 720p | 0 |
| 3365.33 | **stage A**: selector → `39000000` (readback ok) | | | | | | |
| 3380.54 | held 15 s, guards clean | `39000000` | `04000000` | `03000203` | 0 | 720p | 0 |
| 3380.59 | **stage B**: gain → `144c0000` (readback ok) | | | | | | |
| 3395.83 | held 15 s, guards clean | `39000000` | `144c0000` | `03000203` | 0 | 720p | 0 |
| 3395.88 | revert: gain → `04000000`, selector → `29000000` | | | | | | |
| 3398.16 | `memory_agent dis 4` | | | | | | |
| 3398.19 | reverted | `29000000` | `04000000` | `03000200` | 0 | 720p | 0 |

* The `+0x320` capture pair cycled `4c3ef000`/`4c5ee000`/`4c7ed000`
  throughout.
* The blue-screen words (`05140d54 = 0`, `051c00b8 = 38`,
  `051c0364 = f0000000`) and the panel mirror didn't change.
* No abort; `done ok`.

## Operator observation and video

* **Operator:** the panel showed the host desktop, going from greyscale to
  colour. The colour didn't look right.
* **Video:** `local/lcd-photos/test_105/IMG_1062.mov` (slow motion, not in
  git). Frames extracted: `contact.jpg` (every 2 s of playback),
  `grey-50s.png` (stage A), `colour-100s.png` (stage B).
* **Test image:** a 1500×844 chart, filling 1280×720. From top to bottom:
  * R, G and B gradient bars (rows 0–135);
  * 12 saturated hue squares (142–277);
  * line/checker patterns (284–418);
  * gamma squares on grey (425–560);
  * a 12-step grey wedge (567–702);
  * a grey ramp (710–844).

**Stage A (greyscale): luma and geometry correct.**

* Full panel, 12 columns, rows in the right places.
* The COSMIC top bar ("Workspaces", "Applications", the clock) is legible.
* The hue squares show the expected luma: yellow, green and cyan bright;
  red, blue and violet dark.
* The patterns, gamma squares, grey wedge and ramp all reproduce.
* The picture was steady, with no shear, rolling or tearing.

**Stage B (colour): chroma is fetched at half the vertical rate.** Display
line *y* takes its chroma from source line *y/2*. Three independent
features fix the mapping:

* **The hue-square row (142–277) shows green over blue.** The source
  chroma there is lines 71–138: the green bar (45–90) over the blue bar
  (90–135).
* **The hue squares' colours appear on the pattern and gamma rows
  (284–560).** That's source chroma 142–280, the squares stretched to
  twice their height. The red column is solid red down both rows.
* **The grey wedge and ramp (567 onwards) are neutral.** Their chroma comes
  from source 283 onwards (the grey patterns and gamma rows), and nothing
  below source line ~360 ever contributes colour.

Hue order is right (red → orange → yellow → green → cyan → blue → magenta),
so Cb/Cr are not swapped. Range and saturation can't be judged until the
chroma lines up.

## Result

* **The firmware path puts a live, correctly sized and sharp HDMI picture
  on the panel**, with zero IOMMU faults, through `0188`'s identity map. A
  clean revert puts the console back.
* **The one defect is the chroma line rate.** AFBD, as the firmware's
  `win rn 2` programmed it (format byte `0x02`, `0x4c = 02d00500`), steps
  chroma once per two output lines. The `+0x320` pair it reads is the
  capture ring, which is NV16 (4:2:2, one chroma line per luma line). That
  matches §10.14's "4:2:2 vs 4:2:0 chroma lines" row.
* **Corrected by the offline RE (§10.16):** AFBD reading the capture ring
  *is* the stock route, and format `0x02` is the firmware's code for this
  4:2:2 input. NR's compressed 4:2:0 frames are its temporal-NR history,
  and stock runs that history DMA (agents 5/6), which T4/T5 left off. The
  leading hypothesis is that NR's 4:2:0 chroma path needs its history on.
  T6 tests that.
