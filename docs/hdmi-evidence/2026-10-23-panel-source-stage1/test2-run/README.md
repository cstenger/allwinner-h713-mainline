# Test 2: composition routing × AFBD format (10-24)

§10.23.2 / §10.23.7 of [the design](../../../hdmi-panel-source-design-2026-10-23.md).
`t5-board.py --matrix` (staged hash `9d0a8a73…`), run as the unit `h713-t5`.

* **Boot:** T4 cold path `2de066a3…`, with the `0188` identity map.
  * The prompt was caught by a host-side space-sender armed before power-on
    (`../test2-boot3/uart-catch.log`): stopped after 7.3 s, `gp6=0`,
    `mips_status=0`.
  * The census was 0/0. The T4 script was sourced once, the T4 FIT loaded
    from ext4, 720p was re-latched, and the handoff verified
    (`../test2-boot3/`).
* **Earlier attempts:**
  * Attempt 1 (`../test2-boot/`): the operator's replug missed the
    autoboot window. Production booted, nothing was sent, and it was shut
    down cleanly.
  * Attempt 2 (`../test2-boot2/`): the board turned out to be off, and my
    first waiter wrongly watched for the PC-side adapter to vanish. Nothing
    was sent.
* **Before the run:** `win rn 2` and all 9 T5 preconditions passed. The
  operator put the band chart (`tools/hdmi/make-band-chart.py`) full-screen
  on HDMI-A-1 and filmed.
* `events-test2.jsonl` is this run alone; `events.jsonl` also holds earlier
  runs from previous boots.

## Register record

Cell baseline, read at the end of stage B: comp `0x030 = 00400000`,
`0x040 = 02090280`, AFBD `0x10 = 03000203`, `0x4c = 02d00500`.

| Board time (s) | Cell | comp `0x030` | comp `0x040` | AFBD `0x10` | AFBD `0x4c` | IOMMU | TCON | faults |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2870.8 | 0 capture / 4:2:2 | `00400000` | `02090280` | `03000203` | `02d00500` | 0 | 720p | 0 |
| 2886.0 | 1 capture / 4:2:0 | `00400000` | `02090280` | `03000003` | `01680500` | 0 | 720p | 0 |
| 2901.3 | 2 decoder / 4:2:2 | `00000c00` | `02090208` | `03000203` | `02d00500` | 0 | 720p | 0 |
| 2916.5 | 3 decoder / 4:2:0 | `00000c00` | `02090208` | `03000003` | `01680500` | 0 | 720p | 0 |
| 2931.8 | 4 capture / 4:2:2 | `00400000` | `02090280` | `03000203` | `02d00500` | 0 | 720p | 0 |
| 2949.4 | reverted | — | — | `03000200` | — | 0 | 720p | 0 |

* Every write's readback equals its value, and each cell published once
  (`0x6c`, `0x14`).
* Each cell was held 15 s with the guards clean, and AFBD's fetch counters
  moved in every cell (12–17 distinct values).
* Mux `0x68` was never written. No abort; `done ok`.

## Operator observation and video

* **Operator:** "It never looked right, the middle of the test looked all
  wrong."
* **Video:** `local/lcd-photos/test_106/IMG_1068.mov` (slow motion, about
  4× in the middle). Frames: `contact.jpg`, `contact2.jpg`, `cells.png`,
  and `cells23.png` (copied here as `cells23-video-frames.png`).
* **The panel showed the earlier 1500×844 test chart, not the band
  chart.** COSMIC kept or re-applied the old HDMI-A-1 wallpaper. That chart
  reads the y-mapping as well as it did for T5 (§10.15).

**Timeline**, aligned with the run's 15 s steps:

| Video | Picture | Run step |
| --- | --- | --- |
| 2:09–3:12 | greyscale chart | stage A |
| 3:12–6:15 | the T5 picture: *y/2* chroma (the hue row shows the bars' green over blue; the squares' colour runs into the two rows below) | stage B, **cell 0** (capture/4:2:2) and **cell 1** (capture/4:2:0) |
| 6:15–7:15 | the chart squeezed into many narrow repeated tiles across the top third, the rest a flat green field | **cell 2** (decoder/4:2:2) |
| 7:15–8:00 | the same tiled strip, then a green band and a yellow-olive field | **cell 3** (decoder/4:2:0) |
| 8:03–8:15 | the T5 picture again | **cell 4** (capture/4:2:2) |
| 8:18 | console | revert |

## Result

1. **Cell 1 = cell 0.** In capture routing, the AFBD format byte (2 → 0)
   and chroma-row count (720 → 360) **don't change the picture**, even
   though the writes read back and were published. The *y/2* chroma
   doesn't come from AFBD's format fields. Either the capture-routed
   picture doesn't depend on them, or AFBD in capture-address mode takes
   its format from elsewhere: the `+0x300–0x33c` capture-side words differ
   between ours and stock (§10.20 diff: `0x300` `…4218` vs `…4258`, `0x30c`,
   `0x310`).
2. **Decoder routing (cells 2/3) takes effect, but composition then
   expects AFBD in queue-address mode** (mux `0x68` bit 8, `0x10` bit 4,
   frames in the address queue), which is how KMS and stock use it. With
   AFBD left in capture-address mode, the output is garbage: tiles and a
   flat green field, where green is "nothing usable fetched". Decoder
   routing therefore means ARM-supplied frames in the AFBD queue: the
   conversion route, not the firmware path.
3. **H3 is ruled out for the capture-routed picture; the culprit sits in
   the capture-routing path.** No knob found so far changes its vertical
   chroma rate.
